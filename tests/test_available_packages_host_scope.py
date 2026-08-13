# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The package catalog is stored per HOST, but read per OS.

``available_packages`` used to be one shared catalog keyed by
(os_name, os_version, package_manager, package_name) with no host column, and
``handle_packages_batch_start`` DELETEd an OS's rows before re-inserting them.
Two failures followed from that, both real rather than theoretical:

  * every host running an OS transmitted an identical ~89k-row catalog; and
  * two same-OS hosts reporting concurrently deleted each other's rows, and a
    host that died (or was rejected) part-way through left the catalog
    truncated FOR EVERY HOST of that OS.

Scoping the rows by ``host_id`` fixes both, but it moves the risk somewhere
else: the UI still asks an OS-level question ("what can I install on Ubuntu
26.04?"), so every OS-level read must now collapse duplicates across hosts.
Miss one and a ten-host fleet reports 890,000 packages, or shows every package
ten times.

These tests use a real SQLite session rather than mocking the query chain,
because the property under test IS the SQL: a mocked ``.distinct()`` returns
whatever the mock is told to and can never show that deduplication happened.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, distinct
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.functions import count

from backend.persistence.models import AvailablePackage
from backend.persistence.models.core import Base

HOST_A = "11111111-1111-1111-1111-111111111111"
HOST_B = "22222222-2222-2222-2222-222222222222"

# Two hosts, same OS, reporting the same three packages -- the ordinary case
# for a fleet, and the one that inflates every OS-level count.
CATALOG = [("curl", "8.5.0"), ("vim", "9.1"), ("git", "2.43")]


@pytest.fixture(name="session")
def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine, tables=[AvailablePackage.__table__])
    sess = sessionmaker(bind=engine)()
    try:
        yield sess
    finally:
        # Dispose explicitly: letting the in-memory connection be finalized by
        # the garbage collector surfaces as PytestUnraisableExceptionWarning
        # against whichever test happens to run when GC fires.
        sess.close()
        engine.dispose()


def _add(session, host_id, packages, os_name="Ubuntu", os_version="26.04"):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for name, version in packages:
        session.add(
            AvailablePackage(
                host_id=host_id,
                package_name=name,
                package_version=version,
                package_description=f"{name} description",
                package_manager="apt",
                os_name=os_name,
                os_version=os_version,
                created_at=now,
                last_updated=now,
            )
        )
    session.commit()


def test_two_hosts_store_their_own_rows(session):
    """Scoping means duplication in storage -- that is the accepted trade."""
    _add(session, HOST_A, CATALOG)
    _add(session, HOST_B, CATALOG)
    assert session.query(AvailablePackage).count() == 6


def test_os_level_count_is_not_inflated_by_host_count(session):
    """The regression this scoping could easily have introduced.

    count(id) here would report 6 packages for an OS that has 3.
    """
    _add(session, HOST_A, CATALOG)
    _add(session, HOST_B, CATALOG)

    total = session.query(count(distinct(AvailablePackage.package_name))).scalar()
    assert total == len(CATALOG)


def test_deleting_one_hosts_rows_leaves_the_other_intact(session):
    """The concurrency bug, stated as a test.

    Host A re-reporting must not remove Host B's catalog -- previously the
    delete was by (os_name, os_version) and took every host's rows with it.
    """
    _add(session, HOST_A, CATALOG)
    _add(session, HOST_B, CATALOG)

    session.query(AvailablePackage).filter(
        AvailablePackage.host_id == HOST_A,
        AvailablePackage.package_manager == "apt",
    ).delete()
    session.commit()

    remaining = session.query(AvailablePackage).all()
    assert len(remaining) == len(CATALOG)
    assert {r.host_id for r in remaining} == {HOST_B}


def test_hosts_of_the_same_os_may_report_different_catalogs(session):
    """Different enabled repositories are legitimate, and must both survive.

    Under the shared catalog the last writer won and the other host's extra
    package vanished; the OS-level view should now be the union.
    """
    _add(session, HOST_A, CATALOG)
    _add(session, HOST_B, CATALOG + [("nginx", "1.24")])

    names = {
        row[0] for row in session.query(distinct(AvailablePackage.package_name)).all()
    }
    assert names == {"curl", "vim", "git", "nginx"}


def test_legacy_rows_have_no_host(session):
    """Pre-scoping rows are NULL-owned; they must not break an OS-level read."""
    _add(session, None, [("legacy-pkg", "1.0")])
    row = session.query(AvailablePackage).one()
    assert row.host_id is None

    total = session.query(count(distinct(AvailablePackage.package_name))).scalar()
    assert total == 1


def test_a_host_only_sees_its_own_rows_when_asked_per_host(session):
    """The per-host question the automatic collection trigger now asks."""
    _add(session, HOST_A, CATALOG)

    assert (
        session.query(AvailablePackage)
        .filter(AvailablePackage.host_id == HOST_B)
        .first()
        is None
    )
    assert (
        session.query(AvailablePackage)
        .filter(AvailablePackage.host_id == HOST_A)
        .first()
        is not None
    )
