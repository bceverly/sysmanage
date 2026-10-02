# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Server-side observations for the fleet scenarios (Phase 22).

What the agents see (fleet.py) says how the server BEHAVES; this says why:
the message queue's backlog and its oldest message, rows expired (silent data
loss), hosts the heartbeat monitor marked down, database connections, the
server process's CPU and memory, and how long /api/health takes to answer
(the event loop's responsiveness).  Read-only: it never writes to the
database it watches.
"""

import asyncio
import os
import time
from typing import List, Optional

import aiohttp
from sqlalchemy import create_engine, text

_CLK_TCK = os.sysconf("SC_CLK_TCK")

QUEUE_SQL = text(
    "SELECT direction, status, count(*) FROM message_queue GROUP BY direction, status"
)
OLDEST_SQL = text(
    "SELECT EXTRACT(EPOCH FROM (now() AT TIME ZONE 'utc' - min(created_at))) "
    "FROM message_queue WHERE direction = 'inbound' AND status = 'pending'"
)
HOSTS_SQL = text(
    "SELECT approval_status, active, count(*) FROM host "
    "WHERE fqdn LIKE '%.sim.test' GROUP BY approval_status, active"
)
PG_CONN_SQL = text(
    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
)


def _proc_tree(pid: int) -> list:
    """``pid`` and its live descendants -- with SYSMANAGE_UVICORN_WORKERS > 1
    the work happens in the workers, children of the process we started."""
    tree, todo = [], [pid]
    while todo:
        current = todo.pop()
        tree.append(current)
        try:
            with open(
                f"/proc/{current}/task/{current}/children", encoding="ascii"
            ) as fh:
                todo.extend(int(child) for child in fh.read().split())
        except (OSError, ValueError):
            # The process exited between listing and reading: it has no
            # children left to count.
            continue
    return tree


def _one_cpu_seconds(pid: int) -> Optional[float]:
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii") as fh:
            fields = fh.read().rsplit(")", 1)[1].split()
        return sum(int(fields[i]) for i in (11, 12, 13, 14)) / _CLK_TCK
    except (OSError, IndexError, ValueError):
        return None


def _proc_cpu_seconds(pid: int) -> Optional[float]:
    """utime + stime of the process tree (and reaped children), in seconds."""
    readings = [_one_cpu_seconds(member) for member in _proc_tree(pid)]
    if readings[0] is None:
        return None
    return sum(r for r in readings if r is not None)


def _one_rss_mb(pid: int) -> Optional[float]:
    try:
        with open(f"/proc/{pid}/status", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except (OSError, ValueError):
        return None
    return None


def _proc_rss_mb(pid: int) -> Optional[float]:
    readings = [_one_rss_mb(member) for member in _proc_tree(pid)]
    if readings[0] is None:
        return None
    return sum(r for r in readings if r is not None)


class Observer:
    """Samples the server every ``interval`` seconds into ``samples``."""

    def __init__(self, base_url: str, db_url: str, pid_getter, interval: float = 5.0):
        self.base = base_url.rstrip("/")
        url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        self.engine = create_engine(
            url, pool_size=1, max_overflow=0, pool_pre_ping=True
        )
        self.pid_getter = pid_getter
        self.interval = interval
        self.samples: List[dict] = []
        self._task: Optional[asyncio.Task] = None
        self._last_cpu = None
        self._started = time.monotonic()

    def _db_sample(self) -> dict:
        out = {
            "queue": {},
            "oldest_inbound_pending_s": None,
            "hosts": {},
            "pg_connections": None,
        }
        try:
            with self.engine.connect() as conn:
                for direction, status, count in conn.execute(QUEUE_SQL):
                    out["queue"][f"{direction}.{status}"] = count
                oldest = conn.execute(OLDEST_SQL).scalar()
                out["oldest_inbound_pending_s"] = (
                    round(float(oldest), 1) if oldest is not None else None
                )
                for approval, active, count in conn.execute(HOSTS_SQL):
                    key = f"{approval}.{'up' if active else 'down'}"
                    out["hosts"][key] = count
                out["pg_connections"] = conn.execute(PG_CONN_SQL).scalar()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            out["db_error"] = type(exc).__name__
        return out

    async def _health_ms(self, session) -> Optional[float]:
        t0 = time.monotonic()
        try:
            async with session.get(f"{self.base}/api/health",
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:  # fmt: skip
                await resp.read()
                return (
                    round((time.monotonic() - t0) * 1000, 1)
                    if resp.status == 200
                    else None
                )
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            return None

    def _cpu_percent(self, pid, now) -> Optional[float]:
        cpu = _proc_cpu_seconds(pid) if pid else None
        result = None
        if cpu is not None and self._last_cpu and self._last_cpu[0] == pid:
            elapsed = now - self._last_cpu[2]
            # A worker that died and was replaced takes its CPU time with it.
            if elapsed > 0 and cpu >= self._last_cpu[1]:
                result = round(100 * (cpu - self._last_cpu[1]) / elapsed, 1)
        self._last_cpu = (pid, cpu, now) if cpu is not None else None
        return result

    async def _loop(self):
        async with aiohttp.ClientSession() as session:
            while True:
                now = time.monotonic()
                pid = self.pid_getter()
                sample = await asyncio.to_thread(self._db_sample)
                sample.update(
                    t=round(now - self._started, 1),
                    health_ms=await self._health_ms(session),
                    server_cpu_percent=self._cpu_percent(pid, now),
                    server_rss_mb=_proc_rss_mb(pid) if pid else None,
                )
                self.samples.append(sample)
                await asyncio.sleep(max(0.0, self.interval - (time.monotonic() - now)))

    def start(self):
        self._started = time.monotonic()
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self.engine.dispose()

    def mark(self, label: str):
        """Note an event (a restart) on the timeline."""
        self.samples.append(
            {"t": round(time.monotonic() - self._started, 1), "event": label}
        )
