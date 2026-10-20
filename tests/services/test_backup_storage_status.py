# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The storage side of a backup target (24.4, 24.5, 24.8): every warning
the Backups page shows -- no storage host, one that cannot run restate, a
seal the filesystem cannot take, storage jobs falling behind -- and the
filesystem report a storage host's configure reply carries."""

import json
import uuid
from datetime import timedelta

import pytest

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_results as results
from backend.services import backup_storage_status as status
from backend.services import backup_views as views
from tests.services.test_backup_results import (  # noqa: F401  pylint: disable=unused-import
    _setup,
    sent,
)

# pylint: disable=redefined-outer-name


def _warnings(session, s):
    session.commit()
    return views.target_dict(s.target, session)["warnings"]


def _fs(s, fstype, subvolume=None):
    s.target.storage_fs_type = fstype
    s.target.storage_is_btrfs_subvolume = subvolume
    s.target.storage_fs_checked_at = jobs.now()


def _run(session, s, action, status_word="ok", ago_hours=0.0, host=None):
    at = jobs.now() - timedelta(hours=ago_hours)
    run = models.BackupRun(
        id=uuid.uuid4(), policy_id=s.policy.id,
        host_id=(host or (s.host if action == "capture" else s.nas)).id,
        action=action, status=status_word, queued_at=at, finished_at=at,
    )  # fmt: skip
    session.add(run)
    session.commit()
    return run


def test_no_storage_host_is_a_problem(session):
    s = _setup(session)
    s.target.storage_host_id = None
    found = views.target_dict(s.target, session)
    assert found["warnings"] == ["no_storage_host", "not_sealed"]
    assert found["problem"] is True and found["storage_status"] is None
    assert views.attention_count(views.overview(session)) == 1


def test_a_storage_host_that_cannot_run_restate(session):
    s = _setup(session)
    s.nas.agent_capabilities = json.dumps(
        {"capabilities": [], "unavailable": {"backup": "tool_outdated"}}
    )
    found = views.target_dict(s.target, session)
    assert found["warnings"][0] == "storage_not_equipped"
    assert found["storage_reason"] == "tool_outdated" and found["problem"] is True


def test_an_unchecked_filesystem_is_neutral(session):
    s = _setup(session, seal_mode="zfs_snapshot")
    found = views.target_dict(s.target, session)
    assert found["warnings"] == ["fs_unchecked"] and found["problem"] is False


@pytest.mark.parametrize("fstype", ["ext4", "xfs", "nfs4"])
def test_a_filesystem_that_cannot_snapshot_is_a_caution(session, fstype):
    s = _setup(session)
    _fs(s, fstype)
    found = views.target_dict(s.target, session)
    assert found["warnings"] == ["not_sealed", "fs_cannot_snapshot"]
    assert found["problem"] is False and found["storage_fs"]["type"] == fstype


def test_a_zfs_seal_on_ext4_is_an_error(session):
    s = _setup(session, seal_mode="zfs_snapshot")
    _fs(s, "ext4")
    assert _warnings(session, s) == ["seal_fs_mismatch", "fs_cannot_snapshot"]


def test_a_btrfs_seal_on_zfs_is_an_error(session):
    s = _setup(session, seal_mode="btrfs_snapshot")
    _fs(s, "zfs")
    assert _warnings(session, s) == ["seal_fs_mismatch"]


def test_a_btrfs_seal_needs_a_subvolume(session):
    s = _setup(session, seal_mode="btrfs_snapshot")
    _fs(s, "btrfs", subvolume=False)
    found = views.target_dict(s.target, session)
    assert found["warnings"] == ["btrfs_not_subvolume"] and found["problem"] is True
    _fs(s, "btrfs", subvolume=True)
    assert _warnings(session, s) == []


def test_zfs_on_zfs_is_clean_and_unsealed_zfs_only_says_not_sealed(session):
    s = _setup(session, seal_mode="zfs_snapshot")
    _fs(s, "zfs")
    assert _warnings(session, s) == []
    s.target.seal_mode = "none"
    assert _warnings(session, s) == ["not_sealed"]


def test_a_capture_with_no_seal_after_it_is_stale(session):
    s = _setup(session, seal_mode="zfs_snapshot")
    _fs(s, "zfs")
    capture = _run(session, s, "capture", ago_hours=0.5)
    assert "seal_stale" not in _warnings(session, s)  # still inside the grace
    capture.queued_at = capture.finished_at = jobs.now() - timedelta(hours=2)
    _run(session, s, "seal", ago_hours=3)  # before the capture
    found = views.target_dict(s.target, session)
    assert "seal_stale" in found["warnings"]
    assert found["storage_status"]["stale"]["seal_stale"] == [str(s.host.id)]
    _run(session, s, "seal", ago_hours=0.1)
    assert "seal_stale" not in _warnings(session, s)


def test_no_prune_for_twice_the_interval_is_stale(session):
    s = _setup(session)  # interval 24 hours
    _fs(s, "zfs")
    _run(session, s, "capture", ago_hours=40)
    assert "prune_stale" not in _warnings(session, s)
    _run(session, s, "capture", ago_hours=60)  # the first, 60 hours ago
    assert "prune_stale" in _warnings(session, s)
    _run(session, s, "prune", ago_hours=1)
    assert "prune_stale" not in _warnings(session, s)


def test_no_check_for_twice_the_check_interval_is_stale(session):
    s = _setup(session)  # check every 7 days
    _fs(s, "zfs")
    _run(session, s, "capture", ago_hours=1)
    _run(session, s, "prune", ago_hours=0.5)
    _run(session, s, "capture", ago_hours=24 * 15)
    _run(session, s, "check", ago_hours=24 * 15)
    found = views.target_dict(s.target, session)
    assert "check_stale" in found["warnings"] and found["problem"] is True
    _run(session, s, "check", "different", ago_hours=1)  # a check that ran
    assert "check_stale" not in _warnings(session, s)


def test_the_storage_status_counts_and_last_runs(session):
    s = _setup(session, storage_acked=0)
    _run(session, s, "prune", ago_hours=3)
    _run(session, s, "check", "failed", ago_hours=2)
    _run(session, s, "check", "ok", ago_hours=1, host=s.host)  # not the NAS
    found = status.storage_status(session, s.target)
    assert (found["policies"], found["confirmed"]) == (1, 0)
    assert found["last_seal"] is None
    assert found["last_prune"]["status"] == "ok"
    assert found["last_check"]["status"] == "failed"


def test_a_storage_configure_reply_records_the_filesystem(session, sent):
    s = _setup(session)
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    reply = {"storage_fs": {"type": "btrfs", "mount_point": "/srv",
                            "path": "/srv/backups/restate", "btrfs_subvolume": False}}  # fmt: skip
    results.record_command_result(
        session, {"command_id": run.command_id, "success": True, "result": reply}
    )
    target = s.target
    assert (target.storage_fs_type, target.storage_fs_mount) == ("btrfs", "/srv")
    assert target.storage_is_btrfs_subvolume is False
    assert target.storage_fs_checked_at is not None


def test_a_host_configure_reply_never_touches_the_filesystem(session, sent):
    s = _setup(session)
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    results.record_command_result(
        session,
        {"command_id": run.command_id, "success": True,
         "result": {"storage_fs": {"type": "ext4"}}},
    )  # fmt: skip
    assert s.target.storage_fs_type is None


@pytest.mark.parametrize("reply", [None, {}, {"storage_fs": "ext4"}, "junk"])
def test_an_agent_that_does_not_say_keeps_the_last_answer(reply):
    target = models.BackupTarget(storage_fs_type="zfs")
    status.record_storage_fs(target, reply)
    assert target.storage_fs_type == "zfs"


def test_unknown_values_are_stored_as_unknown():
    target = models.BackupTarget()
    status.record_storage_fs(
        target, {"storage_fs": {"type": None, "mount_point": 5, "btrfs_subvolume": "y"}}
    )
    assert target.storage_fs_type is None and target.storage_fs_mount is None
    assert target.storage_is_btrfs_subvolume is None
    assert target.storage_fs_checked_at is not None
