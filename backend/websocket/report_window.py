# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""How long a newly connected agent should spread its first reports over
(Phase 22.2).

WHY
---
A connecting agent sends its whole inventory at once: OS, hardware, users,
software, updates -- some thirty messages.  The 10,000-agent storm
(2026-10-02) connected the fleet in under a minute and queued ~300,000
messages; the server drained ~50 a second and was still working through
136,000 of them at the end.  The connections were fine; the burst was not.

HOW
---
``registration_success`` carries ``initial_report_window_seconds``: the agent
starts its first collection at a random moment within it.  The server sizes it
from the work it already has plus the work it can see coming:

    projected = inbound messages pending
              + agents registered in the last minute (all workers)
                x messages a first report adds
    window    = projected / messages drained a second, at most the maximum

"Drained a second" is what the server measured over the last minute (each
worker counts its own drain, times the workers), never less than the
configured ``initial_report_drain_per_second`` -- a quiet server measures
almost nothing.  The 10k run (2026-10-02) drained 150-200/s against the
configured 50, so every agent got the 30-minute maximum.

A quiet server answers 0 (report now).  The backlog alone lags a storm -- the
first thousand agents connect before their reports are queued -- so recent
registrations count too.  Fails open: no count, no delay.

Per worker; the pending count is cached ``REFRESH_SECONDS``.  Tuned in
``security.agent_connection_limits``: ``initial_report_drain_per_second``,
``initial_report_messages_per_agent``, ``initial_report_max_window_seconds``.
"""

import logging
import os
import threading
import time
from collections import deque

from sqlalchemy import func, select

from backend.persistence.models import MessageQueue
from backend.websocket.queue_enums import QueueDirection, QueueStatus

logger = logging.getLogger(__name__)

DEFAULT_DRAIN_PER_SECOND = 50.0  # measured, 10k storm on an 8-core laptop
DEFAULT_MESSAGES_PER_AGENT = 10.0  # a reconnect sends less than a first install
DEFAULT_MAX_WINDOW_SECONDS = 1800.0
REFRESH_SECONDS = 10.0
RECENT_SECONDS = 60.0
QUIET_SECONDS = 5.0  # a window shorter than this is not worth the delay

_lock = threading.Lock()
_pending = {}  # database key -> (counted_at, pending)
_registrations = deque()  # monotonic times, this worker
_processed = deque()  # (monotonic time, messages) this worker's drain finished


def _limits() -> tuple:
    from backend.config import config  # pylint: disable=import-outside-toplevel

    raw = (config.get_config().get("security") or {}).get("agent_connection_limits")
    raw = raw if isinstance(raw, dict) else {}
    try:
        drain = float(
            raw.get("initial_report_drain_per_second", DEFAULT_DRAIN_PER_SECOND)
        )
        per_agent = float(
            raw.get("initial_report_messages_per_agent", DEFAULT_MESSAGES_PER_AGENT)
        )
        longest = float(
            raw.get("initial_report_max_window_seconds", DEFAULT_MAX_WINDOW_SECONDS)
        )
    except (TypeError, ValueError):
        return (DEFAULT_DRAIN_PER_SECOND, DEFAULT_MESSAGES_PER_AGENT,
                DEFAULT_MAX_WINDOW_SECONDS)  # fmt: skip
    return max(0.1, drain), max(0.0, per_agent), max(0.0, longest)


def _workers() -> int:
    try:
        return max(1, int(os.environ.get("SYSMANAGE_UVICORN_WORKERS", "1")))
    except ValueError:
        return 1


def _pending_inbound(db, now: float) -> int:
    key = str(db.get_bind().url)
    with _lock:
        cached = _pending.get(key)
    if cached and now - cached[0] < REFRESH_SECONDS:
        return cached[1]
    count = db.execute(
        select(func.count())  # pylint: disable=not-callable
        .select_from(MessageQueue)
        .where(
            MessageQueue.direction == QueueDirection.INBOUND,
            MessageQueue.status == QueueStatus.PENDING,
        )
    ).scalar_one()
    with _lock:
        _pending[key] = (now, int(count))
    return int(count)


def _recent_registrations(now: float) -> int:
    with _lock:
        _registrations.append(now)
        while _registrations and now - _registrations[0] > RECENT_SECONDS:
            _registrations.popleft()
        return len(_registrations)


def record_processed(count: int, clock=time.monotonic) -> None:
    """The inbound drain finished ``count`` messages just now."""
    if count > 0:
        now = clock()
        with _lock:
            _processed.append((now, count))
            _trim_processed(now)


def _trim_processed(now: float) -> None:
    while _processed and now - _processed[0][0] > RECENT_SECONDS:
        _processed.popleft()


def measured_drain_rate(clock=time.monotonic) -> float:
    """Messages a second the whole server drained over the last minute."""
    now = clock()
    with _lock:
        _trim_processed(now)
        done = sum(count for _at, count in _processed)
    return done / RECENT_SECONDS * _workers()


def suggest(db, clock=time.monotonic) -> int:
    """Seconds this newly registered agent should spread its first reports over."""
    now = clock()
    recent = _recent_registrations(now)
    try:
        drain, per_agent, longest = _limits()
        pending = _pending_inbound(db, now)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Could not size the initial report window; using 0", exc_info=True
        )
        return 0
    projected = pending + recent * _workers() * per_agent
    drain = max(drain, measured_drain_rate(clock))
    window = min(longest, projected / drain)
    return 0 if window < QUIET_SECONDS else int(window)


def reset() -> None:
    """Forget the cached count and recent registrations (tests)."""
    with _lock:
        _pending.clear()
        _registrations.clear()
        _processed.clear()
