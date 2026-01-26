"""
Inbound message processor for SysManage.
Handles processing of messages received from agents.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.utils.verbosity_logger import get_logger
from backend.websocket.message_router import log_message_data, route_inbound_message
from backend.websocket.mock_connection import MockConnection
from backend.websocket.queue_manager import (
    QueueDirection,
    QueueStatus,
    server_queue_manager,
)

logger = get_logger(__name__)


async def process_pending_messages(
    db: Session,
) -> None:  # NOSONAR - cognitive complexity
    """
    Process all pending messages in the queue.

    Args:
        db: Database session
    """
    print("_process_pending_messages() called", flush=True)
    logger.info("_process_pending_messages() called")

    # Expire all cached objects to ensure we get fresh data from the database
    # This prevents stale objects from being returned by queries
    db.expire_all()

    print(f"Got database session: {db}", flush=True)
    logger.info("Got database session")

    # First, expire old messages to prevent infinite processing loops
    expired_count = server_queue_manager.expire_old_messages(db)
    if expired_count > 0:
        logger.info("Expired %d old messages", expired_count)

    from backend.persistence.models import Host, MessageQueue

    # Define stuck message threshold (messages older than 30 seconds)
    stuck_threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        seconds=30
    )

    # First, reset stuck IN_PROGRESS messages back to PENDING
    stuck_messages = (
        db.query(MessageQueue)
        .filter(
            MessageQueue.direction == QueueDirection.INBOUND,
            MessageQueue.status == QueueStatus.IN_PROGRESS,
            MessageQueue.started_at < stuck_threshold,
        )
        .all()
    )

    if stuck_messages:
        logger.warning(
            "Found %s stuck IN_PROGRESS messages, resetting to PENDING",
            len(stuck_messages),
        )
        print(
            f"Found {len(stuck_messages)} stuck IN_PROGRESS messages, resetting to PENDING",
            flush=True,
        )
        for msg in stuck_messages:
            msg.status = QueueStatus.PENDING
            msg.started_at = None
            print(
                f"Reset message {msg.message_id} from IN_PROGRESS back to PENDING",
                flush=True,
            )
        db.commit()

    # Now get all hosts with pending messages (including newly reset ones)
    # Exclude expired messages from processing
    host_ids = (
        db.query(MessageQueue.host_id)
        .filter(
            MessageQueue.direction == QueueDirection.INBOUND,
            MessageQueue.status == QueueStatus.PENDING,
            MessageQueue.host_id.is_not(None),
            MessageQueue.expired_at.is_(None),
        )
        .distinct()
        .limit(10)
        .all()
    )

    print(
        f"Found {len(host_ids)} hosts with pending messages",
        flush=True,
    )
    logger.info("Found %s hosts with pending messages", len(host_ids))

    for (host_id,) in host_ids:
        # Check if host exists and is still approved before processing its messages
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            logger.warning(
                _("Host %s no longer exists, deleting all its messages from queue"),
                host_id,
            )
            deleted = server_queue_manager.delete_messages_for_host(host_id, db=db)
            logger.info(
                _("Deleted %d messages for non-existent host %s"),
                deleted,
                host_id,
            )
            continue

        if host.approval_status != "approved":
            logger.warning(
                _(
                    "Host %s (FQDN: %s) no longer approved (status: %s), deleting all its messages from queue"
                ),
                host_id,
                host.fqdn,
                host.approval_status,
            )
            deleted = server_queue_manager.delete_messages_for_host(host_id, db=db)
            logger.info(
                _("Deleted %d messages for unapproved host %s"),
                deleted,
                host_id,
            )
            continue

        # Host exists and is approved - process its messages
        logger.info(
            _("Processing messages for approved host %s (FQDN: %s)"),
            host_id,
            host.fqdn,
        )
        host_messages = server_queue_manager.dequeue_messages_for_host(
            host_id=host_id, direction=QueueDirection.INBOUND, limit=10, db=db
        )

        for message in host_messages:
            await process_validated_message(message, host, db)

    # Second, handle messages with NULL host_id by extracting hostname from message data
    # Exclude expired messages from processing
    null_host_messages = (
        db.query(MessageQueue)
        .filter(
            MessageQueue.direction == QueueDirection.INBOUND,
            MessageQueue.status == QueueStatus.PENDING,
            MessageQueue.host_id.is_(None),
            MessageQueue.expired_at.is_(None),
        )
        .limit(10)
        .all()
    )

    for message in null_host_messages:
        logger.info(_("Processing message with NULL host_id: %s"), message.message_id)

        # Deserialize message data to extract hostname
        try:
            message_data = server_queue_manager.deserialize_message_data(message)

            # Check if this is a SYSTEM_INFO message (registration) - these don't require host lookup
            from backend.websocket.messages import MessageType

            if message.message_type == MessageType.SYSTEM_INFO:
                logger.info(
                    _("Processing SYSTEM_INFO registration message %s"),
                    message.message_id,
                )
                # SYSTEM_INFO messages are processed without host validation
                # The handler will create/update the host record
                await process_system_info_message(message, db)
                continue

            hostname = message_data.get("hostname")

            # Try connection info if no hostname in message data
            if not hostname:
                connection_info = message_data.get("_connection_info", {})
                hostname = connection_info.get("hostname")

            if not hostname:
                logger.warning(
                    _("Message %s missing hostname, deleting"),
                    message.message_id,
                )
                server_queue_manager.mark_failed(
                    message.message_id,
                    "Missing hostname in message data",
                    db=db,
                )
                continue

            # Look up host by hostname
            host = db.query(Host).filter(Host.fqdn == hostname).first()

            if not host:
                logger.warning(
                    _("Host %s not found for message %s, deleting"),
                    hostname,
                    message.message_id,
                )
                server_queue_manager.mark_failed(
                    message.message_id, f"Host {hostname} not found", db=db
                )
                continue

            if host.approval_status != "approved":
                logger.warning(
                    _("Host %s not approved (status: %s) for message %s, deleting"),
                    hostname,
                    host.approval_status,
                    message.message_id,
                )
                server_queue_manager.mark_failed(
                    message.message_id, f"Host {hostname} not approved", db=db
                )
                continue

            # Host is valid and approved - process the message
            logger.info(
                _("Processing NULL host_id message for approved host %s (ID: %s)"),
                hostname,
                host.id,
            )
            await process_validated_message(message, host, db)

        except Exception as e:
            logger.error(
                _("Error processing NULL host_id message %s: %s"),
                message.message_id,
                str(e),
            )
            server_queue_manager.mark_failed(
                message.message_id, f"Processing error: {str(e)}", db=db
            )


async def process_validated_message(message, host, db: Session) -> None:
    """
    Process a message with pre-validated host information.

    Args:
        message: The message queue entry to process
        host: The validated host object
        db: Database session
    """
    try:
        print(
            f"Starting to process message {message.message_id} of type {message.message_type}",
            flush=True,
        )
        logger.info(
            "Starting to process message %s of type %s",
            message.message_id,
            message.message_type,
        )

        # Mark message as being processed
        if not server_queue_manager.mark_processing(message.message_id, db=db):
            logger.warning(
                _("Could not mark message %s as processing"), message.message_id
            )
            return

        # Deserialize message data
        print(
            f"About to deserialize message data for {message.message_id}",
            flush=True,
        )
        message_data = server_queue_manager.deserialize_message_data(message)
        data_size = len(str(message_data)) if message_data else 0
        data_keys = list(message_data.keys()) if message_data else []
        print(
            f"Deserialized message data - keys: {data_keys}, size: {data_size} bytes",
            flush=True,
        )
        logger.info(
            "Deserialized message data - keys: %s, size: %s bytes",
            data_keys,
            data_size,
        )

        # Create connection object with host info
        mock_connection = MockConnection(host.id)
        mock_connection.hostname = host.fqdn

        logger.info(
            _("Processing queued message: %s (type: %s, host: %s)"),
            message.message_id,
            message.message_type,
            host.fqdn,
        )

        # Log specific data for different message types
        log_message_data(message.message_type, message_data)

        # Route to appropriate handler based on message type
        success = await route_inbound_message(
            message.message_type, db, mock_connection, message_data
        )

        if success:
            # Mark message as completed and remove from queue
            print(
                f"Marking message {message.message_id} as completed",
                flush=True,
            )
            server_queue_manager.mark_completed(message.message_id, db=db)
            logger.info(
                _("Successfully processed and completed message: %s for host %s"),
                message.message_id,
                host.fqdn,
            )
            print(
                f"Message {message.message_id} marked as completed successfully",
                flush=True,
            )
        else:
            print(
                f"Message {message.message_id} processing failed",
                flush=True,
            )
            # Mark message as failed and remove from queue
            server_queue_manager.mark_failed(
                message.message_id, error_message="Unknown message type", db=db
            )
            logger.error(
                _("Failed to process message %s: unknown message type"),
                message.message_id,
            )

    except Exception as e:
        logger.error(
            _("Error processing message %s for host %s: %s"),
            message.message_id,
            host.fqdn,
            str(e),
        )
        # Mark message as failed and remove from queue
        server_queue_manager.mark_failed(
            message.message_id, error_message=str(e), db=db
        )


async def process_system_info_message(message, db: Session) -> None:
    """
    Process a SYSTEM_INFO registration message.
    This is special because the host may not exist yet.
    """
    try:
        logger.info("Processing SYSTEM_INFO message %s", message.message_id)

        # Mark message as being processed
        if not server_queue_manager.mark_processing(message.message_id, db=db):
            logger.warning(
                _("Could not mark SYSTEM_INFO message %s as processing"),
                message.message_id,
            )
            return

        # Deserialize message data
        message_data = server_queue_manager.deserialize_message_data(message)

        # Extract connection info
        connection_info = message_data.get("_connection_info", {})

        # Create a mock connection with the stored connection info
        mock_connection = MockConnection(None)  # No host_id yet
        mock_connection.agent_id = connection_info.get("agent_id")
        mock_connection.hostname = connection_info.get("hostname")
        mock_connection.ipv4 = connection_info.get("ipv4")
        mock_connection.ipv6 = connection_info.get("ipv6")
        mock_connection.platform = connection_info.get("platform")

        # Call the system_info handler
        from backend.api.message_handlers import handle_system_info

        _response = await handle_system_info(db, mock_connection, message_data)

        # Mark as completed
        server_queue_manager.mark_completed(message.message_id, db=db)
        logger.info("Successfully processed SYSTEM_INFO message %s", message.message_id)

    except Exception as e:
        logger.error(
            _("Error processing SYSTEM_INFO message %s: %s"),
            message.message_id,
            str(e),
            exc_info=True,
        )
        server_queue_manager.mark_failed(
            message.message_id, error_message=str(e), db=db
        )
