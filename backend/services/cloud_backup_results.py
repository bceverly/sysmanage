# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Results and progress of iCloud Photos jobs (ROADMAP 24.12).

The storage host's agent sends ``cloud_backup_progress`` while a job runs and
one ``cloud_backup_result`` when it ends, both keyed by the run id.  A
message naming a run that belongs to another host is ignored and logged.

An authentication failure is recorded as ``needs_sign_in`` -- on the run and
on the account -- never as "no new photos": the Backups page and the
dashboard show it as "Needs sign-in" until someone presses Connect again.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import cloud_backup_jobs as cloud
from backend.services import cloud_backup_tick as tick

logger = logging.getLogger(__name__)

_TEXT_LIMIT = 16000
_STATUSES = (cloud.OK, cloud.FAILED, cloud.NEEDS_SIGN_IN)
_PHASES = ("installing", "preparing", "signing_in", "waiting_code", "downloading")


def _int(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _text(value: Any, limit: int = _TEXT_LIMIT) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text[-limit:] if len(text) > limit else text


def _run(db: Session, host_id: Any, payload: Dict[str, Any]):
    try:
        key = uuid.UUID(str(payload.get("run_id")))
    except ValueError:
        logger.warning("cloud backup message with a bad run id from host %s", host_id)
        return None
    run = (
        db.query(models.CloudBackupRun).filter(models.CloudBackupRun.id == key).first()
    )
    if run is None or str(run.host_id) != str(host_id):
        logger.warning(
            "cloud backup message for run %s from host %s ignored: not its run",
            key,
            host_id,
        )
        return None
    return run


def _account(db: Session, run) -> Optional[models.CloudBackupAccount]:
    if run.account_id is None:
        return None
    return (
        db.query(models.CloudBackupAccount)
        .filter(models.CloudBackupAccount.id == run.account_id)
        .first()
    )


def record_progress(db: Session, host_id: Any, payload: Dict[str, Any]):
    run = _run(db, host_id, payload)
    if run is None or run.status not in cloud.PENDING:
        return None
    phase = payload.get("phase")
    progress = {
        "phase": phase if phase in _PHASES else "downloading",
        "downloaded": _int(payload.get("downloaded")),
        "present": _int(payload.get("present")),
        "failed": _int(payload.get("failed")),
        "line": _text(payload.get("line"), 500),
        # A heartbeat: a full download can run for days (cloud_backup_tick).
        "at": cloud.now().isoformat(),
    }
    run.progress = json.dumps(progress)
    if run.started_at is None:
        run.started_at = cloud.now()
    if run.status == cloud.QUEUED:
        run.status = cloud.RUNNING
    return run


def _libraries(value: Any) -> Optional[List[str]]:
    if not isinstance(value, list):
        return None
    found = []
    for item in value[:100]:
        try:
            found.append(cloud.valid_library(item))
        except cloud.CloudBackupRefused:
            continue
    return found


def _enable_result(db: Session, run, payload: Dict[str, Any], status: str) -> None:
    row = cloud.enable_row(db, run.target_id)
    if row is None or row.run_id != run.id:
        return
    row.status = cloud.OK if status == cloud.OK else cloud.FAILED
    row.reason = _text(payload.get("reason"), 64)
    row.detail = _text(payload.get("detail"))
    row.tool_version = _text(payload.get("tool_version"), 32) or row.tool_version
    row.install_method = _text(payload.get("install_method"), 16) or row.install_method
    row.cloud_root = _text(payload.get("cloud_root"), 1024) or row.cloud_root
    row.finished_at = cloud.now()
    if row.status == cloud.OK:
        # The agent now advertises cloud_backup_run: learn it at once, not at
        # its next restart (as Equip for backup does).
        # pylint: disable=import-outside-toplevel
        from backend.services import agent_capability_service  # noqa: PLC0415

        agent_capability_service.request_refresh(db, run.host_id)


def _account_result(
    account: models.CloudBackupAccount, run, payload: Dict[str, Any], status: str
) -> None:
    now = cloud.now()
    account.updated_at = now
    if status == cloud.NEEDS_SIGN_IN:
        account.state = cloud.STATE_NEEDS_SIGN_IN
        account.state_message = run.message
        if run.action == cloud.CONNECT:
            account.session_created_at = None
        return
    if status == cloud.FAILED:
        # A failed download leaves a good sign-in alone.
        if account.state != cloud.STATE_NEEDS_SIGN_IN:
            account.state = cloud.STATE_FAILED
        account.state_message = run.message
        return
    account.state, account.state_message = cloud.STATE_OK, None
    if run.action == cloud.CONNECT:
        account.session_created_at = now
        account.session_warned_at = None
    libraries = _libraries(payload.get("libraries"))
    if libraries is not None:
        account.libraries = json.dumps(libraries)
    if run.action in cloud.TRANSFER_ACTIONS:
        account.last_good_at = now
        if run.action == cloud.RECONCILE:
            account.last_full_at = now
    photos, size = _int(payload.get("photos_local")), _int(payload.get("bytes_local"))
    if photos is not None:
        account.photos_local = photos
    if size is not None:
        account.bytes_local = size


def _reason(payload: Dict[str, Any], detail: Optional[str]) -> Optional[str]:
    """The agent's reason code; Apple's refusal named even when an older agent
    called it "tool_failed", so the cooldown retry (cloud_backup_tick) works
    with it too."""
    reason = _text(payload.get("reason"), 64)
    if reason in (None, "tool_failed") and tick.apple_stopped(detail):
        return tick.APPLE_BUSY
    return reason


# The agent's own words for Apple's refusal: run messages are the agent's text.
APPLE_BUSY_MESSAGE = (
    "Apple is limiting downloads for this account. Nothing is lost: "
    "the download is tried again after a cooldown."
)


def _stopped_by_apple(run, status: str, detail: Optional[str]) -> bool:
    """A download reported good although Apple cut it off.

    icloudpd 1.32.3 can log Apple's refusal and still exit 0, and an agent
    that judged on the exit called that run a success: on 2026-11-06 nas's
    first full pass stopped at 16,445 of about 32,000 photos and was
    recorded as the week's full pass, so the daily downloads (which stop at
    the newest photos already present) would never reach the rest.  Read as
    Apple's refusal, it carries on after the cooldown instead.
    """
    return (
        status == cloud.OK
        and run.action in cloud.TRANSFER_ACTIONS
        and tick.apple_stopped(detail)
    )


def _ran_with(db: Session, run, payload: Dict[str, Any]) -> None:
    """The icloudpd an account's job ran: the agent upgrades it to its pin
    before a run, so Enable's version goes stale without this."""
    version = _text(payload.get("tool_version"), 32)
    row = cloud.enable_row(db, run.target_id) if version else None
    if row is not None:
        row.tool_version = version


def record_result(db: Session, host_id: Any, payload: Dict[str, Any]):
    """Store one job's outcome; the run, or None when ignored."""
    run = _run(db, host_id, payload)
    if run is None:
        return None
    if run.status in cloud.FINAL:
        logger.info("cloud backup run %s already ended; result ignored", run.id)
        return run
    status = payload.get("status")
    if status not in _STATUSES:
        status = cloud.FAILED
    detail = _text(payload.get("detail"))
    if _stopped_by_apple(run, status, detail):
        status = cloud.FAILED
        payload = {
            **payload,
            "reason": tick.APPLE_BUSY,
            "message": APPLE_BUSY_MESSAGE,
        }
    now = cloud.now()
    run.status = status
    run.finished_at = now
    run.started_at = run.started_at or now
    run.mfa_code = None
    run.exit_code = (
        payload.get("exit_code") if isinstance(payload.get("exit_code"), int) else None
    )
    run.message = _text(payload.get("message"), 2000)
    run.downloaded = _int(payload.get("downloaded"))
    run.present = _int(payload.get("present"))
    run.failed_count = _int(payload.get("failed"))
    run.bytes_downloaded = _int(payload.get("bytes"))
    run.result = json.dumps(
        {
            "reason": _reason(payload, detail),
            "detail": detail,
            "duration": _int(payload.get("duration")),
        }
    )
    run.progress = None
    if run.action == cloud.ENABLE:
        _enable_result(db, run, payload, status)
    else:
        _ran_with(db, run, payload)
    account = _account(db, run)
    if account is not None and run.action != cloud.REMOVE:
        _account_result(account, run, payload, status)
    if run.action == cloud.REMOVE and status == cloud.OK and account is not None:
        db.delete(account)
    logger.info(
        "cloud backup %s run %s on host %s: %s",
        run.action, run.id, host_id, status,
    )  # fmt: skip
    _audit(db, run, status)
    return run


def _audit(db: Session, run, status: str) -> None:
    # pylint: disable=import-outside-toplevel
    from backend.services.audit_service import (  # noqa: PLC0415
        ActionType,
        AuditService,
        EntityType,
    )

    AuditService.log(
        db=db,
        user_id=None,
        username="agent",
        action_type=ActionType.UPDATE,
        entity_type=EntityType.HOST,
        entity_id=str(run.host_id),
        entity_name=None,
        description=f"Cloud backup {run.action} finished: {status}",
        details={
            "run_id": str(run.id),
            "account_id": str(run.account_id) if run.account_id else None,
            "downloaded": run.downloaded,
            "failed": run.failed_count,
        },
        commit=False,
    )
