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
import subprocess  # nosec B404 - fixed argv (ps, pgrep)
import time
from typing import List, Optional

import aiohttp
from sqlalchemy import create_engine, text

# /proc is Linux-only (the harness runs there); importing must still work on
# Windows, where the harness's pure helpers are unit-tested.
_CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100

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
TOP_STATEMENTS_SQL = text(
    "SELECT query, calls, rows, total_exec_time AS total_ms, mean_exec_time AS mean_ms "
    "FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 25"
)
PG_CONN_SQL = text(
    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
)


_HAVE_PROC = os.path.isdir("/proc/self")


def _ps_tree(pid: int) -> list:
    """No /proc (OpenBSD, the macOS-like BSDs): children through pgrep."""
    tree, todo = [], [pid]
    while todo:
        current = todo.pop()
        tree.append(current)
        out = subprocess.run(  # nosec B603 B607 - fixed argv
            ["pgrep", "-P", str(current)], capture_output=True, text=True, check=False
        ).stdout
        todo.extend(int(child) for child in out.split())
    return tree


def _cputime_seconds(value: str) -> float:
    """BSD ps ``time``: [[dd-]hh:]mm:ss[.cc]."""
    days, _, clock = value.rpartition("-")
    seconds = 0.0
    for part in clock.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds + (int(days) * 86400 if days else 0)


def _ps_readings(pid: int):
    """(cpu seconds, rss MB) of the process tree through ``ps``, or Nones."""
    tree = {str(p) for p in _ps_tree(pid)}
    # Every process, filtered here: OpenBSD's ps reads only the first pid of
    # "-p a,b" (and only the last of repeated -p), which measured just the
    # supervisor and showed a busy server at 0.3% CPU.
    out = subprocess.run(  # nosec B603 B607 - fixed argv
        ["ps", "-A", "-o", "pid=,rss=,time="],
        capture_output=True, text=True, check=False,
    ).stdout  # fmt: skip
    rows = [line.split() for line in out.splitlines() if line.strip()]
    rows = [row for row in rows if row and row[0] in tree]
    if not rows:
        return None, None
    try:
        cpu = sum(_cputime_seconds(row[2]) for row in rows)
        rss = sum(int(row[1]) for row in rows) / 1024
    except (IndexError, ValueError):
        return None, None
    return cpu, rss


# Processes that are part of a load run besides the server tree and this
# observer: the database, the container plumbing, OpenBAO.
RUN_COMMANDS = ("postgres", "docker-proxy", "containerd", "dockerd", "bao", "ssh")


def _all_cpu_seconds() -> dict:
    """pid -> (ppid, command, cpu seconds) for every process, via ``ps``."""
    out = subprocess.run(  # nosec B603 B607 - fixed argv
        ["ps", "-A", "-o", "pid=,ppid=,comm=,time="],
        capture_output=True, text=True, check=False,
    ).stdout  # fmt: skip
    table = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            table[int(parts[0])] = (
                int(parts[1]),
                parts[2],
                _cputime_seconds(parts[-1]),
            )
        except ValueError:
            continue
    return table


def _descendants(table: dict, roots) -> set:
    children = {}
    for pid, (ppid, _comm, _cpu) in table.items():
        children.setdefault(ppid, []).append(pid)
    found, todo = set(), [r for r in roots if r]
    while todo:
        pid = todo.pop()
        if pid not in found:
            found.add(pid)
            todo.extend(children.get(pid, []))
    return found


class OtherCpu:
    """CPU used by processes that are NOT part of the run, per CPU of this
    machine, between two calls.  2026-10-04: a run on a workstation shared
    with a browser, chat clients and another project's test suite looked
    three times worse than the code was; load average could not tell that
    apart from a busy server on a small box, CPU time per process can."""

    def __init__(self):
        self._last = None  # (monotonic time, {pid: cpu seconds})

    def sample(self, server_pid) -> Optional[float]:
        now = time.monotonic()
        table = _all_cpu_seconds()
        if not table:
            return None
        ours = _descendants(table, [server_pid, os.getpid()])
        other = {pid: cpu for pid, (_ppid, comm, cpu) in table.items()
                 if pid not in ours and not comm.startswith(RUN_COMMANDS)}  # fmt: skip
        result = None
        if self._last is not None and now > self._last[0]:
            used = sum(max(0.0, cpu - self._last[1].get(pid, 0.0))
                       for pid, cpu in other.items() if pid in self._last[1])  # fmt: skip
            result = round(used / (now - self._last[0]) / (os.cpu_count() or 1), 2)
        self._last = (now, other)
        return result


def host_load_per_cpu() -> Optional[float]:
    """1-minute load average per CPU of THIS machine.  Over ~1.5 the server
    shares the box with other work and the run is not a clean measurement
    (2026-10-04: another project's test suite plus 26 GB of swap made one run
    look 3x worse than the code was)."""
    try:
        return round(os.getloadavg()[0] / (os.cpu_count() or 1), 2)
    except (AttributeError, OSError):
        return None


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
    if not _HAVE_PROC:
        return _ps_readings(pid)[0]
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
    if not _HAVE_PROC:
        return _ps_readings(pid)[1]
    readings = [_one_rss_mb(member) for member in _proc_tree(pid)]
    if readings[0] is None:
        return None
    return sum(r for r in readings if r is not None)


def _engine_for(db_url: str):
    url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_size=1, max_overflow=0, pool_pre_ping=True)


def _add_db_counts(conn, out: dict) -> None:
    """One database's queue and host counts, summed into ``out``."""
    for direction, status, count in conn.execute(QUEUE_SQL):
        key = f"{direction}.{status}"
        out["queue"][key] = out["queue"].get(key, 0) + count
    oldest = conn.execute(OLDEST_SQL).scalar()
    if oldest is not None:
        out["oldest_inbound_pending_s"] = max(
            round(float(oldest), 1), out["oldest_inbound_pending_s"] or 0.0
        )
    for approval, active, count in conn.execute(HOSTS_SQL):
        key = f"{approval}.{'up' if active else 'down'}"
        out["hosts"][key] = out["hosts"].get(key, 0) + count


class Observer:
    """Samples the server every ``interval`` seconds into ``samples``."""

    def __init__(self, base_url: str, db_url: str, pid_getter, interval: float = 5.0, tenant_db_urls=(),):  # fmt: skip  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self.base = base_url.rstrip("/")
        self.engine = _engine_for(db_url)
        # Multi-tenant stacks: a tenant's hosts and queue live in its own
        # database; queue and host counts are summed across all of them.
        self.tenant_engines = [_engine_for(u) for u in tenant_db_urls]
        self.pid_getter = pid_getter
        self.interval = interval
        self.samples: List[dict] = []
        self.top_statements: List[dict] = []
        self._task: Optional[asyncio.Task] = None
        self._last_cpu = None
        self._other_cpu = OtherCpu()
        self._started = time.monotonic()

    def _db_sample(self) -> dict:
        out = {
            "queue": {},
            "oldest_inbound_pending_s": None,
            "hosts": {},
            "pg_connections": None,
        }
        try:
            for engine in [self.engine, *self.tenant_engines]:
                with engine.connect() as conn:
                    _add_db_counts(conn, out)
            with self.engine.connect() as conn:
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
                    host_load_per_cpu=host_load_per_cpu(),
                    other_cpu_per_cpu=self._other_cpu.sample(pid),
                )
                self.samples.append(sample)
                await asyncio.sleep(max(0.0, self.interval - (time.monotonic() - now)))

    def start(self):
        self._started = time.monotonic()
        self._statements("reset")
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self.top_statements = self._statements("top")
        self.engine.dispose()
        for engine in self.tenant_engines:
            engine.dispose()

    def _statements(self, action: str) -> list:
        """pg_stat_statements: zero it at the start, report the costliest
        statements at the end.  Empty where the extension is unavailable (a
        --db-url database without it); never fails the run."""
        try:
            with self.engine.begin() as conn:
                if action == "reset":
                    conn.execute(
                        text("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
                    )
                    conn.execute(text("SELECT pg_stat_statements_reset()"))
                    return []
                rows = conn.execute(TOP_STATEMENTS_SQL).mappings().all()
        except Exception:  # pylint: disable=broad-exception-caught
            return []
        return [
            {"total_ms": round(r["total_ms"]), "calls": r["calls"],
             "mean_ms": round(r["mean_ms"], 3), "rows": r["rows"],
             "query": r["query"][:300]}  # fmt: skip
            for r in rows
        ]

    def mark(self, label: str):
        """Note an event (a restart) on the timeline."""
        self.samples.append(
            {"t": round(time.monotonic() - self._started, 1), "event": label}
        )
