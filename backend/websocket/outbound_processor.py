"""
Outbound message processor for SysManage.
Handles processing and sending of messages from server to agents.
"""

from datetime import datetime, timezone
from typing import Dict

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.utils.verbosity_logger import get_logger
from backend.websocket.queue_manager import (
    QueueDirection,
    QueueStatus,
    server_queue_manager,
)

logger = get_logger(__name__)


async def process_outbound_messages(db: Session) -> None:
    """
    Process outbound messages from the server to agents.

    Args:
        db: Database session
    """
    logger.info("Processing outbound messages")
    print(
        "=== OUTBOUND PROCESSOR: Starting to process outbound messages ===", flush=True
    )

    from backend.persistence.models import Host, MessageQueue

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Get outbound messages for all hosts
    # Only pick up messages that are ready to be processed:
    # - scheduled_at is NULL (immediate), OR
    # - scheduled_at <= now (scheduled time has passed, including retries)
    outbound_messages = (
        db.query(MessageQueue)
        .filter(
            MessageQueue.direction == QueueDirection.OUTBOUND,
            MessageQueue.status == QueueStatus.PENDING,
            MessageQueue.host_id.is_not(None),
            or_(
                MessageQueue.scheduled_at.is_(None),
                MessageQueue.scheduled_at <= now,
            ),
        )
        .order_by(MessageQueue.priority.desc(), MessageQueue.created_at.asc())
        .limit(20)
        .all()
    )

    print(
        f"=== OUTBOUND PROCESSOR: Found {len(outbound_messages)} pending outbound messages ===",
        flush=True,
    )
    for msg in outbound_messages:
        print(
            f"=== OUTBOUND PROCESSOR: Message ID: {msg.message_id}, Type: {msg.message_type}, Host: {msg.host_id}, Status: {msg.status} ===",
            flush=True,
        )
        # Try to deserialize and show command_type if it's a command
        try:
            msg_data = server_queue_manager.deserialize_message_data(msg)
            if (
                msg.message_type == "command"
                and "data" in msg_data
                and "command_type" in msg_data["data"]
            ):
                print(
                    f"=== OUTBOUND PROCESSOR: Command type: {msg_data['data']['command_type']} ===",
                    flush=True,
                )
        except Exception as e:
            print(
                f"=== OUTBOUND PROCESSOR: Could not deserialize message: {e} ===",
                flush=True,
            )

    # Group messages by host for efficient processing
    messages_by_host = {}
    for message in outbound_messages:
        if message.host_id:
            if message.host_id not in messages_by_host:
                messages_by_host[message.host_id] = []
            messages_by_host[message.host_id].append(message)

    # Process messages for each host
    for host_id, host_messages in messages_by_host.items():
        # Check if host exists and is approved
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            logger.warning(
                "Host %d not found, marking outbound messages as failed", host_id
            )
            for message in host_messages:
                server_queue_manager.mark_failed(
                    message.message_id, "Host not found", db=db
                )
            continue

        if host.approval_status != "approved":
            logger.warning(
                "Host %d not approved, marking outbound messages as failed", host_id
            )
            for message in host_messages:
                server_queue_manager.mark_failed(
                    message.message_id,
                    f"Host not approved (status: {host.approval_status})",
                    db=db,
                )
            continue

        # Process each message for this host
        for message in host_messages:
            await process_outbound_message(message, host, db)


async def process_outbound_message(message, host, db: Session) -> None:
    """
    Process a single outbound message.

    Args:
        message: The message queue entry to process
        host: The host to send the message to
        db: Database session
    """
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
        success = False
        if message.message_type == "command":
            success = await send_command_to_agent(
                message_data, host, message.message_id
            )
        else:
            logger.warning("Unknown outbound message type: %s", message.message_type)

        if success:
            # Mark as SENT (not COMPLETED) - wait for agent acknowledgment
            server_queue_manager.mark_sent(message.message_id, db=db)
            # Log details for create_child_host commands to help debug delivery issues
            command_type = message_data.get("data", {}).get("command_type", "unknown")
            if command_type == "create_child_host":
                distribution = (
                    message_data.get("data", {})
                    .get("parameters", {})
                    .get("distribution", "unknown")
                )
                logger.info(
                    "SENT create_child_host command: message_id=%s, distribution=%s, host=%s (awaiting ack)",
                    message.message_id,
                    distribution,
                    host.fqdn,
                )
            else:
                logger.info(
                    "Sent outbound message: %s to host %s (awaiting acknowledgment)",
                    message.message_id,
                    host.fqdn,
                )
        else:
            server_queue_manager.mark_failed(
                message.message_id, "Failed to send message to agent", db=db
            )

    except Exception as e:
        logger.error(
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
        print(
            f"=== OUTBOUND PROCESSOR: About to send command message {queue_message_id} to host {host.fqdn} ===",
            flush=True,
        )
        print(f"=== OUTBOUND PROCESSOR: Command data: {command_data} ===", flush=True)
        success = await connection_manager.send_to_host(host.id, message)
        print(f"=== OUTBOUND PROCESSOR: Send result: {success} ===", flush=True)

        if not success:
            logger.warning(
                "Failed to send command to host %s - agent may not be connected",
                host.fqdn,
            )

        return success

    except Exception as e:
        logger.error("Error sending command to agent: %s", str(e))
        return False
