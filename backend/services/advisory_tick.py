# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Keep the vendor advisory catalog, and what applies to each host, current
without anyone pressing Refresh.

The catalog (``shared_advisory``) is filled by the licensed
``advisory_engine`` from every distribution's own feed -- Ubuntu, Debian,
Red Hat, Fedora, SUSE, Alpine, FreeBSD and OpenBSD.  Until 2026-11-23 it
filled only when someone pressed Refresh on the Advisories page, and each
host's applicable advisories were recomputed only from its own page.  This
tick refreshes the catalog when it is empty or the last SUCCESSFUL refresh
is older than ``REFRESH_EVERY``, and then recomputes every approved host in
every host database.  A failed refresh is retried after the tick interval,
not on every pass.

Started from ``background_ticks`` only when ``advisory_engine`` is loaded.
On an air-gapped repository server it never fetches: the catalog arrives on
the media and ``recompute_now`` runs after each ingest.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.config import config as config_module
from backend.licensing.features import ModuleCode
from backend.licensing.license_service import license_service
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import iter_host_databases, shared_sessionmaker
from backend.startup.leadership import singleton_task
from backend.startup.tick_runner import run_periodic

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 3600
ERROR_BACKOFF_SECONDS = 900
# Vendors publish advisories through the day; daily keeps hosts honest
# without hammering eight feeds.
REFRESH_EVERY = timedelta(days=1)

_TASK: Optional[asyncio.Task] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _engine():
    if not license_service.has_module(ModuleCode.ADVISORY_ENGINE):
        return None
    return module_loader.get_module("advisory_engine")


def refresh_due(db, now: datetime) -> Optional[str]:
    """Why a refresh is due now ("empty" / "stale"), or None."""
    log = models.AdvisoryIngestionLog
    last_good = (
        db.query(log)
        .filter(log.status == "success")
        .order_by(log.completed_at.desc())
        .first()
    )
    if last_good is not None and last_good.completed_at is not None:
        if last_good.completed_at > now - REFRESH_EVERY:
            return None
        return "stale"
    last_try = db.query(log).order_by(log.started_at.desc()).first()
    if last_try is None or last_try.started_at <= now - timedelta(
        seconds=TICK_INTERVAL_SECONDS
    ):
        return "empty"
    return None


def _recompute_all(engine, shared) -> int:
    """Recompute applicable advisories for every approved host; how many."""
    service = engine._advisory_service  # pylint: disable=protected-access
    done = 0
    for label, _tenant, db in iter_host_databases():
        try:
            hosts = (
                db.query(models.Host.id)
                .filter(models.Host.approval_status == "approved")
                .all()
            )
            for (host_id,) in hosts:
                try:
                    service.compute_applicable_advisories(
                        host_id, db, models, adv_db=shared
                    )
                    done += 1
                except Exception:  # pylint: disable=broad-except
                    db.rollback()
                    logger.exception(
                        "Advisories could not be computed for host %s in %s",
                        host_id,
                        label,
                    )
        finally:
            db.close()
    return done


def recompute_now() -> int:
    """Recompute every approved host against the catalog as it is now (an
    air-gap ingest just loaded it); how many hosts.  Never raises."""
    engine = _engine()
    if engine is None:
        return 0
    shared = shared_sessionmaker()()
    try:
        return _recompute_all(engine, shared)
    except Exception:  # pylint: disable=broad-except
        logger.exception("Advisories could not be recomputed")
        return 0
    finally:
        shared.close()


def run_one_tick() -> Optional[str]:
    """Refresh the catalog if due, then recompute every host; the reason it
    ran, or None.  Never raises.  An air-gapped repository server reaches no
    feed: its catalog arrives on the media (``airgap_catalog``)."""
    engine = _engine()
    if engine is None or config_module.is_repository():
        return None
    shared = shared_sessionmaker()()
    try:
        reason = refresh_due(shared, _utcnow())
        if reason is None:
            return None
        result = engine._advisory_service.refresh_advisories(  # pylint: disable=protected-access
            shared, models
        )
        hosts = _recompute_all(engine, shared)
        logger.info(
            "Advisory catalog refreshed (%s): %s; %d hosts recomputed",
            reason,
            (result or {}).get("processed"),
            hosts,
        )
        return reason
    except Exception:  # pylint: disable=broad-except
        # The engine records each source's failure in the ingestion log.
        logger.exception("Advisory catalog refresh failed")
        shared.rollback()
        return None
    finally:
        shared.close()


async def advisory_tick_service() -> None:
    await run_periodic(
        "Advisory tick",
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
        _TASK = singleton_task(advisory_tick_service())
        logger.info("Advisory tick started")
        return _TASK
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Advisory tick did not start: %s", exc)
        return None
