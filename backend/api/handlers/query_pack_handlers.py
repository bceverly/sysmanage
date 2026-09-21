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
