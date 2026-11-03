# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""What the Backups page and the dashboard show for iCloud Photos (24.12).

Never a password: an account says only whether one is set and when.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import cloud_backup_jobs as cloud
from backend.services import cloud_backup_tick as tick
from backend.services.agent_capability_service import get_capability_report

ENABLE_GROUP = "cloud_backup_enable"
RUN_LIMIT = 50


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def run_dict(run: models.CloudBackupRun) -> Dict[str, Any]:
    result = cloud.parse_json(run.result) or {}
    return {
        "id": str(run.id),
        "account_id": str(run.account_id) if run.account_id else None,
        "action": run.action,
        "status": run.status,
        "queued_at": _iso(run.queued_at),
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "requested_by": run.requested_by,
        "progress": cloud.parse_json(run.progress),
        "message": run.message,
        "reason": result.get("reason"),
        "detail": result.get("detail"),
        "duration": result.get("duration"),
        "exit_code": run.exit_code,
        "downloaded": run.downloaded,
        "present": run.present,
        "failed": run.failed_count,
        "bytes": run.bytes_downloaded,
        "waiting_code": run.status == cloud.WAITING_CODE,
    }


def _current_run(db: Session, account_id) -> Optional[models.CloudBackupRun]:
    return (
        db.query(models.CloudBackupRun)
        .filter(
            models.CloudBackupRun.account_id == account_id,
            models.CloudBackupRun.status.in_(cloud.PENDING),
        )
        .order_by(models.CloudBackupRun.queued_at.desc())
        .first()
    )


def _last_run(db: Session, account_id) -> Optional[models.CloudBackupRun]:
    return (
        db.query(models.CloudBackupRun)
        .filter(
            models.CloudBackupRun.account_id == account_id,
            models.CloudBackupRun.action.in_(cloud.TRANSFER_ACTIONS),
            models.CloudBackupRun.status.in_(cloud.FINAL),
        )
        .order_by(models.CloudBackupRun.queued_at.desc())
        .first()
    )


def status_of(account: models.CloudBackupAccount, current) -> str:
    """The one word the page shows: running, waiting_code, needs_sign_in,
    failed, ok, or new (never signed in)."""
    if current is not None:
        return (
            cloud.WAITING_CODE
            if current.status == cloud.WAITING_CODE
            else (cloud.RUNNING)
        )
    if account.state == cloud.STATE_NEEDS_SIGN_IN:
        return cloud.NEEDS_SIGN_IN
    if account.session_created_at is None:
        return cloud.STATE_NEW
    return account.state


def account_dict(db: Session, account: models.CloudBackupAccount) -> Dict[str, Any]:
    now = cloud.now()
    current = _current_run(db, account.id)
    last = _last_run(db, account.id)
    return {
        "id": str(account.id),
        "provider": account.provider,
        "apple_id": account.apple_id,
        "display_name": account.display_name,
        "library": account.library,
        "libraries": cloud.parse_json(account.libraries) or [],
        "password_set": bool(account.password_ref),
        "password_set_at": _iso(account.password_set_at),
        "dir_name": account.dir_name,
        "enabled": bool(account.enabled),
        "interval_hours": account.interval_hours,
        "window_start_hour": account.window_start_hour,
        "until_found": account.until_found,
        "auto_delete": bool(account.auto_delete),
        "status": status_of(account, current),
        "state_message": account.state_message,
        "session_created_at": _iso(account.session_created_at),
        "session_expires_at": _iso(tick.expires_at(account)),
        "session_expiring": tick.expiring(account, now),
        "last_good_at": _iso(account.last_good_at),
        "last_full_at": _iso(account.last_full_at),
        "photos_local": account.photos_local,
        "bytes_local": account.bytes_local,
        "run_requested": account.run_requested_at is not None,
        "current_run": run_dict(current) if current is not None else None,
        "last_run": run_dict(last) if last is not None else None,
        "created_at": _iso(account.created_at),
    }


def _support(host) -> Dict[str, Any]:
    """Whether the storage host's agent can enable it, and if not, why."""
    report = get_capability_report(host) if host is not None else None
    if not report:
        return {"supported": None, "reason": "agent_outdated" if host else "no_host"}
    for key in ("not_applicable", "unavailable"):
        reason = (report.get(key) or {}).get(ENABLE_GROUP)
        if reason:
            return {"supported": False, "reason": str(reason)}
    if ENABLE_GROUP in (report.get("capabilities") or []):
        return {"supported": True, "reason": None}
    return {"supported": False, "reason": "agent_outdated"}


def _enable_dict(row: Optional[models.CloudBackupEnable]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {
        "status": row.status,
        "reason": row.reason,
        "detail": row.detail,
        "tool_version": row.tool_version,
        "install_method": row.install_method,
        "cloud_root": row.cloud_root,
        "requested_by": row.requested_by,
        "requested_at": _iso(row.requested_at),
        "finished_at": _iso(row.finished_at),
    }


def accounts(db: Session, target_id) -> List[models.CloudBackupAccount]:
    return (
        db.query(models.CloudBackupAccount)
        .filter(models.CloudBackupAccount.target_id == target_id)
        .order_by(models.CloudBackupAccount.created_at)
        .all()
    )


def overview(db: Session) -> Dict[str, Any]:
    if cloud.airgapped():
        return {"available": False, "reason": "airgapped"}
    target = jobs.the_target(db)
    if target is None:
        return {"available": True, "target": None, "accounts": []}
    host = jobs.storage_host(db, target)
    return {
        "available": True,
        "target": {
            "id": str(target.id),
            "name": target.name,
            "storage_path": target.storage_path,
        },
        "storage_host": (
            {"id": str(host.id), "fqdn": host.fqdn} if host is not None else None
        ),
        "support": _support(host),
        "enable": _enable_dict(cloud.enable_row(db, target.id)),
        "enabled": cloud.enabled(db, target.id),
        "accounts": [account_dict(db, a) for a in accounts(db, target.id)],
    }


def runs(db: Session, account_id=None, limit: int = RUN_LIMIT) -> List[Dict[str, Any]]:
    query = db.query(models.CloudBackupRun)
    if account_id is not None:
        query = query.filter(models.CloudBackupRun.account_id == account_id)
    rows = query.order_by(models.CloudBackupRun.queued_at.desc()).limit(limit).all()
    return [run_dict(row) for row in rows]


def summary(db: Session) -> Dict[str, Any]:
    """Counts for the dashboard's backup card."""
    empty = {
        "enabled": False,
        "accounts": 0,
        "ok": 0,
        "running": 0,
        "needs_sign_in": 0,
        "failed": 0,
        "expiring": 0,
    }
    if cloud.airgapped():
        return empty
    target = jobs.the_target(db)
    if target is None:
        return empty
    counts = dict(empty, enabled=cloud.enabled(db, target.id))
    now = cloud.now()
    for account in accounts(db, target.id):
        counts["accounts"] += 1
        word = status_of(account, _current_run(db, account.id))
        if word in (cloud.RUNNING, cloud.WAITING_CODE):
            counts["running"] += 1
        elif word == cloud.NEEDS_SIGN_IN:
            counts["needs_sign_in"] += 1
        elif word == cloud.STATE_FAILED:
            counts["failed"] += 1
        elif word == cloud.STATE_OK:
            counts["ok"] += 1
        if word != cloud.NEEDS_SIGN_IN and tick.expiring(account, now):
            counts["expiring"] += 1
    return counts
