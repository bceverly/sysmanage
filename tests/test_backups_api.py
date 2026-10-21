# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The Backups API (Phase 24): roles, the one-target rule, policy versioning,
back up now, and restores that only ever stage -- with an explicit
acknowledgment for an unsigned snapshot."""

import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import backups as api
from backend.persistence import models
from backend.security.roles import SecurityRoles
from backend.services import backup_jobs as jobs
from backend.services import backup_results as results
from backend.services import backup_tick as tick
from backend.services import backup_views as views
from tests.services.test_backup_results import _host, _setup


def _user(*roles):
    return SimpleNamespace(
        id=uuid.uuid4(), userid="ops@example.com", has_role=lambda r: r in roles
    )


MANAGER = _user(SecurityRoles.MANAGE_BACKUPS)
RESTORER = _user(SecurityRoles.MANAGE_BACKUPS, SecurityRoles.RESTORE_FILES)
NOBODY = _user()


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


def _target_body(**extra):
    return api.TargetBody(name="nas", host_mount_point="/mnt/backups", **extra)


async def _status(coro):
    with pytest.raises(HTTPException) as caught:
        await coro
    return caught.value.status_code


@pytest.mark.asyncio
async def test_targets_need_the_role_and_community_has_one(session):
    assert await _status(api.create_target(_target_body(), session, NOBODY)) == 403
    made = await api.create_target(_target_body(), session, MANAGER)
    assert made["warnings"] == ["no_storage_host", "not_sealed"]
    assert made["problem"] is True
    assert await _status(api.create_target(_target_body(), session, MANAGER)) == 409
    audit = session.query(models.AuditLog).all()
    assert any("Backup target created" in a.description for a in audit)


def _btrfs(
    nas_id, storage_path="/srv/backups/restate", snapshot_dir="/srv/backups/.snapshots"
):
    return _target_body(
        storage_host_id=nas_id, storage_path=storage_path,
        seal_mode="btrfs_snapshot", btrfs_snapshot_dir=snapshot_dir,
    )  # fmt: skip


def _bad_btrfs_bodies(nas_id):
    return (
        _btrfs(nas_id, snapshot_dir=None),  # needs the snapshot directory
        _btrfs(nas_id, snapshot_dir="snapshots"),  # relative
        _btrfs(nas_id, snapshot_dir="/srv/backups/restate"),  # the subvolume
        _btrfs(nas_id, snapshot_dir="/srv/backups/restate/.snap"),  # inside it
        _btrfs(nas_id, snapshot_dir="/srv/../etc"),
        _btrfs(nas_id, snapshot_dir="/srv/snaps/"),  # not normalized
        _btrfs(nas_id, snapshot_dir="/srv/-r"),  # an option to btrfs
        _btrfs(nas_id, snapshot_dir="/srv/snap shots"),
        _btrfs(nas_id, storage_path="/srv/back ups"),
        _btrfs(nas_id, snapshot_dir="/"),
    )


@pytest.mark.asyncio
async def test_a_btrfs_target_is_accepted_and_sends_its_seal(session):
    nas = _host(session, fqdn="nas.lab")
    made = await api.create_target(_btrfs(str(nas.id)), session, MANAGER)
    assert made["seal_mode"] == "btrfs_snapshot"
    assert made["btrfs_snapshot_dir"] == "/srv/backups/.snapshots"
    target = session.query(models.BackupTarget).one()
    assert jobs.seal_job(target) == {
        "mode": "btrfs_snapshot",
        "subvolume": "/srv/backups/restate",
        "snapshot_dir": "/srv/backups/.snapshots",
    }


def test_the_seal_job_for_each_mode():
    zfs = SimpleNamespace(seal_mode="zfs_snapshot", zfs_dataset="tank/b")
    assert jobs.seal_job(zfs) == {"mode": "zfs_snapshot", "dataset": "tank/b"}
    assert jobs.seal_job(SimpleNamespace(seal_mode=None)) == {"mode": "none"}


@pytest.mark.asyncio
async def test_moving_the_storage_path_forgets_the_filesystem(session):
    s = _setup(session)
    s.target.storage_fs_type = "ext4"
    s.target.storage_fs_checked_at = jobs.now()
    session.commit()
    same = _target_body(
        storage_host_id=str(s.nas.id), storage_path="/srv/backups/restate"
    )
    await api.update_target(str(s.target.id), same, session, MANAGER)
    assert s.target.storage_fs_type == "ext4"
    moved = _target_body(storage_host_id=str(s.nas.id), storage_path="/srv/new")
    await api.update_target(str(s.target.id), moved, session, MANAGER)
    assert s.target.storage_fs_type is None and s.target.storage_fs_checked_at is None


@pytest.mark.asyncio
async def test_target_validation(session):
    nas = _host(session, fqdn="nas.lab")
    for body in (
        api.TargetBody(name="n", host_mount_point="relative"),
        api.TargetBody(name="n", host_mount_point="/mnt/../etc"),
        _target_body(seal_mode="btrfs"),
        _target_body(seal_mode="zfs_snapshot"),
        _target_body(max_concurrent=0),
        _target_body(storage_host_id=str(nas.id)),  # no storage path
        *_bad_btrfs_bodies(str(nas.id)),
    ):
        assert await _status(api.create_target(body, session, MANAGER)) == 422
    sealed = await api.create_target(
        _target_body(
            storage_host_id=str(nas.id), storage_path="/srv/b",
            seal_mode="zfs_snapshot", zfs_dataset="tank/b",
        ),
        session, MANAGER,
    )  # fmt: skip
    assert sealed["warnings"] == ["fs_unchecked"]
    assert sealed["storage_hostname"] == "nas.lab" and sealed["problem"] is False


@pytest.mark.asyncio
async def test_changing_the_target_resends_every_hosts_job_files(session):
    s = _setup(session)
    body = _target_body(storage_host_id=str(s.nas.id), storage_path="/srv/new")
    await api.update_target(str(s.target.id), body, session, MANAGER)
    assert s.policy.config_version == 2
    assert await _status(api.delete_target(str(s.target.id), session, MANAGER)) == 409


@pytest.mark.asyncio
async def test_a_policy_needs_a_target_and_bumps_its_version(session):
    host = _host(session)
    body = api.PolicyBody(interval_hours=12, quiesce_with=["postgres"])
    assert await _status(api.put_policy(str(host.id), body, session, MANAGER)) == 409
    await api.create_target(_target_body(), session, MANAGER)
    made = await api.put_policy(str(host.id), body, session, MANAGER)
    assert (made["config_version"], made["configured"]) == (1, False)
    again = await api.put_policy(str(host.id), body, session, MANAGER)
    assert again["config_version"] == 2 and again["quiesce_with"] == ["postgres"]
    for bad in (
        api.PolicyBody(interval_hours=0),
        api.PolicyBody(window_start_hour=24),
        api.PolicyBody(keep_last=0),
        api.PolicyBody(check_interval_days=91),
        api.PolicyBody(quiesce_with=["Bad Name"]),
    ):
        assert await _status(api.put_policy(str(host.id), bad, session, MANAGER)) == 422
    assert await _status(api.put_policy(str(host.id), body, session, NOBODY)) == 403


@pytest.mark.asyncio
async def test_path_rules_reach_the_hosts_capture_and_estimate(session, sent):
    s = _setup(session)
    body = api.PolicyBody(
        keep_paths=["/home/*/Downloads"], skip_paths=["**/previews", "/var/tmp"]
    )
    saved = await api.put_policy(str(s.host.id), body, session, MANAGER)
    assert saved["keep_paths"] == ["/home/*/Downloads"]
    assert saved["skip_paths"] == ["**/previews", "/var/tmp"]
    config = jobs.host_configuration(s.policy, s.target, s.host)
    for action in ("capture", "estimate"):
        assert config["jobs"][action]["keep_paths"] == ["/home/*/Downloads"]
        assert config["jobs"][action]["skip_paths"] == ["**/previews", "/var/tmp"]
    cleared = await api.put_policy(str(s.host.id), api.PolicyBody(), session, MANAGER)
    assert cleared["keep_paths"] == [] and cleared["skip_paths"] == []
    config = jobs.host_configuration(s.policy, s.target, s.host)
    assert "skip_paths" not in config["jobs"]["capture"]
    assert config["jobs"]["estimate"] == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pattern",
    ["", " /lead", "/trail ", "/a\nstate /etc", "#x", "x" * 513],
    ids=["empty", "leading", "trailing", "newline", "comment", "too-long"],
)
async def test_a_path_rule_that_could_break_the_rules_file_is_refused(session, pattern):
    s = _setup(session)
    body = api.PolicyBody(skip_paths=[pattern])
    assert await _status(api.put_policy(str(s.host.id), body, session, MANAGER)) == 422


@pytest.mark.asyncio
async def test_saving_a_policy_sends_its_job_files_at_once(session, sent):
    # Not on the next five-minute tick, and even with no schedule: "Back up
    # now" needs the job files (24.0 lab, 2026-10-20).
    s = _setup(session)
    body = api.PolicyBody(enabled=False)
    await api.put_policy(str(s.host.id), body, session, MANAGER)
    configured = sorted((h, p["role"]) for h, c, p in sent if c == "backup_configure")
    assert configured == sorted([(str(s.host.id), "host"), (str(s.nas.id), "storage")])
    assert not [c for _h, c, p in sent if c == "backup_run"]


@pytest.mark.asyncio
async def test_backup_now(session, sent):
    s = _setup(session)
    run = await api.backup_now(str(s.host.id), None, session, MANAGER)
    assert run["action"] == "capture" and sent[0][0] == str(s.host.id)
    assert await _status(api.backup_now(str(s.host.id), None, session, MANAGER)) == 409
    check = await api.backup_now(
        str(s.host.id), api.RunBody(action="check"), session, MANAGER
    )
    assert check["host_id"] == str(s.nas.id)
    assert await _status(
        api.backup_now(str(s.host.id), api.RunBody(action="prune"), session, MANAGER)
    ) == 422  # fmt: skip
    s.host.agent_capabilities = None
    assert await _status(api.backup_now(str(s.host.id), None, session, MANAGER)) == 409


@pytest.mark.asyncio
async def test_restore_stages_and_needs_the_unsigned_acknowledgment(session, sent):
    s = _setup(session)
    session.add(models.BackupSnapshot(
        id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id,
        name="2026-10-20T010000Z", signed=False, seen_at=datetime(2026, 10, 20),
    ))  # fmt: skip
    session.commit()
    body = api.RestoreBody(snapshot="2026-10-20T010000Z", include=["/etc/nginx"])
    assert (
        await _status(api.backup_restore(str(s.host.id), body, session, MANAGER)) == 403
    )
    assert (
        await _status(api.backup_restore(str(s.host.id), body, session, RESTORER))
        == 409
    )
    body.acknowledge_unsigned = True
    out = await api.backup_restore(str(s.host.id), body, session, RESTORER)
    _, command, params = sent[-1]
    assert command == "backup_restore"
    assert params["dry_run"] is True and params["allow_unverified"] is True
    assert params["include"] == ["/etc/nginx"]
    assert out["staging_path"] == f"/var/lib/sysmanage-agent/restore/{out['id']}"
    for bad in (
        api.RestoreBody(snapshot="../x", acknowledge_unsigned=True),
        api.RestoreBody(snapshot="ok", include=["/a/../b"], acknowledge_unsigned=True),
        api.RestoreBody(snapshot="ok", include=["/a"] * 51, acknowledge_unsigned=True),
    ):
        assert (
            await _status(api.backup_restore(str(s.host.id), bad, session, RESTORER))
            == 422
        )
    missing = api.RestoreBody(snapshot="nope", acknowledge_unsigned=True)
    assert (
        await _status(api.backup_restore(str(s.host.id), missing, session, RESTORER))
        == 404
    )


@pytest.mark.asyncio
async def test_runs_are_paginated_and_overview_counts(session, sent):
    s = _setup(session)
    for _ in range(3):
        run = jobs.queue_run(session, s.policy, s.host.id, "estimate")
        run.status = "ok"
    session.commit()
    page = await api.list_runs(str(s.host.id), None, 2, 0, session)
    assert page["total"] == 3 and len(page["runs"]) == 2
    overview = await api.backups_overview(session)
    rows = {r["host_id"]: r for r in overview["hosts"]}
    assert rows[str(s.host.id)]["status"] == "never"
    assert rows[str(s.nas.id)]["status"] == "no_policy"
    summary = await api.backups_summary(session)
    assert summary["configured"] is True and summary["attention"] == 0
    s.target.storage_host_id = None  # no storage host: one problem
    session.commit()
    assert (await api.backups_summary(session))["attention"] == 1


def _capture(session, s, status, ago_hours):
    at = jobs.now() - timedelta(hours=ago_hours)
    session.add(models.BackupRun(
        id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id, action="capture",
        status=status, queued_at=at, finished_at=at, restate_version="2.0.0.0",
    ))  # fmt: skip
    session.commit()


@pytest.mark.parametrize(
    "history, expected",
    [
        ([("ok", 1)], "ok"),
        ([("incomplete", 1)], "incomplete"),
        ([("ok", 60)], "overdue"),
        ([("ok", 2), ("failed", 1)], "failed"),
        ([("ok", 2), ("busy", 1)], "ok"),
    ],
)
def test_host_status_words(session, history, expected):
    s = _setup(session)
    for status, ago in history:
        _capture(session, s, status, ago)
    assert views.host_status(session, s.host)["status"] == expected


def test_a_running_capture_outranks_the_last_failure(session):
    # Lab 2026-10-20: the page said "Failed" while a capture was running,
    # and "Last backup" showed when the failed run ended.
    s = _setup(session)
    _capture(session, s, "ok", 30)
    _capture(session, s, "failed", 2)
    entry = views.host_status(session, s.host)
    assert entry["status"] == "failed"
    assert entry["last_capture"]["status"] == "failed"
    assert entry["last_good_capture"]["status"] == "ok"
    jobs.queue_run(session, s.policy, s.host.id, "capture")
    session.commit()
    entry = views.host_status(session, s.host)
    assert entry["status"] == "running" and entry["next_due"] is None
    assert entry["last_capture"]["status"] == "failed"  # still reported


def test_never_backed_up_has_no_last_good_capture(session):
    s = _setup(session)
    _capture(session, s, "failed", 1)
    assert views.host_status(session, s.host)["last_good_capture"] is None


def test_status_not_equipped_and_coverage(session):
    s = _setup(session)
    s.host.agent_capabilities = json.dumps(
        {"capabilities": [], "unavailable": {"backup": "missing_tool"}}
    )
    entry = views.host_status(session, s.host)
    assert (entry["status"], entry["reason"]) == ("not_equipped", "missing_tool")
    assert (
        views.coverage(
            SimpleNamespace(platform="Linux", platform_release="Ubuntu 26.04")
        )
        == "full"
    )
    assert (
        views.coverage(SimpleNamespace(platform="FreeBSD", platform_release="14.3"))
        == "files_only"
    )
    assert (
        views.coverage(SimpleNamespace(platform="Windows", platform_release="11"))
        == "unsupported"
    )


def test_a_keyless_check_is_never_verified():
    def run(status, result):
        return SimpleNamespace(action="check", status=status, result=json.dumps(result))

    assert (
        views.check_label(run("ok", {"metadata_only": True})) == "metadata_check_passed"
    )
    assert views.check_label(run("ok", {"read_all": True})) == "verified"
    assert views.check_label(run("different", {"read_all": True})) == "changed"
    assert views.check_label(run("failed", {})) is None


# ---------------------------------------------------------------------------
# bulk "Back up now": requests drain under the target's concurrency cap
# ---------------------------------------------------------------------------


def _another_policy(session, s, fqdn):
    host = _host(session, fqdn=fqdn)
    policy = models.BackupPolicy(
        id=uuid.uuid4(), host_id=host.id, target_id=s.target.id, enabled=True,
        interval_hours=24, keep_last=14, check_interval_days=7, quiesce=False,
        config_version=1, host_acked_version=1, storage_acked_version=1,
        created_at=s.policy.created_at, updated_at=s.policy.updated_at,
    )  # fmt: skip
    session.add(policy)
    session.commit()
    return host, policy


def _captures_sent(sent):
    return [h for h, c, p in sent if c == "backup_run" and p.get("action") == "capture"]


@pytest.mark.asyncio
async def test_bulk_backup_now_starts_up_to_the_cap_and_queues_the_rest(session, sent):

    s = _setup(session)  # max_concurrent=2
    h2, _p2 = _another_policy(session, s, "two.lab")
    h3, p3 = _another_policy(session, s, "three.lab")
    bare = _host(session, fqdn="bare.lab")
    answer = await api.bulk_backup_now(
        api.BulkBackupBody(host_ids=[str(s.host.id), str(h2.id), str(h3.id),
                                     str(bare.id), "not-a-uuid", str(h2.id)]),
        session, MANAGER,
    )  # fmt: skip
    assert (answer["requested"], answer["started"], answer["waiting"]) == (3, 2, 1)
    assert {(x["fqdn"], x["reason"]) for x in answer["skipped"]} == {
        ("bare.lab", "no_policy"), (None, "no_host")
    }  # fmt: skip
    assert sorted(_captures_sent(sent)) == sorted([str(s.host.id), str(h2.id)])
    assert p3.capture_requested_at is not None
    assert views.host_status(session, h3)["capture_requested"] is True
    # the first capture ends: its slot goes to the waiting host
    first = (
        session.query(models.BackupRun)
        .filter_by(host_id=s.host.id, action="capture")
        .one()
    )
    results.record_result(session, s.host.id, {
        "run_id": str(first.id), "policy_id": str(first.policy_id),
        "action": "capture", "status": "failed", "exit": 2, "result": {},
    })  # fmt: skip
    assert str(h3.id) in _captures_sent(sent)
    assert p3.capture_requested_at is None


@pytest.mark.asyncio
async def test_bulk_backup_now_skips_a_running_host_and_needs_the_role(session, sent):
    s = _setup(session)
    jobs.queue_run(session, s.policy, s.host.id, "capture")
    session.commit()
    answer = await api.bulk_backup_now(
        api.BulkBackupBody(host_ids=[str(s.host.id)]), session, MANAGER
    )
    assert answer["requested"] == 0 and answer["skipped"][0]["reason"] == "running"
    body = api.BulkBackupBody(host_ids=[str(s.host.id)])
    assert await _status(api.bulk_backup_now(body, session, NOBODY)) == 403


def test_a_request_the_host_can_no_longer_run_is_dropped(session, sent, caplog):

    s = _setup(session)
    s.policy.capture_requested_at = jobs.now()
    s.host.approval_status = "pending"
    session.commit()
    assert tick.start_requested(session) == 0
    assert s.policy.capture_requested_at is None
    assert "can no longer run it" in caplog.text


# ---------------------------------------------------------------------------
# the job list: Clear hides finished runs; retention deletes old ones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_hides_finished_runs_but_keeps_pending_and_history(session, sent):
    s = _setup(session)
    _capture(session, s, "ok", 5)
    _capture(session, s, "failed", 2)
    jobs.queue_run(session, s.policy, s.host.id, "capture")  # still queued
    session.commit()
    answer = await api.clear_runs(session, MANAGER)
    assert answer == {"cleared": 2}
    listed = await api.list_runs(None, None, 50, 0, session)
    assert [r["status"] for r in listed["runs"]] == ["queued"]
    everything = await api.list_runs(None, None, 50, 0, session, include_cleared=True)
    assert everything["total"] == 3
    # history still drives the page: the last good capture is still known
    assert views.host_status(session, s.host)["last_good_capture"] is not None
    assert await _status(api.clear_runs(session, NOBODY)) == 403


def test_retention_deletes_old_runs_but_keeps_each_kinds_newest(session):
    s = _setup(session)
    for ago_days in (90, 60, 45):
        _capture(session, s, "ok", ago_days * 24)
    _capture(session, s, "failed", 50 * 24)  # the only failed one: kept
    _capture(session, s, "ok", 1)  # recent
    old_pending = jobs.queue_run(session, s.policy, s.host.id, "check")
    old_pending.queued_at = jobs.now() - timedelta(days=99)
    session.commit()
    removed = jobs.prune_run_history(session, jobs.now())
    session.commit()
    left = session.query(models.BackupRun).filter_by(action="capture").all()
    assert removed == 3  # the three old ok captures; the newest ok is recent
    assert sorted(r.status for r in left) == ["failed", "ok"]
    assert session.get(models.BackupRun, old_pending.id) is not None  # not final


@pytest.mark.asyncio
async def test_a_restores_staging_path_is_where_restate_put_it(session, sent):
    s = _setup(session)
    run = models.BackupRun(
        id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id, action=jobs.RESTORE,
        status="ok", queued_at=jobs.now(), finished_at=jobs.now(),
        result=json.dumps({"restore": {"root": "/home/me/dev/sysmanage-agent/restore/r1"}}),
    )  # fmt: skip
    session.add(run)
    session.commit()
    got = await api.get_run(str(run.id), session)
    assert got["staging_path"] == "/home/me/dev/sysmanage-agent/restore/r1"
    run.result = json.dumps({})  # an older result: the computed default
    session.commit()
    got = await api.get_run(str(run.id), session)
    assert got["staging_path"] == jobs.staging_dir(run.id)
