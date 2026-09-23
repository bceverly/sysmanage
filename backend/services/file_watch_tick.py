# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Periodic driver for file-watch assignments (Phase 21.1 S7).

Assignments are storage-only without this: an operator could bind a watch list
to a host, a tag or a site and nothing would ever collect it. This is the loop
that makes an assignment mean something.

It deliberately mirrors ``query_pack_tick`` rather than inventing a second
scheduling model -- same derived due-ness, same per-tick bound, same per-
database isolation -- because a fleet with two schedulers that disagree about
what "every 60 minutes" means is worse than one with a scheduler that is
slightly wrong.

DUE-NESS IS DERIVED, NOT STORED
-------------------------------
An assignment is due when its interval has elapsed since
``last_dispatched_at``, computed each tick. No ``next_run`` column to migrate
when added, keep correct when the interval changes, or repair when it drifts
-- each of which is a way for collection to silently stop. A window missed
while the server was down fires ONCE on the next tick rather than replaying
every interval it slept through.

WHY A HOST WITH NO PATHS IS NOT DISPATCHED TO
----------------------------------------------
Sending an empty watch list would come back a clean success with zero rows,
and ingestion would then DELETE every path previously recorded for that host
-- turning a misconfigured assignment into a silent loss of the baseline the
differ compares against. A host with nothing to watch is counted and skipped.

WHY AN AGENT THAT CANNOT SERVE THE TABLE IS SKIPPED TOO
--------------------------------------------------------
``file_watch_service.should_dispatch`` requires a POSITIVE advertisement of
``sysmanage_file_state``. An agent too old to know the table would answer the
query with an error, and the run would grade as a FAILURE -- which reads as
"this host is broken" rather than "this host is not equipped yet".
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.models.file_watch import (
    DEFAULT_INTERVAL_MINUTES,
    MIN_INTERVAL_MINUTES,
)
from backend.persistence.partitions import iter_host_databases
from backend.services import file_watch_service as fws
from backend.services import query_pack_dispatch as dispatch
from backend.services import query_pack_service as svc

logger = logging.getLogger(__name__)

# Matches the query-pack tick: the finest interval a watch may ask for is 5
# minutes, so a tighter cadence is churn and a looser one slips a cycle.
TICK_INTERVAL_SECONDS = 60
ERROR_BACKOFF_SECONDS = 30

# Per tick, per database. After an outage an unbounded pass would queue a
# collection to every host in the fleet at once; the tick returns in a minute.
MAX_DISPATCHES_PER_TICK = 50


def _is_due(assignment, now: datetime) -> bool:
    """Has this assignment's interval elapsed?

    Never dispatched is always due -- that is what makes a newly created
    assignment collect promptly rather than after one full interval of
    silence.
    """
    if assignment.last_dispatched_at is None:
        return True
    interval = max(
        int(assignment.interval_minutes or DEFAULT_INTERVAL_MINUTES),
        MIN_INTERVAL_MINUTES,
    )
    return now - assignment.last_dispatched_at >= timedelta(minutes=interval)


def due_assignments(db_session, host, now: datetime) -> List[Any]:
    """Enabled assignments for this host whose window has arrived."""
    return [a for a in fws.assignments_for(db_session, host) if _is_due(a, now)]


def _dispatch_one(db_session, host, assignments, now, summary) -> bool:
    """Queue one collection for one host. Returns False if it could not go.

    Per-host isolation is the point: an offline host, or one whose agent
    predates the fact contract, must not stop the rest of the fleet.
    """
    if not fws.should_dispatch(host):
        summary["not_equipped"] += 1
        return False

    # Curated lists live in the SHARED partition, so the lookup is injected
    # rather than queried inline -- the cross-partition read stays explicit.
    paths = fws.resolve_paths(db_session, host, shared_lookup=fws.shared_watch_paths)
    if not paths:
        # See WHY A HOST WITH NO PATHS IS NOT DISPATCHED TO.
        summary["nothing_to_watch"] += 1
        return False

    try:
        # A file watch IS a one-query pack, so the run row, the correlation
        # and the grading are the ones S4 already proved in production.
        run = svc.start_run(
            db_session,
            host.id,
            {"assignment_id": str(assignments[0].id)},
            {"pack_name": fws.WATCH_QUERY_NAME, "queries": []},
        )
        payload = fws.build_dispatch(paths, run_id=run.id)
        dispatch.queue_run(db_session, host.id, payload)
        return True
    except Exception:  # pylint: disable=broad-except
        # Includes UnsupportedCapabilityError, an ordinary outcome for an
        # agent that cannot take this command -- not a fault worth a
        # traceback every tick.
        logger.info(
            "File watch not queued for host %s; it cannot take this command",
            host.id,
        )
        db_session.rollback()
        return False


def _touch(db_session, assignments, now) -> None:
    """Advance each assignment's cursor.

    Advanced even when the dispatch did NOT go out. The window did arrive; it
    simply could not be served. Leaving it unset would re-evaluate the same
    assignment on every tick forever, which for an offline host means a log
    line a minute until somebody notices.
    """
    for assignment in assignments:
        assignment.last_dispatched_at = now


def _tick_one_database(db_session, now, summary) -> None:
    """Run the tick against ONE database. Never raises.

    Isolated per database so one unreachable tenant cannot stop every other
    tenant's collection for the rest of the tick.
    """
    try:
        if db_session.query(models.FileWatchAssignment).count() == 0:
            return

        hosts = db_session.query(models.Host).filter(models.Host.active.is_(True)).all()

        dispatched_here = 0
        for host in hosts:
            if dispatched_here >= MAX_DISPATCHES_PER_TICK:
                summary["deferred"] += 1
                break
            assignments = due_assignments(db_session, host, now)
            if not assignments:
                continue
            summary["due"] += 1
            if _dispatch_one(db_session, host, assignments, now, summary):
                summary["queued"] += 1
                dispatched_here += 1
            _touch(db_session, assignments, now)

        if summary["due"]:
            db_session.commit()
    except Exception:  # pylint: disable=broad-except
        logger.exception("File watch assignment tick failed")
        db_session.rollback()


def run_one_tick() -> Dict[str, Any]:
    """Dispatch every due assignment once. Never raises.

    Public so an operator endpoint or a test can drive exactly one tick
    without waiting a minute for the loop.
    """
    summary: Dict[str, Any] = {
        "due": 0,
        "queued": 0,
        "nothing_to_watch": 0,
        "not_equipped": 0,
        "deferred": 0,
    }

    if module_loader.get_module("config_management_engine") is None:
        # Same gate and same reason as the query-pack tick: watch lists and
        # their assignments are authored through the config-management router,
        # so without that module none can exist and the loop would wake every
        # minute to find nothing. The golden-host differ this feeds sits behind
        # the same module.
        return summary

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # EVERY database. Assignments, watch lists and hosts all live in a
    # tenant's own database, so a tick reading only the bootstrap one finds
    # zero assignments and reports a clean due=0 -- collection silently never
    # runs for anyone under multi-tenancy, and nothing errors anywhere.
    for _label, _tenant, db_session in iter_host_databases():
        try:
            _tick_one_database(db_session, now, summary)
        finally:
            db_session.close()
    return summary


async def file_watch_tick_service() -> None:
    """Background service: one tick every ``TICK_INTERVAL_SECONDS``."""
    logger.info(
        "Starting file-watch assignment tick service (interval=%ds)",
        TICK_INTERVAL_SECONDS,
    )
    while True:
        try:
            summary = run_one_tick()
            if summary["due"]:
                logger.info(
                    "File watch tick: due=%d queued=%d nothing_to_watch=%d "
                    "not_equipped=%d deferred=%d",
                    summary["due"],
                    summary["queued"],
                    summary["nothing_to_watch"],
                    summary["not_equipped"],
                    summary["deferred"],
                )
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("File watch tick service cancelled -- exiting loop")
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception("File watch tick service error -- sleeping then retrying")
            await asyncio.sleep(ERROR_BACKOFF_SECONDS)
