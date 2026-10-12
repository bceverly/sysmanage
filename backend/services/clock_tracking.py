# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
The server's own measurement of every host's clock (Phase 23.3 S2).

THE MEASUREMENT
---------------
The server stamps ``clock.t1`` on each message as it writes it to an agent's
socket (``AgentConnection.send_message``).  The agent stamps t2 on receipt and
t3 as its next heartbeat leaves, and echoes all three; the server stamps t4
the moment that heartbeat arrives (``api/agent.py``), before any queue.  Then

    offset = ((t2 - t1) + (t3 - t4)) / 2      (host minus server)
    delay  = (t4 - t1) - (t3 - t2)            (network round trip)

Queue residence between t2 and t3 drops out.  The S0 spike (2026-10-12): the
median of such samples within 2 ms of ground truth on five OSes with replies
held up to 2 s.  Single samples strayed up to 47 ms on Wi-Fi, so the host's
figure is always the MEDIAN of the last ``WINDOW`` samples.

A HOST SO FAR OFF ITS MESSAGES ARE REFUSED
------------------------------------------
Message validation rejects any message whose own timestamp is more than 30
minutes from the server's clock -- so the hosts this feature exists for most
would never be measured.  For a bound connection, the refused heartbeat's
timestamp still gives a coarse offset (``method = "timestamp"``): accurate to
seconds, which is plenty when the clock is half an hour wrong.

NO PER-HEARTBEAT WRITES
-----------------------
Samples live on the connection object, in memory, with the socket.  A host's
row is written at most once per ``PERSIST_SECONDS`` -- sooner only if the
median moved by ``PERSIST_JUMP_MS`` -- through one batched UPDATE per database
per ``FLUSH_SECONDS``, like the Phase 22.2 heartbeat batch.  One history row
per host per ``HISTORY_SECONDS``.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import bindparam, delete, insert, update
from sqlalchemy.orm import sessionmaker

from backend.persistence.models import Host, HostClockSample

logger = logging.getLogger(__name__)

WINDOW = 9  # samples in the median
MAX_DELAY_S = 30.0  # a round trip longer than this measures nothing useful
STEP_TOLERANCE_S = 0.5  # wall t3-t2 vs monotonic hold: the clock was stepped
PERSIST_SECONDS = 300
PERSIST_JUMP_MS = 250.0
HISTORY_SECONDS = 900
RETENTION_DAYS = 30
FLUSH_SECONDS = 5.0

METHOD_EXCHANGE = "exchange"
METHOD_TIMESTAMP = "timestamp"


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def sample_from_clock(clock: Any, t4: float) -> Optional[Tuple[float, float]]:
    """``(offset_s, delay_s)`` from a heartbeat's ``clock`` block, or None
    when the block is malformed, the round trip is implausible, or the host's
    clock was stepped while the reply waited (wall vs monotonic disagree)."""
    if not isinstance(clock, dict):
        return None
    t1, t2, t3 = (_number(clock.get(k)) for k in ("t1", "t2", "t3"))
    hold = _number(clock.get("hold"))
    if None in (t1, t2, t3, hold) or hold < 0:
        return None
    if abs((t3 - t2) - hold) > STEP_TOLERANCE_S:
        return None
    delay = (t4 - t1) - (t3 - t2)
    if delay < 0 or delay > MAX_DELAY_S:
        return None
    return ((t2 - t1) + (t3 - t4)) / 2, delay


def _state(connection) -> Dict[str, Any]:
    state = getattr(connection, "clock_state", None)
    if not isinstance(state, dict):
        state = {"samples": deque(maxlen=WINDOW), "method": METHOD_EXCHANGE}
        connection.clock_state = state
    return state


def observe(connection, clock: Any, t4: float) -> bool:
    """Record one exchange sample on ``connection``; True if it was usable."""
    sample = sample_from_clock(clock, t4)
    if sample is None:
        return False
    state = _state(connection)
    if state["method"] != METHOD_EXCHANGE:
        state["samples"].clear()  # the coarse estimate is superseded
        state["method"] = METHOD_EXCHANGE
    state["samples"].append(sample)
    return True


def observe_refused(connection, message_timestamp: str, t4: float) -> bool:
    """A heartbeat refused for its timestamp still says how far off it is."""
    try:
        sent = datetime.fromisoformat(str(message_timestamp).replace("Z", "+00:00"))
    except ValueError:
        return False
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=timezone.utc)
    state = _state(connection)
    if state["method"] != METHOD_TIMESTAMP:
        state["samples"].clear()
        state["method"] = METHOD_TIMESTAMP
    state["samples"].append((sent.timestamp() - t4, None))
    return True


def current(connection) -> Optional[Dict[str, Any]]:
    """The connection's smoothed figure, or None before any sample."""
    state = getattr(connection, "clock_state", None)
    if not isinstance(state, dict) or not state["samples"]:
        return None
    offsets = [s[0] for s in state["samples"]]
    delays = [s[1] for s in state["samples"] if s[1] is not None]
    return {
        "offset_ms": round(statistics.median(offsets) * 1000, 3),
        "rtt_ms": round(statistics.median(delays) * 1000, 3) if delays else None,
        "samples": len(offsets),
        "method": state["method"],
    }


def reset(connection) -> None:
    """Forget the samples: the clock was just stepped (S5), so every earlier
    sample measures a clock that no longer exists.  The next figure is
    persisted as soon as there is one."""
    state = getattr(connection, "clock_state", None)
    if isinstance(state, dict):
        state["samples"].clear()
        state.pop("persisted_at", None)
        state.pop("persisted_offset", None)


# --------------------------------------------------------------------------
# persistence: rate-limited, batched
# --------------------------------------------------------------------------

_pending: Dict[str, Tuple[object, Dict[str, Any]]] = {}
_lock = threading.Lock()
_flusher = None
_last_prune: Dict[int, float] = {}  # per database

_table = Host.__table__
_UPDATE = (
    update(_table)
    .where(_table.c.id == bindparam("hid"))
    .values(
        clock_offset_ms=bindparam("offset_ms"),
        clock_rtt_ms=bindparam("rtt_ms"),
        clock_samples=bindparam("samples"),
        clock_method=bindparam("method"),
        clock_measured_at=bindparam("measured_at"),
    )
)


def persist_if_due(connection, engine) -> bool:
    """Queue this connection's figure for writing when it is due.  Called on
    every heartbeat; writes nothing most of the time."""
    host_id = getattr(connection, "host_id", None)
    figure = current(connection)
    if not host_id or figure is None or engine is None:
        return False
    state = connection.clock_state
    now = time.monotonic()
    last_at = state.get("persisted_at")
    last_offset = state.get("persisted_offset")
    moved = (
        last_offset is None or abs(figure["offset_ms"] - last_offset) > PERSIST_JUMP_MS
    )
    if last_at is not None and now - last_at < PERSIST_SECONDS and not moved:
        return False
    history_due = now - state.get("history_at", -HISTORY_SECONDS) >= HISTORY_SECONDS
    state["persisted_at"], state["persisted_offset"] = now, figure["offset_ms"]
    if history_due:
        state["history_at"] = now
    row = {
        **figure,
        "measured_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "history": history_due,
    }
    _queue(str(host_id), engine, row)
    return True


def _queue(host_id: str, engine, row: Dict[str, Any]) -> None:
    global _flusher  # pylint: disable=global-statement
    with _lock:
        previous = _pending.get(host_id)
        if previous is not None and previous[1].get("history"):
            row["history"] = True  # never lose a due history point
        _pending[host_id] = (engine, row)
    if _flusher is None or _flusher.done():
        try:
            _flusher = asyncio.get_running_loop().create_task(_flush_forever())
        except RuntimeError:  # no running loop (sync tests): write now
            flush()


def flush() -> int:
    """Write every pending figure; returns how many hosts were updated."""
    with _lock:
        batch = dict(_pending)
        _pending.clear()
    if not batch:
        return 0
    by_engine: Dict[object, list] = {}
    for host_id, (engine, row) in batch.items():
        by_engine.setdefault(engine, []).append({"hid": uuid.UUID(host_id), **row})
    written = 0
    for engine, rows in by_engine.items():
        try:
            _write(engine, rows)
            written += len(rows)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception(
                "Clock tracking: could not record %d host clock(s); retrying next flush",
                len(rows),
            )
            with _lock:
                for row in rows:
                    host_id = str(row.pop("hid"))
                    _pending.setdefault(host_id, (engine, row))
    return written


def _write(engine, rows) -> None:
    history = [
        {
            "id": uuid.uuid4(),
            "host_id": r["hid"],
            "measured_at": r["measured_at"],
            "offset_ms": r["offset_ms"],
            "rtt_ms": r["rtt_ms"],
            "method": r["method"],
        }
        for r in rows
        if r.get("history")
    ]
    with sessionmaker(bind=engine)() as session:
        session.execute(_UPDATE, rows)
        if history:
            session.execute(insert(HostClockSample.__table__), history)
        if time.monotonic() - _last_prune.get(id(engine), float("-inf")) > 3600:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
                days=RETENTION_DAYS
            )
            session.execute(
                delete(HostClockSample.__table__).where(
                    HostClockSample.__table__.c.measured_at < cutoff
                )
            )
            _last_prune[id(engine)] = time.monotonic()
        session.commit()


async def _flush_forever() -> None:
    while True:
        await asyncio.sleep(FLUSH_SECONDS)
        try:
            await asyncio.to_thread(flush)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Clock tracking flush failed")
