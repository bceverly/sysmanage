# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Site-side actuation of coordinator-dispatched commands (Phase 12.2).

When a coordinator dispatches a command (reboot, apply_updates,
deploy_packages, run_script, …) it is pushed down to the site and
lands in the ``federation_received_commands`` inbox in status
``queued`` (see ``federation_inbox_service``).  Something on the site
then has to actually *run* that command against the site's local
agents and report the outcome back up.  This module is that
"something" — the **command-fanout** half of the site's actuation
loop.  The Pro+ ``federation_site_engine`` background worker calls
:func:`fanout_queued_commands` each tick.

Architecture — *everything is queued, nothing is called directly* so
the path survives network outages on both legs:

  1. **Fan-out (this server → its agents).**  For each queued
     received-command we resolve the target hosts and, for each,
     enqueue a normal outbound ``command`` message via the same
     ``QueueOperations`` path a local operator uses
     (``backend/api/fleet.py``).  A background thread delivers it to
     the agent when the agent is reachable; an offline agent gets it
     on reconnect.  We register a correlation in ``proplus_dispatch``
     so the agent's eventual ``command_result`` routes back here.
     The received-command transitions ``queued`` → ``in_progress``.

  2. **Report-back (agent → this server → coordinator).**  When an
     agent's result returns, ``route_proplus_command_result`` calls
     :func:`record_command_host_result`.  Once every dispatched host
     has reported, we transition the received-command to its terminal
     state and enqueue a ``command_result`` packet onto the federation
     *sync* queue.  The site's outbound sync worker (already built)
     pushes that packet up to the coordinator on its next cycle — so
     the upstream leg is queued too, never a blocking call.

No direct HTTP is performed anywhere in this module.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import federation_inbox_service as inbox_svc
from backend.services import federation_sync_queue_service as sync_svc
from backend.websocket.messages import CommandMessage, CommandType
from backend.websocket.queue_enums import QueueDirection

logger = logging.getLogger(__name__)

# Federated command verbs (as dispatched by the coordinator) mapped to
# the local agent ``CommandType``.  A coordinator may also dispatch a
# literal local CommandType value; :func:`_resolve_command_type` accepts
# either form so the vocabulary can grow coordinator-side without a
# site-side code change for pass-through verbs.
_FEDERATED_COMMAND_MAP = {
    "reboot": CommandType.REBOOT_SYSTEM,
    "reboot_system": CommandType.REBOOT_SYSTEM,
    "apply_updates": CommandType.APPLY_UPDATES,
    "update_system": CommandType.UPDATE_SYSTEM,
    "deploy_packages": CommandType.INSTALL_PACKAGE,
    "install_package": CommandType.INSTALL_PACKAGE,
    "run_script": CommandType.EXECUTE_SCRIPT,
    "execute_script": CommandType.EXECUTE_SCRIPT,
    "execute_shell": CommandType.EXECUTE_SHELL,
}


class UnsupportedFederatedCommandError(ValueError):
    """Raised when a received command_type has no local CommandType mapping."""


def _resolve_command_type(command_type: str) -> CommandType:
    key = (command_type or "").strip().lower()
    mapped = _FEDERATED_COMMAND_MAP.get(key)
    if mapped is not None:
        return mapped
    # Accept a literal local CommandType value (e.g. "restart_service").
    try:
        return CommandType(key)
    except ValueError as exc:
        raise UnsupportedFederatedCommandError(
            f"No local command mapping for federated command_type '{command_type}'"
        ) from exc


def _parse_target_ids(cmd: "models.FederationReceivedCommand") -> Optional[List[str]]:
    """Explicit target host ids, or ``None`` meaning 'all local hosts'."""
    raw = getattr(cmd, "target_host_ids_json", None)
    if not raw:
        return None
    try:
        ids = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return [str(h) for h in ids] if ids else None


def _resolve_target_hosts(
    session: Session, target_ids: Optional[List[str]]
) -> Tuple[List[Any], List[str]]:
    """Resolve a command's targets to local ``Host`` rows.

    Returns ``(hosts, missing_ids)``.  Explicit ids that don't resolve
    to an approved host are returned in ``missing_ids`` so the caller
    can record them as immediate failures (and still reach a terminal
    aggregate once the resolvable hosts report).  ``None`` target_ids
    means "every approved, active host at this site".
    """
    if target_ids is None:
        hosts = (
            session.query(models.Host)
            .filter(models.Host.approval_status == "approved")
            .filter(models.Host.active.is_(True))
            .all()
        )
        return hosts, []

    hosts = []
    missing: List[str] = []
    for hid in target_ids:
        host = (
            session.query(models.Host)
            .filter(models.Host.id == hid)
            .filter(models.Host.approval_status == "approved")
            .first()
        )
        if host is None:
            missing.append(hid)
        else:
            hosts.append(host)
    return hosts, missing


def _enqueue_local_command(
    session: Session,
    *,
    host_id: str,
    command_type: CommandType,
    parameters: Dict[str, Any],
    timeout: int,
    queue_ops: Any,
) -> str:
    """Queue one outbound agent command; return the message_id used.

    The queue-row id is pinned to the ``CommandMessage``'s own
    ``message_id`` so the id the agent echoes back in
    ``command_result.command_id`` is exactly our correlation key
    (mirrors ``proplus_dispatch._enqueue_apply_plan``).
    """
    cmd_message = CommandMessage(command_type, parameters, timeout)
    queue_ops.enqueue_message(
        message_type="command",
        message_data=cmd_message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host_id),
        message_id=cmd_message.message_id,
        db=session,
    )
    return cmd_message.message_id


def fanout_queued_commands(
    session: Session,
    *,
    limit: int = 50,
    default_timeout: int = 300,
    queue_ops: Any = None,
) -> Dict[str, Any]:
    """Drain queued received-commands and fan each out to local agents.

    Idempotent per tick: only ``queued`` commands are picked up, and a
    command is advanced to ``in_progress`` before this function returns,
    so a re-entrant tick never double-dispatches.  Returns a summary
    ``{"dispatched": n_commands, "messages": n_agent_messages,
       "failed": n_commands_failed}``.  Best-effort per command — one
    bad command never blocks the rest.
    """
    if queue_ops is None:
        from backend.websocket.queue_operations import (  # pylint: disable=import-outside-toplevel
            QueueOperations,
        )

        queue_ops = QueueOperations()

    from backend.services.proplus_dispatch import (  # pylint: disable=import-outside-toplevel
        register_federation_command_correlation,
    )

    summary = {"dispatched": 0, "messages": 0, "failed": 0}
    queued = inbox_svc.list_queued_commands(session, limit=limit)
    for cmd in queued:
        fed_id = str(cmd.id)
        try:
            command_type = _resolve_command_type(cmd.command_type)
        except UnsupportedFederatedCommandError as exc:
            _fail_command(session, cmd, error=str(exc))
            summary["failed"] += 1
            continue

        try:
            parameters = json.loads(cmd.parameters_json or "{}")
        except (ValueError, TypeError):
            parameters = {}

        target_ids = _parse_target_ids(cmd)
        hosts, missing = _resolve_target_hosts(session, target_ids)

        if not hosts and not missing:
            _fail_command(session, cmd, error="no target hosts resolved")
            summary["failed"] += 1
            continue

        # Move to in_progress and seed progress BEFORE dispatching so a
        # result that races back finds a consistent target set.
        dispatched_ids = [str(h.id) for h in hosts]
        progress = {
            "target_host_ids": dispatched_ids + missing,
            "results": {
                hid: {"success": False, "detail": "host not found"} for hid in missing
            },
        }
        cmd.result_json = json.dumps(progress, sort_keys=True)
        inbox_svc.update_command_status(
            session, cmd.id, new_status=inbox_svc.CMD_STATUS_IN_PROGRESS
        )

        for host in hosts:
            message_id = _enqueue_local_command(
                session,
                host_id=str(host.id),
                command_type=command_type,
                parameters=parameters,
                timeout=default_timeout,
                queue_ops=queue_ops,
            )
            register_federation_command_correlation(message_id, fed_id, str(host.id))
            summary["messages"] += 1

        summary["dispatched"] += 1

        # A command whose only targets were all unresolvable is already
        # fully "reported" — settle it immediately.
        if not hosts and missing:
            _settle_if_complete(session, cmd.id)

    session.commit()
    logger.info(
        "Federation command fan-out: %s dispatched, %s agent messages, %s failed",
        summary["dispatched"],
        summary["messages"],
        summary["failed"],
    )
    return summary


def record_command_host_result(
    session: Session,
    federated_command_id: Any,
    host_id: str,
    *,
    success: bool,
    detail: Optional[str] = None,
) -> None:
    """Record one host's outcome for a dispatched federated command.

    Called from ``route_proplus_command_result`` when an agent's
    ``command_result`` correlates to a federation dispatch.  Idempotent
    on replays and terminal commands.  When the last outstanding host
    reports, the command is settled and a ``command_result`` packet is
    enqueued onto the sync queue for the coordinator.
    """
    try:
        cmd = inbox_svc.get_received_command(session, federated_command_id)
    except inbox_svc.ReceivedCommandNotFoundError:
        return
    if cmd.status in (inbox_svc.CMD_STATUS_COMPLETED, inbox_svc.CMD_STATUS_FAILED):
        return

    try:
        progress = json.loads(cmd.result_json or "{}")
    except (ValueError, TypeError):
        progress = {}
    progress.setdefault("target_host_ids", [])
    results = progress.setdefault("results", {})
    results[str(host_id)] = {"success": bool(success), "detail": detail or ""}
    cmd.result_json = json.dumps(progress, sort_keys=True)

    _settle_if_complete(session, cmd.id)
    session.commit()


def _settle_if_complete(session: Session, federated_command_id: Any) -> None:
    """Transition to terminal + enqueue the upstream packet once all in."""
    cmd = inbox_svc.get_received_command(session, federated_command_id)
    try:
        progress = json.loads(cmd.result_json or "{}")
    except (ValueError, TypeError):
        return
    targets = progress.get("target_host_ids") or []
    results = progress.get("results") or {}
    if not targets or len(results) < len(targets):
        return  # still waiting on at least one host

    all_ok = all(r.get("success") for r in results.values())
    new_status = (
        inbox_svc.CMD_STATUS_COMPLETED if all_ok else inbox_svc.CMD_STATUS_FAILED
    )
    aggregate = {
        "status": new_status,
        "host_count": len(targets),
        "success_count": sum(1 for r in results.values() if r.get("success")),
        "results": results,
    }
    inbox_svc.update_command_status(
        session, cmd.id, new_status=new_status, result=aggregate
    )
    _enqueue_result_upstream(session, str(cmd.id), aggregate)


def _enqueue_result_upstream(
    session: Session, federated_command_id: str, aggregate: Dict[str, Any]
) -> None:
    """Queue the command_result packet for the outbound sync worker."""
    sync_svc.enqueue(
        session,
        payload_type="command_result",
        payload={"command_id": federated_command_id, **aggregate},
        dedup_key=f"command_result:{federated_command_id}",
    )


def _fail_command(
    session: Session, cmd: "models.FederationReceivedCommand", *, error: str
) -> None:
    """Mark a received command failed and queue the failure upstream.

    Used for pre-dispatch failures (unmappable command_type, no targets)
    where there is nothing to wait on.  ``queued`` → ``failed`` is a
    legal FSM edge, so no intermediate ``in_progress`` is needed.
    """
    aggregate = {"status": inbox_svc.CMD_STATUS_FAILED, "error": error, "results": {}}
    inbox_svc.update_command_status(
        session, cmd.id, new_status=inbox_svc.CMD_STATUS_FAILED, result=aggregate
    )
    _enqueue_result_upstream(session, str(cmd.id), aggregate)
    logger.warning("Federation command %s failed pre-dispatch: %s", cmd.id, error)
