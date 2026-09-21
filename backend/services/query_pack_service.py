# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Query-pack persistence (Phase 21.1 S4).

This file owns the DATABASE. Every RULE -- what makes a pack valid, which
assignment wins when a host matches several, when one is due, how a run is
graded -- belongs to the licensed engine and is reached through
``query_pack_shim``. Re-deciding any of them here is how two copies of a rule
start disagreeing.

THE PACK-RESOLUTION SHAPE
-------------------------
A pack is either curated (``shared`` partition) or tenant-authored (``tenant``
partition), and an assignment names exactly one of them. The shared reference
is SOFT -- no ForeignKey across a partition boundary -- so an assignment can
outlive the pack it names. ``resolve_pack`` returns ``None`` for that rather
than an empty query list: a pack with no queries would dispatch, run nothing,
and come back a clean success, reporting a host as measured when the pack it
was measured against no longer exists.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.persistence.partitions import PARTITION_SHARED, partition_session
from backend.services import query_pack_shim as shim

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    """Naive-UTC now. Public because the result handler closes runs too."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


_utcnow = utcnow


# ---------------------------------------------------------------------------
# the curated catalog (shared partition)
# ---------------------------------------------------------------------------


def list_shared_packs(include_deprecated: bool = False) -> List[Dict[str, Any]]:
    """The curated catalog, as plain dicts.

    Dicts rather than ORM objects because the rows come from a DIFFERENT
    session on a different partition. Handing a caller a detached instance
    from a closed session is how ``DetachedInstanceError`` appears three
    layers away from the code that caused it.
    """
    with partition_session(partition=PARTITION_SHARED) as session:
        query = session.query(models.SharedQueryPack)
        if not include_deprecated:
            query = query.filter(models.SharedQueryPack.deprecated.is_(False))
        packs = query.order_by(models.SharedQueryPack.name).all()
        return [_shared_pack_dict(p) for p in packs]


def get_shared_pack(shared_pack_id) -> Optional[Dict[str, Any]]:
    """One curated pack with its queries, or None."""
    with partition_session(partition=PARTITION_SHARED) as session:
        pack = (
            session.query(models.SharedQueryPack)
            .filter(models.SharedQueryPack.id == shared_pack_id)
            .one_or_none()
        )
        return _shared_pack_dict(pack, with_queries=True) if pack else None


def _shared_pack_dict(pack, with_queries: bool = False) -> Dict[str, Any]:
    out = {
        "id": str(pack.id),
        "slug": pack.slug,
        "name": pack.name,
        "description": pack.description,
        "version": pack.version,
        "category": pack.category,
        "deprecated": pack.deprecated,
        "source": pack.source,
        "curated": True,
        "query_count": len(pack.queries or []),
    }
    if with_queries:
        out["queries"] = [_query_dict(q) for q in pack.queries or []]
    return out


def _query_dict(query) -> Dict[str, Any]:
    return {
        "id": str(query.id),
        "name": query.name,
        "sql": query.sql,
        "description": query.description,
        "required_tables": list(query.required_tables or []),
        "interval_minutes": query.interval_minutes,
        "platforms": list(query.platforms or []),
    }


# ---------------------------------------------------------------------------
# tenant-authored packs
# ---------------------------------------------------------------------------


def list_packs(db: Session) -> List[models.QueryPack]:
    return db.query(models.QueryPack).order_by(models.QueryPack.name).all()


def get_pack(db: Session, pack_id) -> Optional[models.QueryPack]:
    return (
        db.query(models.QueryPack).filter(models.QueryPack.id == pack_id).one_or_none()
    )


def create_pack(
    db: Session, name: str, queries: List[Dict[str, Any]], **kw
) -> Tuple[Optional[models.QueryPack], List[str]]:
    """Validate then store. Returns ``(pack, problems)``.

    Validation comes FIRST and from the engine. A pack stored before it was
    checked is a pack that can be assigned and dispatched before anyone finds
    out, and the SQL in it is tenant-authored.
    """
    verdict = shim.validate_pack({"name": name, "queries": queries})
    if not verdict.get("valid"):
        return None, list(verdict.get("problems") or [])

    pack = models.QueryPack(
        id=uuid.uuid4(),
        name=name,
        description=kw.get("description"),
        version=1,
        enabled=kw.get("enabled", True),
        created_by=kw.get("created_by"),
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(pack)
    # Flushed before the children are added: the queries carry a real
    # ForeignKey to the pack, and SQLAlchemy orders inserts from
    # relationship() rather than from ForeignKey alone.
    db.flush()
    for query in queries:
        db.add(_new_query_row(pack.id, query))
    db.flush()
    return pack, []


def _new_query_row(pack_id, query: Dict[str, Any]) -> models.QueryPackQuery:
    return models.QueryPackQuery(
        id=uuid.uuid4(),
        pack_id=pack_id,
        name=query.get("name"),
        sql=query.get("sql"),
        description=query.get("description"),
        required_tables=list(query.get("required_tables") or []),
        interval_minutes=query.get("interval_minutes") or shim.DEFAULT_INTERVAL_MINUTES,
        platforms=list(query.get("platforms") or []),
    )


def update_pack(
    db: Session, pack: models.QueryPack, **changes
) -> Tuple[Optional[models.QueryPack], List[str]]:
    """Apply changes, re-validating whatever the result is.

    The version bumps whenever the QUERIES change, and not when only the
    description does: the version is what an assignment compares against to
    answer "this pack changed under you", and bumping it for a typo fix would
    cry wolf.
    """
    queries = changes.get("queries")
    name = changes.get("name", pack.name)

    if queries is not None:
        verdict = shim.validate_pack({"name": name, "queries": queries})
        if not verdict.get("valid"):
            return None, list(verdict.get("problems") or [])

    if "name" in changes and changes["name"] is not None:
        pack.name = changes["name"]
    if "description" in changes:
        pack.description = changes["description"]
    if "enabled" in changes and changes["enabled"] is not None:
        pack.enabled = changes["enabled"]

    if queries is not None:
        for existing in list(pack.queries or []):
            db.delete(existing)
        db.flush()
        for query in queries:
            db.add(_new_query_row(pack.id, query))
        pack.version = (pack.version or 1) + 1

    pack.updated_at = utcnow()
    db.flush()
    if queries is not None:
        # The relationship was loaded BEFORE the swap, so without this the
        # caller still sees the old queries -- and the API serialises the pack
        # it gets back from here, which means a successful edit would answer
        # with the rows it just replaced.
        db.expire(pack, ["queries"])
    return pack, []


def delete_pack(db: Session, pack: models.QueryPack) -> None:
    db.delete(pack)
    db.flush()


def pack_dict(pack: models.QueryPack, with_queries: bool = False) -> Dict[str, Any]:
    out = {
        "id": str(pack.id),
        "name": pack.name,
        "description": pack.description,
        "version": pack.version,
        "enabled": pack.enabled,
        "curated": False,
        "created_by": pack.created_by,
        "created_at": pack.created_at.isoformat() if pack.created_at else None,
        "query_count": len(pack.queries or []),
    }
    if with_queries:
        out["queries"] = [_query_dict(q) for q in pack.queries or []]
    return out


# ---------------------------------------------------------------------------
# assignments
# ---------------------------------------------------------------------------


def list_assignments(db: Session) -> List[models.QueryPackAssignment]:
    return db.query(models.QueryPackAssignment).all()


def create_assignment(db: Session, **kw) -> Tuple[Optional[Any], List[str]]:
    """Bind a pack to a host, a tag or a site.

    Refuses an assignment with no target. It is NOT a fleet-wide wildcard: a
    policy that silently applied to every host because a field was left empty
    gets noticed only after it has run everywhere. The engine enforces the
    same rule when resolving; this refuses it at the door so the row never
    exists.
    """
    problems = []
    pack_id = kw.get("pack_id")
    shared_pack_id = kw.get("shared_pack_id")
    if bool(pack_id) == bool(shared_pack_id):
        problems.append("an assignment names exactly one pack")
    targets = [kw.get("host_id"), kw.get("tag_id"), kw.get("site_id")]
    if sum(1 for t in targets if t) != 1:
        problems.append("an assignment targets exactly one host, tag or site")
    interval = kw.get("interval_minutes") or shim.DEFAULT_INTERVAL_MINUTES
    if interval < shim.MIN_INTERVAL_MINUTES:
        problems.append(
            f"interval must be at least {shim.MIN_INTERVAL_MINUTES} minutes"
        )
    if problems:
        return None, problems

    assignment = models.QueryPackAssignment(
        id=uuid.uuid4(),
        pack_id=pack_id,
        shared_pack_id=shared_pack_id,
        host_id=kw.get("host_id"),
        tag_id=kw.get("tag_id"),
        site_id=kw.get("site_id"),
        enabled=kw.get("enabled", True),
        interval_minutes=interval,
        created_by=kw.get("created_by"),
        created_at=_utcnow(),
    )
    db.add(assignment)
    db.flush()
    return assignment, []


def assignment_dict(assignment) -> Dict[str, Any]:
    return {
        "id": str(assignment.id),
        "pack_id": str(assignment.pack_id) if assignment.pack_id else None,
        "shared_pack_id": (
            str(assignment.shared_pack_id) if assignment.shared_pack_id else None
        ),
        "host_id": str(assignment.host_id) if assignment.host_id else None,
        "tag_id": str(assignment.tag_id) if assignment.tag_id else None,
        "site_id": str(assignment.site_id) if assignment.site_id else None,
        "enabled": assignment.enabled,
        "interval_minutes": assignment.interval_minutes,
        "last_dispatched_at": (
            assignment.last_dispatched_at.isoformat()
            if assignment.last_dispatched_at
            else None
        ),
    }


def resolve_pack(db: Session, resolved: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The pack an assignment names, with its queries — or None.

    ``None`` for a curated pack that no longer exists. Returning an empty
    query list instead would dispatch a pack that runs nothing and comes back
    a clean success, reporting a host as measured against a pack that is gone.
    """
    if resolved.get("shared_pack_id"):
        pack = get_shared_pack(resolved["shared_pack_id"])
        if pack is None:
            logger.warning(
                "Query pack assignment %s names shared pack %s, which is not "
                "in the catalog on this server",
                resolved.get("assignment_id"),
                resolved.get("shared_pack_id"),
            )
        return pack

    row = get_pack(db, resolved.get("pack_id"))
    if row is None or not row.enabled:
        return None
    return pack_dict(row, with_queries=True)


# ---------------------------------------------------------------------------
# runs and results
# ---------------------------------------------------------------------------


def start_run(db: Session, host_id, resolved, pack: Dict[str, Any]):
    """Open a run row at dispatch time, so a host that never answers is visible.

    Created PENDING before the command is queued rather than on the way back:
    a run that only exists once results arrive means a host which received a
    pack and went silent leaves no trace at all, and "never answered" is
    exactly what an operator needs to see.
    """
    run = models.QueryPackRun(
        id=uuid.uuid4(),
        assignment_id=resolved.get("assignment_id"),
        pack_id=pack.get("id") if not pack.get("curated") else None,
        shared_pack_id=pack.get("id") if pack.get("curated") else None,
        pack_name=pack.get("name"),
        host_id=host_id,
        status=models.RUN_STATUS_PENDING,
        started_at=_utcnow(),
    )
    db.add(run)
    db.flush()
    return run


def record_results(db: Session, run, payload: Dict[str, Any]):
    """Store what an agent returned and grade the run.

    Grading goes through the shim, which keeps the substrate's property: a
    host that could not answer some queries grades ``partial``, never
    ``success``. Collapsing those would report the host compliant on a
    question nobody asked it.
    """
    results = list((payload or {}).get("results") or [])
    graded = shim.grade_run(results)

    run.status = graded["status"]
    run.queries_total = graded["queries_total"]
    run.queries_ok = graded["queries_ok"]
    run.queries_not_covered = graded["queries_not_covered"]
    run.queries_failed = graded["queries_failed"]
    run.contract_version = payload.get("contract_version")
    run.completed_at = _utcnow()

    now = _utcnow()
    for result in results:
        name = result.get("name")
        status = result.get("status")
        rows = result.get("rows") or []
        if status != models.QUERY_STATUS_OK or not rows:
            # ONE row standing for "asked, not answered" (or answered with
            # nothing). Without it a not-covered query would leave no trace,
            # and the run's counts would be the only evidence the question was
            # ever asked.
            db.add(
                models.QueryPackResultRow(
                    id=uuid.uuid4(),
                    run_id=run.id,
                    query_name=name,
                    status=status or models.QUERY_STATUS_ERROR,
                    reason=result.get("reason") or result.get("error"),
                    columns=None,
                    collected_at=now,
                )
            )
            continue
        for row in rows:
            db.add(
                models.QueryPackResultRow(
                    id=uuid.uuid4(),
                    run_id=run.id,
                    query_name=name,
                    status=models.QUERY_STATUS_OK,
                    columns=row,
                    collected_at=now,
                )
            )
    db.flush()
    return run


def run_dict(run, with_results: bool = False) -> Dict[str, Any]:
    out = {
        "id": str(run.id),
        "host_id": str(run.host_id),
        "pack_name": run.pack_name,
        "status": run.status,
        "contract_version": run.contract_version,
        "queries_total": run.queries_total,
        "queries_ok": run.queries_ok,
        "queries_not_covered": run.queries_not_covered,
        "queries_failed": run.queries_failed,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
    if with_results:
        out["results"] = [
            {
                "query_name": r.query_name,
                "status": r.status,
                "reason": r.reason,
                "columns": r.columns,
            }
            for r in run.results or []
        ]
    return out
