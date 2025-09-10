"""
Background message processor for SysManage.
Processes queued messages from agents asynchronously.
"""

import asyncio
from datetime import timedelta
from typing import Dict, Any

from sqlalchemy.orm import Session

from backend.persistence.db import get_db
from backend.utils.verbosity_logger import get_logger
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
    handle_script_execution_result,
    handle_reboot_status_update,
)
from backend.i18n import _

logger = get_logger(__name__)


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
                        f"Processing cycle #{cycle_count} - About to call _process_pending_messages()",
                        flush=True,
                    )
                    logger.info("Processing cycle #%s starting", cycle_count)
                    await self._process_pending_messages()
                    print(
                        f"Processing cycle #{cycle_count} - Finished calling _process_pending_messages()",
                        flush=True,
                    )
                    logger.info("Processing cycle #%s completed", cycle_count)
                except Exception as e:
                    logger.error(
                        _("Error in message processing loop: %s"), str(e), exc_info=True
                    )
                    print(
                        f"Error in processing cycle #{cycle_count}: {e}",
                        flush=True,
                    )

                # Wait before next processing cycle
                print(
                    f"Cycle #{cycle_count} complete - Sleeping for {self.process_interval} seconds before next cycle",
                    flush=True,
                )
                logger.info(
                    "Cycle #%s complete, sleeping %ss",
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
        print("_process_pending_messages() called", flush=True)
        logger.info("_process_pending_messages() called")

        db = next(get_db())
        print(f"Got database session: {db}", flush=True)
        logger.info("Got database session")

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
                f"Found {len(host_ids)} hosts with pending messages",
                flush=True,
            )
            logger.info("Found %s hosts with pending messages", len(host_ids))

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

            # Third, process outbound messages (from server to agents)
            await self._process_outbound_messages(db)

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

            # Debug: Show message type comparison
            logger.info(
                "message_type='%s', SCRIPT_EXECUTION_RESULT='%s', equal=%s",
                message.message_type,
                MessageType.SCRIPT_EXECUTION_RESULT,
                message.message_type == MessageType.SCRIPT_EXECUTION_RESULT,
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

            elif message.message_type == MessageType.SCRIPT_EXECUTION_RESULT:
                logger.info("Processing SCRIPT_EXECUTION_RESULT")
                await handle_script_execution_result(db, mock_connection, message_data)
                success = True

            elif message.message_type == MessageType.REBOOT_STATUS_UPDATE:
                logger.info("Processing REBOOT_STATUS_UPDATE")
                await handle_reboot_status_update(db, mock_connection, message_data)
                success = True

            else:
                logger.warning(
                    _("Unknown message type in queue: %s (expected: %s)"),
                    message.message_type,
                    MessageType.SCRIPT_EXECUTION_RESULT,
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
            if message.message_type == MessageType.HARDWARE_UPDATE:
                cpu_vendor = message_data.get("cpu_vendor", "N/A")
                cpu_model = message_data.get("cpu_model", "N/A")
                memory_mb = message_data.get("memory_total_mb", "N/A")
                storage_count = len(message_data.get("storage_devices", []))
                print(
                    f"Hardware data - CPU: {cpu_vendor} {cpu_model}, Memory: {memory_mb} MB, Storage: {storage_count} devices",
                    flush=True,
                )
                logger.info(
                    "Hardware data - CPU: %s %s, Memory: %s MB, Storage: %s devices",
                    cpu_vendor,
                    cpu_model,
                    memory_mb,
                    storage_count,
                )
            elif message.message_type == MessageType.SOFTWARE_INVENTORY_UPDATE:
                total_packages = message_data.get("total_packages", 0)
                software_packages = message_data.get("software_packages", [])
                print(
                    f"Software data - Total packages: {total_packages}, Sample: {software_packages[0] if software_packages else 'None'}",
                    flush=True,
                )
                logger.info(
                    "Software data - Total packages: %s, Sample: %s",
                    total_packages,
                    software_packages[0] if software_packages else "None",
                )
            elif message.message_type == MessageType.USER_ACCESS_UPDATE:
                total_users = message_data.get("total_users", 0)
                total_groups = message_data.get("total_groups", 0)
                print(
                    f"User access data - Users: {total_users}, Groups: {total_groups}",
                    flush=True,
                )
                logger.info(
                    "User access data - Users: %s, Groups: %s",
                    total_users,
                    total_groups,
                )

            # Route to appropriate handler based on message type
            success = False

            if message.message_type == MessageType.OS_VERSION_UPDATE:
                print("About to call handle_os_version_update", flush=True)
                try:
                    await handle_os_version_update(db, mock_connection, message_data)
                    success = True
                    print(
                        "Successfully processed OS version update",
                        flush=True,
                    )
                except Exception as e:
                    print(
                        f"ERROR in handle_os_version_update: {e}",
                        flush=True,
                    )
                    logger.error(
                        "Error in handle_os_version_update: %s",
                        e,
                        exc_info=True,
                    )
                    success = False

            elif message.message_type == MessageType.HARDWARE_UPDATE:
                print("About to call handle_hardware_update", flush=True)
                try:
                    await handle_hardware_update(db, mock_connection, message_data)
                    success = True
                    print(
                        "Successfully processed hardware update",
                        flush=True,
                    )
                except Exception as e:
                    print(
                        f"ERROR in handle_hardware_update: {e}",
                        flush=True,
                    )
                    logger.error(
                        "Error in handle_hardware_update: %s",
                        e,
                        exc_info=True,
                    )
                    success = False

            elif message.message_type == MessageType.USER_ACCESS_UPDATE:
                print(
                    "About to call handle_user_access_update",
                    flush=True,
                )
                try:
                    await handle_user_access_update(db, mock_connection, message_data)
                    success = True
                    print(
                        "Successfully processed user access update",
                        flush=True,
                    )
                except Exception as e:
                    print(
                        f"ERROR in handle_user_access_update: {e}",
                        flush=True,
                    )
                    logger.error(
                        "Error in handle_user_access_update: %s",
                        e,
                        exc_info=True,
                    )
                    success = False

            elif message.message_type == MessageType.SOFTWARE_INVENTORY_UPDATE:
                print("About to call handle_software_update", flush=True)
                try:
                    await handle_software_update(db, mock_connection, message_data)
                    success = True
                    print(
                        "Successfully processed software inventory update",
                        flush=True,
                    )
                except Exception as e:
                    print(
                        f"ERROR in handle_software_update: {e}",
                        flush=True,
                    )
                    logger.error(
                        "Error in handle_software_update: %s",
                        e,
                        exc_info=True,
                    )
                    success = False

            elif message.message_type == MessageType.PACKAGE_UPDATES_UPDATE:
                print(
                    "About to call handle_package_updates_update",
                    flush=True,
                )
                await handle_package_updates_update(db, mock_connection, message_data)
                success = True
                print("Successfully processed package updates", flush=True)

            elif message.message_type == MessageType.SCRIPT_EXECUTION_RESULT:
                print(
                    "About to call handle_script_execution_result",
                    flush=True,
                )
                await handle_script_execution_result(db, mock_connection, message_data)
                success = True
                print(
                    "Successfully processed script execution result",
                    flush=True,
                )

            elif message.message_type == MessageType.REBOOT_STATUS_UPDATE:
                print(
                    "About to call handle_reboot_status_update",
                    flush=True,
                )
                await handle_reboot_status_update(db, mock_connection, message_data)
                success = True
                print(
                    "Successfully processed reboot status update",
                    flush=True,
                )

            else:
                print(
                    f"Unknown message type: {message.message_type}",
                    flush=True,
                )
                logger.warning(
                    _("Unknown message type in queue: %s"), message.message_type
                )
                success = False

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

    async def _process_outbound_messages(self, db: Session):
        """Process outbound messages from the server to agents."""
        logger.info("Processing outbound messages")

        from backend.persistence.models import MessageQueue, Host

        # Get outbound messages for all hosts
        outbound_messages = (
            db.query(MessageQueue)
            .filter(
                MessageQueue.direction == QueueDirection.OUTBOUND,
                MessageQueue.status == QueueStatus.PENDING,
                MessageQueue.host_id.is_not(None),
            )
            .order_by(MessageQueue.priority.desc(), MessageQueue.created_at.asc())
            .limit(20)
            .all()
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
                await self._process_outbound_message(message, host, db)

    async def _process_outbound_message(self, message, host, db: Session):
        """Process a single outbound message."""
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
                success = await self._send_command_to_agent(
                    message_data, host, message.message_id
                )
            else:
                logger.warning(
                    "Unknown outbound message type: %s", message.message_type
                )

            if success:
                server_queue_manager.mark_completed(message.message_id, db=db)
                logger.info(
                    "Successfully sent outbound message: %s to host %s",
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

    async def _send_command_to_agent(
        self, command_data: dict, host, message_id: str
    ) -> bool:
        """Send a command message to an agent."""
        from backend.websocket.messages import create_command_message
        from backend.websocket.connection_manager import connection_manager

        try:
            # Create the command message
            # Check if this is a script execution command
            if "execution_id" in command_data:
                message = create_command_message("execute_script", command_data)
            else:
                # Other types of commands
                message = create_command_message("generic_command", command_data)

            # Send via connection manager
            logger.info(
                "Sending command message %s to host %s (%s)",
                message_id,
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
            logger.error("Error sending command to agent: %s", str(e))
            return False


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
