# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Outbound message processor for SysManage.
Handles processing and sending of messages from server to agents.
"""

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from backend.startup.leadership import multi_process
from backend.utils.verbosity_logger import get_logger
from backend.websocket.queue_manager import (
    QueueDirection,
    QueueStatus,
    server_queue_manager,
)

logger = get_logger(__name__)


# Phase 22.2 outbound starvation.  The pass used to take the global top 20
# pending messages per database: messages held by a closed maintenance window
# or waiting for a polling agent stayed pending at the head of that list and
# could block every other host, and even unblocked a 10,000-host push took 8+
# minutes at 20 a second.  Now it mirrors the inbound drain: oldest-waiting
# host first, a bounded number per host per round, rounds until the time
# budget is spent; a deferred message carries a not-before time
# (``scheduled_at``) so it stops being "due"; hosts on the HTTP poll fallback
# are left to their polls.
OUTBOUND_BUDGET_SECONDS = 0.5
OUTBOUND_HOST_BATCH = 50
OUTBOUND_PER_HOST = 20
MAINTENANCE_RECHECK_SECONDS = 60  # an override or a window opening is seen within this


def _due_outbound(queue_model, now):
    return and_(
        queue_model.direction == QueueDirection.OUTBOUND,
        queue_model.status == QueueStatus.PENDING,
        queue_model.host_id.is_not(None),
        queue_model.expired_at.is_(None),
        or_(queue_model.scheduled_at.is_(None), queue_model.scheduled_at <= now),
    )


def _waiting_hosts(db, now, limit, visited=()):
    """Hosts with due outbound messages, oldest-waiting first -- only those
    this process can deliver to, and not already visited in this drain (a
    host whose message stays pending must not hold the next round's slots)."""
    from backend.persistence.models import Host, MessageQueue  # noqa: PLC0415
    from backend.websocket import poll_presence  # noqa: PLC0415

    query = db.query(MessageQueue.host_id).filter(_due_outbound(MessageQueue, now))
    polling = poll_presence.polling_host_ids()
    skip = list(polling) + list(visited)
    if skip:
        query = query.filter(MessageQueue.host_id.notin_(skip))
    if multi_process():
        # Only the worker holding a host's WebSocket can deliver to it; another
        # worker would find no socket and fail the message.
        local = local_hostnames()
        if not local:
            return []
        query = query.join(Host, Host.id == MessageQueue.host_id).filter(
            func.lower(Host.fqdn).in_(local)
        )
    return [
        host_id
        for (host_id,) in query.group_by(MessageQueue.host_id)
        .order_by(func.min(MessageQueue.created_at))
        .limit(limit)
        .all()
    ]


def _defer(messages, now, reason) -> None:
    from backend.services.maintenance_window_service import (  # noqa: PLC0415
        DEFERRED_MARKER,
    )

    not_before = now + timedelta(seconds=MAINTENANCE_RECHECK_SECONDS)
    for message in messages:
        message.scheduled_at = not_before
        message.error_message = DEFERRED_MARKER  # released by any window change
    logger.info(
        "%s; deferring %d message(s) until %s", reason, len(messages), not_before
    )


async def _send_to_host(db, host_id, now, deadline, seen) -> int:
    """Deliver this host's due messages; returns how many were handled."""
    from backend.persistence.models import Host  # noqa: PLC0415
    from backend.services.maintenance_window_service import (  # noqa: PLC0415
        GATED_MESSAGE_TYPES,
        is_dispatch_allowed,
    )

    messages = [
        message
        for message in server_queue_manager.dequeue_messages_for_host(
            host_id=host_id,
            direction=QueueDirection.OUTBOUND,
            limit=OUTBOUND_PER_HOST,
            db=db,
        )
        if message.message_id not in seen
    ]
    seen.update(message.message_id for message in messages)
    if not messages:
        return 0

    host = db.query(Host).filter(Host.id == host_id).first()
    if host is None or host.approval_status != "approved":
        reason = (
            "Host not found"
            if host is None
            else f"Host not approved (status: {host.approval_status})"
        )
        logger.warning("%s for host %s; failing its outbound messages", reason, host_id)
        for message in messages:
            server_queue_manager.mark_failed(message.message_id, reason, db=db)
        return len(messages)

    # Maintenance-window gating (Phase 14.2): change actions wait while the
    # host is outside its windows or in a blackout; control-plane pushes
    # (e.g. logging_config_update) are never gated.  Deferred with a
    # not-before time, so they stop occupying the drain until it is re-checked.
    gated = [m for m in messages if m.message_type in GATED_MESSAGE_TYPES]
    if gated and not is_dispatch_allowed(db, host_id, now):
        _defer(gated, now, f"Maintenance window closed for host {host.fqdn}")
        messages = [m for m in messages if m.message_type not in GATED_MESSAGE_TYPES]

    sent = 0
    for message in messages:
        await process_outbound_message(message, host, db)
        sent += 1
        if time.monotonic() >= deadline:
            break
    return sent


async def process_outbound_messages(db: Session) -> bool:  # NOSONAR
    """Deliver due outbound messages within this call's time budget.

    Returns True when it stopped with work still waiting, so the caller can
    come straight back instead of sleeping."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    deadline = time.monotonic() + OUTBOUND_BUDGET_SECONDS
    seen, visited = set(), set()
    while time.monotonic() < deadline:
        host_ids = _waiting_hosts(db, now, OUTBOUND_HOST_BATCH, visited)
        if not host_ids:
            return False
        for host_id in host_ids:
            if time.monotonic() >= deadline:
                return True
            visited.add(host_id)
            await _send_to_host(db, host_id, now, deadline, seen)
    return True


def local_hostnames() -> list:
    """Lower-cased hostnames of the agents connected to THIS process."""
    from backend.websocket.connection_manager import (  # noqa: PLC0415
        connection_manager,
    )

    return sorted({name.lower() for name in connection_manager.hostname_to_agent})


def _log_command_sent(message, message_data, host) -> None:
    """Emit the SENT log line for a command; extra create_child_host detail to
    aid delivery debugging."""
    command_type = message_data.get("data", {}).get("command_type", "unknown")
    if command_type != "create_child_host":
        logger.info(
            "Sent outbound message: %s to host %s (awaiting ack)",
            message.message_id,
            host.fqdn,
        )
        return
    params = message_data.get("data", {}).get("parameters", {})
    distribution = params.get("distribution", "unknown")
    child_name = params.get("vm_name") or params.get("container_name") or distribution
    logger.info(
        "SENT create_child_host command to agent: "
        "message_id=%s, child_name=%s, child_type=%s, "
        "distribution=%s, hostname=%s, host=%s (awaiting ack)",
        message.message_id,
        child_name,
        params.get("child_type", "unknown"),
        distribution,
        params.get("hostname", "unknown"),
        host.fqdn,
    )


def _awaiting_poll(host) -> bool:
    """True when ``host`` has no WebSocket but is polling over HTTP."""
    from backend.websocket import poll_presence  # noqa: PLC0415
    from backend.websocket.connection_manager import (  # noqa: PLC0415
        connection_manager,
    )

    if connection_manager.get_agent_by_hostname(host.fqdn):
        return False
    return poll_presence.recently_polled(host.id)


async def process_outbound_message(message, host, db: Session) -> None:
    """
    Process a single outbound message.

    Args:
        message: The message queue entry to process
        host: The host to send the message to
        db: Database session
    """
    if _awaiting_poll(host):
        # No socket, but the agent is on the HTTP fallback: leave the message
        # PENDING so its next poll collects it (see poll_presence).
        return
    try:
        # Mark message as processing
        if not server_queue_manager.mark_processing(message.message_id, db=db):
            logger.warning(
                "Could not mark outbound message %s as processing",
                message.message_id,
            )
            return

        # Deserialize message data
        message_data = server_queue_manager.deserialize_message_data(message)

        logger.info(
            "Processing outbound message: %s (type: %s) for host %s",
            message.message_id,
            message.message_type,
            host.fqdn,
        )

        # Handle different types of outbound messages
        if message.message_type == "command":
            success = await send_command_to_agent(
                message_data, host, message.message_id
            )
            if success:
                # Mark as SENT (not COMPLETED) - wait for agent acknowledgment
                server_queue_manager.mark_sent(message.message_id, db=db)
                _log_command_sent(message, message_data, host)
            else:
                server_queue_manager.mark_failed(
                    message.message_id, "Failed to send message to agent", db=db
                )
        elif message.message_type == "logging_config_update":
            # Fire-and-forget config push: the agent applies it and does not
            # send an acknowledgment, so mark COMPLETED on a successful send
            # rather than SENT-awaiting-ack (which would retry forever).
            success = await send_message_to_agent(
                message_data, host, message.message_id
            )
            if success:
                server_queue_manager.mark_completed(message.message_id, db=db)
                logger.info("Sent logging_config_update to host %s", host.fqdn)
            else:
                server_queue_manager.mark_failed(
                    message.message_id, "Failed to send message to agent", db=db
                )
        else:
            logger.warning("Unknown outbound message type: %s", message.message_type)
            server_queue_manager.mark_failed(
                message.message_id,
                f"Unknown outbound message type: {message.message_type}",
                db=db,
            )

    except Exception as e:
        logger.exception(
            "Error processing outbound message %s: %s", message.message_id, str(e)
        )
        server_queue_manager.mark_failed(
            message.message_id, f"Processing error: {str(e)}", db=db
        )


async def send_command_to_agent(
    command_data: dict, host, queue_message_id: str
) -> bool:
    """
    Send a command message to an agent.

    Args:
        command_data: The command data to send
        host: The host to send the command to
        queue_message_id: The queue message ID (for acknowledgment tracking)

    Returns:
        True if command was sent successfully, False otherwise
    """
    from backend.websocket.connection_manager import connection_manager

    try:
        # The command_data is already a properly formatted message from create_command_message
        # called in the API endpoints, so we can send it directly without wrapping again
        message = command_data.copy()
        # Add the queue message_id so the agent knows which ID to acknowledge
        message["queue_message_id"] = queue_message_id

        # Send via connection manager
        logger.info(
            "Sending command message %s to host %s (%s)",
            queue_message_id,
            host.id,
            host.fqdn,
        )
        success = await connection_manager.send_to_host(host.id, message)

        if not success:
            logger.warning(
                "Failed to send command to host %s - agent may not be connected",
                host.fqdn,
            )

        return success

    except Exception as e:
        logger.exception("Error sending command to agent: %s", str(e))
        return False


async def send_message_to_agent(
    message_data: dict, host, queue_message_id: str
) -> bool:
    """Send a non-command server message (e.g. logging_config_update) to an agent.

    The message_data is already a full message envelope; we attach the queue id
    and deliver it over the agent's websocket connection.  Returns True on a
    successful send (the agent may or may not acknowledge, depending on type).
    """
    from backend.websocket.connection_manager import connection_manager

    try:
        message = message_data.copy()
        message["queue_message_id"] = queue_message_id
        logger.info(
            "Sending %s message %s to host %s (%s)",
            message.get("message_type"),
            queue_message_id,
            host.id,
            host.fqdn,
        )
        success = await connection_manager.send_to_host(host.id, message)
        if not success:
            logger.warning(
                "Failed to send %s to host %s - agent may not be connected",
                message.get("message_type"),
                host.fqdn,
            )
        return success
    except Exception as e:
        logger.exception("Error sending message to agent: %s", str(e))
        return False
