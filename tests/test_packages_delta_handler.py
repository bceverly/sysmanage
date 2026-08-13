# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A delta may only be applied to the base it was computed against.

The agent sends puts (added/changed) and takes (removed) plus the fingerprint of
the catalog it diffed against.  If that is not the catalog the server holds, the
diff describes changes to something else, and applying it leaves our copy quietly
wrong -- and wrong permanently, because every later delta is applied on top.

Rejecting is cheap and self-correcting: the agent responds by sending a full
catalog, which is always right.  So the server refuses whenever it cannot prove
the bases agree, and these tests are mostly about that refusal.

Uses a real SQLite session, because what is under test is the SQL: whether a put
replaces a row or duplicates it, and whether a take removes only THIS host's row,
cannot be shown with a mocked query chain.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api import package_handlers
from backend.persistence.models import AvailablePackage
from backend.persistence.models.core import Base

HOST_A = "11111111-1111-1111-1111-111111111111"
HOST_B = "22222222-2222-2222-2222-222222222222"
BASE_FP = "basefingerprint01"
NEW_FP = "newfingerprint02"


class _Connection:
    def __init__(self, host_id=HOST_A):
        self.host_id = host_id


class _Host:
    id = HOST_A
    fqdn = "gdr-t14"
    platform = "Linux"
    platform_release = "Ubuntu 26.04"

    def __init__(self, fingerprint=BASE_FP):
        self.available_packages_fingerprint = fingerprint
        self.available_packages_fingerprint_at = None


class _Session:
    """Real AvailablePackage storage; Host queries answered from a stub."""

    def __init__(self, sa_session, host):
        self._s = sa_session
        self._host = host

    def query(self, model, *args, **kwargs):
        if model is AvailablePackage:
            return self._s.query(model, *args, **kwargs)
        return _HostQuery(self._host)

    def execute(self, *args, **kwargs):
        return self._s.execute(*args, **kwargs)

    def add(self, obj):
        self._s.add(obj)

    def commit(self):
        self._s.commit()

    def rollback(self):
        self._s.rollback()


class _HostQuery:
    def __init__(self, host):
        self._host = host

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return self._host


@pytest.fixture(name="ctx")
def _ctx():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine, tables=[AvailablePackage.__table__])
    sa_session = sessionmaker(bind=engine)()
    host = _Host()
    try:
        yield _Session(sa_session, host), sa_session, host
    finally:
        sa_session.close()
        engine.dispose()


def _seed(sa_session, host_id, name, version, manager="apt"):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    sa_session.add(
        AvailablePackage(
            host_id=host_id,
            package_name=name,
            package_version=version,
            package_description="",
            package_manager=manager,
            os_name="Ubuntu",
            os_version="26.04",
            created_at=now,
            last_updated=now,
        )
    )
    sa_session.commit()


def _delta(puts=None, takes=None, base=BASE_FP, new=NEW_FP):
    return {
        "base_fingerprint": base,
        "new_fingerprint": new,
        "puts": puts or [],
        "takes": takes or [],
        "os_name": "Ubuntu",
        "os_version": "26.04",
    }


@pytest.mark.asyncio
async def test_a_mismatched_base_is_rejected_and_nothing_changes(ctx):
    """The property everything else depends on."""
    db, sa_session, host = ctx
    _seed(sa_session, HOST_A, "curl", "8.5.0")

    result = await package_handlers.handle_packages_delta(
        db,
        _Connection(),
        _delta(
            takes=[{"package_manager": "apt", "name": "curl"}],
            base="a-different-catalog",
        ),
    )

    assert result["error_type"] == "delta_base_mismatch"
    assert sa_session.query(AvailablePackage).count() == 1, "rows must be untouched"
    assert host.available_packages_fingerprint == BASE_FP


@pytest.mark.asyncio
@pytest.mark.parametrize("base", [None, ""])
async def test_a_delta_without_a_base_is_rejected(ctx, base):
    """No stated base means nothing to verify against."""
    db, sa_session, _ = ctx
    _seed(sa_session, HOST_A, "curl", "8.5.0")
    result = await package_handlers.handle_packages_delta(
        db, _Connection(), _delta(base=base)
    )
    assert result["error_type"] == "delta_base_mismatch"
    assert sa_session.query(AvailablePackage).count() == 1


@pytest.mark.asyncio
async def test_a_put_for_a_new_package_inserts(ctx):
    db, sa_session, _ = ctx
    result = await package_handlers.handle_packages_delta(
        db,
        _Connection(),
        _delta(puts=[{"package_manager": "apt", "name": "nginx", "version": "1.24"}]),
    )
    assert result["status"] == "delta_applied"
    row = sa_session.query(AvailablePackage).one()
    assert (row.package_name, row.package_version, row.host_id) == (
        "nginx",
        "1.24",
        HOST_A,
    )


@pytest.mark.asyncio
async def test_a_put_for_an_existing_package_replaces_it(ctx):
    """A version change must REPLACE, not accumulate a second row.

    Duplicating would inflate every OS-level count and make the catalog
    disagree with the fingerprint both sides think they share.
    """
    db, sa_session, _ = ctx
    _seed(sa_session, HOST_A, "curl", "8.5.0")

    await package_handlers.handle_packages_delta(
        db,
        _Connection(),
        _delta(puts=[{"package_manager": "apt", "name": "curl", "version": "8.6.0"}]),
    )

    rows = sa_session.query(AvailablePackage).all()
    assert len(rows) == 1
    assert rows[0].package_version == "8.6.0"


@pytest.mark.asyncio
async def test_a_take_removes_only_this_hosts_row(ctx):
    """Another host running the same OS must keep its catalog."""
    db, sa_session, _ = ctx
    _seed(sa_session, HOST_A, "curl", "8.5.0")
    _seed(sa_session, HOST_B, "curl", "8.5.0")

    await package_handlers.handle_packages_delta(
        db, _Connection(), _delta(takes=[{"package_manager": "apt", "name": "curl"}])
    )

    remaining = sa_session.query(AvailablePackage).all()
    assert [r.host_id for r in remaining] == [HOST_B]


@pytest.mark.asyncio
async def test_applying_a_delta_records_the_new_fingerprint(ctx):
    """So the next delta has a base, and an unchanged catalog can be skipped."""
    db, _, host = ctx
    await package_handlers.handle_packages_delta(
        db,
        _Connection(),
        _delta(puts=[{"package_manager": "apt", "name": "nginx", "version": "1.24"}]),
    )
    assert host.available_packages_fingerprint == NEW_FP
    assert host.available_packages_fingerprint_at is not None


@pytest.mark.asyncio
async def test_malformed_entries_are_skipped_not_fatal(ctx):
    """One bad entry must not abort a delta that is otherwise fine."""
    db, sa_session, _ = ctx
    result = await package_handlers.handle_packages_delta(
        db,
        _Connection(),
        _delta(
            puts=[
                {"package_manager": "apt", "name": "", "version": "1"},
                {"package_manager": "apt", "name": "ok", "version": ""},
                {"package_manager": "apt", "name": "good", "version": "1.0"},
            ],
            takes=[{"package_manager": "", "name": ""}],
        ),
    )
    assert result["status"] == "delta_applied"
    assert [r.package_name for r in sa_session.query(AvailablePackage).all()] == [
        "good"
    ]


@pytest.mark.asyncio
async def test_an_empty_delta_is_accepted(ctx):
    """Agreed base, nothing changed: valid, and still advances the fingerprint."""
    db, sa_session, host = ctx
    result = await package_handlers.handle_packages_delta(db, _Connection(), _delta())
    assert result["status"] == "delta_applied"
    assert result["puts_applied"] == 0 and result["takes_applied"] == 0
    assert sa_session.query(AvailablePackage).count() == 0
    assert host.available_packages_fingerprint == NEW_FP
