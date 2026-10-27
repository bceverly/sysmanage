# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""When did a queued command actually leave for its agent?

A command's time to answer has to start when it is SENT, not when it was
queued: a maintenance window (Phase 14.2) can hold a change command for
days, and an offline agent holds everything.  Timing from the queue time
marked held work failed -- and then queued it again, so the host got both
when the window opened (Equip for backup and scheduled backups, 2026-10-27).

One id serves the command and its outbound queue row (queue_command), so the
row is found by the command id.  The queue cleans up old rows; a command
whose row is gone is timed from the caller's own fallback.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services.maintenance_window_service import DEFERRED_MARKER
from backend.websocket.queue_enums import QueueStatus


@dataclass(frozen=True)
class Delivery:
    """A command's outbound queue row, as far as timing goes."""

    sent_at: Optional[datetime]  # the latest send (resends move it later)
    waiting: bool  # never sent yet: held by a window, or the agent is away
    held: bool  # waiting because a maintenance window is closed


def deliveries(
    db: Session, command_ids: Iterable[Optional[str]]
) -> Dict[str, Delivery]:
    """``{command id: Delivery}`` for the ids whose queue row still exists."""
    ids = sorted({str(cid) for cid in command_ids if cid})
    if not ids:
        return {}
    rows = (
        db.query(
            models.MessageQueue.message_id,
            models.MessageQueue.status,
            models.MessageQueue.started_at,
            models.MessageQueue.error_message,
        )
        .filter(models.MessageQueue.message_id.in_(ids))
        .all()
    )
    found = {}
    for message_id, status, started_at, error_message in rows:
        waiting = started_at is None and status == QueueStatus.PENDING
        found[message_id] = Delivery(
            sent_at=started_at,
            waiting=waiting,
            held=waiting and error_message == DEFERRED_MARKER,
        )
    return found


def delivery(db: Session, command_id: Optional[str]) -> Optional[Delivery]:
    return deliveries(db, [command_id]).get(str(command_id)) if command_id else None


def clock_start(found: Optional[Delivery], fallback: datetime) -> Optional[datetime]:
    """When the time to answer began: the send; None while it waits to be
    sent (it cannot be late yet); ``fallback`` when the row is gone or ended
    without being sent."""
    if found is None:
        return fallback
    if found.sent_at is not None:
        return found.sent_at
    return None if found.waiting else fallback
