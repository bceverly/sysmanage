# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Keep the OS end-of-life registry current without anyone clicking Refresh.

The registry (``shared_os_lifecycle``) is filled from endoflife.date by the
licensed ``lifecycle_engine``.  It used to fill only when someone pressed
"Refresh EOL data", so a new server reported every host as Unknown until
then (production, 2026-10-16: 0 releases, no ingestion ever).  This tick
refreshes it when it is empty, and again once the last SUCCESSFUL refresh is
older than ``REFRESH_EVERY``.  A failed refresh is retried an hour later --
the tick interval -- not on every pass.

Started from ``background_ticks`` only when ``lifecycle_engine`` is loaded.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.licensing.features import ModuleCode
from backend.licensing.license_service import license_service
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import shared_sessionmaker
from backend.startup.leadership import singleton_task
from backend.startup.tick_runner import run_periodic

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 3600
ERROR_BACKOFF_SECONDS = 900
# Release dates change rarely; a day is fresh enough and polite to the source.
REFRESH_EVERY = timedelta(days=1)

_TASK: Optional[asyncio.Task] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _engine():
    if not license_service.has_module(ModuleCode.LIFECYCLE_ENGINE):
        return None
    return module_loader.get_module("lifecycle_engine")


def _naive(moment: Optional[datetime]) -> Optional[datetime]:
    if moment is not None and moment.tzinfo is not None:
        return moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def refresh_due(db, now: datetime) -> Optional[str]:
    """Why a refresh is due now ("empty" / "stale"), or None.

    Empty and the last attempt under an hour old (it failed): wait, so an
    unreachable source is not hit on every pass."""
    if db.query(models.SharedOsLifecycle).first() is None:
        last_try = (
            db.query(models.OsLifecycleIngestionLog)
            .order_by(models.OsLifecycleIngestionLog.started_at.desc())
            .first()
        )
        started = _naive(last_try.started_at) if last_try else None
        if started is None or started <= now - timedelta(seconds=TICK_INTERVAL_SECONDS):
            return "empty"
        return None
    last_good = (
        db.query(models.OsLifecycleIngestionLog)
        .filter(models.OsLifecycleIngestionLog.status == "success")
        .order_by(models.OsLifecycleIngestionLog.completed_at.desc())
        .first()
    )
    finished = _naive(last_good.completed_at) if last_good else None
    if finished is None or finished <= now - REFRESH_EVERY:
        return "stale"
    return None


def run_one_tick() -> Optional[str]:
    """Refresh the registry if due; the reason it ran, or None.  Never raises."""
    engine = _engine()
    if engine is None:
        return None
    session = shared_sessionmaker()()
    try:
        reason = refresh_due(session, _utcnow())
        if reason is None:
            return None
        result = (
            engine._lifecycle_service.refresh_eol(  # pylint: disable=protected-access
                session, models
            )
        )
        logger.info(
            "OS lifecycle registry refreshed (%s): %s releases",
            reason,
            (result or {}).get("releases_processed"),
        )
        return reason
    except Exception:  # pylint: disable=broad-except
        # The engine records the failure in shared_os_lifecycle_ingestion_log.
        logger.exception("OS lifecycle registry refresh failed")
        session.rollback()
        return None
    finally:
        session.close()


async def os_lifecycle_tick_service() -> None:
    await run_periodic(
        "OS lifecycle tick",
        run_one_tick,
        TICK_INTERVAL_SECONDS,
        ERROR_BACKOFF_SECONDS,
        logger=logger,
    )


def start_if_licensed():
    """Start the tick when the engine is loaded; the task or None.  Never fatal."""
    global _TASK  # pylint: disable=global-statement
    if _engine() is None:
        return None
    if _TASK is not None and not _TASK.done():
        return _TASK
    try:
        _TASK = singleton_task(os_lifecycle_tick_service())
        logger.info("OS lifecycle tick started")
        return _TASK
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("OS lifecycle tick did not start: %s", exc)
        return None
