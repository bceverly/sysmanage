# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet restore jobs (ROADMAP 27.2, Enterprise backup_ops_engine): one
restore asked of many hosts, in waves, each host from its own snapshot."""

# pylint: disable=redefined-outer-name,unused-argument,protected-access

import importlib.util
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.api import backups_fleet_restore as api
from backend.api import backups_four_eyes as eyes_api
from backend.persistence import models
from backend.security.roles import SecurityRoles
from backend.services import backup_fleet_restore as fleet
from backend.services import backup_four_eyes as four_eyes
from tests.services.test_backup_results import EQUIPPED, _setup
from tests.test_backups_api import (
    _status,
    sent,
)  # noqa: F401  pylint: disable=unused-import

_SO = (Path.home() / "dev" / "sysmanage-professional-plus" / "module-source"
       / "backup_ops_engine" / "backup_ops_engine.abi3.so")  # fmt: skip


def _person(userid, *roles):
    return SimpleNamespace(
        id=uuid.uuid4(), userid=userid, has_role=lambda r: r in roles
    )


ALICE = _person("alice@example.com", SecurityRoles.RESTORE_FILES)
BOB = _person("bob@example.com", SecurityRoles.RESTORE_FILES)


@pytest.fixture
def eng(monkeypatch):
    """The engine as just built (the packaged bundles may predate fleet
    restores); skipped without a Pro+ checkout."""
    if not _SO.exists():
        pytest.skip("no Pro+ backup_ops_engine build")
    spec = importlib.util.spec_from_file_location("backup_ops_engine", _SO)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(fleet, "engine", lambda: module)
    monkeypatch.setattr(four_eyes, "engine", lambda: module)
    monkeypatch.setattr(four_eyes, "enabled", lambda: False)
    return module


def _fleet(session, n=3, snaps=((3, "a"), (1, "b"))):
    """``n`` equipped hosts on one target, each with its own snapshots,
    ``snaps`` = (days ago, name suffix)."""
    s = _setup(session)
    hosts = [s.host]
    for i in range(1, n):
        host = models.Host(id=uuid.uuid4(), fqdn=f"web{i:02d}.lab", active=True,
                           approval_status="approved", agent_capabilities=EQUIPPED)  # fmt: skip
        session.add(host)
        session.flush()
        session.add(models.BackupPolicy(
            id=uuid.uuid4(), host_id=host.id, target_id=s.target.id, enabled=True,
            interval_hours=24, keep_last=14, check_interval_days=7, quiesce=False,
            config_version=1, host_acked_version=1, storage_acked_version=1,
            created_at=datetime(2026, 10, 1), updated_at=datetime(2026, 10, 1),
        ))  # fmt: skip
        hosts.append(host)
    session.commit()
    now = datetime(2026, 11, 24, 12)
    for host in hosts:
        policy = session.query(models.BackupPolicy).filter_by(host_id=host.id).one()
        for days, suffix in snaps:
            session.add(models.BackupSnapshot(
                id=uuid.uuid4(), policy_id=policy.id, host_id=host.id,
                name=f"2026-11-{24 - days:02d}T000000Z-{suffix}", signed=True,
                created_at=now - timedelta(days=days), seen_at=now,
            ))  # fmt: skip
    session.commit()
    return hosts


def _body(hosts, **over):
    fields = {"name": "after the incident", "host_ids": [str(h.id) for h in hosts],
              "include": ["/etc/nginx"], "concurrency": 2}  # fmt: skip
    fields.update(over)
    return api.FleetRestoreBody(**fields)


def _restores(sent):
    return [c for c in sent if c[1] == "backup_restore"]


def _finish(session, job_id, status="ok"):
    job = session.get(models.BackupFleetRestore, uuid.UUID(job_id))
    for target in job.targets:
        if target.run_id:
            session.get(models.BackupRun, target.run_id).status = status
    session.commit()


def test_hosts_are_released_in_waves_each_from_its_own_newest_snapshot(
    session, sent, eng
):
    hosts = _fleet(session)
    out = api.create_fleet_restore(_body(hosts), session, ALICE)
    assert out["status"] == "running" and out["concurrency"] == 2
    first = _restores(sent)
    assert len(first) == 2  # the wave: never more than the concurrency
    assert {c[2]["snapshot"].endswith("-b") for c in first} == {True}
    assert out["counts"] == {"running": 2, "waiting": 1}

    _finish(session, out["id"])
    fleet.tick(session)
    assert len(_restores(sent)) == 3  # the next wave
    _finish(session, out["id"])
    fleet.tick(session)
    done = api.get_fleet_restore(out["id"], session, ALICE)
    assert done["status"] == "completed" and done["counts"] == {"ok": 3}
    assert {t["fqdn"] for t in done["targets"]} == {h.fqdn for h in hosts}


def test_before_picks_the_last_good_snapshot_and_skips_a_host_without_one(
    session, sent, eng
):
    hosts = _fleet(session, n=2)
    newest_only = hosts[1]
    policy = session.query(models.BackupPolicy).filter_by(host_id=newest_only.id).one()
    for snap in session.query(models.BackupSnapshot).filter_by(policy_id=policy.id):
        if snap.name.endswith("-a"):
            session.delete(snap)
    session.commit()
    before = datetime(2026, 11, 22, 12)  # after "a" (3 days ago), before "b"
    out = api.create_fleet_restore(_body(hosts, before=before), session, ALICE)
    (restore,) = _restores(sent)
    assert restore[2]["snapshot"].endswith("-a")
    skipped = [t for t in out["targets"] if t["status"] == "skipped"]
    assert [t["host_id"] for t in skipped] == [str(newest_only.id)]
    assert skipped[0]["message"] == "No snapshot to restore from"


def test_a_host_that_cannot_take_it_is_recorded_and_the_others_go_on(
    session, sent, eng
):
    hosts = _fleet(session)
    hosts[0].agent_capabilities = None  # not equipped
    session.commit()
    out = api.create_fleet_restore(_body(hosts, concurrency=5), session, ALICE)
    assert len(_restores(sent)) == 2
    assert out["counts"] == {"running": 2, "skipped": 1}


def test_a_host_refused_as_it_is_released_takes_no_slot(session, sent, eng):
    # Lab, 2026-11-25: with concurrency 1 a refused host used the tick's one
    # slot, so the next host waited a whole tick (three refusals, three ticks).
    hosts = _fleet(session)
    for host in hosts[:2]:
        host.agent_capabilities = None  # not equipped: refused when released
    session.commit()
    out = api.create_fleet_restore(_body(hosts, concurrency=1), session, ALICE)
    assert len(_restores(sent)) == 1  # the third host, in the same tick
    assert out["counts"] == {"running": 1, "skipped": 2}


def test_hosts_are_released_in_the_order_they_were_listed(session, sent, eng):
    # Targets were ordered by their random ids (lab, 2026-11-25).
    hosts = _fleet(session, n=5)
    order = [hosts[i] for i in (3, 0, 4, 1, 2)]
    out = api.create_fleet_restore(_body(order, concurrency=1), session, ALICE)
    assert [t["host_id"] for t in out["targets"]] == [str(h.id) for h in order]
    (first,) = _restores(sent)
    assert first[0] == str(order[0].id)


@pytest.mark.asyncio
async def test_an_in_place_fleet_restore_waits_for_a_second_person(
    session, sent, eng, monkeypatch
):
    monkeypatch.setattr(four_eyes, "enabled", lambda: True)
    hosts = _fleet(session)
    out = api.create_fleet_restore(
        _body(hosts, in_place=True, acknowledge_in_place=True), session, ALICE
    )
    assert out["status"] == "awaiting_approval" and _restores(sent) == []
    request = (
        session.query(models.BackupRestoreRequest).filter_by(kind="fleet_restore").one()
    )
    rid = str(request.id)
    # The approver sees which files every host would have overwritten.
    assert json.loads(request.body)["include"] == ["/etc/nginx"]
    assert await _status(lambda: eyes_api.approve_restore(rid, session, ALICE)) == 403
    eyes_api.approve_restore(rid, session, BOB)
    assert len(_restores(sent)) == 2
    assert all(c[2]["in_place"] for c in _restores(sent))
    job = api.get_fleet_restore(out["id"], session, ALICE)
    assert job["status"] == "running" and job["approved_by"] == BOB.userid


def test_a_fleet_restore_into_staging_does_not_wait_for_a_second_person(
    session, sent, eng, monkeypatch
):
    # Four-eyes holds a restore over existing files, not one into staging;
    # the engine held every fleet restore while the setting was on (lab,
    # 2026-11-25).
    monkeypatch.setattr(four_eyes, "enabled", lambda: True)
    hosts = _fleet(session)
    out = api.create_fleet_restore(_body(hosts), session, ALICE)
    assert out["status"] == "running" and len(_restores(sent)) == 2
    assert session.query(models.BackupRestoreRequest).count() == 0


def test_a_rejected_fleet_restore_never_runs(session, sent, eng, monkeypatch):
    monkeypatch.setattr(four_eyes, "enabled", lambda: True)
    hosts = _fleet(session)
    out = api.create_fleet_restore(
        _body(hosts, in_place=True, acknowledge_in_place=True), session, ALICE
    )
    rid = str(
        session.query(models.BackupRestoreRequest)
        .filter_by(kind="fleet_restore")
        .one()
        .id
    )
    eyes_api.reject_restore(
        rid, eyes_api.RejectBody(reason="wrong paths"), session, BOB
    )
    fleet.tick(session)
    job = api.get_fleet_restore(out["id"], session, ALICE)
    assert job["status"] == "rejected" and _restores(sent) == []


def test_a_withdrawn_fleet_restore_is_canceled_not_rejected(
    session, sent, eng, monkeypatch
):
    # The requester calling it off read "rejected" (lab, 2026-11-25).
    monkeypatch.setattr(four_eyes, "enabled", lambda: True)
    hosts = _fleet(session)
    out = api.create_fleet_restore(
        _body(hosts, in_place=True, acknowledge_in_place=True), session, ALICE
    )
    rid = str(
        session.query(models.BackupRestoreRequest)
        .filter_by(kind="fleet_restore")
        .one()
        .id
    )
    eyes_api.withdraw_restore(rid, session, ALICE)
    fleet.tick(session)
    job = api.get_fleet_restore(out["id"], session, ALICE)
    assert job["status"] == "canceled" and _restores(sent) == []
    assert {t["status"] for t in job["targets"]} == {"canceled"}


def test_cancel_stops_the_waiting_hosts_and_lets_running_ones_finish(
    session, sent, eng
):
    hosts = _fleet(session)
    out = api.create_fleet_restore(_body(hosts), session, ALICE)
    after = api.cancel_fleet_restore(out["id"], session, ALICE)
    assert after["status"] == "canceled"
    assert after["counts"] == {"running": 2, "canceled": 1}
    _finish(session, out["id"])
    fleet.tick(session)
    job = api.get_fleet_restore(out["id"], session, ALICE)
    assert job["counts"] == {"ok": 2, "canceled": 1} and job["finished_at"]
    assert len(_restores(sent)) == 2


@pytest.mark.asyncio
async def test_without_the_engine_it_is_402_and_bad_paths_are_refused(
    session, sent, monkeypatch, eng
):
    hosts = _fleet(session, n=1)
    bad = _body(hosts, include=["relative/path"])
    assert await _status(lambda: api.create_fleet_restore(bad, session, ALICE)) == 422
    monkeypatch.setattr(fleet, "engine", lambda: None)
    assert (
        await _status(lambda: api.create_fleet_restore(_body(hosts), session, ALICE))
        == 402
    )
