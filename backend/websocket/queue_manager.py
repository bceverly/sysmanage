"""
Server-side Message Queue Manager for SysManage.
Manages persistent message queues for server-to-agent communication.

This module provides a unified interface to queue operations by delegating
to specialized components for operations, maintenance, and statistics.
"""

from datetime import datetime
from typing import Any, Dict, List, Union

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import MessageQueue
from backend.utils.verbosity_logger import get_logger
from backend.websocket.queue_enums import Priority, QueueDirection, QueueStatus
from backend.websocket.queue_maintenance import QueueMaintenance
from backend.websocket.queue_operations import QueueOperations
from backend.websocket.queue_stats import QueueStats

logger = get_logger(__name__)


class ServerMessageQueueManager:
    """
    Server-side message queue manager for reliable agent communication.

    Handles both inbound (from agents) and outbound (to agents) message queues
    with retry logic, priority handling, host-specific queuing, and broadcast support.

    This class delegates to specialized components:
    - QueueOperations: Core enqueue/dequeue/status operations
    - QueueMaintenance: Cleanup, expiration, and deletion
    - QueueStats: Statistics and monitoring
    """

    def __init__(self):
        """Initialize the server queue manager."""
        self._operations = QueueOperations()
        self._maintenance = QueueMaintenance()
        self._stats = QueueStats()
        logger.info(_("Server message queue manager initialized"))

    # Delegate core operations to QueueOperations
    def enqueue_message(  # pylint: disable=too-many-positional-arguments
        self,
        message_type: str,
        message_data: Dict[str, Any],
        direction: Union[str, QueueDirection],
        host_id: str = None,
        priority: Union[str, Priority] = Priority.NORMAL,
        message_id: str = None,
        scheduled_at: datetime = None,
        max_retries: int = 3,
        correlation_id: str = None,
        reply_to: str = None,
        db: Session = None,
    ) -> str:
        """
        Add a message to the server queue.

        Args:
            message_type: Type of message (e.g., 'command', 'broadcast')
            message_data: Message payload as dictionary
            direction: Message direction (inbound/outbound)
            host_id: Target host ID (None for broadcast messages)
            priority: Message priority (low/normal/high/urgent)
            message_id: Optional custom message ID (UUID will be generated if not provided)
            scheduled_at: Optional time to process message (for delays)
            max_retries: Maximum retry attempts
            correlation_id: Optional correlation ID for request/response tracking
            reply_to: Optional message ID this is replying to
            db: Optional database session (will create if not provided)

        Returns:
            str: Message ID of queued message
        """
        return self._operations.enqueue_message(
            message_type=message_type,
            message_data=message_data,
            direction=direction,
            host_id=host_id,
            priority=priority,
            message_id=message_id,
            scheduled_at=scheduled_at,
            max_retries=max_retries,
            correlation_id=correlation_id,
            reply_to=reply_to,
            db=db,
        )

    def dequeue_messages_for_host(  # pylint: disable=too-many-positional-arguments
        self,
        host_id: str,
        direction: Union[str, QueueDirection] = QueueDirection.OUTBOUND,
        limit: int = 10,
        priority_order: bool = True,
        db: Session = None,
    ) -> List[MessageQueue]:
        """
        Get pending messages for a specific host.

        Args:
            host_id: Target host ID
            direction: Message direction to dequeue
            limit: Maximum number of messages to return
            priority_order: Whether to order by priority (urgent first)
            db: Optional database session

        Returns:
            List[MessageQueue]: Ready messages ordered by priority/creation time
        """
        return self._operations.dequeue_messages_for_host(
            host_id=host_id,
            direction=direction,
            limit=limit,
            priority_order=priority_order,
            db=db,
        )

    def dequeue_broadcast_messages(
        self,
        direction: Union[str, QueueDirection] = QueueDirection.OUTBOUND,
        limit: int = 10,
        db: Session = None,
    ) -> List[MessageQueue]:
        """
        Get pending broadcast messages (messages without specific host_id).

        Args:
            direction: Message direction to dequeue
            limit: Maximum number of messages to return
            db: Optional database session

        Returns:
            List[MessageQueue]: Ready broadcast messages
        """
        return self._operations.dequeue_broadcast_messages(
            direction=direction,
            limit=limit,
            db=db,
        )

    def mark_processing(self, message_id: str, db: Session = None) -> bool:
        """
        Mark a message as currently being processed.

        Args:
            message_id: ID of message to mark as in progress
            db: Optional database session

        Returns:
            bool: True if successfully marked, False if message not found or already processed
        """
        return self._operations.mark_processing(message_id=message_id, db=db)

    def mark_completed(self, message_id: str, db: Session = None) -> bool:
        """
        Mark a message as successfully processed.

        Args:
            message_id: ID of message to mark as completed
            db: Optional database session

        Returns:
            bool: True if successfully marked, False if message not found
        """
        return self._operations.mark_completed(message_id=message_id, db=db)

    def mark_failed(
        self,
        message_id: str,
        error_message: str = None,
        retry: bool = True,
        db: Session = None,
    ) -> bool:
        """
        Mark a message as failed and optionally retry.

        Args:
            message_id: ID of message to mark as failed
            error_message: Optional error description
            retry: Whether to retry the message if retries are available
            db: Optional database session

        Returns:
            bool: True if successfully marked, False if message not found
        """
        return self._operations.mark_failed(
            message_id=message_id,
            error_message=error_message,
            retry=retry,
            db=db,
        )

    def deserialize_message_data(self, message: MessageQueue) -> Dict[str, Any]:
        """
        Deserialize message data from JSON.

        Args:
            message: MessageQueue instance

        Returns:
            Dict[str, Any]: Deserialized message data
        """
        return self._operations.deserialize_message_data(message=message)

    def mark_sent(self, message_id: str, db: Session = None) -> bool:
        """
        Mark a message as sent to the agent, awaiting acknowledgment.

        This status indicates the message was successfully transmitted over the
        websocket, but we haven't received confirmation the agent processed it.

        Args:
            message_id: ID of message to mark as sent
            db: Optional database session

        Returns:
            bool: True if successfully marked, False if message not found
        """
        return self._operations.mark_sent(message_id=message_id, db=db)

    def mark_acknowledged(self, message_id: str, db: Session = None) -> bool:
        """
        Mark a sent message as acknowledged by the agent.

        This marks the message as COMPLETED since the agent confirmed receipt.

        Args:
            message_id: ID of message that was acknowledged
            db: Optional database session

        Returns:
            bool: True if successfully marked, False if message not found or wrong status
        """
        return self._operations.mark_acknowledged(message_id=message_id, db=db)

    def retry_unacknowledged_messages(
        self, timeout_seconds: int = 60, db: Session = None
    ) -> int:
        """
        Find messages in SENT status that haven't been acknowledged and retry them.

        This should be called periodically to handle messages that were sent but
        the agent crashed/disconnected before acknowledging.

        Args:
            timeout_seconds: How long to wait for ack before considering it lost
            db: Optional database session

        Returns:
            int: Number of messages marked for retry
        """
        return self._operations.retry_unacknowledged_messages(
            timeout_seconds=timeout_seconds, db=db
        )

    # Delegate maintenance operations to QueueMaintenance
    def cleanup_old_messages(
        self, older_than_days: int = 7, keep_failed: bool = True, db: Session = None
    ) -> int:
        """
        Clean up old completed messages to prevent database growth.

        Args:
            older_than_days: Remove messages older than this many days
            keep_failed: Whether to keep failed messages for debugging
            db: Optional database session

        Returns:
            int: Number of messages deleted
        """
        return self._maintenance.cleanup_old_messages(
            older_than_days=older_than_days,
            keep_failed=keep_failed,
            db=db,
        )

    def delete_messages_for_host(self, host_id: str, db: Session = None) -> int:
        """
        Delete all messages for a specific host from the queue.

        Args:
            host_id: ID of the host whose messages should be deleted
            db: Optional database session

        Returns:
            Number of messages deleted
        """
        return self._maintenance.delete_messages_for_host(host_id=host_id, db=db)

    def expire_old_messages(self, db: Session = None) -> int:
        """
        Mark old messages as expired based on configuration timeout.

        This prevents old messages from being processed and helps maintain
        queue health by avoiding infinite message loops.

        Args:
            db: Optional database session

        Returns:
            Number of messages marked as expired
        """
        return self._maintenance.expire_old_messages(db=db)

    def delete_failed_messages(self, message_ids: List[str], db: Session = None) -> int:
        """
        Delete specific failed/expired messages by their IDs.

        Args:
            message_ids: List of message IDs to delete
            db: Optional database session

        Returns:
            Number of messages deleted
        """
        return self._maintenance.delete_failed_messages(
            message_ids=message_ids,
            db=db,
        )

    # Delegate statistics operations to QueueStats
    def get_queue_stats(
        self,
        host_id: str = None,
        direction: Union[str, QueueDirection] = None,
        db: Session = None,
    ) -> Dict[str, Any]:
        """
        Get queue statistics for monitoring.

        Args:
            host_id: Optional host ID to filter by
            direction: Optional direction to filter by
            db: Optional database session

        Returns:
            Dict[str, Any]: Statistics including pending, processing, completed, failed counts
        """
        return self._stats.get_queue_stats(
            host_id=host_id,
            direction=direction,
            db=db,
        )

    def get_failed_messages(
        self, limit: int = 100, db: Session = None
    ) -> List[MessageQueue]:
        """
        Get a list of failed and expired messages for management UI.

        Args:
            limit: Maximum number of messages to return
            db: Optional database session

        Returns:
            List of failed/expired messages
        """
        return self._stats.get_failed_messages(limit=limit, db=db)


# Global instance for server-wide use
server_queue_manager = ServerMessageQueueManager()

# Re-export enums for backward compatibility
# This allows existing code to import directly from queue_manager
__all__ = [
    "ServerMessageQueueManager",
    "server_queue_manager",
    "QueueStatus",
    "QueueDirection",
    "Priority",
]
