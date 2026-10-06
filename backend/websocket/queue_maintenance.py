# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Queue Maintenance Operations for SysManage.
Handles cleanup, expiration, and deletion of queue messages.
"""

from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.chunked_delete import delete_in_chunks
from backend.persistence.db import get_db
from backend.persistence.models import MessageQueue
from backend.utils.verbosity_logger import get_logger
from backend.websocket.queue_enums import QueueDirection, QueueStatus

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
            statuses = [QueueStatus.COMPLETED]
            if not keep_failed:
                statuses.append(QueueStatus.FAILED)

            # Bulk DELETEs by id, never loading the rows (a real backlog --
            # 157k rows, each with a large message_data payload -- pulled
            # gigabytes into memory).  In chunks, each committed (Phase 22.2):
            # one DELETE of a day's completed messages at fleet scale held a
            # single transaction for millions of rows.  This commits the
            # caller's session too, chunk by chunk.
            deleted_count = delete_in_chunks(
                db,
                MessageQueue,
                MessageQueue.completed_at < cutoff_date,
                MessageQueue.status.in_(statuses),
            )

            logger.info(
                _("Cleaned up %d old messages"),
                deleted_count,
            )
            return deleted_count

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.exception(_("Failed to cleanup old messages: %s"), str(e))
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

            logger.info(
                _("Deleted %(count)d messages for host %(host_id)s"),
                {"count": count, "host_id": host_id},
            )
            return count

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.exception(
                _("Failed to delete messages for host %(host_id)s: %(error)s"),
                {"host_id": host_id, "error": e},
            )
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

            # Phase 22.2: an INBOUND message expires on time since its last
            # ATTEMPT, never just for waiting its turn.  Expiring by age turned
            # any backlog into silent data loss -- an agent's report thrown
            # away because the server was busy.  A hard ceiling (default 24 h)
            # still bounds a backlog that can never be worked off.  OUTBOUND
            # keeps age-based expiry on purpose: a command delivered an hour
            # late (a reboot, a patch run) is worse than one never delivered.
            ceiling_hours = config.get("message_queue", {}).get(
                "inbound_max_age_hours", 24
            )
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            # pylint: disable-next=assignment-from-no-return  # pylint cannot infer SQLAlchemy func.*
            last_attempt = func.coalesce(
                MessageQueue.last_error_at, MessageQueue.started_at
            )
            inbound_stale = and_(
                MessageQueue.direction == QueueDirection.INBOUND,
                or_(
                    and_(last_attempt.is_not(None), last_attempt < cutoff_time),
                    MessageQueue.created_at < now - timedelta(hours=ceiling_hours),
                ),
            )
            outbound_stale = and_(
                MessageQueue.direction != QueueDirection.INBOUND,
                MessageQueue.created_at < cutoff_time,
            )
            # Only messages still pending or in progress; completed, failed and
            # already-expired rows are left alone.
            messages_to_expire = db.query(MessageQueue).filter(
                and_(
                    or_(inbound_stale, outbound_stale),
                    MessageQueue.status.in_(
                        [QueueStatus.PENDING, QueueStatus.IN_PROGRESS]
                    ),
                    MessageQueue.expired_at.is_(None),  # Not already expired
                )
            )
            inbound_count = messages_to_expire.filter(
                MessageQueue.direction == QueueDirection.INBOUND
            ).count()
            if inbound_count:
                # Loud: these are agent reports the server never used.
                logger.warning(
                    "Expiring %d inbound agent message(s): retried for %d minutes "
                    "without success, or waiting longer than %d hours",
                    inbound_count,
                    timeout_minutes,
                    ceiling_hours,
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
                    _(
                        "Marked %(count)d old messages as expired (older than %(timeout)d minutes)"
                    ),
                    {"count": count, "timeout": timeout_minutes},
                )

            return count

        except Exception as e:
            if not session_provided:
                db.rollback()
            logger.exception(_("Failed to expire old messages: %s"), str(e))
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
            logger.exception(_("Failed to delete failed messages: %s"), str(e))
            return 0
        finally:
            if not session_provided:
                db.close()
