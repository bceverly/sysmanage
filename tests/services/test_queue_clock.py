# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""queue_clock hands back naive-UTC send times, whatever the database gives.

PostgreSQL returns message_queue.started_at timezone-aware; the callers
subtract it from naive-UTC times, which raised a TypeError and broke the
Backups page once an Equip command had been sent (production, 2026-10-31)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from backend.services import queue_clock
from backend.websocket.queue_enums import QueueStatus


def _db(rows):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = rows
    return db


def test_an_aware_send_time_comes_back_naive_utc():
    aware = datetime(2026, 10, 31, 16, 48, 35, tzinfo=timezone(timedelta(hours=-4)))
    db = _db([("c1", QueueStatus.COMPLETED, aware, None)])
    sent = queue_clock.delivery(db, "c1").sent_at
    assert sent.tzinfo is None
    assert sent == datetime(2026, 10, 31, 20, 48, 35)
    now = datetime(2026, 10, 31, 20, 50, 0)  # naive UTC, as jobs.now()
    assert now - queue_clock.clock_start(
        queue_clock.delivery(db, "c1"), now
    ) == timedelta(seconds=85)


def test_a_naive_send_time_is_left_alone():
    naive = datetime(2026, 10, 31, 20, 48, 35)
    db = _db([("c1", QueueStatus.COMPLETED, naive, None)])
    assert queue_clock.delivery(db, "c1").sent_at == naive


def test_an_unsent_command_has_no_send_time():
    db = _db([("c1", QueueStatus.PENDING, None, None)])
    found = queue_clock.delivery(db, "c1")
    assert found.sent_at is None and found.waiting
    assert queue_clock.clock_start(found, datetime(2026, 10, 31)) is None
