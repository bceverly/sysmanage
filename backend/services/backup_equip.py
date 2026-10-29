# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Equip for backup: have a host's agent install restate (ROADMAP Phase 24).

The agent decides everything about the install (backup/equip.py: Ubuntu's PPA,
FreeBSD's checked release package); the server only asks, keeps the latest
attempt per host in ``backup_equip``, and -- when it succeeds -- asks the
agent for a fresh capability report, so the host reads "equipped" within
seconds instead of after its agent's next restart.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import agent_capability_service as capabilities
from backend.services import backup_jobs as jobs
from backend.services import queue_clock

logger = logging.getLogger(__name__)

GROUP = "backup_equip"
COMMAND = "equip_backup"
RUNNING, OK, FAILED = "running", "ok", "failed"
# An install that has not answered in this long AFTER IT WAS SENT is shown as
# failed (the agent went away, or its answer was lost); a new attempt may
# start.  Time spent queued -- held for a maintenance window, or waiting for
# an offline agent -- does not count (services/queue_clock.py).
STALE_AFTER = timedelta(hours=1)
# Why "Equip for backup" is not offered, as codes the UI translates.
NOT_NEEDED = "equipped"
AGENT_OUTDATED = "agent_outdated"
NOT_APPLICABLE = "not_applicable"
IN_PROGRESS = "in_progress"
# The equipped reasons Equip can fix (it installs restate and the NFS client).
FIXABLE = ("missing_tool", "tool_outdated", "missing_nfs_client")


def _row(db: Session, host_id: Any) -> Optional[models.BackupEquip]:
    return (
        db.query(models.BackupEquip)
        .filter(models.BackupEquip.host_id == host_id)
        .first()
    )


def _running(db: Session, row: Optional[models.BackupEquip], now) -> bool:
    if row is None or row.status != RUNNING:
        return False
    started = queue_clock.clock_start(
        queue_clock.delivery(db, row.command_id), row.requested_at
    )
    return started is None or now - started < STALE_AFTER


def _held(db: Session, row: models.BackupEquip) -> bool:
    """Queued and deferred by the host's maintenance window."""
    found = queue_clock.delivery(db, row.command_id)
    return found is not None and found.held


def blocker(db: Session, host: models.Host, now=None) -> Optional[str]:
    """Why Equip for backup cannot start on this host now, or None."""
    now = now or jobs.now()
    ready, reason = jobs.equipped(host)
    if ready or reason not in FIXABLE:
        return NOT_NEEDED if ready else reason
    report = capabilities.get_capability_report(host) or {}
    if GROUP in (report.get("not_applicable") or {}):
        return NOT_APPLICABLE
    if GROUP not in (report.get("capabilities") or []):
        return AGENT_OUTDATED
    if _running(db, _row(db, host.id), now):
        return IN_PROGRESS
    return None


def state(db: Session, host_id: Any, now=None) -> Optional[Dict[str, Any]]:
    """The latest attempt for the Backups page; a stale "running" reads as
    failed with reason ``no_answer``."""
    row = _row(db, host_id)
    if row is None:
        return None
    now = now or jobs.now()
    status, reason = row.status, row.reason
    if status == RUNNING and not _running(db, row, now):
        status, reason = FAILED, "no_answer"
    return {
        "status": status,
        "reason": reason,
        "held": status == RUNNING and _held(db, row),
        "detail": row.detail,
        "installed": row.installed,
        "requested_at": row.requested_at.isoformat() if row.requested_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def start(
    db: Session, host: models.Host, userid: str
) -> Tuple[Optional[str], Optional[str]]:
    """Ask the host's agent to install restate: ``(command_id, None)``, or
    ``(None, blocker code)`` when it cannot start.  The caller commits."""
    # pylint: disable=import-outside-toplevel
    from backend.services.config_mgmt_dispatch import queue_command  # noqa: PLC0415
    from backend.websocket.messages import CommandType  # noqa: PLC0415

    why = blocker(db, host)
    if why:
        return None, why
    command_id = queue_command(db, host.id, CommandType.EQUIP_BACKUP, {})
    row = _row(db, host.id) or models.BackupEquip(host_id=host.id)
    row.status, row.reason, row.detail, row.installed = RUNNING, None, None, None
    row.command_id = command_id
    row.requested_by = userid
    row.requested_at = jobs.now()
    row.finished_at = None
    db.add(row)
    return command_id, None


def record_result(db: Session, host_id: Any, message_data: Dict[str, Any]) -> bool:
    """The agent's answer to an equip_backup command.  On success, ask it for
    a fresh capability report straight away.  False when it answers none of
    ours.  The caller commits."""
    command_id = message_data.get("command_id")
    row = (
        db.query(models.BackupEquip)
        .filter(models.BackupEquip.command_id == str(command_id))
        .first()
        if command_id
        else None
    )
    if row is None or str(row.host_id) != str(host_id):
        logger.warning(
            "equip_backup result from host %s for unknown command %s ignored",
            host_id,
            command_id,
        )
        return False
    outcome = message_data.get("result") or {}
    succeeded = bool(message_data.get("success")) and not message_data.get("error")
    row.finished_at = jobs.now()
    if succeeded:
        row.status, row.reason = OK, None
        row.installed = str(outcome.get("installed") or "")[:32] or None
        capabilities.request_refresh(db, row.host_id)
    else:
        row.status = FAILED
        row.reason = str(outcome.get("reason") or "install_failed")[:32]
        detail = outcome.get("detail") or message_data.get("error") or ""
        row.detail = str(detail)[-800:]
    return True
