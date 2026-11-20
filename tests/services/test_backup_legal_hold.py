# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Legal hold (ROADMAP 27.2): held snapshots are kept by every prune until
released -- whatever the license -- and placing or releasing one is
Enterprise (backup_ops_engine), with an owner and a reason, audited."""

# pylint: disable=redefined-outer-name,unused-argument

import json
import uuid
from datetime import datetime

import pytest

from backend.api import backups_legal_hold as api
from backend.persistence import models
from backend.services import backup_jobs as jobs
from tests.services.test_backup_results import _setup
from tests.test_backups_api import MANAGER, NOBODY, _status

BODY = api.HoldBody(owner="Case 2026-114", reason="Litigation hold, counsel's request")


@pytest.fixture
def ops_engine(monkeypatch):
    from tests._engine_loader import (  # pylint: disable=import-outside-toplevel
        require_engine,
    )

    eng = require_engine("backup_ops_engine")
    monkeypatch.setattr(api.module_loader, "get_module", lambda code: eng)
    return eng


def _held_setup(session, abilities=("keep_yearly", "keep_snapshot")):
    s = _setup(session)
    s.policy.storage_abilities = json.dumps(list(abilities))
    for name in ("20261101T010000Z", "20261102T010000Z"):
        session.add(models.BackupSnapshot(
            id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id,
            name=name, signed=True, seen_at=datetime(2026, 11, 2),
        ))  # fmt: skip
    session.commit()
    return s


def test_a_hold_is_kept_by_every_prune(session, ops_engine):
    s = _held_setup(session)
    before = s.policy.config_version
    api.place_legal_hold(str(s.host.id), "20261101T010000Z", BODY, session, MANAGER)
    assert jobs.prune_keep(s.policy)["keep_snapshot"] == ["20261101T010000Z"]
    assert s.policy.config_version == before + 1  # the storage job is re-sent
    assert jobs.prune_keep(s.policy)["keep_last"] == s.policy.keep_last  # a rule too


def test_holds_are_honored_without_the_engine(session, ops_engine, monkeypatch):
    s = _held_setup(session)
    api.place_legal_hold(str(s.host.id), "20261101T010000Z", BODY, session, MANAGER)
    monkeypatch.setattr(api.module_loader, "get_module", lambda code: None)
    # A lapse: placing and releasing are refused, the hold still protects.
    assert jobs.prune_keep(s.policy)["keep_snapshot"] == ["20261101T010000Z"]


@pytest.mark.asyncio
async def test_release_drops_it_from_the_prune(session, ops_engine):
    s = _held_setup(session)
    hold = api.place_legal_hold(
        str(s.host.id), "20261101T010000Z", BODY, session, MANAGER
    )
    released = api.release_legal_hold(hold["id"], session, MANAGER)
    assert released["released_by"] == MANAGER.userid
    assert "keep_snapshot" not in jobs.prune_keep(s.policy)
    assert (
        await _status(lambda: api.release_legal_hold(hold["id"], session, MANAGER))
        == 409
    )


@pytest.mark.asyncio
async def test_a_storage_host_that_cannot_keep_it_is_refused(session, ops_engine):
    s = _held_setup(session, abilities=("keep_yearly",))
    assert await _status(lambda: api.place_legal_hold(
        str(s.host.id), "20261101T010000Z", BODY, session, MANAGER)) == 409  # fmt: skip
    assert "keep_snapshot" not in jobs.prune_keep(s.policy)


@pytest.mark.asyncio
async def test_a_missing_snapshot_a_second_hold_and_the_role(session, ops_engine):
    s = _held_setup(session)
    host = str(s.host.id)
    assert await _status(lambda: api.place_legal_hold(
        host, "20990101T000000Z", BODY, session, MANAGER)) == 404  # fmt: skip
    assert await _status(lambda: api.place_legal_hold(
        host, "20261101T010000Z", BODY, session, NOBODY)) == 403  # fmt: skip
    api.place_legal_hold(host, "20261101T010000Z", BODY, session, MANAGER)
    assert await _status(lambda: api.place_legal_hold(
        host, "20261101T010000Z", BODY, session, MANAGER)) == 409  # fmt: skip


@pytest.mark.asyncio
async def test_placing_needs_the_engine(session, monkeypatch):
    monkeypatch.setattr(api.module_loader, "get_module", lambda code: None)
    s = _held_setup(session)
    assert await _status(lambda: api.place_legal_hold(
        str(s.host.id), "20261101T010000Z", BODY, session, MANAGER)) == 402  # fmt: skip
    assert await _status(lambda: api.list_legal_holds(session)) == 402


def test_the_list_shows_holds_in_force_first(session, ops_engine):
    s = _held_setup(session)
    first = api.place_legal_hold(
        str(s.host.id), "20261101T010000Z", BODY, session, MANAGER
    )
    api.place_legal_hold(str(s.host.id), "20261102T010000Z", BODY, session, MANAGER)
    api.release_legal_hold(first["id"], session, MANAGER)
    holds = api.list_legal_holds(session)["holds"]
    assert [h["released_at"] is None for h in holds] == [True, False]
    assert holds[0]["owner"] == "Case 2026-114"


def test_an_owner_and_a_reason_are_required():
    with pytest.raises(ValueError):
        api.HoldBody(owner="", reason="x")
    with pytest.raises(ValueError):
        api.HoldBody(owner="x", reason="")
