# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Can a host reach its backup storage? (ROADMAP Phase 24)

A backed-up host mounts its repository from the storage host over NFSv4: one
TCP port, 2049, at the storage host's address.  The server asks each host's
agent to open a connection there (``check_backup_storage``, the address and
nothing else) and keeps the last answer per host in ``backup_reach``.  A
host that cannot reach it is not offered backups -- Equip, a policy, Back up
now, the bulk actions and the scheduler all pass it by -- with a message
saying so, rather than failing every night (production, 2026-10-30: the
server's own cloud droplet and the home NAS).

Never-checked, still-checking, or checked against another address (the
storage host moved) is unknown, and unknown never blocks.  Checks are asked
for when a host has none for the current address, once a day after that,
and on "Check again".
"""

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.services import agent_capability_service as capabilities
from backend.services import backup_jobs as jobs

logger = logging.getLogger(__name__)

GROUP = "backup_reach"
COMMAND = "check_backup_storage"
PORT = 2049
UNREACHABLE = "storage_unreachable"
RECHECK_AFTER = timedelta(days=1)
# A check unanswered this long (agent away) may be asked again.
ANSWER_WITHIN = timedelta(minutes=10)


def storage_address(db: Session) -> Optional[Dict[str, Any]]:
    """``{"address", "host_id", "fqdn"}`` of the target's storage host, as
    hosts mount from it (its IPv4, backup_jobs.nfs_source), or None."""
    storage = jobs.storage_host(db, jobs.the_target(db))
    address = jobs.host_address(storage) if storage is not None else None
    if not address:
        return None
    return {"address": address, "host_id": storage.id, "fqdn": storage.fqdn}


def _row(db: Session, host_id: Any) -> Optional[models.BackupReach]:
    return (
        db.query(models.BackupReach)
        .filter(models.BackupReach.host_id == host_id)
        .first()
    )


def can_check(host: models.Host) -> bool:
    """The host's agent has the check (its capability report says so)."""
    report = capabilities.get_capability_report(host) or {}
    return GROUP in (report.get("capabilities") or [])


def state(db: Session, host: models.Host) -> Optional[Dict[str, Any]]:
    """The last answer for the current storage address, or None (unknown)."""
    storage = storage_address(db)
    row = _row(db, host.id)
    if storage is None or row is None or row.address != storage["address"]:
        return None
    if row.reachable is None:
        return None
    return {
        "reachable": bool(row.reachable),
        "address": row.address,
        "port": row.port,
        "storage_fqdn": storage["fqdn"],
        "error": row.error,
        "checked_at": row.checked_at.isoformat() if row.checked_at else None,
    }


def blocked(db: Session, host: models.Host) -> bool:
    """Known not to reach the storage (unknown never blocks)."""
    found = state(db, host)
    return found is not None and not found["reachable"]


def message(db: Session, host: models.Host) -> str:
    """Why backups are not offered to this host."""
    found = state(db, host) or {}
    return _(
        "This host cannot reach the backup storage (%(storage)s, %(address)s, "
        "NFS port %(port)s). Backups need a network path to it."
    ) % {
        "storage": found.get("storage_fqdn") or "",
        "address": found.get("address") or "",
        "port": found.get("port") or PORT,
    }


def due(db: Session, host: models.Host, now=None) -> bool:
    """A check is wanted: none for the current address, the last one is a
    day old, or one asked for went unanswered."""
    storage = storage_address(db)
    if storage is None or str(storage["host_id"]) == str(host.id):
        return False  # the storage host does not mount its own storage
    now = now or jobs.now()
    row = _row(db, host.id)
    if row is None or row.address != storage["address"]:
        return True
    if row.checked_at is None or row.requested_at > row.checked_at:
        return row.requested_at + ANSWER_WITHIN <= now
    return row.checked_at + RECHECK_AFTER <= now


def start(db: Session, host: models.Host, force: bool = False) -> Optional[str]:
    """Ask the host's agent to check; its command id, or None when it was
    not asked (no storage, no capability, or not due).  The caller commits."""
    # pylint: disable=import-outside-toplevel
    from backend.services.config_mgmt_dispatch import queue_command  # noqa: PLC0415
    from backend.websocket.messages import CommandType  # noqa: PLC0415

    storage = storage_address(db)
    if storage is None or not can_check(host) or not (force or due(db, host)):
        return None
    if str(storage["host_id"]) == str(host.id):
        return None
    command_id = queue_command(
        db, host.id, CommandType.CHECK_BACKUP_STORAGE, {"address": storage["address"]}
    )
    row = _row(db, host.id) or models.BackupReach(host_id=host.id)
    if row.address != storage["address"]:
        row.reachable, row.error, row.checked_at = None, None, None
    row.address, row.port = storage["address"], PORT
    row.command_id, row.requested_at = command_id, jobs.now()
    db.add(row)
    db.flush()  # its answer finds it by command id
    return command_id


def record_result(db: Session, host_id: Any, message_data: Dict[str, Any]) -> bool:
    """The agent's answer.  False when it answers none of ours, or is not an
    answer (an invalid address the agent refused).  The caller commits."""
    command_id = message_data.get("command_id")
    row = (
        db.query(models.BackupReach)
        .filter(models.BackupReach.command_id == str(command_id))
        .first()
        if command_id
        else None
    )
    if row is None or str(row.host_id) != str(host_id):
        logger.warning(
            "check_backup_storage result from host %s for unknown command %s ignored",
            host_id,
            command_id,
        )
        return False
    outcome = message_data.get("result") or {}
    if isinstance(outcome.get("result"), dict):
        outcome = outcome["result"]  # the agent wraps its handler's answer
    if not isinstance(outcome.get("reachable"), bool):
        logger.warning(
            "check_backup_storage from host %s gave no answer: %s",
            host_id,
            outcome.get("error") or message_data.get("error"),
        )
        return False
    row.reachable = outcome["reachable"]
    row.error = str(outcome.get("error") or "")[:255] or None
    row.checked_at = jobs.now()
    if not row.reachable:
        logger.info(
            "Host %s cannot reach its backup storage at %s:%s (%s)",
            host_id,
            row.address,
            row.port,
            row.error,
        )
    return True


def refuse_if_blocked(db: Session, host: models.Host) -> None:
    """HTTP 409 with the reason, for an action that needs the storage."""
    # pylint: disable=import-outside-toplevel
    from fastapi import HTTPException  # noqa: PLC0415

    if blocked(db, host):
        raise HTTPException(status_code=409, detail=message(db, host))
