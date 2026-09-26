# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The advisor collects the fact rows its rules read (ROADMAP 21.2 S2b).

The server stores fact rows only as query-pack results, and S2 reads them from
queries named ``advisor.<table>``. Nothing dispatched those, so every fact
rule was ``not_collected``. This module dispatches them: one query-pack run
per host, built from the ENABLED rules (``advisor_engine.collection_queries``
-- only the tables and columns some rule reads).

THE SAME DISPATCH PATH, NOT A SECOND ONE
----------------------------------------
Runs go through ``query_pack_service.start_run`` and
``query_pack_dispatch.build_payload`` / ``queue_run`` exactly as an assignment's
do, so the licensed query-pack engine filters against the host's advertised
coverage (a host is never asked about a table it does not serve), results
come back through the ordinary handler, and the runs show up in Recent Runs
as ``advisor-facts``. There is no assignment row: an assignment names a host,
tag or site, and the advisor's target is "every host its rules need", which
changes as rules do.

DUE-NESS IS DERIVED, NOT STORED
-------------------------------
A host is due when its newest completed advisor run is older than
``COLLECT_INTERVAL``, or when that run did not include every query the rules
now need, or its rows lack a column they now read (a new rule reading a new
table or column must not wait half a day). A run
still pending inside ``PENDING_GRACE`` blocks another -- an offline host would
otherwise collect a queued command every tick.

``COLLECT_INTERVAL`` is HALF the facts freshness limit (1 day), so one missed
collection does not turn every fact rule ``stale``.

BOUNDED STORAGE
---------------
Query-pack runs have no retention, and a daily ``processes`` collection is
hundreds of rows a host. Per host, only the newest completed advisor run (and
a pending one inside the grace window) is kept; the rest are deleted, and
their result rows with them.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from backend.persistence import models
from backend.services import advisor_evidence as ev
from backend.services import query_pack_dispatch as dispatch
from backend.services import query_pack_service as svc

logger = logging.getLogger(__name__)

ADVISOR_PACK_NAME = "advisor-facts"
COLLECT_INTERVAL = timedelta(hours=12)
PENDING_GRACE = timedelta(hours=6)
_PACK = {"id": None, "name": ADVISOR_PACK_NAME, "curated": False}


def _advisor_runs(db, host_id) -> List[Any]:
    """This host's advisor collections, newest first."""
    run = models.QueryPackRun
    return (
        db.query(run)
        .filter(
            run.host_id == host_id,
            run.pack_name == ADVISOR_PACK_NAME,
            run.pack_id.is_(None),
            run.shared_pack_id.is_(None),
            run.assignment_id.is_(None),
            run.live_query_id.is_(None),
        )
        .order_by(run.started_at.desc())
        .all()
    )


def _pending(run) -> bool:
    return run.completed_at is None


def _collected(db, run) -> Dict[str, Optional[set]]:
    """``{query_name: columns the stored rows carry}`` for one run; ``None``
    for a query that answered with no rows (nothing to judge columns by)."""
    result = models.QueryPackResultRow
    out: Dict[str, Optional[set]] = {}
    for name, columns in db.query(result.query_name, result.columns).filter(
        result.run_id == run.id
    ):
        if isinstance(columns, dict):
            out[name] = (out.get(name) or set()) | set(columns)
        else:
            out.setdefault(name, None)
    return out


def is_due(db, runs, queries, now) -> bool:
    """Should this host be asked again? See DUE-NESS above.

    Also due when a query's stored rows LACK a column the rules now read: a
    rule that starts filtering on ``type`` must not be evaluated against rows
    collected without it (every row would read NULL and silently not match).
    """
    if any(_pending(r) and now - r.started_at < PENDING_GRACE for r in runs):
        return False
    completed = next((r for r in runs if not _pending(r)), None)
    if completed is None or now - completed.started_at >= COLLECT_INTERVAL:
        return True
    collected = _collected(db, completed)
    for query in queries:
        if query["name"] not in collected:
            return True
        have = collected[query["name"]]
        if have is not None and not set(query.get("columns") or ()) <= have:
            return True
    return False


def prune(db, runs, now) -> List[Any]:
    """Keep the newest completed run and in-grace pending ones; delete the
    rest. Returns the runs kept, newest first."""
    keep_completed = next((r for r in runs if not _pending(r)), None)
    kept = []
    for run in runs:
        if run is keep_completed or (
            _pending(run) and now - run.started_at < PENDING_GRACE
        ):
            kept.append(run)
        else:
            db.delete(run)
    return kept


def _dispatch(db, host, queries) -> str:
    """Queue one collection. Returns an outcome code for the summary."""
    payload = dispatch.build_payload(_PACK, queries, host)
    if payload is None:
        return "no_engine"
    if not payload.get("queries"):
        # The host serves none of the tables the rules read. Nothing to ask;
        # the rules say why through host_facts (not_applicable/unsupported).
        return "nothing_to_run"
    try:
        # A savepoint: a refused command must not roll back the advisor
        # results already written in this session.
        with db.begin_nested():
            run = svc.start_run(db, host.id, {"assignment_id": None}, _PACK)
            payload["run_id"] = str(run.id)
            dispatch.queue_run(db, host.id, payload)
        return "queued"
    except Exception:  # pylint: disable=broad-except
        # Includes an agent too old to take RUN_QUERY_PACK -- ordinary, and
        # its fact rules then stay not_collected, which is what they are.
        logger.info("Advisor fact collection not queued for host %s", host.id)
        return "refused"


def collect(engine, db, hosts, rules, now, summary: Dict[str, Any]) -> None:
    """Dispatch due collections and prune old ones, for ``hosts``. Never raises
    past a host: one host's failure must not stop the others'."""
    queries = engine.collection_queries(rules, ev.FACT_QUERY_PREFIX)
    for host in hosts:
        try:
            found = _advisor_runs(db, host.id)
            runs = prune(db, found, now)
            summary["collections_pruned"] += len(found) - len(runs)
            if not queries or not host.active or not is_due(db, runs, queries, now):
                continue
            outcome = _dispatch(db, host, queries)
            summary["collections_" + outcome] += 1
            if outcome == "no_engine":
                return  # the same for every host; stop asking
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "Advisor fact collection failed for host %s (%s)", host.id, host.fqdn
            )
