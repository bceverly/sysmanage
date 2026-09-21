# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Query pack CRUD, assignment and results (Phase 21.1 S4).

WHY THE WHOLE ROUTER IS LICENCE-GATED
-------------------------------------
The fact SUBSTRATE is open-source and stays that way: every agent serves the
osquery-schema tables whatever licence the server holds, because better
inventory drives adoption. What is Professional is the MANAGEMENT plane --
authoring packs, assigning them as policy per host/tag/site, pacing collection
and reading the results. So the gate sits on the router rather than per route:
a new endpoint added here is gated by default, which is the safe direction to
fail.

WHY THE RULES LIVE IN THE ENGINE
--------------------------------
Validation, assignment precedence, due-ness and run grading all come from
``query_pack_engine`` via ``query_pack_shim``. This file owns HTTP,
persistence and authorisation, and deliberately re-implements none of them.

ROLES
-----
Reuses the SCRIPT roles, as configuration profiles do. A stored pack is the
same class of object as a saved script -- executable content, authored once
and run against hosts -- so the same entitlement should govern both, and a
parallel set would need seeding into ``security_roles`` for no behavioural
gain.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.feature_gate import require_module_loaded
from backend.licensing.features import ModuleCode
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import query_pack_service as svc
from backend.services import query_pack_shim as shim

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[
        Depends(JWTBearer()),
        Depends(require_module_loaded(ModuleCode.QUERY_PACK_ENGINE)),
    ]
)


class QueryIn(BaseModel):
    """One query in a pack."""

    name: str
    sql: str
    description: Optional[str] = None
    required_tables: Optional[List[str]] = None
    interval_minutes: Optional[int] = None
    platforms: Optional[List[str]] = None


class PackCreateRequest(BaseModel):
    name: str
    queries: List[QueryIn]
    description: Optional[str] = None
    enabled: bool = True


class PackUpdateRequest(BaseModel):
    """Fields to change. Omitted fields are left alone."""

    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    queries: Optional[List[QueryIn]] = None


class AssignmentCreateRequest(BaseModel):
    pack_id: Optional[str] = None
    shared_pack_id: Optional[str] = None
    host_id: Optional[str] = None
    tag_id: Optional[str] = None
    site_id: Optional[str] = None
    interval_minutes: Optional[int] = None
    enabled: bool = True


def _require_role(user, role) -> None:
    if not user.has_role(role):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required") % role.value,
        )


def _as_uuid(value: str, message: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=message) from exc


def _refuse(problems: List[str]) -> None:
    """Turn engine problems into one 400 the author can act on.

    Every problem at once rather than the first: an author fixing a pack wants
    the whole list, not one per save.
    """
    raise HTTPException(
        status_code=400,
        detail=_("The query pack was rejected: %s") % "; ".join(problems),
    )


@router.get("/query-packs/catalog")
async def list_catalog(
    include_deprecated: bool = False,
) -> List[Dict[str, Any]]:
    """The curated catalog — global reference data, one copy for everyone."""
    return svc.list_shared_packs(include_deprecated=include_deprecated)


@router.get("/query-packs")
async def list_packs(
    db: Session = Depends(get_tenant_db),
) -> List[Dict[str, Any]]:
    """Packs this customer wrote."""
    return [svc.pack_dict(p) for p in svc.list_packs(db)]


@router.get("/query-packs/{pack_id}")
async def get_pack(
    pack_id: str,
    db: Session = Depends(get_tenant_db),
) -> Dict[str, Any]:
    pack = svc.get_pack(db, _as_uuid(pack_id, _("Invalid query pack ID format")))
    if pack is None:
        raise HTTPException(status_code=404, detail=_("Query pack not found"))
    return svc.pack_dict(pack, with_queries=True)


@router.post("/query-packs")
async def create_pack(
    request: PackCreateRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require_role(current_user, SecurityRoles.ADD_SCRIPT)
    pack, problems = svc.create_pack(
        db,
        request.name,
        [q.model_dump() for q in request.queries],
        description=request.description,
        enabled=request.enabled,
        created_by=current_user.userid,
    )
    if problems:
        _refuse(problems)
    db.commit()
    return svc.pack_dict(pack, with_queries=True)


@router.put("/query-packs/{pack_id}")
async def update_pack(
    pack_id: str,
    request: PackUpdateRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    pack = svc.get_pack(db, _as_uuid(pack_id, _("Invalid query pack ID format")))
    if pack is None:
        raise HTTPException(status_code=404, detail=_("Query pack not found"))

    changes = request.model_dump(exclude_unset=True)
    if changes.get("queries") is not None:
        changes["queries"] = [dict(q) for q in changes["queries"]]
    updated, problems = svc.update_pack(db, pack, **changes)
    if problems:
        db.rollback()
        _refuse(problems)
    db.commit()
    return svc.pack_dict(updated, with_queries=True)


@router.delete("/query-packs/{pack_id}")
async def delete_pack(
    pack_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, str]:
    _require_role(current_user, SecurityRoles.DELETE_SCRIPT)
    pack = svc.get_pack(db, _as_uuid(pack_id, _("Invalid query pack ID format")))
    if pack is None:
        raise HTTPException(status_code=404, detail=_("Query pack not found"))
    svc.delete_pack(db, pack)
    db.commit()
    return {"status": "deleted"}


@router.post("/query-packs/validate")
async def validate_pack(
    request: PackCreateRequest,
) -> Dict[str, Any]:
    """Check a pack without storing it, so the editor can say why.

    Its own endpoint rather than inferring from a failed create: an author
    wants to know the SQL is acceptable before committing a name, and a 400
    from create leaves no draft behind to fix.
    """
    return shim.validate_pack(
        {"name": request.name, "queries": [q.model_dump() for q in request.queries]}
    )


@router.get("/query-packs/assignments/all")
async def list_assignments(
    db: Session = Depends(get_tenant_db),
) -> List[Dict[str, Any]]:
    return [svc.assignment_dict(a) for a in svc.list_assignments(db)]


@router.post("/query-packs/assignments")
async def create_assignment(
    request: AssignmentCreateRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    payload = request.model_dump()
    for field in ("pack_id", "shared_pack_id", "host_id", "tag_id", "site_id"):
        if payload.get(field):
            payload[field] = _as_uuid(
                payload[field], _("Invalid ID format in the assignment")
            )
    assignment, problems = svc.create_assignment(
        db, created_by=current_user.userid, **payload
    )
    if problems:
        db.rollback()
        _refuse(problems)
    db.commit()
    return svc.assignment_dict(assignment)


@router.delete("/query-packs/assignments/{assignment_id}")
async def delete_assignment(
    assignment_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, str]:
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    assignment = (
        db.query(models.QueryPackAssignment)
        .filter(
            models.QueryPackAssignment.id
            == _as_uuid(assignment_id, _("Invalid assignment ID format"))
        )
        .one_or_none()
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail=_("Assignment not found"))
    db.delete(assignment)
    db.commit()
    return {"status": "deleted"}


@router.get("/query-packs/runs/recent")
async def list_runs(
    host_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_tenant_db),
) -> List[Dict[str, Any]]:
    """Recent runs, newest first."""
    query = db.query(models.QueryPackRun)
    if host_id:
        query = query.filter(
            models.QueryPackRun.host_id
            == _as_uuid(host_id, _("Invalid host ID format"))
        )
    runs = (
        query.order_by(models.QueryPackRun.started_at.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [svc.run_dict(r) for r in runs]


@router.get("/query-packs/runs/{run_id}")
async def get_run(
    run_id: str,
    db: Session = Depends(get_tenant_db),
) -> Dict[str, Any]:
    run = (
        db.query(models.QueryPackRun)
        .filter(models.QueryPackRun.id == _as_uuid(run_id, _("Invalid run ID format")))
        .one_or_none()
    )
    if run is None:
        raise HTTPException(status_code=404, detail=_("Query pack run not found"))
    return svc.run_dict(run, with_results=True)
