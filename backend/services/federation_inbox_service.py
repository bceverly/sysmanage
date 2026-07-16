# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Site-side inbox services (Phase 12.2).

Helpers for the two inbox tables a site uses to receive policy
pushes and dispatched commands from its coordinator:

  * ``federation_received_policies``
  * ``federation_received_commands``

Both tables store the coordinator-assigned primary key so the site
can dedup-by-id on replay (the coordinator may push the same policy
twice if its previous attempt got TCP-dropped before the ack).

The Pro+ ``federation_site_engine`` wraps these helpers in inbound
``POST /api/v1/federation/site/policies`` and
``POST /api/v1/federation/site/commands`` handlers.  Outbound
"command-result" packets back to the coordinator go through
``federation_sync_queue_service.enqueue`` with
``payload_type="command_result"``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.persistence.models.federation import (
    FederationReceivedCommand,
    FederationReceivedPolicy,
)

# ---------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------


class FederationInboxError(Exception):
    """Base class for inbox errors."""


class ReceivedPolicyNotFoundError(FederationInboxError, LookupError):
    """Raised when a received-policy id doesn't resolve."""


class ReceivedCommandNotFoundError(FederationInboxError, LookupError):
    """Raised when a received-command id doesn't resolve."""


class InvalidCommandStateError(FederationInboxError, ValueError):
    """Raised when a received-command FSM transition isn't valid."""


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


# ---------------------------------------------------------------------
# Policy inbox
# ---------------------------------------------------------------------


def receive_policy(
    session: Session,
    *,
    policy_id: Any,
    policy_type: str,
    name: str,
    definition: Dict[str, Any],
    version: int,
) -> FederationReceivedPolicy:
    """Accept a policy push from the coordinator.

    Upserts by ``policy_id`` (the coordinator's primary key, shared
    on both sides).  If a row with the same id already exists, this
    is a re-push from the coordinator — we update only if the
    incoming ``version`` is strictly greater than what we have.  The
    "applied" state is preserved on update so a re-push doesn't
    silently revert an applied policy back to unapplied.

    Returns the inbox row (caller commits).
    """
    if not policy_type or not policy_type.strip():
        raise ValueError("policy_type is required")
    if not name or not name.strip():
        raise ValueError("policy name is required")
    if not isinstance(definition, dict):
        raise ValueError("definition must be a dict")
    if version <= 0:
        raise ValueError("version must be > 0")

    pid = _coerce_uuid(policy_id)
    existing = session.get(FederationReceivedPolicy, pid)

    if existing is None:
        row = FederationReceivedPolicy(
            policy_id=pid,
            policy_type=policy_type.strip(),
            name=name.strip(),
            definition_json=json.dumps(definition, sort_keys=True),
            version=version,
            received_at=_utcnow_naive(),
            applied=False,
        )
        session.add(row)
        return row

    if version <= existing.version:
        # Older / same-version replay — ignore.
        return existing
    # Newer version arrived: refresh fields, reset apply state.
    existing.policy_type = policy_type.strip()
    existing.name = name.strip()
    existing.definition_json = json.dumps(definition, sort_keys=True)
    existing.version = version
    existing.received_at = _utcnow_naive()
    existing.applied = False
    existing.applied_at = None
    existing.apply_error = None
    return existing


def get_received_policy(session: Session, policy_id: Any) -> FederationReceivedPolicy:
    pid = _coerce_uuid(policy_id)
    row = session.get(FederationReceivedPolicy, pid)
    if row is None:
        raise ReceivedPolicyNotFoundError(f"No received policy with id={pid}")
    return row


def list_unapplied_policies(
    session: Session, *, policy_type: Optional[str] = None
) -> List[FederationReceivedPolicy]:
    """Return policies waiting to be applied locally.

    The site engine's apply worker drains this list each tick,
    materialises the policy into local tables (update profiles,
    firewall roles, ...), and calls :func:`mark_policy_applied` /
    :func:`mark_policy_apply_failed` per row.
    """
    stmt = select(FederationReceivedPolicy).where(
        FederationReceivedPolicy.applied.is_(False)
    )
    if policy_type is not None:
        stmt = stmt.where(FederationReceivedPolicy.policy_type == policy_type)
    stmt = stmt.order_by(FederationReceivedPolicy.received_at)
    return list(session.execute(stmt).scalars().all())


def mark_policy_applied(session: Session, policy_id: Any) -> FederationReceivedPolicy:
    """Record successful local application of a received policy.

    Idempotent — applying twice is a no-op (the apply_at timestamp
    stays at the first success).  ``apply_error`` is cleared in
    case the previous attempt had failed before this success.
    """
    row = get_received_policy(session, policy_id)
    if not row.applied:
        row.applied = True
        row.applied_at = _utcnow_naive()
    row.apply_error = None
    return row


def mark_policy_apply_failed(
    session: Session,
    policy_id: Any,
    *,
    error: str,
) -> FederationReceivedPolicy:
    """Record a failed local application.  Leaves ``applied=False``
    so the worker retries on the next tick."""
    if not error:
        raise ValueError("error string is required for mark_policy_apply_failed")
    row = get_received_policy(session, policy_id)
    row.apply_error = error
    return row


# ---------------------------------------------------------------------
# Command inbox
# ---------------------------------------------------------------------

CMD_STATUS_QUEUED = "queued"
CMD_STATUS_IN_PROGRESS = "in_progress"
CMD_STATUS_COMPLETED = "completed"
CMD_STATUS_FAILED = "failed"

_CMD_TERMINAL = {CMD_STATUS_COMPLETED, CMD_STATUS_FAILED}

# Allowed transitions on the received-command FSM.  Mirrors the
# dispatched-command FSM at the coordinator (12.1.F) so the two
# sides stay in lockstep when the site reports status back.
_CMD_ALLOWED = {
    CMD_STATUS_QUEUED: {CMD_STATUS_IN_PROGRESS, CMD_STATUS_FAILED},
    CMD_STATUS_IN_PROGRESS: {CMD_STATUS_COMPLETED, CMD_STATUS_FAILED},
}


def receive_command(
    session: Session,
    *,
    command_id: Any,
    command_type: str,
    parameters: Optional[Dict[str, Any]] = None,
    target_host_ids: Optional[Sequence[Any]] = None,
) -> FederationReceivedCommand:
    """Accept a command-dispatch push from the coordinator.

    Like :func:`receive_policy`, upserts by ``command_id`` so a
    coordinator re-push (e.g. after a network-drop ack timeout)
    doesn't duplicate the command.  If the row already exists in a
    terminal state, the replay is a no-op (we don't reset a
    completed command).
    """
    if not command_type or not command_type.strip():
        raise ValueError("command_type is required")

    cid = _coerce_uuid(command_id)
    existing = session.get(FederationReceivedCommand, cid)
    if existing is not None:
        # Re-push from coordinator.  If we already finished the
        # command, ignore — the site already pushed the result
        # upstream; no need to re-do anything.  If still in flight
        # or queued, just refresh the parameters in case the
        # coordinator amended them.
        if existing.status in _CMD_TERMINAL:
            return existing
        existing.command_type = command_type.strip()
        existing.parameters_json = json.dumps(parameters or {}, sort_keys=True)
        if target_host_ids is not None:
            existing.target_host_ids_json = json.dumps(
                [str(_coerce_uuid(h)) for h in target_host_ids]
            )
        return existing

    target_uuids: List[str] = []
    if target_host_ids:
        target_uuids = [str(_coerce_uuid(h)) for h in target_host_ids]

    row = FederationReceivedCommand(
        id=cid,
        command_type=command_type.strip(),
        parameters_json=json.dumps(parameters or {}, sort_keys=True),
        target_host_ids_json=json.dumps(target_uuids) if target_uuids else None,
        received_at=_utcnow_naive(),
        status=CMD_STATUS_QUEUED,
    )
    session.add(row)
    return row


def get_received_command(
    session: Session, command_id: Any
) -> FederationReceivedCommand:
    cid = _coerce_uuid(command_id)
    row = session.get(FederationReceivedCommand, cid)
    if row is None:
        raise ReceivedCommandNotFoundError(f"No received command with id={cid}")
    return row


def list_queued_commands(
    session: Session, *, limit: int = 100
) -> List[FederationReceivedCommand]:
    """Commands waiting for the site engine to dispatch to local agents.

    Drained by the site engine's command-fanout worker each tick.
    """
    if limit <= 0:
        raise ValueError("limit must be > 0")
    return list(
        session.execute(
            select(FederationReceivedCommand)
            .where(FederationReceivedCommand.status == CMD_STATUS_QUEUED)
            .order_by(FederationReceivedCommand.received_at)
            .limit(limit)
        )
        .scalars()
        .all()
    )


def update_command_status(
    session: Session,
    command_id: Any,
    *,
    new_status: str,
    result: Optional[Dict[str, Any]] = None,
) -> FederationReceivedCommand:
    """Advance a received-command's FSM.

    Idempotent on same-state replays (network jitter, worker
    restart).  Terminal states stamp ``completed_at`` and the
    final ``result_json``; the site engine's "report back upstream"
    worker then enqueues a ``command_result`` payload into the
    sync queue.
    """
    row = get_received_command(session, command_id)

    if row.status == new_status:
        # Idempotent replay; allow result to be patched in case
        # the worker re-ran with fresher detail.
        if result is not None:
            row.result_json = json.dumps(result, sort_keys=True)
        return row

    allowed = _CMD_ALLOWED.get(row.status, set())
    if new_status not in allowed:
        raise InvalidCommandStateError(
            f"Cannot transition received command {row.id} from "
            f"'{row.status}' to '{new_status}' "
            f"(allowed: {sorted(allowed) or 'none — terminal'})"
        )

    row.status = new_status
    if result is not None:
        row.result_json = json.dumps(result, sort_keys=True)
    if new_status in _CMD_TERMINAL:
        row.completed_at = _utcnow_naive()
    return row
