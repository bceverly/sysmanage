# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Ad-hoc fleet-wide live queries (Phase 21.1 S5).

One statement, typed at a console, fanned out across a fleet -- BOUNDED the way
fleet jobs are, rather than dispatched to everything at once.

WHY TARGETS ARE CREATED UP FRONT BUT NOT DISPATCHED
----------------------------------------------------
Every targeted host gets a run row immediately, in ``waiting``. Only
``concurrency`` of them are released at a time. Two things fall out of that
which matter more than they look:

* the operator sees the TOTAL straight away -- "0 of 400" rather than a number
  that grows as dispatch proceeds, which is indistinguishable from a stalled
  fan-out; and
* a host that is never reached still has a row saying so, instead of leaving
  no trace at all.

WHY THE WAVE ADVANCES ON RESULT ARRIVAL
---------------------------------------
A live query is interactive. Waiting for a 60-second tick to release the next
host would make a 400-host query take hours regardless of how fast the hosts
answer. So the ingest path calls ``advance`` as each result lands, and the
sweeper below exists only for the hosts that never answer at all.

NOT MEASURED IS STILL NOT EMPTY
-------------------------------
``not_covered_count`` is tracked separately from ``failed_count``. A host that
does not serve the tables has not failed -- folding the two together would make
a Windows box look broken for lacking ``mounts``.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import query_pack_dispatch as dispatch
from backend.services import query_pack_shim as shim

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create(
    db: Session,
    sql: str,
    hosts: List[Any],
    **kw,
) -> tuple:
    """Create a live query and its target rows. Returns ``(live, problems)``.

    Validation happens BEFORE any row is written. A statement stored and
    targeted before it was checked is one that can be dispatched by the
    advance path a moment later, and the SQL is operator-typed.
    """
    problems = shim.validate_live_query(sql, kw.get("required_tables"))
    if problems:
        return None, problems
    if not hosts:
        # Not an error: targeting a tag that matches nothing is a legitimate
        # thing to do and the honest answer is an empty, completed query --
        # NOT a running one with nothing able to finish it.
        problems = []

    live = models.QueryPackLiveQuery(
        id=uuid.uuid4(),
        name=kw.get("name"),
        sql=sql,
        required_tables=list(kw.get("required_tables") or []),
        status=models.LIVE_PENDING,
        concurrency=shim.clamp_concurrency(kw.get("concurrency")),
        timeout_seconds=shim.clamp_timeout(kw.get("timeout_seconds")),
        total_targets=len(hosts),
        requested_by=kw.get("requested_by"),
        created_at=utcnow(),
    )
    db.add(live)
    # Flushed before the targets: they carry the live query's id, and
    # SQLAlchemy orders inserts from relationship() rather than from a plain
    # column, so the id has to exist first.
    db.flush()

    for host in hosts:
        db.add(
            models.QueryPackRun(
                id=uuid.uuid4(),
                live_query_id=live.id,
                pack_name=live.name or "live query",
                host_id=host.id,
                status=models.RUN_STATUS_WAITING,
                started_at=utcnow(),
            )
        )
    db.flush()
    return live, []


def _counts(db: Session, live) -> Dict[str, int]:
    """How many of this query's targets are waiting, in flight and settled."""
    rows = (
        db.query(models.QueryPackRun)
        .filter(models.QueryPackRun.live_query_id == live.id)
        .all()
    )
    waiting = sum(1 for r in rows if r.status == models.RUN_STATUS_WAITING)
    in_flight = sum(1 for r in rows if r.status == models.RUN_STATUS_PENDING)
    settled = [
        r
        for r in rows
        if r.status
        not in (
            models.RUN_STATUS_WAITING,
            models.RUN_STATUS_PENDING,
        )
    ]
    return {
        "waiting": waiting,
        "in_flight": in_flight,
        "finished": len(settled),
        "failed": sum(1 for r in settled if r.status == models.RUN_STATUS_FAILED),
        "not_covered": sum(1 for r in settled if r.queries_not_covered),
    }


def advance(db: Session, live) -> int:
    """Release the next wave. Returns how many targets were dispatched.

    Called after creation and again as each result lands, so the fan-out keeps
    exactly ``concurrency`` hosts busy without ever exceeding it.
    """
    if live.status in (models.LIVE_COMPLETED, models.LIVE_CANCELED):
        return 0

    counts = _counts(db, live)
    allowed = shim.next_batch_size(
        live.concurrency, counts["in_flight"], counts["waiting"]
    )

    dispatched = 0
    if allowed > 0:
        targets = (
            db.query(models.QueryPackRun)
            .filter(
                models.QueryPackRun.live_query_id == live.id,
                models.QueryPackRun.status == models.RUN_STATUS_WAITING,
            )
            .limit(allowed)
            .all()
        )
        for run in targets:
            if _dispatch_one(db, live, run):
                dispatched += 1

    _refresh_status(db, live)
    return dispatched


def _dispatch_one(db: Session, live, run) -> bool:
    """Send the query to one host. Returns False if it could not go.

    A host that cannot take the command is settled as FAILED rather than left
    waiting: it would otherwise hold a slot forever and the query would never
    complete.
    """
    host = db.query(models.Host).filter(models.Host.id == run.host_id).one_or_none()
    if host is None:
        run.status = models.RUN_STATUS_FAILED
        run.error = "host no longer exists"
        run.completed_at = utcnow()
        return False

    pack = {
        "name": live.name or "live query",
        "id": str(live.id),
        "version": 1,
        "queries": [
            {
                "name": "live",
                "sql": live.sql,
                "required_tables": list(live.required_tables or []),
            }
        ],
    }
    payload = dispatch.build_payload(pack, pack["queries"], host)
    if payload is None:
        run.status = models.RUN_STATUS_FAILED
        run.error = "the query-pack engine is not loaded"
        run.completed_at = utcnow()
        return False

    payload["run_id"] = str(run.id)
    try:
        dispatch.queue_run(db, host.id, payload)
    except Exception:  # pylint: disable=broad-except
        # Includes UnsupportedCapabilityError for an agent that predates query
        # packs -- an ordinary outcome across a mixed fleet, not a fault.
        logger.info(
            "Live query %s not queued for host %s; it cannot take this command",
            live.id,
            run.host_id,
        )
        run.status = models.RUN_STATUS_FAILED
        run.error = "the agent on this host cannot run query packs"
        run.completed_at = utcnow()
        return False

    run.status = models.RUN_STATUS_PENDING
    run.started_at = utcnow()
    return True


def _refresh_status(db: Session, live) -> None:
    counts = _counts(db, live)
    live.completed_count = counts["finished"]
    live.failed_count = counts["failed"]
    live.not_covered_count = counts["not_covered"]
    if live.started_at is None and counts["in_flight"]:
        live.started_at = utcnow()
    live.status = shim.live_status_after(live.total_targets, counts["finished"])
    if live.status == models.LIVE_COMPLETED and live.completed_at is None:
        live.completed_at = utcnow()
    db.flush()


def sweep_timeouts(db: Session, live) -> int:
    """Settle targets that were dispatched and never answered.

    The reason there is no "wait forever" timeout: one unreachable host would
    hold its slot indefinitely and every host behind it would never be asked.
    The query would appear to hang rather than finish with that host marked
    unreachable, which is a far worse answer than a late one.
    """
    if live.status in (models.LIVE_COMPLETED, models.LIVE_CANCELED):
        return 0
    cutoff = utcnow() - timedelta(seconds=live.timeout_seconds)
    stale = (
        db.query(models.QueryPackRun)
        .filter(
            models.QueryPackRun.live_query_id == live.id,
            models.QueryPackRun.status == models.RUN_STATUS_PENDING,
            models.QueryPackRun.started_at < cutoff,
        )
        .all()
    )
    for run in stale:
        run.status = models.RUN_STATUS_FAILED
        run.error = f"no answer within {live.timeout_seconds}s"
        run.completed_at = utcnow()
    if stale:
        db.flush()
    return len(stale)


def cancel(db: Session, live) -> int:
    """Stop releasing new targets. Already-dispatched ones are left alone.

    Recalling a command that is already on a host's queue is not possible, and
    pretending otherwise would report a host as cancelled while it runs the
    query anyway.
    """
    waiting = (
        db.query(models.QueryPackRun)
        .filter(
            models.QueryPackRun.live_query_id == live.id,
            models.QueryPackRun.status == models.RUN_STATUS_WAITING,
        )
        .all()
    )
    for run in waiting:
        run.status = models.RUN_STATUS_FAILED
        run.error = "cancelled before dispatch"
        run.completed_at = utcnow()
    live.status = models.LIVE_CANCELED
    live.completed_at = utcnow()
    db.flush()
    return len(waiting)


def live_dict(live, with_targets: bool = False, db: Optional[Session] = None):
    out = {
        "id": str(live.id),
        "name": live.name,
        "sql": live.sql,
        "required_tables": list(live.required_tables or []),
        "status": live.status,
        "concurrency": live.concurrency,
        "timeout_seconds": live.timeout_seconds,
        "total_targets": live.total_targets,
        "completed_count": live.completed_count,
        "failed_count": live.failed_count,
        "not_covered_count": live.not_covered_count,
        "requested_by": live.requested_by,
        "created_at": live.created_at.isoformat() if live.created_at else None,
        "completed_at": (live.completed_at.isoformat() if live.completed_at else None),
    }
    if with_targets and db is not None:
        runs = (
            db.query(models.QueryPackRun)
            .filter(models.QueryPackRun.live_query_id == live.id)
            .all()
        )
        out["targets"] = [
            {
                "run_id": str(r.id),
                "host_id": str(r.host_id),
                "status": r.status,
                "queries_ok": r.queries_ok,
                "queries_not_covered": r.queries_not_covered,
                "error": r.error,
                "rows": [
                    {"status": x.status, "reason": x.reason, "columns": x.columns}
                    for x in (r.results or [])
                ],
            }
            for r in runs
        ]
    return out
