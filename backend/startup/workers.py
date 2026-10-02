# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""How many server worker processes to run (Phase 22.2).

WHY
---
One worker is one Python interpreter: under load it uses at most about one
CPU core.  The 10,000-agent storm (2026-10-02) ran 4 workers at ~84% of a core
each on an 8-core machine and was CPU-bound; the count was a hand-set
environment variable defaulting to 1, so a stock install used one core
however big the machine.

THE DEFAULT, for this machine
-----------------------------
* CPUs: one worker per CPU, minus a quarter of them (at least one) kept for
  PostgreSQL -- usually on the same machine -- and the OS.  8 CPUs -> 6,
  4 -> 3, 2 -> 1.
* Memory: each worker held ~750 MB under the 10k load; budget 1 GB each after
  2 GB for the database and the OS.  A 4 GB machine gets at most 2.
* At most 16; at least 1.
* SQLite: always 1 -- several workers need PostgreSQL (leader election and
  per-host queue claims use its advisory locks).

OVERRIDES, strongest first
--------------------------
1. ``SYSMANAGE_UVICORN_WORKERS`` in the environment (CI, the load harness);
2. ``api.workers`` in sysmanage.yaml -- a number, or ``auto`` (the default);
3. the computed default above.

``main.py`` resolves the count once and exports it as
``SYSMANAGE_UVICORN_WORKERS`` before starting uvicorn, so every worker -- and
the pool sizing and leader election inside each one -- sees the same number.
"""

import logging
import os
from typing import Optional, Tuple

from backend.persistence import pool_sizing

logger = logging.getLogger(__name__)

ENV_VAR = "SYSMANAGE_UVICORN_WORKERS"
MAX_WORKERS = 16
GB_PER_WORKER = 1.0
GB_RESERVED = 2.0


def recommend(cpus: int, memory_gb: Optional[float]) -> int:
    """The worker count for a machine of this size."""
    by_cpu = cpus - max(1, cpus // 4)
    count = by_cpu
    if memory_gb:
        count = min(count, int((memory_gb - GB_RESERVED) // GB_PER_WORKER))
    return max(1, min(MAX_WORKERS, count))


def _positive_int(value) -> Optional[int]:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number >= 1 else None


def resolve(app_config: Optional[dict], sqlite: bool) -> Tuple[int, str]:
    """``(workers, why)`` for this server."""
    env = os.environ.get(ENV_VAR)
    if env:
        count = _positive_int(env)
        if count is None:
            logger.warning("%s=%r is not a positive number; ignoring it", ENV_VAR, env)
        else:
            return _sqlite_cap(count, sqlite, f"{ENV_VAR}={count}")
    configured = ((app_config or {}).get("api") or {}).get("workers", "auto")
    if str(configured).strip().lower() not in ("", "auto", "none"):
        count = _positive_int(configured)
        if count is None:
            logger.warning(
                "api.workers=%r is not a positive number or 'auto'; using auto",
                configured,
            )
        else:
            return _sqlite_cap(count, sqlite, f"api.workers={count}")
    cpus, memory_gb = pool_sizing.machine_capacity()
    count = recommend(cpus, memory_gb)
    memory = f"{memory_gb:.1f} GB" if memory_gb else "unknown memory"
    return _sqlite_cap(count, sqlite, f"auto: {cpus} CPUs, {memory}")


def _sqlite_cap(count: int, sqlite: bool, why: str) -> Tuple[int, str]:
    if sqlite and count > 1:
        return 1, f"{why}, but SQLite supports one worker"
    return count, why
