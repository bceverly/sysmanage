"""
Queue Statistics and Monitoring for SysManage.
Provides statistics and reporting for message queue management.
"""

from typing import Any, Dict, List, Union

from sqlalchemy import and_
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.db import get_db
from backend.persistence.models import MessageQueue
from backend.utils.verbosity_logger import get_logger
from backend.websocket.queue_enums import QueueDirection, QueueStatus

logger = get_logger(__name__)


class QueueStats:
    """Statistics and monitoring operations for message queues."""

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
        session_provided = db is not None
        if not session_provided:
            db = next(get_db())

        try:
            messages = (
                db.query(MessageQueue)
                .filter(
                    MessageQueue.status.in_([QueueStatus.FAILED, QueueStatus.EXPIRED])
                )
                .order_by(MessageQueue.created_at.desc())
                .limit(limit)
                .all()
            )

            return messages

        except Exception as e:
            logger.error(_("Failed to get failed messages: %s"), str(e))
            return []
        finally:
            if not session_provided:
                db.close()
