# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""One leader among the server's worker processes (Phase 22.2).

WHY
---
With ``SYSMANAGE_UVICORN_WORKERS`` > 1 uvicorn runs the whole lifespan in
every worker, so every tick -- heartbeat monitor, alert evaluator, schedulers,
retention, feed refreshes, the discovery beacon -- ran once PER WORKER: alerts
evaluated four times, schedules dispatched four times, the beacon's UDP bind
failing in all but one worker.  Work that belongs to the whole server must run
in exactly one process.

HOW
---
Every worker asks PostgreSQL for one session-level advisory lock on a
connection it keeps.  The worker that gets it is the leader; ``singleton()``
tasks run there.  In the other workers those tasks wait, and each worker asks
for the lock again every ``RETRY_SECONDS``: when the leader dies its
connection closes, PostgreSQL releases the lock, a follower takes it and its
waiting tasks start.  (uvicorn restarts the dead worker; it comes back as a
follower.)

The leader checks its connection every ``RETRY_SECONDS``.  If the connection
was lost and the lock cannot be taken back -- another worker holds it now --
this worker's ticks are running without the lock, so it shuts itself down
(uvicorn starts a fresh worker in its place) rather than run them twice.

Work that is per process stays per process: the queue processor (inbound
claims are per host, see ``inbound_processor``; outbound goes to this worker's
own WebSockets), the Graylog health check, module loading.

SQLite and other non-PostgreSQL databases have no advisory locks and support
one worker only: every process is its own leader, and more than one worker is
refused loudly at startup (``check_worker_support``).
"""

import asyncio
import contextlib
import os
import signal
from typing import Optional

from sqlalchemy import text

from backend.persistence import pool_sizing
from backend.utils.verbosity_logger import get_logger

logger = get_logger(__name__)

# 'SYSMANAG' -- any constant works; it only has to be SysManage's own.
LEADER_LOCK_KEY = 0x5359534D414E4147
RETRY_SECONDS = 15.0
# Every worker holds this lock SHARED for its whole life, so counting its
# holders counts the live server processes on this database -- whether they
# came from SYSMANAGE_UVICORN_WORKERS, `uvicorn --workers N` or another
# machine.  (Two-key form: its own namespace, apart from the leader lock and
# the inbound drain's per-host locks.)
MEMBER_LOCK = (0x534E, 1)
_MEMBERS_SQL = text(
    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
    "AND classid::bigint = :c AND objid::bigint = :k AND objsubid = 2 AND granted "
    "AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
)


class Leadership:
    """This process's view of who runs the server-wide background work."""

    def __init__(self):
        self._engine = None
        self._conn = None
        self._member_conn = None
        self.members = 1  # live server processes sharing this database
        self._event: Optional[asyncio.Event] = None
        self._watch_task = None

    # -- state ------------------------------------------------------------------

    @property
    def is_leader(self) -> bool:
        return self._event is not None and self._event.is_set()

    def _uses_locks(self) -> bool:
        return self._engine is not None and self._engine.dialect.name == "postgresql"

    # -- the lock ---------------------------------------------------------------

    def _try_acquire(self) -> bool:
        """Take the lock on a connection this process then keeps; blocking."""
        conn = self._engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            held = bool(
                conn.execute(
                    text("SELECT pg_try_advisory_lock(:key)"), {"key": LEADER_LOCK_KEY}
                ).scalar()
            )
        except Exception:
            conn.close()
            raise
        if held:
            self._conn = conn
        else:
            conn.close()
        return held

    def _still_held(self) -> bool:
        """Is the leader's connection alive?  (Its lock lives as long as it.)"""
        try:
            self._conn.execute(text("SELECT 1"))
            return True
        except Exception:  # pylint: disable=broad-exception-caught
            try:
                self._conn.invalidate()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            self._conn = None
            return False

    # -- membership -------------------------------------------------------------

    def _count_members(self) -> int:
        """Join (once) and count the processes holding the member lock; blocking."""
        c, k = MEMBER_LOCK
        if self._member_conn is None:
            conn = self._engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            )
            try:
                conn.execute(
                    text("SELECT pg_advisory_lock_shared(:c, :k)"), {"c": c, "k": k}
                )
            except Exception:
                conn.invalidate()
                raise
            self._member_conn = conn
        try:
            count = self._member_conn.execute(_MEMBERS_SQL, {"c": c, "k": k}).scalar()
        except Exception:
            with contextlib.suppress(Exception):
                self._member_conn.invalidate()
            self._member_conn = None  # rejoin next time
            raise
        return max(1, int(count or 0))

    async def _refresh_members(self) -> None:
        try:
            members = await asyncio.to_thread(self._count_members)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Leader election: could not count server processes (%s); keeping %d",
                exc,
                self.members,
            )
            return
        if members != self.members:
            logger.info("Server processes sharing this database: %d", members)
        self.members = members

    # -- lifecycle --------------------------------------------------------------

    async def start(self, engine) -> None:
        """Decide this process's role; call once, early in the lifespan."""
        self._engine = engine
        self._event = asyncio.Event()
        if not self._uses_locks():
            self._event.set()
            return
        await self._refresh_members()
        try:
            won = await asyncio.to_thread(self._try_acquire)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error(
                "Leader election: could not ask PostgreSQL for the leader lock "
                "(%s); retrying every %.0f s, background work waits",
                exc,
                RETRY_SECONDS,
            )
            won = False
        if won:
            self._event.set()
            logger.info(
                "Leader election: this worker (pid %d) runs the background work",
                os.getpid(),
            )
        else:
            logger.info(
                "Leader election: another worker leads; this worker (pid %d) "
                "serves requests and agents and stands by",
                os.getpid(),
            )
        self._watch_task = asyncio.create_task(self._watch())

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(RETRY_SECONDS)
            await self._refresh_members()
            try:
                await self._check()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning("Leader election: check failed (%s); will retry", exc)

    async def _check(self) -> None:
        if not self.is_leader:
            if await asyncio.to_thread(self._try_acquire):
                logger.warning(
                    "Leader election: the leader is gone; this worker (pid %d) "
                    "takes over the background work",
                    os.getpid(),
                )
                self._event.set()
            return
        if await asyncio.to_thread(self._still_held):
            return
        if await asyncio.to_thread(self._try_acquire):
            logger.warning(
                "Leader election: the database connection dropped; the leader "
                "lock was taken back"
            )
            return
        logger.critical(
            "Leader election: this worker (pid %d) lost the leader lock to another "
            "worker while running the background work; shutting this worker down "
            "so it cannot run twice (uvicorn starts a replacement)",
            os.getpid(),
        )
        os.kill(os.getpid(), signal.SIGTERM)

    async def stop(self) -> None:
        if self._watch_task is not None:
            self._watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watch_task
            self._watch_task = None
        for name in ("_conn", "_member_conn"):
            conn = getattr(self, name)
            if conn is None:
                continue
            setattr(self, name, None)
            # invalidate, not close: a closed connection goes back to the pool
            # and its session -- and the lock with it -- would live on there.
            with contextlib.suppress(Exception):
                await asyncio.to_thread(conn.invalidate)

    # -- singleton tasks --------------------------------------------------------

    async def _when_leader(self, coro):
        if self._event is not None and not self._event.is_set():
            try:
                await self._event.wait()
            except asyncio.CancelledError:
                coro.close()  # never started: no "never awaited" warning
                raise
        return await coro

    def singleton(self, coro) -> asyncio.Task:
        """``asyncio.create_task`` for work that must run in ONE process.

        Runs ``coro`` now in the leader; in a follower the task waits and runs
        it if this worker becomes the leader.  Before ``start()`` (tests, a
        single process) it simply runs."""
        return asyncio.create_task(self._when_leader(coro))


def check_worker_support(engine) -> None:
    """Refuse more than one worker on a database without advisory locks."""
    workers = pool_sizing.server_workers()
    if workers > 1 and engine.dialect.name != "postgresql":
        raise RuntimeError(
            f"SYSMANAGE_UVICORN_WORKERS={workers} needs PostgreSQL: on "
            f"{engine.dialect.name} the workers cannot agree on who runs the "
            "background work or claim queued messages safely. Use one worker."
        )


def multi_process() -> bool:
    """True when other server processes share this database's queues: the
    configured worker count, or the processes actually counted (a server
    started with `uvicorn --workers N`, or a second machine)."""
    return pool_sizing.server_workers() > 1 or leadership.members > 1


leadership = Leadership()


def singleton_task(coro) -> asyncio.Task:
    """Module-level shorthand for ``leadership.singleton``."""
    return leadership.singleton(coro)
