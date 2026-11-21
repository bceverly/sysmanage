# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Moving a host with its backups to another target (27.3): copy, check,
then switch.  The source storage host copies every snapshot into the new
target through its restate-proxy; the new storage host protects, checks and
lists the copy; only then does the policy name the new target, and the old
repository is kept as it is for the grace period."""

# pylint: disable=redefined-outer-name,unused-argument

import json
import uuid
from datetime import datetime, timedelta

import pytest

from backend.api import backups as api
from backend.api import backups_targets as targets_api
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_moves as moves
from backend.services import backup_replicas as replicas
from backend.services import backup_results as results
from backend.services import backup_targets as targets
from tests.services.test_backup_replicas import _ack, _finish, _runs
from tests.services.test_backup_results import (  # noqa: F401  pylint: disable=unused-import
    _host,
    _setup,
    sent,
)
from tests.test_backups_api import MANAGER, _status

TOKEN = "a" * 64
NOW = datetime(2026, 11, 20, 3, 0)


@pytest.fixture
def ops_engine(monkeypatch):
    from tests._engine_loader import (  # pylint: disable=import-outside-toplevel
        require_engine,
    )

    eng = require_engine("backup_ops_engine")
    monkeypatch.setattr(targets, "engine", lambda: eng)
    return eng


def _new_target(session, s, transport="proxy"):
    """Another target, on its own storage host, behind restate-proxy."""
    nas2 = _host(session, fqdn="nas.dc2.lab")
    stamp = datetime(2026, 11, 1)
    extra = (
        {"proxy_host": "backup.dc2.lab", "proxy_port": 8443,
         "proxy_pin_sha256": "c" * 64}
        if transport == "proxy" else {}
    )  # fmt: skip
    target = models.BackupTarget(
        id=uuid.uuid4(), name="Offsite", location="DC2",
        host_mount_point="/mnt/offsite", storage_host_id=nas2.id,
        storage_path="/srv/offsite/restate", max_concurrent=2, seal_mode="none",
        transport=transport, created_at=stamp, updated_at=stamp, **extra,
    )  # fmt: skip
    session.add(target)
    s.policy.storage_abilities = json.dumps(["replica_copy"])
    session.commit()
    s.new, s.nas2 = target, nas2
    return s


def _snapshot(session, s, name, gone=False):
    session.add(
        models.BackupSnapshot(
            id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id, name=name,
            seen_at=NOW, gone_at=NOW if gone else None,
        )  # fmt: skip
    )
    session.commit()


def _start(session, s):
    body = api.PolicyBody(target_id=str(s.new.id))
    api.save_policy(session, MANAGER, s.host, body)
    _took_job_files(session)
    return replicas.moving(session, s.policy)[0]


def _took_job_files(session):
    """The host and its storage host acknowledged the configures."""
    for run in _runs(session, jobs.CONFIGURE):
        run.status = "ok"
    session.commit()


def _ready(session, s, row):
    """The source made its copy token; the new storage host took the copy's
    job files and prepared the repository."""
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    session.commit()
    _ack(session, _runs(session, jobs.CONFIGURE)[-1],
         {"copy_tokens": {str(row.id): TOKEN}})  # fmt: skip
    replicas.configure_pending(session)
    session.commit()
    _ack(session, _runs(session, "off_configure")[-1])
    _finish(session, _runs(session, "off_prepare")[-1])
    _took_job_files(session)


def _setup_with_history(session):
    s = _new_target(session, _setup(session))
    _snapshot(session, s, "20261119T010000Z")
    _snapshot(session, s, "20261120T010000Z")
    return s


def test_a_host_with_backups_moves_by_copy_and_stays_until_the_switch(
    session, sent, ops_engine
):
    s = _setup_with_history(session)
    row = _start(session, s)
    assert row.status == moves.COPYING
    assert row.repo_dir == jobs.policy_repo_dir(s.policy, s.host)
    assert s.policy.target_id == s.target.id  # still backing up where it is
    # The source storage host is told where to copy; its grant is append.
    jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    session.commit()
    entry = sent[-1][2]["replicas"][0]
    assert entry["id"] == str(row.id)
    assert entry["url"] == f"https://backup.dc2.lab:8443/v1/replica-{row.id}"
    _ack(session, _runs(session, jobs.CONFIGURE)[-1],
         {"copy_tokens": {str(row.id): TOKEN}})  # fmt: skip
    replicas.configure_pending(session)
    session.commit()
    payload = sent[-1][2]
    assert payload["policy_id"] == str(row.id)
    assert payload["target"]["proxy"]["grants"] == [
        {"client": f"replica-{row.id}", "token_sha256": [TOKEN],
         "operations": ["append"]}
    ]  # fmt: skip
    # Nothing is pruned or sealed on the new target before the switch.
    assert set(payload["jobs"]) == {"check", "du", "protect"}


def test_the_copy_is_checked_then_the_policy_switches(session, sent, ops_engine):
    s = _setup_with_history(session)
    row = _start(session, s)
    _ready(session, s, row)
    for name in ("20261119T010000Z", "20261120T010000Z"):
        copy = _runs(session, "copy")[-1]
        assert sent[-1][2]["snapshot"] == name
        assert str(copy.host_id) == str(s.nas.id)  # the source storage host
        _finish(session, copy, copy={"snapshot": name})
    assert row.status == moves.VERIFYING
    _finish(session, _runs(session, "off_protect")[-1])
    check = _runs(session, "off_check")[-1]
    assert str(check.host_id) == str(s.nas2.id)
    _finish(session, check)
    version = s.policy.config_version
    _finish(session, _runs(session, "off_du")[-1], du={"bytes": 99, "snapshots": [
        {"name": "20261119T010000Z"}, {"name": "20261120T010000Z"}]})  # fmt: skip
    assert row.status == moves.SWITCHED
    assert s.policy.target_id == s.new.id
    assert s.policy.config_version == version + 1  # everyone is told
    assert row.keep_until - row.switched_at == timedelta(days=14)
    # Told at once, not on the next tick: the new storage host stores it now.
    told = {
        str(r.host_id) for r in _runs(session, jobs.CONFIGURE) if r.status == "queued"
    }
    assert str(s.nas2.id) in told
    # The copy's grant leaves the new target's clients; it no longer copies.
    assert f"replica-{row.id}" not in replicas.target_clients(session, s.new)
    assert replicas.copy_rows(session, s.policy) == []


def test_a_snapshot_made_while_copying_is_copied_before_the_switch(
    session, sent, ops_engine
):
    s = _setup_with_history(session)
    row = _start(session, s)
    _ready(session, s, row)
    for name in ("20261119T010000Z", "20261120T010000Z"):
        _finish(session, _runs(session, "copy")[-1], copy={"snapshot": name})
    _finish(session, _runs(session, "off_protect")[-1])
    _finish(session, _runs(session, "off_check")[-1])
    _snapshot(session, s, "20261121T010000Z")  # the nightly ran meanwhile
    _finish(session, _runs(session, "off_du")[-1], du={"snapshots": [
        {"name": "20261119T010000Z"}, {"name": "20261120T010000Z"}]})  # fmt: skip
    assert row.status == moves.COPYING and s.policy.target_id == s.target.id
    assert sent[-1][2]["snapshot"] == "20261121T010000Z"


def test_a_failed_check_stops_the_move_and_the_host_stays(session, sent, ops_engine):
    s = _setup_with_history(session)
    row = _start(session, s)
    _ready(session, s, row)
    for name in ("20261119T010000Z", "20261120T010000Z"):
        _finish(session, _runs(session, "copy")[-1], copy={"snapshot": name})
    _finish(session, _runs(session, "off_protect")[-1])
    _finish(session, _runs(session, "off_check")[-1], status="failed")
    assert row.status == moves.FAILED
    assert s.policy.target_id == s.target.id


def test_the_switch_waits_for_the_host_to_be_idle(session, sent, ops_engine):
    s = _setup_with_history(session)
    row = _start(session, s)
    row.status, row.verified_at = moves.VERIFYING, NOW
    row.snapshots = json.dumps(["20261119T010000Z", "20261120T010000Z"])
    capture = jobs.queue_run(session, s.policy, s.host.id, "capture")
    session.commit()
    assert capture is not None
    assert moves.try_switch(session, row) is False
    capture.status = "ok"
    session.commit()
    moves.tick(session, NOW)
    assert row.status == moves.SWITCHED


@pytest.mark.asyncio
async def test_what_refuses_a_move(session, sent, ops_engine):
    s = _setup_with_history(session)
    s.new.transport, s.new.proxy_host = "nfs", None
    session.commit()
    body = api.PolicyBody(target_id=str(s.new.id))
    assert await _status(lambda: api.save_policy(session, MANAGER, s.host, body)) == 409
    s.new.transport, s.new.proxy_host = "proxy", "backup.dc2.lab"
    s.policy.storage_abilities = json.dumps([])  # an older storage agent
    session.commit()
    assert await _status(lambda: api.save_policy(session, MANAGER, s.host, body)) == 409
    assert replicas.moving(session, s.policy) == []


@pytest.mark.asyncio
async def test_a_move_is_canceled_only_on_purpose(session, sent, ops_engine):
    s = _setup_with_history(session)
    row = _start(session, s)
    # Saving the schedule (the dialog sends the current target) keeps it.
    api.save_policy(session, MANAGER, s.host, api.PolicyBody(keep_last=9))
    assert row.status == moves.COPYING
    targets_api.cancel_move(str(row.id), session, MANAGER)
    assert row.status == moves.CANCELED
    assert s.policy.target_id == s.target.id
    assert replicas.copy_rows(session, s.policy) == []
    again = lambda: targets_api.cancel_move(str(row.id), session, MANAGER)  # noqa: E731
    assert await _status(again) == 409


def test_a_host_without_backups_just_switches(session, sent, ops_engine):
    s = _new_target(session, _setup(session))
    api.save_policy(session, MANAGER, s.host, api.PolicyBody(target_id=str(s.new.id)))
    assert s.policy.target_id == s.new.id
    assert replicas.moving(session, s.policy) == []


def test_the_old_repository_is_kept_for_the_seal_retention_when_longer(session):
    old = models.BackupTarget(seal_mode="zfs", seal_keep_days=30)
    assert moves.keep_days(old) == 30
    assert (
        moves.keep_days(models.BackupTarget(seal_mode="none", seal_keep_days=90)) == 14
    )
    assert moves.keep_days(None) == 14


def test_the_old_storage_hosts_audit_is_quietly_accepted(session, sent, ops_engine):
    s = _setup_with_history(session)
    row = _start(session, s)
    row.status, row.switched_at = moves.SWITCHED, NOW
    s.policy.target_id = s.new.id
    session.commit()
    payload = {"policy_id": str(s.policy.id), "storage_audit": {"checks": []}}
    assert results.record_storage_audit(session, s.nas.id, payload) is True
    # The move's own copy, audited under its id by the new storage host.
    payload = {"policy_id": str(row.id), "storage_audit": {"checks": []}}
    assert results.record_storage_audit(session, s.nas2.id, payload) is True


def test_the_host_card_shows_the_move(session, sent, ops_engine):
    s = _setup_with_history(session)
    row = _start(session, s)
    shown = moves.view(session, s.policy, NOW)
    assert shown["status"] == "copying" and shown["target"] == "Offsite"
    assert shown["from_target"] == s.target.name
    assert shown["total"] == 2 and shown["behind"] == 2
    row.status, row.switched_at = moves.SWITCHED, NOW
    row.keep_until = NOW + timedelta(days=14)
    assert moves.view(session, s.policy, NOW)["keep_until"].startswith("2026-12-04")
    assert moves.view(session, s.policy, NOW + timedelta(days=15)) is None
