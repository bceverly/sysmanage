"""
Background message processor for SysManage.
Processes queued messages from agents asynchronously.
"""

import asyncio
import logging
from datetime import timedelta
from typing import Dict, Any

from sqlalchemy.orm import Session

from backend.persistence.db import get_db
from backend.websocket.queue_manager import (
    server_queue_manager,
    QueueDirection,
    QueueStatus,
)
from backend.websocket.messages import MessageType
from backend.api.data_handlers import (
    handle_os_version_update,
    handle_hardware_update,
    handle_user_access_update,
    handle_software_update,
    handle_package_updates_update,
)
from backend.i18n import _

logger = logging.getLogger(__name__)


class MessageProcessor:
    """
    Background service that processes queued messages from agents.

    This service runs continuously, dequeuing messages and processing them
    using the appropriate handlers. It ensures reliable processing of
    agent data updates without blocking WebSocket connections.
    """

    def __init__(self):
        """Initialize the message processor."""
        self.running = False
        self.process_interval = 1.0  # Process messages every second

    async def start(self):
        """Start the background message processing loop."""
        # Use both logger and print to ensure we see the message
        logger.info("DEBUG: MessageProcessor.start() called")
        print("DEBUG: MessageProcessor.start() called", flush=True)

        if self.running:
            logger.info("DEBUG: MessageProcessor already running, returning early")
            print(
                "DEBUG: MessageProcessor already running, returning early", flush=True
            )
            return

        self.running = True
        logger.info(_("Message processor started"))
        print("DEBUG: Message processor started - running flag set to True", flush=True)

        cycle_count = 0
        try:
            while self.running:
                cycle_count += 1
                try:
                    print(
                        f"DEBUG: MSGPROC Processing cycle #{cycle_count} - About to call _process_pending_messages()",
                        flush=True,
                    )
                    logger.info(
                        "DEBUG: MSGPROC Processing cycle #%s starting", cycle_count
                    )
                    await self._process_pending_messages()
                    print(
                        f"DEBUG: MSGPROC Processing cycle #{cycle_count} - Finished calling _process_pending_messages()",
                        flush=True,
                    )
                    logger.info(
                        "DEBUG: MSGPROC Processing cycle #%s completed", cycle_count
                    )
                except Exception as e:
                    logger.error(
                        _("Error in message processing loop: %s"), str(e), exc_info=True
                    )
                    print(
                        f"DEBUG: MSGPROC Error in processing cycle #{cycle_count}: {e}",
                        flush=True,
                    )

                # Wait before next processing cycle
                print(
                    f"DEBUG: MSGPROC Cycle #{cycle_count} complete - Sleeping for {self.process_interval} seconds before next cycle",
                    flush=True,
                )
                logger.info(
                    "DEBUG: MSGPROC Cycle #%s complete, sleeping %ss",
                    cycle_count,
                    self.process_interval,
                )
                await asyncio.sleep(self.process_interval)
        except asyncio.CancelledError:
            logger.info(_("Message processor cancelled"))
        finally:
            self.running = False
            logger.info(_("Message processor stopped"))

    def stop(self):
        """Stop the background message processing."""
        self.running = False

    async def _process_pending_messages(self):
        """Process all pending messages in the queue."""
        print("DEBUG: MSGPROC _process_pending_messages() called", flush=True)
        logger.info("DEBUG: MSGPROC _process_pending_messages() called")

        db = next(get_db())
        print(f"DEBUG: MSGPROC Got database session: {db}", flush=True)
        logger.info("DEBUG: MSGPROC Got database session")

        try:
            # Get all hosts with pending or stuck messages
            # For simplicity, we'll process messages for all hosts
            # In a more sophisticated implementation, we could process per-host

            from backend.persistence.models import MessageQueue, Host
            from datetime import datetime, timezone

            # Define stuck message threshold (messages older than 30 seconds)
            stuck_threshold = datetime.now(timezone.utc) - timedelta(seconds=30)

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
                    "DEBUG: MSGPROC Found %s stuck IN_PROGRESS messages, resetting to PENDING",
                    len(stuck_messages),
                )
                print(
                    f"DEBUG: MSGPROC Found {len(stuck_messages)} stuck IN_PROGRESS messages, resetting to PENDING",
                    flush=True,
                )
                for msg in stuck_messages:
                    msg.status = QueueStatus.PENDING
                    msg.started_at = None
                    print(
                        f"DEBUG: MSGPROC Reset message {msg.message_id} from IN_PROGRESS back to PENDING",
                        flush=True,
                    )
                db.commit()

            # Now get all hosts with pending messages (including newly reset ones)
            host_ids = (
                db.query(MessageQueue.host_id)
                .filter(
                    MessageQueue.direction == QueueDirection.INBOUND,
                    MessageQueue.status == QueueStatus.PENDING,
                    MessageQueue.host_id.is_not(None),
                )
                .distinct()
                .limit(10)
                .all()
            )

            print(
                f"DEBUG: MSGPROC Found {len(host_ids)} hosts with pending messages",
                flush=True,
            )
            logger.info(
                "DEBUG: MSGPROC Found %s hosts with pending messages", len(host_ids)
            )

            for (host_id,) in host_ids:
                # Check if host exists and is still approved before processing its messages
                host = db.query(Host).filter(Host.id == host_id).first()
                if not host:
                    logger.warning(
                        _(
                            "Host %s no longer exists, deleting all its messages from queue"
                        ),
                        host_id,
                    )
                    deleted = server_queue_manager.delete_messages_for_host(
                        host_id, db=db
                    )
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
                    deleted = server_queue_manager.delete_messages_for_host(
                        host_id, db=db
                    )
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
                    await self._process_validated_message(message, host, db)

            # Second, handle messages with NULL host_id by extracting hostname from message data
            null_host_messages = (
                db.query(MessageQueue)
                .filter(
                    MessageQueue.direction == QueueDirection.INBOUND,
                    MessageQueue.status == QueueStatus.PENDING,
                    MessageQueue.host_id.is_(None),
                )
                .limit(10)
                .all()
            )

            for message in null_host_messages:
                logger.info(
                    _("Processing message with NULL host_id: %s"), message.message_id
                )

                # Deserialize message data to extract hostname
                try:
                    message_data = server_queue_manager.deserialize_message_data(
                        message
                    )
                    hostname = message_data.get("hostname")

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
                            _(
                                "Host %s not approved (status: %s) for message %s, deleting"
                            ),
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
                        _(
                            "Processing NULL host_id message for approved host %s (ID: %s)"
                        ),
                        hostname,
                        host.id,
                    )
                    await self._process_validated_message(message, host, db)

                except Exception as e:
                    logger.error(
                        _("Error processing NULL host_id message %s: %s"),
                        message.message_id,
                        str(e),
                    )
                    server_queue_manager.mark_failed(
                        message.message_id, f"Processing error: {str(e)}", db=db
                    )

        finally:
            db.close()

    async def _process_message(self, message, db: Session):
        """Process a single queued message."""
        try:
            # Mark message as being processed
            if not server_queue_manager.mark_processing(message.message_id, db=db):
                logger.warning(
                    _("Could not mark message %s as processing"), message.message_id
                )
                return

            # Deserialize message data
            message_data = server_queue_manager.deserialize_message_data(message)

            # Create a mock connection object for handlers that expect it
            mock_connection = MockConnection(message.host_id)

            logger.info(
                _("Processing queued message: %s (type: %s)"),
                message.message_id,
                message.message_type,
            )

            # Route to appropriate handler based on message type
            success = False

            if message.message_type == MessageType.OS_VERSION_UPDATE:
                await handle_os_version_update(db, mock_connection, message_data)
                success = True

            elif message.message_type == MessageType.HARDWARE_UPDATE:
                await handle_hardware_update(db, mock_connection, message_data)
                success = True

            elif message.message_type == MessageType.USER_ACCESS_UPDATE:
                await handle_user_access_update(db, mock_connection, message_data)
                success = True

            elif message.message_type == MessageType.SOFTWARE_INVENTORY_UPDATE:
                await handle_software_update(db, mock_connection, message_data)
                success = True

            elif message.message_type == MessageType.PACKAGE_UPDATES_UPDATE:
                await handle_package_updates_update(db, mock_connection, message_data)
                success = True

            else:
                logger.warning(
                    _("Unknown message type in queue: %s"), message.message_type
                )
                success = False

            if success:
                # Mark message as completed
                server_queue_manager.mark_completed(message.message_id, db=db)
                logger.info(_("Successfully processed message: %s"), message.message_id)
            else:
                # Mark message as failed
                server_queue_manager.mark_failed(
                    message.message_id, error_message="Unknown message type", db=db
                )

        except Exception as e:
            logger.error(
                _("Error processing message %s: %s"), message.message_id, str(e)
            )
            # Mark message as failed for retry
            server_queue_manager.mark_failed(
                message.message_id, error_message=str(e), db=db
            )

    async def _process_validated_message(self, message, host, db: Session):
        """Process a message with pre-validated host information."""
        try:
            print(
                f"MSGPROC_DEBUG: Starting to process message {message.message_id} of type {message.message_type}",
                flush=True,
            )
            logger.info(
                "MSGPROC_DEBUG: Starting to process message %s of type %s",
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
                f"MSGPROC_DEBUG: About to deserialize message data for {message.message_id}",
                flush=True,
            )
            message_data = server_queue_manager.deserialize_message_data(message)
            data_size = len(str(message_data)) if message_data else 0
            data_keys = list(message_data.keys()) if message_data else []
            print(
                f"MSGPROC_DEBUG: Deserialized message data - keys: {data_keys}, size: {data_size} bytes",
                flush=True,
            )
            logger.info(
                "MSGPROC_DEBUG: Deserialized message data - keys: %s, size: %s bytes",
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
            if message.message_type == MessageType.HARDWARE_UPDATE:
                cpu_vendor = message_data.get("cpu_vendor", "N/A")
                cpu_model = message_data.get("cpu_model", "N/A")
                memory_mb = message_data.get("memory_total_mb", "N/A")
                storage_count = len(message_data.get("storage_devices", []))
                print(
                    f"MSGPROC_DEBUG: Hardware data - CPU: {cpu_vendor} {cpu_model}, Memory: {memory_mb} MB, Storage: {storage_count} devices",
                    flush=True,
                )
                logger.info(
                    "MSGPROC_DEBUG: Hardware data - CPU: %s %s, Memory: %s MB, Storage: %s devices",
                    cpu_vendor,
                    cpu_model,
                    memory_mb,
                    storage_count,
                )
            elif message.message_type == MessageType.SOFTWARE_INVENTORY_UPDATE:
                total_packages = message_data.get("total_packages", 0)
                software_packages = message_data.get("software_packages", [])
                print(
                    f"MSGPROC_DEBUG: Software data - Total packages: {total_packages}, Sample: {software_packages[0] if software_packages else 'None'}",
                    flush=True,
                )
                logger.info(
                    "MSGPROC_DEBUG: Software data - Total packages: %s, Sample: %s",
                    total_packages,
                    software_packages[0] if software_packages else "None",
                )
            elif message.message_type == MessageType.USER_ACCESS_UPDATE:
                total_users = message_data.get("total_users", 0)
                total_groups = message_data.get("total_groups", 0)
                print(
                    f"MSGPROC_DEBUG: User access data - Users: {total_users}, Groups: {total_groups}",
                    flush=True,
                )
                logger.info(
                    "MSGPROC_DEBUG: User access data - Users: %s, Groups: %s",
                    total_users,
                    total_groups,
                )

            # Route to appropriate handler based on message type
            success = False

            if message.message_type == MessageType.OS_VERSION_UPDATE:
                print(
                    "MSGPROC_DEBUG: About to call handle_os_version_update", flush=True
                )
                try:
                    await handle_os_version_update(db, mock_connection, message_data)
                    success = True
                    print(
                        "MSGPROC_DEBUG: Successfully processed OS version update",
                        flush=True,
                    )
                except Exception as e:
                    print(
                        f"MSGPROC_DEBUG: ERROR in handle_os_version_update: {e}",
                        flush=True,
                    )
                    logger.error(
                        "MSGPROC_DEBUG: Error in handle_os_version_update: %s",
                        e,
                        exc_info=True,
                    )
                    success = False

            elif message.message_type == MessageType.HARDWARE_UPDATE:
                print("MSGPROC_DEBUG: About to call handle_hardware_update", flush=True)
                try:
                    await handle_hardware_update(db, mock_connection, message_data)
                    success = True
                    print(
                        "MSGPROC_DEBUG: Successfully processed hardware update",
                        flush=True,
                    )
                except Exception as e:
                    print(
                        f"MSGPROC_DEBUG: ERROR in handle_hardware_update: {e}",
                        flush=True,
                    )
                    logger.error(
                        "MSGPROC_DEBUG: Error in handle_hardware_update: %s",
                        e,
                        exc_info=True,
                    )
                    success = False

            elif message.message_type == MessageType.USER_ACCESS_UPDATE:
                print(
                    "MSGPROC_DEBUG: About to call handle_user_access_update",
                    flush=True,
                )
                try:
                    await handle_user_access_update(db, mock_connection, message_data)
                    success = True
                    print(
                        "MSGPROC_DEBUG: Successfully processed user access update",
                        flush=True,
                    )
                except Exception as e:
                    print(
                        f"MSGPROC_DEBUG: ERROR in handle_user_access_update: {e}",
                        flush=True,
                    )
                    logger.error(
                        "MSGPROC_DEBUG: Error in handle_user_access_update: %s",
                        e,
                        exc_info=True,
                    )
                    success = False

            elif message.message_type == MessageType.SOFTWARE_INVENTORY_UPDATE:
                print("MSGPROC_DEBUG: About to call handle_software_update", flush=True)
                try:
                    await handle_software_update(db, mock_connection, message_data)
                    success = True
                    print(
                        "MSGPROC_DEBUG: Successfully processed software inventory update",
                        flush=True,
                    )
                except Exception as e:
                    print(
                        f"MSGPROC_DEBUG: ERROR in handle_software_update: {e}",
                        flush=True,
                    )
                    logger.error(
                        "MSGPROC_DEBUG: Error in handle_software_update: %s",
                        e,
                        exc_info=True,
                    )
                    success = False

            elif message.message_type == MessageType.PACKAGE_UPDATES_UPDATE:
                print(
                    "MSGPROC_DEBUG: About to call handle_package_updates_update",
                    flush=True,
                )
                await handle_package_updates_update(db, mock_connection, message_data)
                success = True
                print(
                    "MSGPROC_DEBUG: Successfully processed package updates", flush=True
                )

            else:
                print(
                    f"MSGPROC_DEBUG: Unknown message type: {message.message_type}",
                    flush=True,
                )
                logger.warning(
                    _("Unknown message type in queue: %s"), message.message_type
                )
                success = False

            if success:
                # Mark message as completed and remove from queue
                print(
                    f"MSGPROC_DEBUG: Marking message {message.message_id} as completed",
                    flush=True,
                )
                server_queue_manager.mark_completed(message.message_id, db=db)
                logger.info(
                    _("Successfully processed and completed message: %s for host %s"),
                    message.message_id,
                    host.fqdn,
                )
                print(
                    f"MSGPROC_DEBUG: Message {message.message_id} marked as completed successfully",
                    flush=True,
                )
            else:
                print(
                    f"MSGPROC_DEBUG: Message {message.message_id} processing failed",
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


class MockConnection:
    """Mock connection object for message handlers that expect a WebSocket connection."""

    def __init__(self, host_id: int):
        self.host_id = host_id
        self.hostname = None  # Will be populated by handlers if needed

    async def send_message(self, message: Dict[str, Any]):
        """Mock send_message method - messages are not sent back during queue processing."""
        logger.debug(
            _("Mock connection: would send message %s"),
            message.get("message_type", "unknown"),
        )


# Global message processor instance
message_processor = MessageProcessor()
