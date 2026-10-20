# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backups (Phase 24): what is sent, how results are recorded, and the
storage-side chain a good capture starts (seal before prune, never on the
host)."""

import json
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.api.handlers import backup_handlers
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_results as results

EQUIPPED = json.dumps({"capabilities": ["backup"], "commands": []})


def _host(session, fqdn="Web_01.Lab.Example", caps=EQUIPPED, **extra):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=fqdn,
        active=True,
        approval_status="approved",
        agent_capabilities=caps,
        **extra,
    )
    session.add(host)
    session.commit()
    return host


def _setup(session, seal_mode="none", storage_acked=1):
    host = _host(session)
    nas = _host(session, fqdn="nas.lab")
    stamp = datetime(2026, 10, 1)
    target = models.BackupTarget(
        id=uuid.uuid4(),
        name="nas",
        host_mount_point="/mnt/backups",
        storage_host_id=nas.id,
        storage_path="/srv/backups/restate",
        max_concurrent=2,
        seal_mode=seal_mode,
        zfs_dataset="tank/backups" if seal_mode != "none" else None,
        created_at=stamp,
        updated_at=stamp,
    )
    session.add(target)
    session.flush()
    policy = models.BackupPolicy(
        id=uuid.uuid4(),
        host_id=host.id,
        target_id=target.id,
        enabled=True,
        interval_hours=24,
        keep_last=14,
        check_interval_days=7,
        quiesce=False,
        config_version=1,
        host_acked_version=1,
        storage_acked_version=storage_acked,
        created_at=stamp,
        updated_at=stamp,
    )
    session.add(policy)
    session.commit()
    return SimpleNamespace(host=host, nas=nas, target=target, policy=policy)


@pytest.fixture
def sent():
    calls = []

    def fake(_db, host_id, command_type, parameters):
        calls.append(
            (str(host_id), getattr(command_type, "value", command_type), parameters)
        )
        return str(uuid.uuid4())

    with patch.object(jobs.config_mgmt_dispatch, "queue_command", side_effect=fake):
        yield calls


def _result(run, status="ok", **result):
    return {
        "run_id": str(run.id),
        "policy_id": str(run.policy_id),
        "action": run.action,
        "status": status,
        "exit": {"ok": 0, "incomplete": 3, "failed": 2}.get(status, 0),
        "result": result,
        "started_at": "2026-10-20T01:00:00Z",
        "finished_at": "2026-10-20T01:05:00Z",
        "restate_version": "2.0.0.0",
    }


def test_repo_dir_is_sanitized_fqdn_and_the_host_id():
    host = SimpleNamespace(
        fqdn="Web_01.Lab.Example", id=uuid.UUID("0123456789abcdef0123456789abcdef")
    )
    assert jobs.repo_dir(host) == "web-01.lab.example-01234567"


def test_equipped_reports_the_agents_reason():
    def host(report):
        return SimpleNamespace(
            agent_capabilities=json.dumps(report) if report else None
        )

    assert jobs.equipped(None) == (False, "no_host")
    assert jobs.equipped(host(None)) == (False, "agent_outdated")
    assert jobs.equipped(host({"capabilities": []})) == (False, "agent_outdated")
    assert jobs.equipped(
        host({"capabilities": [], "unavailable": {"backup": "tool_outdated"}})
    ) == (False, "tool_outdated")
    assert jobs.equipped(host({"capabilities": ["backup"]})) == (True, None)


def test_the_host_never_gets_prune_and_storage_gets_seal(session):
    s = _setup(session, seal_mode="zfs_snapshot")
    host_jobs = jobs.host_configuration(s.policy, s.target, s.host)
    storage_jobs = jobs.storage_configuration(s.policy, s.target, s.host)
    assert set(host_jobs["jobs"]) == {"capture", "snapshots", "estimate"}
    assert host_jobs["target"]["mount_point"] == "/mnt/backups"
    assert set(storage_jobs["jobs"]) == {"seal", "prune", "check"}
    assert storage_jobs["target"]["mount_point"] == "/srv/backups/restate"
    assert storage_jobs["jobs"]["seal"] == {
        "mode": "zfs_snapshot",
        "dataset": "tank/backups",
    }
    assert storage_jobs["jobs"]["prune"] == {"keep_last": 14}
    assert host_jobs["target"]["repo_dir"] == storage_jobs["target"]["repo_dir"]


def test_one_id_for_the_run_and_its_command(session, sent):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    host_id, command, params = sent[0]
    assert (host_id, command) == (str(s.host.id), "backup_run")
    assert params == {
        "run_id": str(run.id),
        "policy_id": str(s.policy.id),
        "action": "capture",
    }
    assert run.command_id and run.status == "queued"


def test_configure_ack_records_the_version_per_role(session, sent):
    s = _setup(session, storage_acked=0)
    s.policy.config_version = 3
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    assert sent[0][0] == str(s.nas.id) and sent[0][2]["role"] == "storage"
    assert "config_version" not in sent[0][2]  # kept on the run, not sent
    assert results.record_command_result(
        session, {"command_id": run.command_id, "success": True}
    )
    assert run.status == "ok"
    assert s.policy.storage_acked_version == 3 and s.policy.host_acked_version == 1


def test_a_refused_command_fails_the_run(session, sent):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    results.record_command_result(
        session,
        {"command_id": run.command_id, "success": False, "error": "no_job_file"},
    )
    assert run.status == "failed" and run.message == "no_job_file"
    assert results.record_command_result(session, {"command_id": "nope"}) is False


def test_a_good_capture_seals_on_the_storage_host_then_prunes(session, sent):
    s = _setup(session, seal_mode="zfs_snapshot")
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    payload = _result(
        run, "incomplete", snapshot="2026-10-20T010000Z", paths=812,
        read_bytes=5000, new_bytes=300, repository_bytes=90000,
        unreadable={"count": 1, "first": [{"path": "/x", "reason": "EACCES"}]},
    )  # fmt: skip
    assert results.record_result(session, s.host.id, payload) is run
    assert run.status == "incomplete" and run.exit_code == 3
    assert json.loads(run.result)["unreadable"]["count"] == 1
    assert s.policy.restate_version == "2.0.0.0" and s.policy.repository_bytes == 90000
    snap = session.query(models.BackupSnapshot).one()
    assert (snap.name, snap.files, snap.signed) == ("2026-10-20T010000Z", 812, False)
    assert [(h, c, p["action"]) for h, c, p in sent[1:]] == [
        (str(s.nas.id), "backup_run", "seal")
    ]
    seal = session.query(models.BackupRun).filter_by(action="seal").one()
    results.record_result(session, s.nas.id, _result(seal))
    assert [p["action"] for _h, _c, p in sent[2:]] == ["prune"]


def test_a_failed_seal_holds_the_prune_back(session, sent):
    s = _setup(session, seal_mode="zfs_snapshot")
    seal = jobs.queue_run(session, s.policy, s.nas.id, "seal")
    results.record_result(session, s.nas.id, _result(seal, "failed", error="zfs"))
    assert seal.status == "failed"
    assert [p["action"] for _h, _c, p in sent] == ["seal"]


def test_no_seal_mode_goes_straight_to_prune(session, sent):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    results.record_result(session, s.host.id, _result(run, snapshot="a1"))
    prune = session.query(models.BackupRun).filter_by(action="prune").one()
    assert str(prune.host_id) == str(s.nas.id)
    results.record_result(session, s.nas.id, _result(prune, pruned=["a1"]))
    assert session.query(models.BackupSnapshot).one().gone_at is not None
    assert len(sent) == 2  # the capture and the prune; nothing after a prune


def test_a_snapshot_listing_retires_missing_snapshots(session, sent):
    s = _setup(session)
    for name in ("old", "keep"):
        results._upsert_snapshot(session, s.policy, name, {})
    listing = jobs.queue_run(session, s.policy, s.host.id, "snapshots")
    results.record_result(
        session, s.host.id, _result(listing, snapshots=[{"name": "keep"}, "new"])
    )
    rows = {r.name: r for r in session.query(models.BackupSnapshot).all()}
    assert rows["old"].gone_at is not None
    assert rows["keep"].gone_at is None and rows["new"].gone_at is None


def test_storage_jobs_never_include_du_or_paths_the_agent_owns(session):
    s = _setup(session)
    for config in (
        jobs.host_configuration(s.policy, s.target, s.host),
        jobs.storage_configuration(s.policy, s.target, s.host),
    ):
        assert "config_version" not in config
        for job in config["jobs"].values():
            assert not {"command", "repository", "result", "progress_file"} & set(job)
    storage = jobs.storage_configuration(s.policy, s.target, s.host)
    assert "du" not in storage["jobs"] and storage["jobs"]["seal"] == {"mode": "none"}


def test_a_busy_refusal_is_retried_and_not_configured_resends(session, sent):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    results.record_command_result(
        session, {"command_id": run.command_id, "success": False, "error": "busy"}
    )
    assert run.status == "busy"
    prune = jobs.queue_run(session, s.policy, s.nas.id, "prune")
    results.record_command_result(
        session,
        {"command_id": prune.command_id, "success": False, "error": "not_configured"},
    )
    assert prune.status == "failed"
    assert (s.policy.host_acked_version, s.policy.storage_acked_version) == (1, 0)


def test_restore_sends_include_exclude_and_never_a_destination(session, sent):
    s = _setup(session)
    jobs.queue_restore(
        session,
        s.policy,
        s.host,
        "snap1",
        ["/etc"],
        True,
        True,
        "ops",
        exclude=["/etc/ssl"],
    )
    params = sent[0][2]
    assert params["include"] == ["/etc"] and params["exclude"] == ["/etc/ssl"]
    assert params["dry_run"] is True and params["allow_unverified"] is True
    assert not {"target", "destination", "restore_root"} & set(params)


def test_storage_not_configured_means_no_chain(session, sent):
    s = _setup(session, storage_acked=0)
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    results.record_result(session, s.host.id, _result(run, snapshot="a1"))
    assert len(sent) == 1  # only the capture itself


def test_a_result_from_another_host_or_a_repeat_is_ignored(session, sent):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.host.id, "estimate")
    assert results.record_result(session, s.nas.id, _result(run, bytes=1)) is None
    assert run.status == "queued"
    results.record_result(session, s.host.id, _result(run, bytes=77))
    assert s.policy.estimate_bytes == 77
    results.record_result(session, s.host.id, _result(run, "failed"))
    assert run.status == "ok"


def test_an_unknown_status_word_is_failed(session, sent):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.host.id, "check")
    results.record_result(session, s.host.id, _result(run, "exploded"))
    assert run.status == "failed"


def test_progress_is_kept_until_the_result(session, sent):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    results.record_progress(
        session, s.host.id,
        {"run_id": str(run.id), "action": "capture",
         "progress": {"phase": "scan", "paths": 10, "total_bytes": 9, "evil": 1}},
    )  # fmt: skip
    kept = json.loads(run.progress)
    assert run.status == "running" and kept["paths"] == 10 and kept["total_bytes"] == 9
    assert "evil" not in kept and kept["action"] == "capture"
    results.record_result(session, s.host.id, _result(run, snapshot="x"))
    assert run.progress is None


@pytest.mark.asyncio
async def test_the_handlers_commit_and_never_raise(session, sent):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.host.id, "estimate")
    session.commit()
    connection = SimpleNamespace(host_id=s.host.id)
    out = await backup_handlers.handle_backup_result(
        session, connection, {"data": _result(run, bytes=5)}
    )
    assert out["data"]["stored"] is True
    assert (await backup_handlers.handle_backup_progress(
        session, SimpleNamespace(host_id=None), {}
    ))["message_type"] == "error"  # fmt: skip
    with patch.object(results, "record_result", side_effect=RuntimeError("boom")):
        out = await backup_handlers.handle_backup_result(session, connection, {})
    assert out["message_type"] == "error"


@pytest.mark.asyncio
async def test_command_results_route_to_the_backup_recorder(session, sent):
    from backend.api import message_handlers

    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    session.commit()
    message = {
        "command_id": run.command_id,
        "command_type": "backup_run",
        "success": True,
        "result": {"run_id": str(run.id), "status": "started"},
    }
    connection = SimpleNamespace(host_id=s.host.id, hostname="web")
    with patch.object(message_handlers, "_close_out_command"):
        await message_handlers.handle_command_result(session, connection, message)
    assert run.status == "running"


def test_a_capture_that_created_its_repository_is_logged(session, sent, caplog):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    payload = _result(
        run, "ok", snapshot="2026-10-20T020000Z", created_repository=True,
        repository="/mnt/backups/h-1",
    )  # fmt: skip
    with caplog.at_level("INFO", logger="backend.services.backup_results"):
        results.record_result(session, s.host.id, payload)
    assert "created repository /mnt/backups/h-1" in caplog.text
