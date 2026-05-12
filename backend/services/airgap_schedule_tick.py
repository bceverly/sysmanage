"""Periodic driver for ``AirgapCollectionSchedule`` cron schedules.

The schedule API in ``backend/api/airgap_collection_schedule.py``
exposes a manual ``POST /api/v1/airgap/collector/schedules/tick``
endpoint that fires every due schedule.  Cron-driven scheduling
needs a background loop that calls the same logic on a heartbeat —
otherwise the only way schedules ever fire is if an operator
manually hits ``/tick``.

Design notes:
  * Tick cadence is 60 seconds.  Cron's minimum granularity is one
    minute, so a tighter cadence buys nothing and a looser one
    risks missing minute-boundary schedules.
  * Each tick uses a fresh DB session and closes it at the end —
    no long-lived sessions parked across the asyncio sleep.
  * The service degrades gracefully when ``airgap_collector_engine``
    or ``automation_engine`` is unloaded: the gate at startup
    short-circuits when collector is absent, and the inner tick
    handles automation_engine absence by leaving ``next_run`` alone
    (so schedules fire once and then stop advancing — same
    behaviour as the manual /tick endpoint when automation_engine
    is missing).
  * Errors from a single tick (DB hiccup, malformed
    ``target_request_json``) are caught and logged but never
    propagate up to kill the loop — a single-schedule failure
    should not stop the others from firing on the next iteration.

This is the OSS-side close-out for the "cron-driven collection
scheduling" deliverable.  The cron parser itself lives in
``airgap_collector_engine.parse_collector_cron_fields`` /
``next_collection_from_cron`` (engine-side, Pro+).  The OSS schedule
API and DB model are already in place; this module is just the
periodic-tick driver that ties them together.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from backend.licensing.module_loader import module_loader
from backend.persistence.db import get_db
from backend.persistence import models

logger = logging.getLogger(__name__)

# 60s — matches cron's minimum granularity (one minute).  A tighter
# cadence wastes DB churn; a looser one would let schedules whose
# ``next_run`` lands on the dead minute slip a full cycle.
TICK_INTERVAL_SECONDS = 60

# Shorter back-off on inner exception — the operator should see fast
# recovery on a transient DB blip but a persistent error shouldn't
# spam the logs at full cadence.  Exposed as a constant so tests can
# patch it.
ERROR_BACKOFF_SECONDS = 30


def _run_one_tick() -> dict:
    """Fire every due schedule and advance their ``next_run`` cursors.

    Returns a summary dict for logging — ``fired`` is the count of
    schedules that produced a ``QUEUED`` ``AirgapCollectionRun``,
    ``errors`` is the count of schedules whose
    ``target_request_json`` failed to parse.  Both counts are zero
    on a quiet tick.
    """
    summary = {"fired": 0, "errors": 0, "skipped_automation_absent": False}

    collector = module_loader.get_module("airgap_collector_engine")
    if collector is None:
        # Collector not loaded — nothing to schedule against.  Caller
        # gate already filters this case at startup, but the inner
        # check is cheap and makes the function safe to invoke
        # standalone (e.g. from a test).
        return summary

    automation = module_loader.get_module("automation_engine")

    db = next(get_db())
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        due = (
            db.query(models.AirgapCollectionSchedule)
            .filter(
                models.AirgapCollectionSchedule.enabled.is_(True),
                models.AirgapCollectionSchedule.next_run.isnot(None),
                models.AirgapCollectionSchedule.next_run <= now,
            )
            .all()
        )
        for schedule in due:
            try:
                target_request = json.loads(schedule.target_request_json)
            except (ValueError, TypeError) as exc:
                schedule.last_run = now
                schedule.last_status = "FAILURE"
                logger.exception(
                    "airgap schedule %s has malformed target_request_json: %s",
                    schedule.id,
                    exc,
                )
                summary["errors"] += 1
                continue

            run = models.AirgapCollectionRun(
                iso_label=target_request.get("iso_label", schedule.name),
                media_size_bytes=target_request.get("media_size_bytes", 4_700_000_000),
                include_cve=bool(target_request.get("include_cve", True)),
                include_compliance=bool(target_request.get("include_compliance", True)),
                status="QUEUED",
            )
            db.add(run)
            db.flush()
            schedule.last_run = now
            schedule.last_status = "QUEUED"
            schedule.last_run_id = run.id
            if automation is not None:
                schedule.next_run = automation.next_run_from_cron(
                    schedule.cron, datetime.now(timezone.utc)
                )
            else:
                # automation_engine absent — leave next_run as-is so
                # we don't re-fire on the next tick.  Surface via the
                # summary so the operator can see it in the logs.
                summary["skipped_automation_absent"] = True
            summary["fired"] += 1
        if due:
            db.commit()
    except Exception:  # pylint: disable=broad-except
        # Log + rollback but don't propagate — the next tick can retry.
        logger.exception("airgap collection schedule tick failed")
        db.rollback()
    finally:
        db.close()
    return summary


async def airgap_schedule_tick_service() -> None:
    """Background service: call ``_run_one_tick`` every ``TICK_INTERVAL_SECONDS``.

    Mirrors the structure of ``heartbeat_monitor_service``.  Started
    at server startup only when ``airgap_collector_engine`` is loaded
    (see ``backend/startup/lifecycle.py``).
    """
    logger.info(
        "Starting air-gap collection schedule tick service (interval=%ds)",
        TICK_INTERVAL_SECONDS,
    )
    while True:
        try:
            summary = _run_one_tick()
            if summary["fired"] or summary["errors"]:
                logger.info(
                    "Air-gap schedule tick: fired=%d errors=%d "
                    "automation_engine_absent=%s",
                    summary["fired"],
                    summary["errors"],
                    summary["skipped_automation_absent"],
                )
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Air-gap schedule tick service cancelled — exiting loop")
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "Air-gap schedule tick service error — sleeping then retrying"
            )
            # Shorter back-off than the normal cadence so the operator
            # sees fast recovery on transient DB blips, but not so
            # short that a persistent error spams the logs.
            await asyncio.sleep(ERROR_BACKOFF_SECONDS)
