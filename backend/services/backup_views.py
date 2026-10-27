# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""What the Backups page shows (ROADMAP Phase 24): serialized rows, each
host's backup status and coverage, and the target's warnings.

Status, worst first: ``not_equipped`` (the agent cannot run restate, with
its reason), ``running`` (a capture is in progress -- it outranks how the
previous one ended, which is still in ``last_capture``), ``failed`` (the
last capture failed or was untrusted),
``overdue`` (no good capture for twice the interval), ``incomplete`` (the
last capture skipped unreadable files), ``never``, ``ok``; and ``disabled``
or ``no_policy``.  A keyless ``check`` is ``metadata_only``: it proves the
repository's structure, not its content, and is never shown as "verified".
"""

import json
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import backup_equip
from backend.services import backup_first_fit as first_fit
from backend.services import backup_jobs as jobs
from backend.services import backup_storage_audit as storage_audit
from backend.services import backup_storage_health as storage_health
from backend.services import backup_storage_status as storage_status
from backend.services import backup_tick

OVERDUE_GRACE = timedelta(hours=1)
FULL_COVERAGE = ("ubuntu", "debian")
UNSUPPORTED = ("windows", "macos", "darwin")


def iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _json(text: Optional[str]) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def coverage(host: models.Host) -> str:
    """``full`` (files plus the package baseline restate restores from),
    ``files_only``, or ``unsupported`` (restate has no driver there)."""
    platform = (host.platform or "").lower()
    if platform in UNSUPPORTED:
        return "unsupported"
    release = (host.platform_release or "").lower()
    if release.startswith(FULL_COVERAGE):
        return "full"
    return "files_only"


def target_dict(target: models.BackupTarget, db: Session) -> Dict[str, Any]:
    storage = jobs.storage_host(db, target)
    ready, reason = jobs.equipped(storage) if storage else (False, "no_storage_host")
    status = storage_status.storage_status(db, target) if ready else None
    health = storage_health.storage_health(db, target, storage)
    warnings = storage_status.target_warnings(target, storage, ready, status, health)
    audit = storage_audit.summarize(db, target)
    warnings += storage_audit.warnings(audit)
    return {
        "id": str(target.id),
        "name": target.name,
        "host_mount_point": target.host_mount_point,
        "storage_host_id": (
            str(target.storage_host_id) if target.storage_host_id else None
        ),
        "storage_hostname": storage.fqdn if storage else None,
        "storage_path": target.storage_path,
        "storage_reason": None if ready else reason,
        "max_concurrent": target.max_concurrent,
        "seal_mode": target.seal_mode or "none",
        "zfs_dataset": target.zfs_dataset,
        "btrfs_snapshot_dir": target.btrfs_snapshot_dir,
        "seal_keep_days": jobs.seal_keep_days(target),
        "cache_budget_gb": jobs.cache_budget_gb(target),
        "space_low_percent": storage_health.space_thresholds(target)[0],
        "space_critical_percent": storage_health.space_thresholds(target)[1],
        "storage_fs": {
            "type": target.storage_fs_type,
            "mount_point": target.storage_fs_mount,
            "btrfs_subvolume": target.storage_is_btrfs_subvolume,
            "checked_at": iso(target.storage_fs_checked_at),
        },
        "storage_status": status,
        "storage_health": health,
        "storage_audit": audit,
        "service_account": target.service_account or jobs.DEFAULT_SERVICE_ACCOUNT,
        "warnings": warnings,
        "problem": storage_status.has_problem(warnings)
        or storage_audit.has_error(audit),
        "created_at": iso(target.created_at),
        "updated_at": iso(target.updated_at),
    }


def policy_dict(policy: models.BackupPolicy) -> Dict[str, Any]:
    return {
        "id": str(policy.id),
        "host_id": str(policy.host_id),
        "target_id": str(policy.target_id),
        "enabled": bool(policy.enabled),
        "interval_hours": policy.interval_hours,
        "window_start_hour": policy.window_start_hour,
        "keep_last": policy.keep_last,
        "check_interval_days": policy.check_interval_days,
        "quiesce": bool(policy.quiesce),
        "quiesce_with": jobs.quiesce_names(policy),
        "abilities": jobs.abilities(policy),
        # None: not reported yet (older agent or restate) -- names are typed.
        "available_hooks": (
            json.loads(policy.available_hooks) if policy.available_hooks else None
        ),
        "keep_paths": jobs.path_rules(policy).get("keep_paths", []),
        "skip_paths": jobs.path_rules(policy).get("skip_paths", []),
        "estimate_bytes": policy.estimate_bytes,
        "repository_bytes": policy.repository_bytes,
        "config_version": policy.config_version,
        "configured": policy.host_acked_version >= policy.config_version,
        "storage_configured": policy.storage_acked_version >= policy.config_version,
        "restate_version": policy.restate_version,
        "storage_restate_version": policy.storage_restate_version,
        # Pro+ backup_engine: the current repository's key (never the secret
        # key) and the plain repository it replaced, still restorable.
        "encryption": (
            {
                "fingerprint": policy.encrypt_fingerprint,
                "since": iso(policy.encrypted_at),
                "previous_repository": policy.previous_repository_dir,
            }
            if jobs.encrypted(policy)
            else None
        ),
    }


def check_label(run: models.BackupRun) -> Optional[str]:
    """``verified`` only for a full read; a keyless check is metadata-only."""
    if run.action != "check" or run.status not in ("ok", "different"):
        return None
    result = _json(run.result) or {}
    if result.get("metadata_only") or not result.get("read_all"):
        return "metadata_check_passed" if run.status == "ok" else "metadata_changed"
    return "verified" if run.status == "ok" else "changed"


def run_dict(run: models.BackupRun) -> Dict[str, Any]:
    return {
        "id": str(run.id),
        "policy_id": str(run.policy_id),
        "host_id": str(run.host_id),
        "action": run.action,
        "status": run.status,
        "exit_code": run.exit_code,
        "queued_at": iso(run.queued_at),
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
        "snapshot": run.snapshot,
        "message": run.message,
        "restate_version": run.restate_version,
        "requested_by": run.requested_by,
        "progress": _json(run.progress),
        "result": _json(run.result),
        "check_label": check_label(run),
        "parameters": _json(run.parameters),
    }


def snapshot_dict(row: models.BackupSnapshot) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "created_at": iso(row.created_at),
        "bytes": row.bytes,
        "new_bytes": row.new_bytes,
        "unique_bytes": row.unique_bytes,
        "files": row.files,
        "signed": bool(row.signed),
        "seen_at": iso(row.seen_at),
        "gone_at": iso(row.gone_at),
    }


def _status(db: Session, policy, last_capture, now) -> str:
    good = jobs.latest_run(db, policy.id, "capture", statuses=jobs.GOOD_CAPTURE)
    if last_capture is None:
        return "never"
    if last_capture.status in ("failed", "untrusted"):
        return "failed"
    if good is not None:
        ended = good.finished_at or good.queued_at
        if ended + timedelta(hours=2 * policy.interval_hours) + OVERDUE_GRACE < now:
            return "overdue"
        if last_capture.status == "incomplete":
            return "incomplete"
        return "ok"
    return "overdue" if last_capture.status == "busy" else "never"


def _running(db: Session, policy: models.BackupPolicy):
    """The policy's newest queued or running job, if any."""
    return (
        db.query(models.BackupRun)
        .filter(
            models.BackupRun.policy_id == policy.id,
            models.BackupRun.status.in_(jobs.PENDING),
        )
        .order_by(models.BackupRun.queued_at.desc())
        .first()
    )


def _recent_runs(db: Session, policy, last_capture, running) -> Dict[str, Any]:
    """The last capture, last good capture, last check and running job."""
    good = jobs.latest_run(db, policy.id, "capture", statuses=jobs.GOOD_CAPTURE)
    last_check = jobs.latest_run(db, policy.id, "check", statuses=jobs.FINAL)
    found = {
        "last_capture": last_capture,
        "last_good_capture": good,
        "last_check": last_check,
        "running": running,
    }
    return {key: run_dict(run) if run else None for key, run in found.items()}


def host_status(db: Session, host: models.Host, now=None) -> Dict[str, Any]:
    """One host's backup summary, for the hosts table and the Info tab."""
    now = now or jobs.now()
    ready, reason = jobs.equipped(host)
    policy = (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.host_id == host.id)
        .first()
    )
    entry: Dict[str, Any] = {
        "host_id": str(host.id),
        "fqdn": host.fqdn,
        "platform": host.platform,
        "platform_release": host.platform_release,
        "equipped": ready,
        "reason": reason,
        # Equip for backup: the latest attempt, and why it cannot start now
        # (None when it can) -- see services/backup_equip.py.
        "equip": backup_equip.state(db, host.id, now),
        "equip_blocker": backup_equip.blocker(db, host, now),
        "coverage": coverage(host),
        "policy": policy_dict(policy) if policy else None,
        "last_capture": None,
        "last_good_capture": None,
        "last_check": None,
        "running": None,
        "capture_requested": False,
        "next_due": None,
        "snapshot_count": 0,
        "first_fit": None,
    }
    if policy is None:
        entry["status"] = "no_policy" if ready else "not_equipped"
        return entry
    last_capture = jobs.latest_run(db, policy.id, "capture", statuses=jobs.FINAL)
    running = _running(db, policy)
    entry.update(_recent_runs(db, policy, last_capture, running))
    # A bulk "Back up now" waiting for a free slot under the target's cap.
    entry["capture_requested"] = policy.capture_requested_at is not None
    due = backup_tick.capture_due_at(db, policy)
    capturing = running is not None and running.action == "capture"
    entry["next_due"] = iso(due or now) if policy.enabled and not capturing else None
    entry["snapshot_count"] = (
        db.query(models.BackupSnapshot)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.gone_at.is_(None),
        )
        .count()
    )
    entry["first_fit"] = first_fit.fit(db, policy, jobs.the_target(db))
    if not ready:
        entry["status"] = "not_equipped"
    elif capturing:
        entry["status"] = "running"
    elif not policy.enabled:
        entry["status"] = "disabled"
    else:
        entry["status"] = _status(db, policy, last_capture, now)
    return entry


def overview(db: Session) -> Dict[str, Any]:
    target = jobs.the_target(db)
    hosts = (
        db.query(models.Host)
        .filter(models.Host.approval_status == "approved")
        .order_by(models.Host.fqdn)
        .all()
    )
    rows: List[Dict[str, Any]] = [host_status(db, host) for host in hosts]
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    versions = sorted(
        {
            version
            for row in rows
            if row["policy"]
            for version in (
                row["policy"]["restate_version"],
                row["policy"]["storage_restate_version"],
            )
            if version
        }
    )
    return {
        "target": target_dict(target, db) if target else None,
        "hosts": rows,
        "counts": counts,
        "restate_versions": versions,
    }


# Host statuses the dashboard flags: no good backup in time, a run that
# ended incomplete (files it could not read, a service it could not pause),
# or a failed one.
ATTENTION_STATUSES = ("overdue", "incomplete", "failed")


def target_problem(data: Dict[str, Any]) -> bool:
    """The target's storage side is broken: no storage host, stale seal /
    prune / check, a failed drive or critically full storage."""
    target = data["target"]
    return bool(target and target["problem"])


def attention_count(data: Dict[str, Any]) -> int:
    """What the dashboard flags: hosts in ATTENTION_STATUSES, plus the
    target once when its storage side is broken."""
    hosts = sum(data["counts"].get(s, 0) for s in ATTENTION_STATUSES)
    # A host whose first backup would not fit is held: it needs a look too.
    held = sum(
        1
        for row in data["hosts"]
        if row["status"] not in ATTENTION_STATUSES
        and row.get("first_fit")
        and not row["first_fit"]["fits"]
    )
    return hosts + held + int(target_problem(data))
