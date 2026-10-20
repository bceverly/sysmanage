# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The storage side of a backup target, as the Backups page shows it
(ROADMAP 24.4, 24.5, 24.8).

Hosts write append-only; sealing, pruning and checking happen on the
target's storage host.  Without one -- or with one whose agent cannot run
restate -- captures still land but are never sealed, pruned or checked, and
the repositories only grow.  That has to be loud, so the target carries
warning codes, worst first:

* ``no_storage_host``, ``storage_not_equipped`` -- storage jobs cannot run;
* ``seal_fs_mismatch``, ``btrfs_not_subvolume`` -- the seal mode cannot work
  on the filesystem the storage host reported, so every seal fails;
* ``seal_stale`` (a good capture with no seal after it),
  ``prune_stale`` (no prune for twice the capture interval),
  ``check_stale`` (no check for twice the check interval);
* ``not_sealed`` (seal mode none), ``fs_cannot_snapshot`` (the storage path
  is on a filesystem that cannot snapshot: it works, but cannot be sealed);
* ``fs_unchecked`` -- the storage host has not reported its filesystem yet.

``PROBLEMS`` are the ones that make the target count once on the
dashboard's "Backups overdue or failed" card.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import backup_jobs as jobs

SNAPSHOT_FILESYSTEMS = {"zfs_snapshot": "zfs", "btrfs_snapshot": "btrfs"}
# A seal is queued by the capture's own result, or by the next tick.
SEAL_GRACE = timedelta(hours=1)
PROBLEMS = (
    "no_storage_host",
    "storage_not_equipped",
    "seal_fs_mismatch",
    "btrfs_not_subvolume",
    "seal_stale",
    "prune_stale",
    "check_stale",
)
_STORAGE_FS_LIMITS = {"type": 64, "mount_point": 1024}


def iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _text(value: Any, limit: int) -> Optional[str]:
    return value[:limit] if isinstance(value, str) and value else None


def record_storage_fs(target: models.BackupTarget, reply: Any) -> None:
    """Keep what the storage host said about its filesystem (a storage
    ``backup_configure`` success).  An agent that does not say leaves the
    last answer alone."""
    report = reply.get("storage_fs") if isinstance(reply, dict) else None
    if not isinstance(report, dict):
        return
    target.storage_fs_type = _text(report.get("type"), _STORAGE_FS_LIMITS["type"])
    target.storage_fs_mount = _text(
        report.get("mount_point"), _STORAGE_FS_LIMITS["mount_point"]
    )
    subvolume = report.get("btrfs_subvolume")
    target.storage_is_btrfs_subvolume = (
        subvolume if isinstance(subvolume, bool) else None
    )
    target.storage_fs_checked_at = jobs.now()


def forget_storage_fs(target: models.BackupTarget) -> None:
    """The storage host or path changed: the old answer is about elsewhere."""
    target.storage_fs_type = None
    target.storage_fs_mount = None
    target.storage_is_btrfs_subvolume = None
    target.storage_fs_checked_at = None


def fs_warnings(target: models.BackupTarget) -> List[str]:
    """What the storage filesystem allows, against the seal mode."""
    fstype = (target.storage_fs_type or "").lower()
    if not fstype:
        return ["fs_unchecked"]
    found = []
    needed = SNAPSHOT_FILESYSTEMS.get(target.seal_mode or "none")
    if needed and fstype != needed:
        found.append("seal_fs_mismatch")
    elif needed == "btrfs" and target.storage_is_btrfs_subvolume is False:
        found.append("btrfs_not_subvolume")
    if fstype not in SNAPSHOT_FILESYSTEMS.values():
        found.append("fs_cannot_snapshot")
    return found


def _brief(run: Optional[models.BackupRun]) -> Optional[Dict[str, Any]]:
    if run is None:
        return None
    return {
        "status": run.status,
        "finished_at": iso(run.finished_at or run.queued_at),
        "message": run.message,
    }


def _last_on_storage(db: Session, target, action: str) -> Optional[models.BackupRun]:
    return (
        db.query(models.BackupRun)
        .filter(
            models.BackupRun.host_id == target.storage_host_id,
            models.BackupRun.action == action,
            models.BackupRun.status.in_(jobs.FINAL),
        )
        .order_by(models.BackupRun.queued_at.desc())
        .first()
    )


def _ended(run: Optional[models.BackupRun]) -> Optional[datetime]:
    return (run.finished_at or run.queued_at) if run else None


def _first_capture(db: Session, policy) -> Optional[datetime]:
    run = (
        db.query(models.BackupRun)
        .filter(
            models.BackupRun.policy_id == policy.id,
            models.BackupRun.action == "capture",
            models.BackupRun.status.in_(jobs.GOOD_CAPTURE),
        )
        .order_by(models.BackupRun.queued_at.asc())
        .first()
    )
    return _ended(run)


def _overdue(last: Optional[datetime], since: datetime, limit, now) -> bool:
    """Nothing within ``limit``, counting from ``since`` when it never ran."""
    return (last or since) + limit < now


def policy_staleness(db: Session, policy, sealing: bool, now: datetime) -> List[str]:
    """Which storage jobs this host's repository is behind on."""
    captured = _ended(jobs.latest_run(db, policy.id, "capture", jobs.GOOD_CAPTURE))
    if captured is None:
        return []
    stale = []
    sealed = _ended(jobs.latest_run(db, policy.id, "seal", ("ok",)))
    if (
        sealing
        and (sealed is None or sealed < captured)
        and captured + SEAL_GRACE < now
    ):
        stale.append("seal_stale")
    first = _first_capture(db, policy) or captured
    pruned = _ended(jobs.latest_run(db, policy.id, "prune", ("ok",)))
    if _overdue(pruned, first, timedelta(hours=2 * policy.interval_hours), now):
        stale.append("prune_stale")
    checked = _ended(jobs.latest_run(db, policy.id, "check", ("ok", "different")))
    if _overdue(checked, first, timedelta(days=2 * policy.check_interval_days), now):
        stale.append("check_stale")
    return stale


def storage_status(
    db: Session, target: models.BackupTarget, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """Job files confirmed, the last seal/prune/check on the storage host,
    and which hosts' repositories are behind."""
    now = now or jobs.now()
    policies = (
        db.query(models.BackupPolicy)
        .filter(
            models.BackupPolicy.target_id == target.id,
            models.BackupPolicy.enabled.is_(True),
        )
        .all()
    )
    sealing = (target.seal_mode or "none") != "none"
    stale: Dict[str, List[str]] = {
        "seal_stale": [],
        "prune_stale": [],
        "check_stale": [],
    }
    confirmed = 0
    for policy in policies:
        confirmed += int(policy.storage_acked_version >= policy.config_version)
        for code in policy_staleness(db, policy, sealing, now):
            stale[code].append(str(policy.host_id))
    last = {
        action: _brief(_last_on_storage(db, target, action))
        for action in jobs.STORAGE_ACTIONS
    }
    return {
        "policies": len(policies),
        "confirmed": confirmed,
        "last_seal": last["seal"],
        "last_prune": last["prune"],
        "last_check": last["check"],
        "stale": stale,
    }


def target_warnings(
    target: models.BackupTarget,
    storage: Optional[models.Host],
    ready: bool,
    status: Optional[Dict[str, Any]],
) -> List[str]:
    """Every warning code for the target, worst first."""
    if storage is None:
        found = ["no_storage_host"]
    elif not ready:
        found = ["storage_not_equipped"]
    else:
        found = []
    fs = fs_warnings(target) if storage is not None else []
    found += [w for w in fs if w in ("seal_fs_mismatch", "btrfs_not_subvolume")]
    if status is not None:
        found += [code for code, hosts in status["stale"].items() if hosts]
    if (target.seal_mode or "none") == "none":
        found.append("not_sealed")
    found += [w for w in fs if w in ("fs_cannot_snapshot", "fs_unchecked")]
    return found


def has_problem(warnings: List[str]) -> bool:
    return any(code in PROBLEMS for code in warnings)
