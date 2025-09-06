"""
Server-side Message Queue Manager for SysManage.
Manages persistent message queues for server-to-agent communication.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Union

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, asc

from backend.persistence.db import get_db
from backend.persistence.models import MessageQueue, Host
from backend.i18n import _

logger = logging.getLogger(__name__)


# Message queue enums - replicated from agent side for consistency
class QueueStatus:
    """Message queue status enumeration."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class QueueDirection:
    """Message queue direction enumeration."""

    OUTBOUND = "outbound"  # Messages to send to agents
    INBOUND = "inbound"  # Messages received from agents


class Priority:
    """Message priority enumeration."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ServerMessageQueueManager:
    """
    Server-side message queue manager for reliable agent communication.

    Handles both inbound (from agents) and outbound (to agents) message queues
    with retry logic, priority handling, host-specific queuing, and broadcast support.
    """

    def __init__(self):
        """Initialize the server queue manager."""
        logger.info(_("Server message queue manager initialized"))

    def enqueue_message(
        self,
        message_type: str,
        message_data: Dict[str, Any],
        direction: Union[str, QueueDirection],
        host_id: int = None,
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
        import uuid

        if message_id is None:
            message_id = str(uuid.uuid4())

        # Ensure direction, priority, and message_type are strings
        if hasattr(direction, "value"):
            direction = direction.value
        if hasattr(priority, "value"):
            priority = priority.value
        if hasattr(message_type, "value"):
            message_type = message_type.value

        # Serialize message data
        serialized_data = json.dumps(message_data, default=str)

        # Use provided session or get a new one
        session_provided = db is not None
        if not session_provided:
            db = next(get_db())

        try:
            # Validate host_id exists if provided
            if host_id is not None:
                host = db.query(Host).filter(Host.id == host_id).first()
                if not host:
                    raise ValueError(
                        _("Host ID {host_id} not found").format(host_id=host_id)
                    )

            queue_item = MessageQueue(
                host_id=host_id,
                message_id=message_id,
                direction=direction,
                message_type=message_type,
                message_data=serialized_data,
                status=QueueStatus.PENDING,
                priority=priority,
                max_retries=max_retries,
                scheduled_at=scheduled_at,
                correlation_id=correlation_id,
                reply_to=reply_to,
                created_at=datetime.now(timezone.utc),
            )

            db.add(queue_item)

            # Add debug logging before commit
            logger.info(
                "QUEUEMANAGER_DEBUG: About to commit message %s (type=%s) to database, session_provided=%s",
                message_id,
                message_type,
                session_provided,
            )

            if not session_provided:
                try:
                    db.commit()
                    logger.info(
                        "QUEUEMANAGER_DEBUG: Successfully committed message %s to database (self-managed session)",
                        message_id,
                    )

                    # Verify the message was actually inserted
                    verification = (
                        db.query(MessageQueue)
                        .filter(MessageQueue.message_id == message_id)
                        .first()
                    )
                    if verification:
                        logger.info(
                            "QUEUEMANAGER_DEBUG: Verified message %s exists in database after commit",
                            message_id,
                        )
                    else:
                        logger.error(
                            "QUEUEMANAGER_DEBUG: Message %s NOT found in database after commit!",
                            message_id,
                        )
                        raise RuntimeError(
                            f"Message {message_id} was not persisted to database despite successful commit"
                        )
                except Exception as commit_error:
                    logger.error(
                        "QUEUEMANAGER_DEBUG: Commit failed for message %s: %s",
                        message_id,
                        commit_error,
                    )
                    raise
            else:
                logger.info(
                    "QUEUEMANAGER_DEBUG: Using provided session for message %s, db.dirty=%s, db.new=%s",
                    message_id,
                    len(db.dirty),
                    len(db.new),
                )

                # For provided sessions, we need to flush to make sure the data is written to the session
                # but the commit will happen later by the caller
                try:
                    db.flush()
                    logger.info(
                        "QUEUEMANAGER_DEBUG: Successfully flushed message %s to provided session",
                        message_id,
                    )

                    # Verify the message was actually added to the session
                    verification = (
                        db.query(MessageQueue)
                        .filter(MessageQueue.message_id == message_id)
                        .first()
                    )
                    if verification:
                        logger.info(
                            "QUEUEMANAGER_DEBUG: Verified message %s exists in session after flush",
                            message_id,
                        )
                    else:
                        logger.error(
                            "QUEUEMANAGER_DEBUG: Message %s NOT found in session after flush!",
                            message_id,
                        )
                        raise RuntimeError(
                            f"Message {message_id} was not added to session despite successful flush"
                        )
                except Exception as flush_error:
                    logger.error(
                        "QUEUEMANAGER_DEBUG: Flush failed for message %s: %s",
                        message_id,
                        flush_error,
                    )
                    raise

            logger.debug(
                _(
                    "Enqueued message: id={message_id}, type={message_type}, direction={direction}, host_id={host_id}"
                ),
                message_id=message_id,
                message_type=message_type,
                direction=direction,
                host_id=host_id,
            )

        except Exception:
            if not session_provided:
                db.rollback()
            raise
        finally:
            if not session_provided:
                db.close()

        return message_id

    def dequeue_messages_for_host(
        self,
        host_id: int,
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
        if hasattr(direction, "value"):
            direction = direction.value

        now = datetime.now(timezone.utc)

        session_provided = db is not None
        if not session_provided:
            db = next(get_db())

        try:
            query = db.query(MessageQueue).filter(
                and_(
                    MessageQueue.host_id == host_id,
                    MessageQueue.direction == direction,
                    MessageQueue.status == QueueStatus.PENDING,
                    or_(
                        MessageQueue.scheduled_at.is_(None),
                        MessageQueue.scheduled_at <= now,
                    ),
                )
            )

            if priority_order:
                # Order by creation time for now, priority sorting done in Python
                query = query.order_by(asc(MessageQueue.created_at))
            else:
                query = query.order_by(asc(MessageQueue.created_at))

            messages = query.limit(limit).all()

            # Sort by priority if requested
            if priority_order and messages:
                priority_map = {
                    Priority.URGENT: 4,
                    Priority.HIGH: 3,
                    Priority.NORMAL: 2,
                    Priority.LOW: 1,
                }
                messages.sort(
                    key=lambda m: (priority_map.get(m.priority, 0), m.created_at),
                    reverse=True,  # Higher priority first, older messages first within priority
                )

            return messages

        finally:
            if not session_provided:
                db.close()

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
        if hasattr(direction, "value"):
            direction = direction.value

        now = datetime.now(timezone.utc)

        session_provided = db is not None
        if not session_provided:
            db = next(get_db())

        try:
            query = (
                db.query(MessageQueue)
                .filter(
                    and_(
                        MessageQueue.host_id.is_(None),  # Broadcast messages
                        MessageQueue.direction == direction,
                        MessageQueue.status == QueueStatus.PENDING,
                        or_(
                            MessageQueue.scheduled_at.is_(None),
                            MessageQueue.scheduled_at <= now,
                        ),
                    )
                )
                .order_by(asc(MessageQueue.created_at))
                .limit(limit)
            )

            return query.all()

        finally:
            if not session_provided:
                db.close()

    def mark_processing(self, message_id: str, db: Session = None) -> bool:
        """
        Mark a message as currently being processed.

        Args:
            message_id: ID of message to mark as in progress
            db: Optional database session

        Returns:
            bool: True if successfully marked, False if message not found or already processed
        """
        session_provided = db is not None
        if not session_provided:
            db = next(get_db())

        try:
            message = db.query(MessageQueue).filter_by(message_id=message_id).first()

            if not message or message.status != QueueStatus.PENDING:
                return False

            message.status = QueueStatus.IN_PROGRESS
            message.started_at = datetime.now(timezone.utc)

            if not session_provided:
                db.commit()

            logger.debug(
                _("Marked message as processing: {message_id}"), message_id=message_id
            )
            return True

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.error(
                _("Failed to mark message {message_id} as processing: {error}"),
                message_id=message_id,
                error=str(e),
            )
            return False
        finally:
            if not session_provided:
                db.close()

    def mark_completed(self, message_id: str, db: Session = None) -> bool:
        """
        Mark a message as successfully processed.

        Args:
            message_id: ID of message to mark as completed
            db: Optional database session

        Returns:
            bool: True if successfully marked, False if message not found
        """
        session_provided = db is not None
        if not session_provided:
            db = next(get_db())

        try:
            message = db.query(MessageQueue).filter_by(message_id=message_id).first()

            if not message:
                return False

            message.status = QueueStatus.COMPLETED
            message.completed_at = datetime.now(timezone.utc)

            if not session_provided:
                db.commit()

            logger.debug(
                _("Marked message as completed: {message_id}"), message_id=message_id
            )
            return True

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.error(
                _("Failed to mark message {message_id} as completed: {error}"),
                message_id=message_id,
                error=str(e),
            )
            return False
        finally:
            if not session_provided:
                db.close()

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
        session_provided = db is not None
        if not session_provided:
            db = next(get_db())

        try:
            message = db.query(MessageQueue).filter_by(message_id=message_id).first()

            if not message:
                return False

            message.retry_count += 1
            message.last_error_at = datetime.now(timezone.utc)

            if error_message:
                message.error_message = error_message

            # Check if we should retry or mark as permanently failed
            if retry and message.retry_count < message.max_retries:
                # Reset to pending for retry with exponential backoff
                message.status = QueueStatus.PENDING
                backoff_seconds = min(
                    60 * (2 ** (message.retry_count - 1)), 3600
                )  # Max 1 hour
                message.scheduled_at = datetime.now(timezone.utc) + timedelta(
                    seconds=backoff_seconds
                )
                message.started_at = None  # Reset processing timestamp

                logger.info(
                    _(
                        "Message {message_id} failed (attempt {retry_count}/{max_retries}), scheduled for retry in {backoff_seconds} seconds"
                    ),
                    message_id=message_id,
                    retry_count=message.retry_count,
                    max_retries=message.max_retries,
                    backoff_seconds=backoff_seconds,
                )
            else:
                # Max retries reached or retry disabled
                message.status = QueueStatus.FAILED
                message.completed_at = datetime.now(timezone.utc)

                logger.warning(
                    _(
                        "Message {message_id} permanently failed after {retry_count} attempts: {error_message}"
                    ),
                    message_id=message_id,
                    retry_count=message.retry_count,
                    error_message=error_message,
                )

            if not session_provided:
                db.commit()

            return True

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.error(
                _("Failed to mark message {message_id} as failed: {error}"),
                message_id=message_id,
                error=str(e),
            )
            return False
        finally:
            if not session_provided:
                db.close()

    def get_queue_stats(
        self,
        host_id: int = None,
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
        if direction and hasattr(direction, "value"):
            direction = direction.value

        session_provided = db is not None
        if not session_provided:
            db = next(get_db())

        try:
            query = db.query(MessageQueue)

            filters = []
            if host_id is not None:
                filters.append(MessageQueue.host_id == host_id)
            if direction:
                filters.append(MessageQueue.direction == direction)

            if filters:
                query = query.filter(and_(*filters))

            all_messages = query.all()

            stats = {
                "total": len(all_messages),
                "pending": sum(
                    1 for m in all_messages if m.status == QueueStatus.PENDING
                ),
                "in_progress": sum(
                    1 for m in all_messages if m.status == QueueStatus.IN_PROGRESS
                ),
                "completed": sum(
                    1 for m in all_messages if m.status == QueueStatus.COMPLETED
                ),
                "failed": sum(
                    1 for m in all_messages if m.status == QueueStatus.FAILED
                ),
            }

            if host_id is not None:
                stats["host_id"] = host_id
            if direction:
                stats["direction"] = direction

            return stats

        finally:
            if not session_provided:
                db.close()

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
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        session_provided = db is not None
        if not session_provided:
            db = next(get_db())

        try:
            query = db.query(MessageQueue).filter(
                and_(
                    MessageQueue.completed_at < cutoff_date,
                    MessageQueue.status == QueueStatus.COMPLETED,
                )
            )

            if not keep_failed:
                # Also clean up old failed messages
                failed_query = db.query(MessageQueue).filter(
                    and_(
                        MessageQueue.completed_at < cutoff_date,
                        MessageQueue.status == QueueStatus.FAILED,
                    )
                )
                query = query.union(failed_query)

            messages_to_delete = query.all()
            deleted_count = len(messages_to_delete)

            for message in messages_to_delete:
                db.delete(message)

            if not session_provided:
                db.commit()

            logger.info(
                _("Cleaned up {deleted_count} old messages"),
                deleted_count=deleted_count,
            )
            return deleted_count

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.error(_("Failed to cleanup old messages: {error}"), error=str(e))
            return 0
        finally:
            if not session_provided:
                db.close()

    def delete_messages_for_host(self, host_id: int, db: Session = None) -> int:
        """
        Delete all messages for a specific host from the queue.

        Args:
            host_id: ID of the host whose messages should be deleted
            db: Optional database session

        Returns:
            Number of messages deleted
        """
        session_provided = db is not None
        if not session_provided:
            db = next(get_db())

        try:
            # Count messages to be deleted
            count = (
                db.query(MessageQueue).filter(MessageQueue.host_id == host_id).count()
            )

            # Delete all messages for this host
            db.query(MessageQueue).filter(MessageQueue.host_id == host_id).delete(
                synchronize_session=False
            )

            if not session_provided:
                db.commit()

            logger.info(_("Deleted %d messages for host %s"), count, host_id)
            return count

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.error(_("Failed to delete messages for host %s: %s"), host_id, e)
            return 0
        finally:
            if not session_provided:
                db.close()

    def deserialize_message_data(self, message: MessageQueue) -> Dict[str, Any]:
        """
        Deserialize message data from JSON.

        Args:
            message: MessageQueue instance

        Returns:
            Dict[str, Any]: Deserialized message data
        """
        try:
            return json.loads(message.message_data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(
                _("Failed to deserialize message {message_id}: {error}"),
                message_id=message.message_id,
                error=str(e),
            )
            return {}


# Global instance for server-wide use
server_queue_manager = ServerMessageQueueManager()
