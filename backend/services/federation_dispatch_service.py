"""
Federation command-dispatch tracking service (Phase 12.1.F).

Records commands the coordinator dispatched to subordinate sites and
the lifecycle of each — ``queued_at_site`` → ``in_progress`` →
``completed`` / ``partial`` / ``failed``.  The Pro+ engine wraps
these as ``/api/v1/federation/commands*`` endpoints.

The dispatch row IS the authoritative record at the coordinator;
the actual command payload (reboot, apply_updates, deploy_packages,
run_script, …) flows to the agent via the site's existing
``MessageQueue`` infrastructure — this service only tracks the
"did we send it and what came back" view.

State machine:

  ``queued_at_site``  initial.  Coordinator dispatched; site has not
                     yet ack'd.
  ``in_progress``    site picked it up + started executing on agents.
  ``partial``        terminal-ish.  Some target hosts succeeded,
                     others failed; ``result_summary`` carries the breakdown.
  ``completed``      terminal.  Every target host reported success.
  ``failed``         terminal.  Site rejected the command outright
                     OR every target host failed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from backend.persistence.models.federation import (
    FederationAuditLog,
    FederationDispatchedCommand,
    FederationSite,
)

# ---------------------------------------------------------------------
# State constants
# ---------------------------------------------------------------------

STATUS_QUEUED_AT_SITE = "queued_at_site"
STATUS_IN_PROGRESS = "in_progress"
STATUS_PARTIAL = "partial"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

_TERMINAL_STATUSES = {
    STATUS_PARTIAL,
    STATUS_COMPLETED,
    STATUS_FAILED,
}

# Allowed state transitions.  Any other move raises
# :class:`InvalidDispatchStateError` so a misbehaving site can't
# resurrect a closed command.
_ALLOWED_TRANSITIONS = {
    STATUS_QUEUED_AT_SITE: {STATUS_IN_PROGRESS, STATUS_FAILED},
    STATUS_IN_PROGRESS: {
        STATUS_PARTIAL,
        STATUS_COMPLETED,
        STATUS_FAILED,
    },
    # Terminal -> any: not allowed.
}

AUDIT_OP_COMMAND_DISPATCHED = "command_dispatched"
AUDIT_OP_COMMAND_STATUS_CHANGED = "command_status_changed"


# ---------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------


class FederationDispatchError(Exception):
    """Base class for dispatch-service errors."""


class DispatchedCommandNotFoundError(FederationDispatchError, LookupError):
    """Raised when a dispatched-command id doesn't resolve."""


class InvalidDispatchStateError(FederationDispatchError, ValueError):
    """Raised when the requested state transition isn't allowed by the FSM."""


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _ensure_command(session: Session, command_id: Any) -> FederationDispatchedCommand:
    cid = _coerce_uuid(command_id)
    cmd = session.get(FederationDispatchedCommand, cid)
    if cmd is None:
        raise DispatchedCommandNotFoundError(f"No dispatched command with id={cid}")
    return cmd


def _ensure_site(session: Session, site_id: Any) -> FederationSite:
    sid = _coerce_uuid(site_id)
    site = session.get(FederationSite, sid)
    if site is None:
        raise LookupError(f"No federation site with id={sid}")
    return site


def _log_audit(
    session: Session,
    operation: str,
    *,
    actor_userid: Optional[str] = None,
    target_site_id: Optional[Any] = None,
    details: Optional[Dict[str, Any]] = None,
) -> FederationAuditLog:
    entry = FederationAuditLog(
        operation=operation,
        actor_userid=actor_userid,
        target_site_id=(
            _coerce_uuid(target_site_id) if target_site_id is not None else None
        ),
        details_json=json.dumps(details) if details else None,
    )
    session.add(entry)
    return entry


# ---------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------


def dispatch_command(
    session: Session,
    *,
    command_type: str,
    target_site_id: Any,
    parameters: Optional[Dict[str, Any]] = None,
    target_host_ids: Optional[Sequence[Any]] = None,
    dispatched_by: Optional[str] = None,
) -> FederationDispatchedCommand:
    """Record a coordinator-initiated command for delivery to a site.

    ``target_host_ids=None`` (or an empty sequence) means "every host
    at the target site".  The list is JSON-serialised; the site's
    engine reads it to fan out to the right agents.

    Status starts at ``queued_at_site``.  The site's engine later
    transitions it through the FSM via :func:`update_command_status`.
    """
    if not command_type or not command_type.strip():
        raise ValueError("command_type is required")
    site = _ensure_site(session, target_site_id)
    if site.status not in {"enrolled"}:
        raise ValueError(
            f"Target site {site.id} status is '{site.status}'; only "
            f"enrolled sites can receive dispatched commands."
        )

    target_uuids: List[str] = []
    if target_host_ids:
        target_uuids = [str(_coerce_uuid(h)) for h in target_host_ids]

    cmd = FederationDispatchedCommand(
        command_type=command_type.strip(),
        parameters_json=json.dumps(parameters or {}, sort_keys=True),
        target_site_id=site.id,
        target_host_ids_json=json.dumps(target_uuids) if target_uuids else None,
        dispatched_by=dispatched_by,
        status=STATUS_QUEUED_AT_SITE,
    )
    session.add(cmd)
    session.flush()

    _log_audit(
        session,
        AUDIT_OP_COMMAND_DISPATCHED,
        actor_userid=dispatched_by,
        target_site_id=site.id,
        details={
            "command_id": str(cmd.id),
            "command_type": command_type.strip(),
            "target_host_count": len(target_uuids),
        },
    )
    return cmd


def get_command(session: Session, command_id: Any) -> FederationDispatchedCommand:
    return _ensure_command(session, command_id)


def list_dispatched_commands(
    session: Session,
    *,
    site_id: Optional[Any] = None,
    status: Optional[str] = None,
    open_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> List[FederationDispatchedCommand]:
    """List dispatched commands, newest first.

    ``open_only=True`` filters to non-terminal statuses (queued /
    in_progress) — used by the Coordinator's "active commands"
    dashboard widget.
    """
    if limit <= 0:
        raise ValueError("limit must be > 0")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    stmt = select(FederationDispatchedCommand)
    if site_id is not None:
        stmt = stmt.where(
            FederationDispatchedCommand.target_site_id == _coerce_uuid(site_id)
        )
    if status is not None:
        stmt = stmt.where(FederationDispatchedCommand.status == status)
    if open_only:
        stmt = stmt.where(FederationDispatchedCommand.status.not_in(_TERMINAL_STATUSES))
    stmt = (
        stmt.order_by(desc(FederationDispatchedCommand.dispatched_at))
        .offset(offset)
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())


def update_command_status(
    session: Session,
    command_id: Any,
    *,
    new_status: str,
    result_summary: Optional[str] = None,
    actor_userid: Optional[str] = None,
) -> FederationDispatchedCommand:
    """Advance a dispatched command's state.

    Validates the transition against the FSM (``_ALLOWED_TRANSITIONS``).
    Terminal statuses stamp ``completed_at``; non-terminal ones leave
    it NULL.  Re-applying the same status is a no-op (idempotent) so
    a site that replays an ack after reconnect doesn't error.
    """
    cmd = _ensure_command(session, command_id)
    if cmd.status == new_status:
        # Idempotent: same-state replays are common after offline
        # reconnect; treat as success rather than an FSM violation.
        if result_summary is not None and result_summary != cmd.result_summary:
            cmd.result_summary = result_summary
        return cmd

    allowed = _ALLOWED_TRANSITIONS.get(cmd.status, set())
    if new_status not in allowed:
        raise InvalidDispatchStateError(
            f"Cannot transition command {cmd.id} from "
            f"'{cmd.status}' to '{new_status}' "
            f"(allowed: {sorted(allowed) or 'none — terminal'})"
        )

    old_status = cmd.status
    cmd.status = new_status
    if result_summary is not None:
        cmd.result_summary = result_summary
    if new_status in _TERMINAL_STATUSES:
        cmd.completed_at = _utcnow_naive()

    _log_audit(
        session,
        AUDIT_OP_COMMAND_STATUS_CHANGED,
        actor_userid=actor_userid,
        target_site_id=cmd.target_site_id,
        details={
            "command_id": str(cmd.id),
            "from_status": old_status,
            "to_status": new_status,
        },
    )
    return cmd
