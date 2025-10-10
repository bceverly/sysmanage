"""
Queue Maintenance Operations for SysManage.
Handles cleanup, expiration, and deletion of queue messages.
"""

from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import and_
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.db import get_db
from backend.persistence.models import MessageQueue
from backend.utils.verbosity_logger import get_logger
from backend.websocket.queue_enums import QueueStatus

logger = get_logger(__name__)


class QueueMaintenance:
    """Maintenance operations for message queue cleanup and management."""

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
        cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=older_than_days
        )

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
                _("Cleaned up %d old messages"),
                deleted_count,
            )
            return deleted_count

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.error(_("Failed to cleanup old messages: %s"), str(e))
            return 0
        finally:
            if not session_provided:
                db.close()

    def delete_messages_for_host(self, host_id: str, db: Session = None) -> int:
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
        from backend.config.config import config

        session_provided = db is not None
        if not session_provided:
            db = next(get_db())

        try:
            # Get expiration timeout from config (default 60 minutes)
            timeout_minutes = config.get("message_queue", {}).get(
                "expiration_timeout_minutes", 60
            )
            cutoff_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
                minutes=timeout_minutes
            )

            # Find messages that should be expired
            # Only expire messages that are still pending or in_progress
            # Don't touch completed, failed, or already expired messages
            messages_to_expire = db.query(MessageQueue).filter(
                and_(
                    MessageQueue.created_at < cutoff_time,
                    MessageQueue.status.in_(
                        [QueueStatus.PENDING, QueueStatus.IN_PROGRESS]
                    ),
                    MessageQueue.expired_at.is_(None),  # Not already expired
                )
            )

            count = messages_to_expire.count()
            if count > 0:
                # Mark messages as expired
                messages_to_expire.update(
                    {
                        "status": QueueStatus.EXPIRED,
                        "expired_at": datetime.now(timezone.utc).replace(tzinfo=None),
                        "error_message": f"Message expired after {timeout_minutes} minutes",
                    },
                    synchronize_session=False,
                )

                if not session_provided:
                    db.commit()

                logger.info(
                    _("Marked %d old messages as expired (older than %d minutes)"),
                    count,
                    timeout_minutes,
                )

            return count

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.error(_("Failed to expire old messages: %s"), str(e))
            return 0
        finally:
            if not session_provided:
                db.close()

    def delete_failed_messages(self, message_ids: List[str], db: Session = None) -> int:
        """
        Delete specific failed/expired messages by their IDs.

        Args:
            message_ids: List of message IDs to delete
            db: Optional database session

        Returns:
            Number of messages deleted
        """
        session_provided = db is not None
        if not session_provided:
            db = next(get_db())

        try:
            count = (
                db.query(MessageQueue)
                .filter(
                    and_(
                        MessageQueue.message_id.in_(message_ids),
                        MessageQueue.status.in_(
                            [QueueStatus.FAILED, QueueStatus.EXPIRED]
                        ),
                    )
                )
                .count()
            )

            if count > 0:
                db.query(MessageQueue).filter(
                    and_(
                        MessageQueue.message_id.in_(message_ids),
                        MessageQueue.status.in_(
                            [QueueStatus.FAILED, QueueStatus.EXPIRED]
                        ),
                    )
                ).delete(synchronize_session=False)

                if not session_provided:
                    db.commit()

                logger.info(_("Deleted %d failed/expired messages"), count)

            return count

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.error(_("Failed to delete failed messages: %s"), str(e))
            return 0
        finally:
            if not session_provided:
                db.close()
