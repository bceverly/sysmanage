# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The hardware health background tick (Phase 23.1 S6).

In every host database, installs smartmontools where a host's drives cannot
be read and an administrator has consented (``smartmontools_install``).
Started from ``background_ticks`` only with Enterprise fleet bulk operations
licensed; each pass checks the license and the consent again.
"""

import asyncio
import logging
from typing import Optional

from backend.persistence.partitions import iter_host_databases
from backend.services import smartmontools_install
from backend.startup.leadership import singleton_task
from backend.startup.tick_runner import run_periodic

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 300
ERROR_BACKOFF_SECONDS = 60

_TASK: Optional[asyncio.Task] = None


def run_one_tick() -> int:
    """One pass over every host database; installs queued.  Never raises."""
    queued = 0
    for label, tenant_id, db in iter_host_databases():
        try:
            queued += smartmontools_install.reconcile(db, tenant_id, label)
            db.commit()
        except Exception:  # pylint: disable=broad-except
            logger.exception("smartmontools auto-install failed for %s", label)
            db.rollback()
        finally:
            db.close()
    return queued


async def hardware_tick_service() -> None:
    await run_periodic(
        "Hardware tick",
        run_one_tick,
        TICK_INTERVAL_SECONDS,
        ERROR_BACKOFF_SECONDS,
        logger=logger,
    )


def start_if_licensed():
    """Start the tick when licensed; the task or None.  Never fatal."""
    global _TASK  # pylint: disable=global-statement
    if not smartmontools_install.licensed():
        return None
    if _TASK is not None and not _TASK.done():
        return _TASK
    try:
        _TASK = singleton_task(hardware_tick_service())
        logger.info("Hardware health tick started")
        return _TASK
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Hardware tick did not start: %s", exc)
        return None
