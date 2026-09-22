# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Ingest query-pack results from an agent (Phase 21.1 S4).

The return leg. The tick opened a ``QueryPackRun`` at dispatch time and put
its id in the command; the agent echoes that id back, which is what lets this
find the run rather than guessing from host and timestamp.

WHY A MISSING RUN IS NOT DROPPED SILENTLY
-----------------------------------------
Results that cannot be attached to a run are logged loudly and discarded. That
is a real loss -- those measurements cannot be taken again until the next
interval -- so it must be visible. It happens when a run row was removed while
its command was in flight, or when an agent replays a very old command; both
are worth knowing about, and neither should invent a run to hang them on.

GRADING STAYS IN ONE PLACE
--------------------------
``query_pack_service.record_results`` grades through the licensed engine, so
"not covered" never collapses into "no rows" on this path either. This handler
does routing and nothing else.
"""

import logging
from typing import Any, Dict, Optional

from backend.persistence import models
from backend.services import file_watch_service as fws
from backend.services import query_pack_service as svc
from backend.utils.log_sanitize import scrub

logger = logging.getLogger(__name__)


async def handle_query_pack_result(
    db, connection, message_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Attach one agent's pack results to its run and grade it."""
    result = message_data.get("result") or {}
    if not message_data.get("success", True):
        # A refused or failed run still has a row to close. Leaving it PENDING
        # forever would present a host as "still collecting" indefinitely.
        return _fail_run(db, message_data, result)

    payload = result.get("result") if isinstance(result.get("result"), dict) else result
    run_id = payload.get("run_id") or result.get("run_id") or message_data.get("run_id")
    run = _find_run(db, run_id)
    if run is None:
        logger.warning(
            "Query pack results arrived for run %s, which does not exist on "
            "this server; %d result(s) discarded",
            scrub(run_id),
            len(payload.get("results") or []),
        )
        return {"status": "ignored"}

    svc.record_results(db, run, payload)
    _advance_live_query(db, run)
    _ingest_file_watch(db, run, payload)
    db.commit()
    logger.info(
        "Query pack run %s graded %s (%d ok, %d not covered, %d failed)",
        run.id,
        run.status,
        run.queries_ok,
        run.queries_not_covered,
        run.queries_failed,
    )
    return {"status": "recorded", "run_status": run.status}


def _ingest_file_watch(db, run, payload) -> None:
    """Project a file-watch run's rows into ``host_file_state``.

    Phase 21.1 S7. A file watch is dispatched AS a one-query pack, so its
    results have already landed in ``query_pack_result_row`` like any other
    pack's. They are ALSO upserted into ``host_file_state``, which is what the
    golden-host differ reads: the result rows are an append-only history of
    runs, while the differ needs "the current state of every watched path on
    this host" -- a different question, and one that would otherwise be a
    correlated subquery per path over the whole run history.

    Never raises. A projection failure must not lose the measurements just
    recorded; they cannot be retaken until the next interval.
    """
    results = [
        r
        for r in (payload or {}).get("results") or []
        if r.get("name") == fws.WATCH_QUERY_NAME
    ]
    if not results:
        return
    try:
        for result in results:
            if result.get("status") != models.QUERY_STATUS_OK:
                # The host was ASKED and could not answer. Ingesting an empty
                # row set here would delete every path we hold for it and
                # silently erase the baseline the differ compares against.
                logger.warning(
                    "File watch for host %s returned %s (%s); keeping the "
                    "previously recorded state rather than clearing it",
                    run.host_id,
                    result.get("status"),
                    result.get("reason") or result.get("error"),
                )
                continue
            count = fws.ingest_rows(db, run.host_id, result.get("rows") or [])
            logger.info(
                "File watch recorded %d watched path(s) for host %s",
                count,
                run.host_id,
            )
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "Failed to project file watch results for run %s into host_file_state",
            run.id,
        )


def _advance_live_query(db, run) -> None:
    """Release the next wave of an ad-hoc query as this answer lands.

    Phase 21.1 S5. Driven from the INGEST path rather than a tick because a
    live query is interactive: waiting up to 60 seconds to release each next
    host would make a 400-host query take hours no matter how fast the hosts
    actually answer.

    Never raises. A failure to advance must not lose the result we just
    recorded -- that measurement cannot be retaken until the operator runs the
    query again.
    """
    if not getattr(run, "live_query_id", None):
        return
    try:
        from backend.services import query_pack_live  # noqa: PLC0415

        live = (
            db.query(models.QueryPackLiveQuery)
            .filter(models.QueryPackLiveQuery.id == run.live_query_id)
            .one_or_none()
        )
        if live is not None:
            query_pack_live.advance(db, live)
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "Could not advance live query %s; its result was still recorded",
            scrub(run.live_query_id),
        )


def _find_run(db, run_id):
    if not run_id:
        return None
    return (
        db.query(models.QueryPackRun)
        .filter(models.QueryPackRun.id == run_id)
        .one_or_none()
    )


def _fail_run(db, message_data, result) -> Dict[str, Any]:
    """Close a run the agent could not complete."""
    run = _find_run(db, (result or {}).get("run_id") or message_data.get("run_id"))
    if run is None:
        logger.warning(
            "Query pack failure arrived with no run to attach it to: %s",
            scrub(message_data.get("error")),
        )
        return {"status": "ignored"}
    run.status = models.RUN_STATUS_FAILED
    run.error = str(message_data.get("error") or "")[:2000]
    run.completed_at = svc.utcnow()
    db.commit()
    return {"status": "failed"}
