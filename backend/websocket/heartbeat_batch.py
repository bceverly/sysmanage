# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Batched heartbeat writes (Phase 22.2).

WHY
---
Every heartbeat loaded its host's row and wrote it back with a commit, inline
on the WebSocket path.  The 10,000-agent storm (2026-10-02): ~333 write
transactions a second for heartbeats alone, worker pools exhausted
("QueuePool limit ... reached"), heartbeats waiting 30 s for a connection.

HOW
---
A connection's FIRST heartbeat takes the full path (reboot orchestration,
geo lookup, privilege / shell / version fields).  After that, a heartbeat
whose reported fields are unchanged only records "this host was seen now"
here; every ``FLUSH_SECONDS`` one bulk UPDATE per database writes them all
(``last_access``, and ``status``/``active`` back to up).  A changed field takes
the full path again.  The heartbeat monitor's timeout is minutes, so a few
seconds of delay in ``last_access`` changes nothing it decides.

Per worker: each worker batches its own connections.
"""

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, Tuple

from sqlalchemy import bindparam, update
from sqlalchemy.orm import sessionmaker

from backend.persistence.models import Host

logger = logging.getLogger(__name__)

FLUSH_SECONDS = 5.0

# host_id -> (engine, seen_at)
_pending: Dict[str, Tuple[object, datetime]] = {}
_lock = threading.Lock()  # note() runs on the loop, flush() on a worker thread
_flusher = None

# Core, not the ORM's bulk-by-primary-key: that raises for the whole batch
# when one host was deleted meanwhile, and a failed batch is kept for retry --
# it would fail forever.  This updates the rows that exist.
_table = Host.__table__
_UPDATE = (
    update(_table)
    .where(_table.c.id == bindparam("hid"))
    .values(last_access=bindparam("seen"), status="up", active=True)
)


def fingerprint(message_data: dict) -> tuple:
    """The heartbeat fields that are written to the host row when they change."""
    shells = message_data.get("enabled_shells")
    return (
        message_data.get("is_privileged"),
        tuple(shells) if isinstance(shells, list) else shells,
        message_data.get("agent_version"),
        message_data.get("public_ip"),
    )


def can_batch(connection, message_data: dict) -> bool:
    """True when this heartbeat changes nothing but ``last_access``."""
    if getattr(connection, "is_mock_connection", False):
        return False  # a queued heartbeat: never touches last_access
    return getattr(connection, "heartbeat_fingerprint", None) == fingerprint(
        message_data
    )


def remember(connection, message_data: dict) -> None:
    """After a full heartbeat: later identical ones may be batched."""
    connection.heartbeat_fingerprint = fingerprint(message_data)


def note(host_id, engine) -> None:
    """Record that ``host_id`` (in ``engine``'s database) was seen now."""
    global _flusher  # pylint: disable=global-statement
    seen_at = datetime.now(timezone.utc).replace(tzinfo=None)
    with _lock:
        _pending[str(host_id)] = (engine, seen_at)
    if _flusher is None or _flusher.done():
        try:
            _flusher = asyncio.get_running_loop().create_task(_flush_forever())
        except RuntimeError:  # no running loop (sync tests): write now
            flush()


def flush() -> int:
    """Write every pending heartbeat; returns how many hosts were updated."""
    with _lock:
        batch = dict(_pending)
        _pending.clear()
    if not batch:
        return 0
    by_engine: Dict[object, list] = {}
    for host_id, (engine, seen_at) in batch.items():
        by_engine.setdefault(engine, []).append(
            {"hid": uuid.UUID(host_id), "seen": seen_at}
        )
    written = 0
    for engine, rows in by_engine.items():
        try:
            with sessionmaker(bind=engine)() as session:
                session.execute(_UPDATE, rows)  # one executemany per database
                session.commit()
            written += len(rows)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception(
                "Heartbeat batch: could not record %d heartbeat(s); retrying next flush",
                len(rows),
            )
            with _lock:  # keep them, unless a newer one arrived meanwhile
                for row in rows:
                    _pending.setdefault(str(row["hid"]), (engine, row["seen"]))
    return written


async def _flush_forever() -> None:
    while True:
        await asyncio.sleep(FLUSH_SECONDS)
        try:
            await asyncio.to_thread(flush)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Heartbeat batch flush failed")
