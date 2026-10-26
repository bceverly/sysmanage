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
from backend.services import backup_views as views

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
    assert set(storage_jobs["jobs"]) == {
        "seal",
        "prune",
        "check",
        "du",
        "repack",
        "protect",
    }
    assert storage_jobs["target"]["mount_point"] == "/srv/backups/restate"
    assert storage_jobs["jobs"]["seal"] == {
        "mode": "zfs_snapshot",
        "dataset": "tank/backups",
        "keep_days": 14,
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
    # the capture, the prune, and then du sizes what is left
    assert [p["action"] for _h, _c, p in sent] == ["capture", "prune", "du"]


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


def test_storage_jobs_never_include_paths_the_agent_owns(session):
    s = _setup(session)
    for config in (
        jobs.host_configuration(s.policy, s.target, s.host),
        jobs.storage_configuration(s.policy, s.target, s.host),
    ):
        assert "config_version" not in config
        for job in config["jobs"].values():
            assert not {"command", "repository", "result", "progress"} & set(job)
    storage = jobs.storage_configuration(s.policy, s.target, s.host)
    # du takes nothing from the server: the agent fills in the repository
    assert storage["jobs"]["du"] == {} and storage["jobs"]["seal"] == {"mode": "none"}


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


def test_a_good_prune_sizes_the_repository_with_du(session, sent):
    s = _setup(session)
    _upsert = results._upsert_snapshot  # pylint: disable=protected-access
    _upsert(session, s.policy, "2026-10-20T010000Z", {"bytes": 1})
    _upsert(session, s.policy, "2026-10-19T010000Z", {"bytes": 1})
    prune = jobs.queue_run(session, s.policy, s.nas.id, "prune")
    results.record_result(session, s.nas.id, _result(prune, pruned=[]))
    du = session.query(models.BackupRun).filter_by(action="du").one()
    assert du.host_id == s.nas.id
    payload = _result(du, du={
        "repository": "/srv/backups/restate/h", "bytes": 52_000, "packs": 9,
        "snapshots": [
            {"name": "2026-10-20T010000Z", "bytes": 50_000, "new_bytes": 2_000,
             "unique_bytes": 1_500, "listed": True},
            {"name": "gone-or-unknown", "bytes": 7},
            "not-an-object",
        ],
    })  # fmt: skip
    results.record_result(session, s.nas.id, payload)
    assert s.policy.repository_bytes == 52_000
    snap = (
        session.query(models.BackupSnapshot).filter_by(name="2026-10-20T010000Z").one()
    )
    assert (snap.bytes, snap.new_bytes, snap.unique_bytes) == (50_000, 2_000, 1_500)


def test_a_failed_prune_does_not_run_du(session, sent):
    s = _setup(session)
    prune = jobs.queue_run(session, s.policy, s.nas.id, "prune")
    results.record_result(session, s.nas.id, _result(prune, "failed"))
    assert session.query(models.BackupRun).filter_by(action="du").count() == 0


def test_a_new_restate_version_re_sends_the_job_files(session, sent):
    s = _setup(session)
    s.policy.restate_version = "2.0.0.1"
    s.policy.storage_restate_version = "2.0.0.1"
    session.commit()
    version = s.policy.config_version
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    payload = _result(run, snapshot="a1")
    payload["restate_version"] = "2.0.0.1"
    results.record_result(session, s.host.id, payload)
    assert s.policy.config_version == version  # same restate: nothing to do
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    payload = _result(run, snapshot="a2")
    payload["restate_version"] = "2.0.0.4"
    results.record_result(session, s.host.id, payload)
    assert s.policy.config_version == version + 1
    assert s.policy.restate_version == "2.0.0.4"
    check = jobs.queue_run(session, s.policy, s.nas.id, "check")
    payload = _result(check)
    payload["restate_version"] = "2.0.0.4"
    results.record_result(session, s.nas.id, payload)
    assert s.policy.config_version == version + 2  # the storage side too


def test_the_first_restate_error_is_the_runs_message(session, sent):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    payload = _result(run, "failed", errors=["", "/mnt/backups/h: Permission denied",
                                             "follow-on"])  # fmt: skip
    results.record_result(session, s.host.id, payload)
    assert run.message == "/mnt/backups/h: Permission denied"


def test_a_captures_repository_qualified_snapshot_is_stored_by_its_bare_name(
    session, sent
):
    # restate names a capture's snapshot <repository>::<name>; restore, prune,
    # du and the listing use <name> (lab 2026-10-21: every restore refused).
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    payload = _result(run, snapshot="/mnt/backups/h-1::20261021T153126Z")
    results.record_result(session, s.host.id, payload)
    assert run.snapshot == "20261021T153126Z"
    snap = session.query(models.BackupSnapshot).one()
    assert snap.name == "20261021T153126Z"
    assert results.snapshot_name("20261021T153126Z") == "20261021T153126Z"


def test_a_repack_runs_on_the_storage_host_and_is_sized_after(session, sent):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.nas.id, "repack")
    assert run.host_id == s.nas.id
    results.record_result(session, s.nas.id, _result(
        run, "ok", packs_rewritten=688, packs_removed=3, bytes_freed=1234,
    ))  # fmt: skip
    assert [p["action"] for _h, _c, p in sent] == ["repack", "du"]


def test_a_stopped_repack_is_sized_too_and_a_failed_one_is_not(session, sent):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.nas.id, "repack")
    results.record_result(session, s.nas.id, _result(run, "incomplete"))
    assert [p["action"] for _h, _c, p in sent] == ["repack", "du"]
    sent.clear()
    run = jobs.queue_run(session, s.policy, s.nas.id, "repack")
    results.record_result(session, s.nas.id, _result(run, "failed"))
    assert [p["action"] for _h, _c, p in sent] == ["repack"]


def test_a_prepare_keeps_the_fresh_audit_and_queues_nothing_after(session, sent):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.nas.id, "prepare")
    payload = _result(
        run,
        "failed",
        reason="zfs_required",
        errors=["FreeBSD exports whole filesystems"],
    )
    payload["storage_audit"] = [{"code": "export_own", "level": "ok", "params": {}}]
    results.record_result(session, s.nas.id, payload)
    assert run.status == "failed" and run.message == "FreeBSD exports whole filesystems"
    assert json.loads(s.policy.storage_audit)[0]["code"] == "export_own"
    assert [p["action"] for _h, _c, p in sent] == ["prepare"]


def _ack_storage(session, s):
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    results.record_command_result(
        session, {"command_id": run.command_id, "success": True}
    )


def test_a_prepared_repository_is_re_prepared_when_its_host_moves(session, sent):
    s = _setup(session)
    s.host.ipv4 = "192.168.4.196"
    _ack_storage(session, s)
    prepare = jobs.queue_run(session, s.policy, s.nas.id, "prepare")
    assert json.loads(prepare.parameters)["client_address"] == "192.168.4.196"
    results.record_result(session, s.nas.id, _result(prepare, "ok", kind="zfs"))
    sent.clear()
    _ack_storage(session, s)  # same address: nothing more
    assert [p.get("action") for _h, _c, p in sent] == [None]
    sent.clear()
    s.host.ipv4 = "192.168.4.200"
    _ack_storage(session, s)
    assert [p.get("action") for _h, _c, p in sent] == [None, "prepare"]
    assert sent[-1][0] == str(s.nas.id)


def test_a_never_prepared_repository_is_not_prepared_behind_the_admins_back(
    session, sent
):
    s = _setup(session)
    s.host.ipv4 = "192.168.4.196"
    _ack_storage(session, s)
    s.host.ipv4 = "192.168.4.200"
    _ack_storage(session, s)
    assert "prepare" not in [p.get("action") for _h, _c, p in sent]


def test_the_reported_nfs_path_reaches_the_host_with_the_storage_address(session, sent):
    s = _setup(session)
    s.nas.ipv4 = "192.168.4.10"
    assert (
        "nfs"
        not in jobs.host_configuration(s.policy, s.target, s.host, s.nas)["target"]
    )
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    version = s.policy.config_version
    results.record_command_result(session, {
        "command_id": run.command_id, "success": True,
        "result": {"nfs_path": "/restate/web-01"},
    })  # fmt: skip
    assert s.policy.storage_nfs_path == "/restate/web-01"
    assert s.policy.config_version == version + 1  # the host is re-sent its jobs
    host_jobs = jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    assert json.loads(host_jobs.parameters)["target"]["nfs"] == {
        "server": "192.168.4.10",
        "path": "/restate/web-01",
    }
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    results.record_command_result(session, {
        "command_id": run.command_id, "success": True,
        "result": {"nfs_path": "/restate/web-01"},
    })  # fmt: skip
    assert s.policy.config_version == version + 1  # unchanged: no more re-sends


def test_the_configure_reply_says_whether_the_storage_host_protects(session, sent):
    s = _setup(session)
    for installed, protects in (
        (["check", "prune", "protect"], True),
        (["check"], False),
    ):
        run = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
        results.record_command_result(session, {
            "command_id": run.command_id, "success": True,
            "result": {"installed": installed},
        })  # fmt: skip
        assert s.policy.storage_protects is protects


@pytest.mark.parametrize(
    "seal_mode,after", [("none", "prune"), ("zfs_snapshot", "seal")]
)
def test_a_good_capture_is_protected_first_where_it_can_be(
    session, sent, seal_mode, after
):
    s = _setup(session, seal_mode=seal_mode)
    s.policy.storage_protects = True
    capture = jobs.queue_run(session, s.policy, s.host.id, "capture")
    results.record_result(session, s.host.id, _result(capture, snapshot="s1"))
    assert [p["action"] for _h, _c, p in sent][-1] == "protect"
    protect = session.query(models.BackupRun).filter_by(action="protect").one()
    assert protect.host_id == s.nas.id
    sent.clear()
    results.record_result(session, s.nas.id, _result(protect, "ok"))
    assert [p["action"] for _h, _c, p in sent] == [after]


def test_a_failed_protect_still_seals(session, sent, caplog):
    s = _setup(session, seal_mode="zfs_snapshot")
    s.policy.storage_protects = True
    protect = jobs.queue_run(session, s.policy, s.nas.id, "protect")
    sent.clear()
    results.record_result(
        session, s.nas.id, _result(protect, "failed", errors=["chown: EPERM"])
    )
    assert [p["action"] for _h, _c, p in sent] == ["seal"]
    assert "can still change or remove" in caplog.text


def test_without_protect_the_chain_is_unchanged(session, sent):
    s = _setup(session)
    capture = jobs.queue_run(session, s.policy, s.host.id, "capture")
    results.record_result(session, s.host.id, _result(capture, snapshot="s1"))
    assert [p["action"] for _h, _c, p in sent][-1] == "prune"


def test_the_host_reports_its_present_quiesce_hooks(session, sent):
    s = _setup(session)
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    results.record_command_result(session, {
        "command_id": run.command_id, "success": True,
        "result": {"installed": ["capture"], "hooks": ["lxd", "docker", "rm -rf /"]},
    })  # fmt: skip
    assert json.loads(s.policy.available_hooks) == ["docker", "lxd"]
    assert views.policy_dict(s.policy)["available_hooks"] == ["docker", "lxd"]


def test_new_storage_job_files_re_protect_without_sealing(session, sent):
    # restate 2.1.0.2 changed how protect protects on ZFS/FreeBSD; a capture
    # cannot run against the old form, so protect once on new job files.
    s = _setup(session, seal_mode="zfs_snapshot")
    session.add(models.BackupSnapshot(
        id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id,
        name="20261020T010000Z", signed=False, seen_at=datetime(2026, 10, 20),
    ))  # fmt: skip
    session.commit()
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    results.record_command_result(session, {
        "command_id": run.command_id, "success": True,
        "result": {"installed": ["check", "prune", "protect"]},
    })  # fmt: skip
    assert [p.get("action") for _h, _c, p in sent][-1] == "protect"
    protect = session.query(models.BackupRun).filter_by(action="protect").one()
    sent.clear()
    results.record_result(session, s.nas.id, _result(protect, "ok"))
    assert sent == []  # no seal, no prune: nothing was captured


def test_no_protect_before_the_first_capture_made_the_repository(session, sent):
    """Production, ubiquiti, 2026-10-25: protect on new job files ran before
    the host's first backup and restate said "not a restate repository"."""
    s = _setup(session)
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    results.record_command_result(session, {
        "command_id": run.command_id, "success": True,
        "result": {"installed": ["check", "prune", "protect"]},
    })  # fmt: skip
    assert "protect" not in [p.get("action") for _h, _c, p in sent]


def test_a_storage_host_without_protect_is_not_asked_to(session, sent):
    s = _setup(session)
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    results.record_command_result(session, {
        "command_id": run.command_id, "success": True,
        "result": {"installed": ["check", "prune"]},
    })  # fmt: skip
    assert "protect" not in [p.get("action") for _h, _c, p in sent]


def test_the_seal_job_carries_how_long_seals_are_kept(session, sent):
    s = _setup(session, seal_mode="zfs_snapshot")
    assert jobs.seal_job(s.target)["keep_days"] == jobs.DEFAULT_SEAL_KEEP_DAYS
    s.target.seal_keep_days = 30
    assert jobs.seal_job(s.target) == {
        "mode": "zfs_snapshot",
        "dataset": "tank/backups",
        "keep_days": 30,
    }
    s.target.seal_mode = "none"
    assert jobs.seal_job(s.target) == {"mode": "none"}
