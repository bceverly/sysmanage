"""
Core Queue Operations for SysManage.
Handles message enqueuing, dequeuing, and status updates.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Union

from sqlalchemy import and_, asc, or_
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.db import get_db
from backend.persistence.models import Host, MessageQueue
from backend.utils.verbosity_logger import get_logger
from backend.websocket.queue_enums import Priority, QueueDirection, QueueStatus

logger = get_logger(__name__)


class QueueOperations:
    """Core operations for message queue management."""

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

            # Check for duplicate script execution commands to prevent multiple queuing
            if (
                message_type == "command"
                and direction == QueueDirection.OUTBOUND
                and host_id is not None
                and "execution_id" in message_data
            ):
                execution_id = message_data.get("execution_id")
                script_content = message_data.get("parameters", {}).get(
                    "script_content"
                )

                # First check: Same execution_id already queued
                existing_command = (
                    db.query(MessageQueue)
                    .filter(
                        MessageQueue.host_id == host_id,
                        MessageQueue.message_type == "command",
                        MessageQueue.direction == QueueDirection.OUTBOUND,
                        MessageQueue.status.in_(
                            [QueueStatus.PENDING, QueueStatus.IN_PROGRESS]
                        ),
                        MessageQueue.message_data.contains(
                            f'"execution_id": "{execution_id}"'
                        ),
                    )
                    .first()
                )

                if existing_command:
                    logger.warning(
                        "Duplicate script execution command for execution_id %s already queued (message_id: %s), skipping",
                        execution_id,
                        existing_command.message_id,
                    )
                    return existing_command.message_id

                # Second check: Same script content within 10 seconds (prevent rapid duplicate requests)
                if script_content:
                    recent_threshold = datetime.now(timezone.utc).replace(
                        tzinfo=None
                    ) - timedelta(seconds=10)

                    similar_command = (
                        db.query(MessageQueue)
                        .filter(
                            MessageQueue.host_id == host_id,
                            MessageQueue.message_type == "command",
                            MessageQueue.direction == QueueDirection.OUTBOUND,
                            MessageQueue.status.in_(
                                [
                                    QueueStatus.PENDING,
                                    QueueStatus.IN_PROGRESS,
                                    QueueStatus.SENT,
                                ]
                            ),
                            MessageQueue.created_at > recent_threshold,
                            MessageQueue.message_data.contains(
                                f'"script_content": "{script_content[:100]}"'
                            ),  # Check first 100 chars
                        )
                        .first()
                    )

                    if similar_command:
                        logger.warning(
                            "Duplicate script execution with similar content within 10 seconds (message_id: %s), skipping new execution_id %s",
                            similar_command.message_id,
                            execution_id,
                        )
                        return similar_command.message_id

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
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )

            db.add(queue_item)

            # Add debug logging before commit
            logger.debug(
                "About to commit message %s (type=%s) to database, session_provided=%s",
                message_id,
                message_type,
                session_provided,
            )

            if not session_provided:
                try:
                    db.commit()
                    logger.debug(
                        "Successfully committed message %s to database (self-managed session)",
                        message_id,
                    )

                    # Verify the message was actually inserted
                    verification = (
                        db.query(MessageQueue)
                        .filter(MessageQueue.message_id == message_id)
                        .first()
                    )
                    if verification:
                        logger.debug(
                            "Verified message %s exists in database after commit",
                            message_id,
                        )
                    else:
                        logger.error(
                            "Message %s NOT found in database after commit!",
                            message_id,
                        )
                        raise RuntimeError(
                            f"Message {message_id} was not persisted to database despite successful commit"
                        )
                except Exception as commit_error:
                    logger.error(
                        "Commit failed for message %s: %s",
                        message_id,
                        commit_error,
                    )
                    raise
            else:
                logger.debug(
                    "Using provided session for message %s, db.dirty=%s, db.new=%s",
                    message_id,
                    len(db.dirty),
                    len(db.new),
                )

                # For provided sessions, we need to flush to make sure the data is written to the session
                # but the commit will happen later by the caller
                try:
                    db.flush()
                    logger.debug(
                        "Successfully flushed message %s to provided session",
                        message_id,
                    )

                    # Verify the message was actually added to the session
                    verification = (
                        db.query(MessageQueue)
                        .filter(MessageQueue.message_id == message_id)
                        .first()
                    )
                    if verification:
                        logger.debug(
                            "Verified message %s exists in session after flush",
                            message_id,
                        )
                    else:
                        logger.error(
                            "Message %s NOT found in session after flush!",
                            message_id,
                        )
                        raise RuntimeError(
                            f"Message {message_id} was not added to session despite successful flush"
                        )
                except Exception as flush_error:
                    logger.error(
                        "Flush failed for message %s: %s",
                        message_id,
                        flush_error,
                    )
                    raise

            logger.debug(
                _("Enqueued message: id=%s, type=%s, direction=%s, host_id=%s"),
                message_id,
                message_type,
                direction,
                host_id,
            )

        except Exception:
            if not session_provided:
                db.rollback()
            raise
        finally:
            if not session_provided:
                db.close()

        return message_id

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
        if hasattr(direction, "value"):
            direction = direction.value

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        session_provided = db is not None
        if not session_provided:
            db = next(get_db())

        try:
            query = db.query(MessageQueue).filter(
                and_(
                    MessageQueue.host_id == host_id,
                    MessageQueue.direction == direction,
                    MessageQueue.status == QueueStatus.PENDING,
                    MessageQueue.expired_at.is_(None),
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

        now = datetime.now(timezone.utc).replace(tzinfo=None)

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
            message.started_at = datetime.now(timezone.utc).replace(tzinfo=None)

            if not session_provided:
                db.commit()

            logger.debug(_("Marked message as processing: %s"), message_id)
            return True

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.error(
                _("Failed to mark message %s as processing: %s"),
                message_id,
                str(e),
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
            message.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)

            if not session_provided:
                db.commit()

            logger.debug(_("Marked message as completed: %s"), message_id)
            return True

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.error(
                _("Failed to mark message %s as completed: %s"),
                message_id,
                str(e),
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
            message.last_error_at = datetime.now(timezone.utc).replace(tzinfo=None)

            if error_message:
                message.error_message = error_message

            # Check if we should retry or mark as permanently failed
            if retry and message.retry_count < message.max_retries:
                # Reset to pending for retry with exponential backoff
                message.status = QueueStatus.PENDING
                backoff_seconds = min(
                    60 * (2 ** (message.retry_count - 1)), 3600
                )  # Max 1 hour
                message.scheduled_at = datetime.now(timezone.utc).replace(
                    tzinfo=None
                ) + timedelta(seconds=backoff_seconds)
                message.started_at = None  # Reset processing timestamp

                logger.debug(
                    _(
                        "Message %s failed (attempt %d/%d), scheduled for retry in %d seconds"
                    ),
                    message_id,
                    message.retry_count,
                    message.max_retries,
                    backoff_seconds,
                )
            else:
                # Max retries reached or retry disabled
                message.status = QueueStatus.FAILED
                message.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)

                logger.warning(
                    _("Message %s permanently failed after %d attempts: %s"),
                    message_id,
                    message.retry_count,
                    error_message,
                )

            if not session_provided:
                db.commit()

            return True

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.error(
                _("Failed to mark message %s as failed: %s"),
                message_id,
                str(e),
            )
            return False
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
                _("Failed to deserialize message %s: %s"),
                message.message_id,
                str(e),
            )
            return {}
