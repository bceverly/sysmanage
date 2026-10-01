# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Database connection pool sizing (Phase 22.2, pulled forward 2026-10-01).

WHY
---
The Phase 22 scale-harness baseline: every run from 50 agents up ended with
SQLAlchemy's default pool (5 + 10 overflow) exhausted, health checks timing
out, the inbound queue frozen and every agent disconnected -- with the CPU
idle.  Two causes, two fixes:

1. every agent WebSocket held a database session for its whole life, so the
   pool drained one agent at a time (fixed in ``backend/api/agent.py``: a
   short-lived session per message);
2. the pool was never sized at all -- it was SQLAlchemy's default on every
   machine, from a 1 GB droplet to a 64-core server (this module).

CONFIGURATION (``sysmanage.yaml``, every key optional)
-----------------------------------------------------
    database_pool:
      size: 16            # connections kept open, per server worker
      max_overflow: 16    # extra connections for bursts, closed when idle
      timeout: 30         # seconds to wait for a free connection
      recycle: 1800       # maximum connection age, seconds (HA: below proxy idle timeouts)
      tenant_size: 2      # per tenant database (multi-tenancy), per worker
      tenant_max_overflow: 6

A key that is absent is computed for THIS machine by ``recommend()``.
Installers run ``python -m backend.persistence.pool_sizing --apply <config>``
so the values are written out where an administrator can see and change them.

THE FORMULA
-----------
With short-lived sessions a connection is busy only while a request handler
or background task is actually talking to the database, so the number in use
tracks the work in flight -- the thread pool behind synchronous endpoints and
the periodic tasks -- not the number of connected agents.  Per worker:

    size         = clamp(2 x CPUs + 8, 10, 40)
    max_overflow = size
    size + max_overflow <= max(20, 25 x GB of RAM)   (PostgreSQL usually shares
                                                       the box; ~10 MB/backend)

THE STARTUP CHECK
-----------------
At startup the server asks PostgreSQL for ``max_connections``.  Every worker's
pool, plus a reserve for everything else (superuser slots, migrations, the
canary, an operator's psql), must fit.  If it does not, the overflow and then
the size are reduced to fit, with a loud warning saying so -- the server never
refuses to start over this, and never silently plans for more connections
than the database will accept.
"""

import argparse
import logging
import os
import sys
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

CONFIG_KEY = "database_pool"
# Connections kept free of SysManage's pools for everything else.
RESERVED_CONNECTIONS = 10
DEFAULT_TIMEOUT = 30
DEFAULT_RECYCLE = 1800
DEFAULT_TENANT_SIZE = 2
DEFAULT_TENANT_OVERFLOW = 6
MIN_SIZE, MAX_SIZE = 10, 40


def _memory_gb() -> Optional[float]:
    """Physical memory in GB, or None when it cannot be read."""
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
    except (AttributeError, OSError, ValueError):
        pass
    if sys.platform == "win32":  # pragma: no cover - exercised on Windows only
        import ctypes  # pylint: disable=import-outside-toplevel

        class _Status(ctypes.Structure):  # pylint: disable=too-few-public-methods
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                        ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                        ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                        ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                        ("avail_extended", ctypes.c_ulonglong)]  # fmt: skip

        status = _Status()
        status.length = ctypes.sizeof(_Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.total / 1024**3
    return None


def machine_capacity() -> Tuple[int, Optional[float]]:
    """(CPUs this process may use, GB of RAM or None)."""
    try:
        cpus = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        cpus = os.cpu_count() or 1
    return max(1, cpus), _memory_gb()


def server_workers() -> int:
    """Uvicorn workers -- each has its own pools."""
    try:
        return max(1, int(os.environ.get("SYSMANAGE_UVICORN_WORKERS", "1") or "1"))
    except ValueError:
        return 1


def recommend(cpus: int, memory_gb: Optional[float]) -> Dict[str, int]:
    """The pool for one worker on a machine of this size."""
    size = max(MIN_SIZE, min(MAX_SIZE, 2 * cpus + 8))
    overflow = size
    if memory_gb:
        ceiling = max(20, int(25 * memory_gb))
        if size + overflow > ceiling:
            size = max(MIN_SIZE // 2, min(size, ceiling // 2))
            overflow = max(0, ceiling - size)
    return {
        "size": size,
        "max_overflow": overflow,
        "timeout": DEFAULT_TIMEOUT,
        "recycle": DEFAULT_RECYCLE,
        "tenant_size": DEFAULT_TENANT_SIZE,
        "tenant_max_overflow": DEFAULT_TENANT_OVERFLOW,
    }


def _int(value, fallback: int, minimum: int) -> int:
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return fallback


def settings(app_config: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """The configured pool, with every missing or unusable key computed."""
    computed = recommend(*machine_capacity())
    raw = (app_config or {}).get(CONFIG_KEY) or {}
    if not isinstance(raw, dict):
        logger.warning(
            "%s in the config is not a mapping; using computed values", CONFIG_KEY
        )
        raw = {}
    minimums = {"size": 1, "max_overflow": 0, "timeout": 1, "recycle": 60,
                "tenant_size": 1, "tenant_max_overflow": 0}  # fmt: skip
    return {
        key: _int(raw.get(key), default, minimums[key])
        for key, default in computed.items()
    }


def engine_kwargs(pool: Dict[str, int]) -> Dict[str, int]:
    """create_engine() arguments for the bootstrap / registry engine."""
    return {
        "pool_size": pool["size"],
        "max_overflow": pool["max_overflow"],
        "pool_timeout": pool["timeout"],
        "pool_recycle": pool["recycle"],
    }


def tenant_engine_kwargs(app_config: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """create_engine() arguments for a tenant database's engine (the licensed
    multitenancy engine calls this; it keeps its own lease-based recycle)."""
    if app_config is None:
        from backend.config import config  # pylint: disable=import-outside-toplevel

        app_config = config.get_config()
    pool = settings(app_config)
    return {"pool_size": pool["tenant_size"], "max_overflow": pool["tenant_max_overflow"],
            "pool_timeout": pool["timeout"]}  # fmt: skip


def fit(
    pool: Dict[str, int], max_connections: int, workers: int
) -> Tuple[Dict[str, int], Optional[str]]:
    """Shrink ``pool`` so every worker's pool fits under the server's limit.

    Returns the pool to use and, when it had to change, why."""
    allowed = (max_connections - RESERVED_CONNECTIONS) // max(1, workers)
    planned = pool["size"] + pool["max_overflow"]
    if allowed <= 0 or planned <= allowed:
        return pool, None
    fitted = dict(pool)
    fitted["max_overflow"] = max(0, allowed - pool["size"])
    if pool["size"] > allowed:
        fitted["size"], fitted["max_overflow"] = max(1, allowed), 0
    reason = (
        f"PostgreSQL max_connections is {max_connections}; with {workers} worker(s) "
        f"and {RESERVED_CONNECTIONS} reserved, each worker may use {allowed}, but "
        f"{CONFIG_KEY} asks for {planned} ({pool['size']} + {pool['max_overflow']}). "
        f"Using {fitted['size']} + {fitted['max_overflow']}. Raise max_connections "
        f"in postgresql.conf or lower {CONFIG_KEY} in sysmanage.yaml."
    )
    return fitted, reason


def server_max_connections(engine) -> Optional[int]:
    """PostgreSQL's max_connections, or None (other databases, or unreachable)."""
    if engine.dialect.name != "postgresql":
        return None
    from sqlalchemy import text  # pylint: disable=import-outside-toplevel

    try:
        with engine.connect() as conn:
            return int(conn.execute(text("SHOW max_connections")).scalar())
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Could not read PostgreSQL max_connections (%s); pool not checked", exc
        )
        return None


# -- install time --------------------------------------------------------------


def config_block(pool: Dict[str, int], cpus: int, memory_gb: Optional[float]) -> str:
    """The YAML an installer appends -- commented, so an admin knows what it is."""
    memory = f"{memory_gb:.1f} GB RAM" if memory_gb else "unknown RAM"
    notes = {
        "size": "connections kept open",
        "max_overflow": "extra connections for bursts",
        "timeout": "seconds to wait for a free connection",
        "recycle": "maximum connection age, seconds",
        "tenant_size": "per tenant database (multi-tenancy)",
        "tenant_max_overflow": "per tenant database, bursts",
    }
    lines = [
        f"  {key}: {pool[key]}".ljust(28) + f"# {note}" for key, note in notes.items()
    ]
    return (
        "\n"
        "# Database connection pool -- sized for this machine at install time\n"
        f"# ({cpus} CPUs, {memory}).  Edit freely; the server checks these against\n"
        "# PostgreSQL's max_connections at startup and shrinks them (with a warning)\n"
        "# if every worker's pool would not fit.  Per server worker.\n"
        f"{CONFIG_KEY}:\n" + "\n".join(lines) + "\n"
    )


def apply_to_file(path: str) -> str:
    """Append a computed ``database_pool`` block unless the file has one.

    Appends text instead of rewriting the YAML so the admin's comments and
    layout survive; never touches an existing block."""
    with open(path, encoding="utf-8") as handle:
        existing = handle.read()
    if any(line.startswith(f"{CONFIG_KEY}:") for line in existing.splitlines()):
        return f"{path} already has {CONFIG_KEY}; left unchanged"
    cpus, memory_gb = machine_capacity()
    block = config_block(recommend(cpus, memory_gb), cpus, memory_gb)
    with open(path, "a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(block)
    return f"{path}: added {CONFIG_KEY} sized for {cpus} CPUs"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Size SysManage's database connection pool"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--print", action="store_true", help="show the values for this machine"
    )
    group.add_argument(
        "--apply", metavar="CONFIG", help="add them to this sysmanage.yaml if absent"
    )
    args = parser.parse_args(argv)
    if args.apply:
        try:
            print(apply_to_file(args.apply))
        except OSError as exc:
            print(f"could not update {args.apply}: {exc}", file=sys.stderr)
            return 1
        return 0
    cpus, memory_gb = machine_capacity()
    print(
        config_block(recommend(cpus, memory_gb), cpus, memory_gb).lstrip("\n"), end=""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
