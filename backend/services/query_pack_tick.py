# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Periodic driver for query-pack assignments (Phase 21.1 S4).

Assignments are storage-only without this: an operator could bind a pack to a
host, a tag or a site and nothing would ever run it. This is the loop that
makes an assignment mean something, and it is the "scheduled collection paced
by the existing tick" the slice calls for.

DUE-NESS IS DERIVED, NOT STORED
-------------------------------
There is no ``next_run`` column -- an assignment is due when its interval has
elapsed since ``last_dispatched_at``, computed each tick. The same reasoning
as the config-profile tick: a stored cursor has to be migrated when added,
kept correct when the interval changes, and repaired when it drifts, and each
of those is a way for collection to silently stop.

It also means a window missed while the server was down fires ONCE on the next
tick rather than replaying every interval it slept through. A catch-up storm
across a fleet is far worse than a late collection.

BOUNDED, PER TENANT
-------------------
``select_due`` caps how many assignments one pass dispatches, oldest-first.
After an outage an unbounded pass would queue a pack to every host in the
fleet at once; the tick comes round again in a minute anyway.

WHAT IT DOES NOT DECIDE
-----------------------
* Which assignment wins when a host matches several -- the licensed engine
  resolves that, and running the same pack three times in one window would
  produce three answers with nothing to say which is authoritative.
* Which queries a host can answer -- the engine filters against the host's
  advertised coverage, so a host never receives a question it cannot answer.
* Whether the host can take the command -- ``enqueue_message`` refuses a
  command the host has not advertised (Phase 19), reused rather than
  re-decided.

Unlicensed servers never reach any of this: assignments cannot be created
without ``query_pack_engine``, so the loop finds nothing.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import iter_host_databases
from backend.services import query_pack_dispatch as dispatch
from backend.services import query_pack_service as svc
from backend.services import query_pack_shim as shim

logger = logging.getLogger(__name__)

# 60s: the finest interval a pack may ask for is 5 minutes, so a tighter
# cadence is pure churn and a looser one lets a boundary slip a cycle.
TICK_INTERVAL_SECONDS = 60
ERROR_BACKOFF_SECONDS = 30

# Per tick, per database. See BOUNDED above.
MAX_DISPATCHES_PER_TICK = 50


def _host_descriptor(db_session, host) -> Dict[str, Any]:
    """The host as the engine wants it: id, tags, site.

    Tags are read per host rather than joined once because the engine's
    resolution is per host by nature, and a fleet tick is bounded anyway.
    """
    tag_ids = [
        str(row.tag_id)
        for row in db_session.query(models.HostTag)
        .filter(models.HostTag.host_id == host.id)
        .all()
    ]
    return {
        "id": str(host.id),
        "tag_ids": tag_ids,
        "site_id": str(host.site_id) if getattr(host, "site_id", None) else None,
    }


def _assignment_dicts(db_session) -> List[Dict[str, Any]]:
    """Enabled assignments, as the plain dicts the engine takes."""
    rows = (
        db_session.query(models.QueryPackAssignment)
        .filter(models.QueryPackAssignment.enabled.is_(True))
        .all()
    )
    return [
        {
            "id": str(row.id),
            "pack_id": str(row.pack_id) if row.pack_id else None,
            "shared_pack_id": (str(row.shared_pack_id) if row.shared_pack_id else None),
            "host_id": str(row.host_id) if row.host_id else None,
            "tag_id": str(row.tag_id) if row.tag_id else None,
            "site_id": str(row.site_id) if row.site_id else None,
            "enabled": row.enabled,
            "interval_minutes": row.interval_minutes,
            "last_dispatched_at": row.last_dispatched_at,
        }
        for row in rows
    ]


def _dispatch_one(db_session, host, resolved, now, summary) -> bool:
    """Queue one pack run for one host. Returns False if it could not go.

    Per-host isolation is the point: an offline host, or one whose agent
    predates query packs, must not stop the rest of the fleet.
    """
    pack = svc.resolve_pack(db_session, resolved)
    if pack is None:
        # A curated pack an assignment names that is not in this server's
        # catalog, or a disabled tenant pack. Counted, not dispatched -- and
        # NOT dispatched as an empty pack, which would come back a clean
        # success and report the host measured against a pack that is gone.
        summary["unresolvable"] += 1
        return False

    payload = dispatch.build_payload(pack, pack.get("queries") or [], host)
    if payload is None:
        # The engine is not loaded. Refusing beats dispatching everything
        # unfiltered, which would send hosts questions they cannot answer.
        summary["no_engine"] += 1
        return False

    if not payload.get("queries") and not payload.get("not_covered"):
        # Nothing to ask this host at all.
        summary["nothing_to_run"] += 1
        return False

    try:
        run = svc.start_run(db_session, host.id, resolved, pack)
        payload["run_id"] = str(run.id)
        dispatch.queue_run(db_session, host.id, payload)
        return True
    except Exception:  # pylint: disable=broad-except
        # Includes UnsupportedCapabilityError, an ordinary outcome for an
        # agent that predates query packs -- not a fault worth a traceback on
        # every tick.
        logger.info(
            "Query pack not queued for host %s; it cannot take this command",
            host.id,
        )
        db_session.rollback()
        return False


def _tick_one_database(db_session, now, summary) -> None:
    """Run the tick against ONE database. Never raises.

    Isolated per database so one unreachable tenant cannot stop every other
    tenant's collection for the rest of the tick.
    """
    try:
        assignments = _assignment_dicts(db_session)
        if not assignments:
            return

        hosts = db_session.query(models.Host).filter(models.Host.active.is_(True)).all()

        dispatched_here = 0
        for host in hosts:
            if dispatched_here >= MAX_DISPATCHES_PER_TICK:
                summary["deferred"] += 1
                break
            descriptor = _host_descriptor(db_session, host)
            resolved = shim.resolve_assignments(descriptor, assignments)
            due = shim.select_due(
                resolved, now, limit=MAX_DISPATCHES_PER_TICK - dispatched_here
            )
            for item in due:
                summary["due"] += 1
                if _dispatch_one(db_session, host, item, now, summary):
                    summary["queued"] += 1
                    dispatched_here += 1
                _touch(db_session, item, now)

        if summary["due"]:
            db_session.commit()
    except Exception:  # pylint: disable=broad-except
        logger.exception("Query pack assignment tick failed")
        db_session.rollback()


def _touch(db_session, item, now) -> None:
    """Advance the assignment's cursor.

    Advanced even when the dispatch did NOT go out. The window did arrive;
    it simply could not be served. Leaving it unset would re-evaluate the same
    assignment on every tick forever, which for an offline host means a log
    line a minute until somebody notices.
    """
    row = (
        db_session.query(models.QueryPackAssignment)
        .filter(models.QueryPackAssignment.id == item.get("assignment_id"))
        .one_or_none()
    )
    if row is not None:
        row.last_dispatched_at = now


def run_one_tick() -> Dict[str, Any]:
    """Dispatch every due assignment once. Never raises.

    Public so an operator endpoint or a test can drive exactly one tick
    without waiting a minute for the loop.
    """
    summary: Dict[str, Any] = {
        "due": 0,
        "queued": 0,
        "unresolvable": 0,
        "nothing_to_run": 0,
        "no_engine": 0,
        "deferred": 0,
    }

    if module_loader.get_module("query_pack_engine") is None:
        # Assignments cannot exist without the module; nothing to do.
        return summary

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # EVERY database. A tenant's assignments, packs and hosts all live in that
    # tenant's database, so a tick reading only the bootstrap one finds zero
    # assignments and reports a clean due=0 -- collection silently never runs
    # for anyone under multi-tenancy, and nothing errors anywhere.
    for _label, _tenant, db_session in iter_host_databases():
        try:
            _tick_one_database(db_session, now, summary)
        finally:
            db_session.close()
    return summary


async def query_pack_tick_service() -> None:
    """Background service: one tick every ``TICK_INTERVAL_SECONDS``."""
    logger.info(
        "Starting query-pack assignment tick service (interval=%ds)",
        TICK_INTERVAL_SECONDS,
    )
    while True:
        try:
            summary = run_one_tick()
            if summary["due"]:
                logger.info(
                    "Query pack tick: due=%d queued=%d unresolvable=%d "
                    "nothing_to_run=%d deferred=%d",
                    summary["due"],
                    summary["queued"],
                    summary["unresolvable"],
                    summary["nothing_to_run"],
                    summary["deferred"],
                )
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Query pack tick service cancelled -- exiting loop")
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception("Query pack tick service error -- sleeping then retrying")
            await asyncio.sleep(ERROR_BACKOFF_SECONDS)
