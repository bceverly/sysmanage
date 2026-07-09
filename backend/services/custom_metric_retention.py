"""Periodic retention pruning for custom-metric time-series samples.

The Custom Metrics feature (Custom Metrics — Slice 1) stores one row in the
tenant ``custom_metric_sample`` table per host, per metric, per cadence tick.
Left alone that table grows without bound.  This module is the OSS-side
retention driver: a background loop that, on a daily cadence, DELETEs samples
older than ``custom_metrics.retention_days`` (default 90) from EVERY provisioned
tenant database — and, in single-tenant / ``multitenancy.enabled`` false mode,
from the one collapsed application database.

This is deliberately OSS: a mechanical ``DELETE`` on an OSS-owned tenant table
(``custom_metric_sample``).  The metric COLLECTION + graphing LOGIC is Pro+
(``observability_engine``); the SCHEMA + this housekeeping prune are OSS, so no
engine change or rebuild is involved.

Design notes (mirrors the other OSS background loops, e.g.
``airgap_schedule_tick`` and the store-and-forward processors):

  * Cadence defaults to 86400s (daily).  Retention is a slow-moving concern;
    a tighter cadence just churns the DB.
  * Per-tenant iteration reuses ``iter_host_databases()`` — it yields the
    bootstrap session plus every provisioned tenant DB when multi-tenancy is
    ON, and ONLY the bootstrap session when it is OFF (collapsed mode).  We
    close every session we are handed (the contract for that generator).
  * The retention window is re-read from settings EACH pass, so an operator
    changing ``custom_metrics_retention_days`` takes effect on the next cycle
    without a restart.
  * Every exception is caught and logged — a bad tenant, a DB hiccup, or a
    settings-read failure must never kill the loop or stall the other tenants.
    Per the "log unresolvable edge cases loudly" rule, each per-tenant prune
    logs its tenant + deleted count.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from backend.config import config as _config
from backend.persistence.models import CustomMetricSample

logger = logging.getLogger(__name__)

# Daily — retention is slow-moving; a tighter cadence just churns the DB.
DEFAULT_INTERVAL_SECONDS = 86400

# Back-off after a whole-pass failure: shorter than the normal cadence so the
# operator sees recovery, but not so short it spams the logs on a persistent
# fault.
ERROR_BACKOFF_SECONDS = 300


def prune_custom_metric_samples(session, retention_days) -> int:
    """DELETE ``CustomMetricSample`` rows older than ``retention_days``.

    Deletes every row whose ``collected_at`` is strictly older than
    ``now(utc) - retention_days``.  Returns the number of rows deleted.  Commits
    the deletion on ``session``.  Synchronous; the caller owns the session's
    lifecycle.

    Cross-dialect: the cutoff is computed in Python and bound as a parameter, so
    the emitted SQL is a plain ``DELETE ... WHERE collected_at < :cutoff`` that
    runs identically on SQLite and PostgreSQL (no DB-specific date arithmetic).

    A non-positive ``retention_days`` disables pruning (returns 0 without
    touching the table) — a guard against a misconfigured ``0``/negative value
    wiping the whole table.
    """
    try:
        retention_days = int(retention_days)
    except (TypeError, ValueError):
        logger.warning(
            "custom-metric retention: non-numeric retention_days=%r; skipping prune",
            retention_days,
        )
        return 0

    if retention_days <= 0:
        logger.warning(
            "custom-metric retention: retention_days=%d is not positive; "
            "skipping prune (refusing to delete all samples)",
            retention_days,
        )
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    deleted = (
        session.query(CustomMetricSample)
        .filter(CustomMetricSample.collected_at < cutoff)
        .delete(synchronize_session=False)
    )
    session.commit()
    return int(deleted or 0)


def _run_one_pass() -> int:
    """Prune every provisioned tenant DB (or just the collapsed DB) once.

    Reads the retention window from settings, then walks
    ``iter_host_databases()`` and prunes each yielded session, logging the
    per-tenant deleted count.  Returns the TOTAL rows deleted across all
    databases.  Never raises — per-tenant failures are logged and skipped so
    one bad tenant can't stall the rest.
    """
    # Late import: avoid an import cycle (partitions -> models -> ... ) at
    # module import time, matching the other background services.
    from backend.persistence.partitions import (  # noqa: PLC0415
        iter_host_databases,
    )

    retention_days = _config.get_custom_metrics_retention_days()
    total_deleted = 0

    for label, tenant_id, session in iter_host_databases():
        try:
            deleted = prune_custom_metric_samples(session, retention_days)
            total_deleted += deleted
            if deleted:
                logger.info(
                    "custom-metric retention: pruned %d sample(s) older than %s "
                    "day(s) from %s (tenant_id=%s)",
                    deleted,
                    retention_days,
                    label,
                    tenant_id,
                )
            else:
                logger.debug(
                    "custom-metric retention: nothing to prune in %s " "(tenant_id=%s)",
                    label,
                    tenant_id,
                )
        except Exception:  # pylint: disable=broad-except
            # Log loudly with the tenant context; never let one database's
            # failure abort the sweep or kill the loop.
            try:
                session.rollback()
            except Exception:  # pylint: disable=broad-except
                pass
            logger.exception(
                "custom-metric retention: prune FAILED for %s (tenant_id=%s); "
                "skipping it this pass",
                label,
                tenant_id,
            )
        finally:
            # iter_host_databases hands us ownership of every session it opens.
            try:
                session.close()
            except Exception:  # pylint: disable=broad-except
                pass

    return total_deleted


async def run_custom_metric_retention_loop(
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Background service: prune stale custom-metric samples on a cadence.

    Every ``interval_seconds`` it runs one prune pass across all provisioned
    tenant databases (or the single collapsed database in single-tenant mode),
    re-reading the retention window from settings each time.  Cancellable via
    ``task.cancel()``; every other exception is caught so the loop is
    self-healing and never dies.
    """
    logger.info(
        "Starting custom-metric retention loop (interval=%ds)",
        interval_seconds,
    )
    while True:
        try:
            total = _run_one_pass()
            logger.info(
                "custom-metric retention pass complete: %d sample(s) pruned total",
                total,
            )
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("Custom-metric retention loop cancelled — exiting")
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "Custom-metric retention loop error — backing off then retrying"
            )
            await asyncio.sleep(ERROR_BACKOFF_SECONDS)
