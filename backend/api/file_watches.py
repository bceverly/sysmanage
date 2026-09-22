# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""File watch lists, their assignment, and collected state (Phase 21.1 S7).

WHY THIS ROUTER IS GATED THE SAME WAY DRIFT IS
-----------------------------------------------
Watched-file state exists to feed the golden-host differ, which sits behind
``config_management_engine``. Gating the authoring surface anywhere else would
let an operator build watch lists they could never compare with. The gate is
on the ROUTER rather than per route, so a new endpoint added here is gated by
default -- the safe direction to fail.

ROLES
-----
Reuses the SCRIPT roles, as query packs and configuration profiles do. A watch
list is the same class of object: authored content, applied to hosts as
policy. A parallel set would need seeding into ``security_roles`` for no
behavioural gain.

NO FILE CONTENT CROSSES THIS SURFACE
-------------------------------------
Nothing here returns file contents, because nothing collects them -- see
``persistence/models/file_watch.py``. A path, a hash and stat metadata are the
whole vocabulary, which is what makes watching /etc/shadow safe.
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
from backend.persistence.models.file_watch import (
    DEFAULT_INTERVAL_MINUTES,
    MIN_INTERVAL_MINUTES,
)
from backend.services import file_watch_service as fws

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[
        Depends(JWTBearer()),
        Depends(require_module_loaded(ModuleCode.CONFIG_MANAGEMENT_ENGINE)),
    ]
)

# A watch list of thousands of paths is a fleet-wide hashing job every
# interval. Bounded at the edge, where the operator can be told why.
MAX_PATHS_PER_WATCH = 500


class PathIn(BaseModel):
    """One watched path."""

    path: str
    description: Optional[str] = None
    platforms: Optional[List[str]] = None


class WatchCreateRequest(BaseModel):
    name: str
    paths: List[PathIn]
    description: Optional[str] = None
    enabled: bool = True


class WatchUpdateRequest(BaseModel):
    name: Optional[str] = None
    paths: Optional[List[PathIn]] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None


class AssignmentCreateRequest(BaseModel):
    watch_id: Optional[str] = None
    shared_watch_id: Optional[str] = None
    host_id: Optional[str] = None
    tag_id: Optional[str] = None
    site_id: Optional[str] = None
    interval_minutes: Optional[int] = None
    enabled: bool = True


def _as_uuid(value: str, message: str):
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=message) from exc


def _require_role(current_user, role) -> None:
    if not current_user.has_role(role):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required") % role.value,
        )


def _validate_paths(paths: List[PathIn]) -> List[str]:
    """Refuse a watch list that cannot be collected honestly.

    Refusing at authoring time rather than silently dropping: a path an
    operator believes is watched, and is not, produces a comparison that looks
    complete and is not -- the failure mode this whole slice exists to remove.
    """
    problems: List[str] = []
    if not paths:
        problems.append(_("A watch list must contain at least one path."))
    if len(paths) > MAX_PATHS_PER_WATCH:
        problems.append(
            _("A watch list may contain at most %d paths.") % MAX_PATHS_PER_WATCH
        )
    seen = set()
    for entry in paths:
        path = (entry.path or "").strip()
        if not path:
            problems.append(_("A watched path cannot be empty."))
            continue
        # Relative paths resolve against the agent's working directory, which
        # is not a property an operator can reason about and differs between
        # hosts -- so the same list would watch different files on each.
        if not (path.startswith("/") or ":" in path[:3] or path.startswith("\\\\")):
            problems.append(_("Watched path must be absolute: %s") % path)
        if path in seen:
            problems.append(_("Duplicate watched path: %s") % path)
        seen.add(path)
    return problems


def _watch_dict(watch, with_paths: bool = False) -> Dict[str, Any]:
    out = {
        "id": str(watch.id),
        "name": watch.name,
        "description": watch.description,
        "version": watch.version,
        "enabled": watch.enabled,
        "created_by": watch.created_by,
        "created_at": watch.created_at.isoformat() if watch.created_at else None,
        "path_count": len(watch.paths or []),
    }
    if with_paths:
        out["paths"] = [
            {
                "id": str(p.id),
                "path": p.path,
                "description": p.description,
                "platforms": p.platforms,
            }
            for p in sorted(watch.paths or [], key=lambda r: r.path)
        ]
    return out


def _assignment_dict(assignment) -> Dict[str, Any]:
    return {
        "id": str(assignment.id),
        "watch_id": str(assignment.watch_id) if assignment.watch_id else None,
        "shared_watch_id": (
            str(assignment.shared_watch_id) if assignment.shared_watch_id else None
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


@router.get("/file-watches")
async def list_watches(db: Session = Depends(get_tenant_db)) -> List[Dict[str, Any]]:
    """Watch lists this customer wrote."""
    return [_watch_dict(w) for w in db.query(models.FileWatch).all()]


@router.get("/file-watches/catalog")
async def list_catalog(include_deprecated: bool = False) -> List[Dict[str, Any]]:
    """The curated catalog — global reference data, one copy for everyone."""
    return fws.list_shared_watches(include_deprecated=include_deprecated)


@router.get("/file-watches/assignments/all")
async def list_assignments(
    db: Session = Depends(get_tenant_db),
) -> List[Dict[str, Any]]:
    return [_assignment_dict(a) for a in db.query(models.FileWatchAssignment).all()]


@router.get("/file-watches/hosts/{host_id}/state")
async def host_state(
    host_id: str,
    db: Session = Depends(get_tenant_db),
) -> Dict[str, Any]:
    """Every watched path on one host, whatever happened to it.

    The absent and unreadable rows are returned too. Filtering them out would
    leave the caller unable to tell a deleted file from an unwatched one,
    which is exactly the distinction this table exists to carry.
    """
    ident = _as_uuid(host_id, _("Invalid host ID format"))
    rows = (
        db.query(models.HostFileState)
        .filter(models.HostFileState.host_id == ident)
        .order_by(models.HostFileState.path)
        .all()
    )
    return {
        "host_id": str(ident),
        "paths": [
            {
                "path": r.path,
                "state": r.state,
                "sha256": r.sha256,
                "size": r.size,
                "mode": r.mode,
                "owner": r.owner,
                "group_name": r.group_name,
                "mtime": r.mtime,
                "type": r.type,
                "target": r.target,
                "collected_at": (
                    r.collected_at.isoformat() if r.collected_at else None
                ),
            }
            for r in rows
        ],
        "counts": _state_counts(rows),
    }


def _state_counts(rows) -> Dict[str, int]:
    """How many paths landed in each state.

    Reported alongside the rows so a caller can say "38 watched, 2 we could
    not read" without walking the list -- and so the blind spots are visible
    without being hunted for.
    """
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row.state] = counts.get(row.state, 0) + 1
    return counts


@router.get("/file-watches/{watch_id}")
async def get_watch(
    watch_id: str,
    db: Session = Depends(get_tenant_db),
) -> Dict[str, Any]:
    watch = (
        db.query(models.FileWatch)
        .filter(models.FileWatch.id == _as_uuid(watch_id, _("Invalid watch ID format")))
        .first()
    )
    if watch is None:
        raise HTTPException(status_code=404, detail=_("File watch not found"))
    return _watch_dict(watch, with_paths=True)


@router.post("/file-watches")
async def create_watch(
    request: WatchCreateRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require_role(current_user, SecurityRoles.ADD_SCRIPT)
    problems = _validate_paths(request.paths)
    if problems:
        raise HTTPException(status_code=400, detail="; ".join(problems))

    watch = models.FileWatch(
        id=uuid.uuid4(),
        name=request.name,
        description=request.description,
        enabled=request.enabled,
        created_by=current_user.userid,
    )
    db.add(watch)
    db.flush()
    for entry in request.paths:
        db.add(
            models.FileWatchPath(
                id=uuid.uuid4(),
                watch_id=watch.id,
                path=entry.path.strip(),
                description=entry.description,
                platforms=entry.platforms,
            )
        )
    db.commit()
    db.refresh(watch)
    return _watch_dict(watch, with_paths=True)


@router.put("/file-watches/{watch_id}")
async def update_watch(
    watch_id: str,
    request: WatchUpdateRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    watch = (
        db.query(models.FileWatch)
        .filter(models.FileWatch.id == _as_uuid(watch_id, _("Invalid watch ID format")))
        .first()
    )
    if watch is None:
        raise HTTPException(status_code=404, detail=_("File watch not found"))

    changes = request.model_dump(exclude_unset=True)
    if changes.get("paths") is not None:
        problems = _validate_paths(request.paths)
        if problems:
            raise HTTPException(status_code=400, detail="; ".join(problems))
        for existing in list(watch.paths or []):
            db.delete(existing)
        db.flush()
        for entry in request.paths:
            db.add(
                models.FileWatchPath(
                    id=uuid.uuid4(),
                    watch_id=watch.id,
                    path=entry.path.strip(),
                    description=entry.description,
                    platforms=entry.platforms,
                )
            )
        # Bumped so an assignment can tell "the list changed under me" from a
        # timestamp comparison, exactly as a query pack's version does.
        watch.version = (watch.version or 1) + 1

    for field in ("name", "description", "enabled"):
        if field in changes:
            setattr(watch, field, changes[field])

    db.commit()
    db.refresh(watch)
    return _watch_dict(watch, with_paths=True)


@router.delete("/file-watches/{watch_id}")
async def delete_watch(
    watch_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, str]:
    _require_role(current_user, SecurityRoles.DELETE_SCRIPT)
    watch = (
        db.query(models.FileWatch)
        .filter(models.FileWatch.id == _as_uuid(watch_id, _("Invalid watch ID format")))
        .first()
    )
    if watch is None:
        raise HTTPException(status_code=404, detail=_("File watch not found"))
    db.delete(watch)
    db.commit()
    return {"status": "deleted"}


@router.post("/file-watches/assignments")
async def create_assignment(
    request: AssignmentCreateRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)

    if bool(request.watch_id) == bool(request.shared_watch_id):
        raise HTTPException(
            status_code=400,
            detail=_("Specify exactly one of watch_id or shared_watch_id."),
        )
    targets = [request.host_id, request.tag_id, request.site_id]
    if sum(1 for t in targets if t) != 1:
        raise HTTPException(
            status_code=400,
            detail=_("Specify exactly one of host_id, tag_id or site_id."),
        )

    interval = request.interval_minutes or DEFAULT_INTERVAL_MINUTES
    if interval < MIN_INTERVAL_MINUTES:
        # Clamped at the edge with an explanation rather than silently: an
        # operator who asks for every minute should be told why they did not
        # get it.
        raise HTTPException(
            status_code=400,
            detail=_("Collection interval must be at least %d minutes.")
            % MIN_INTERVAL_MINUTES,
        )

    assignment = models.FileWatchAssignment(
        id=uuid.uuid4(),
        watch_id=(
            _as_uuid(request.watch_id, _("Invalid watch ID format"))
            if request.watch_id
            else None
        ),
        shared_watch_id=(
            _as_uuid(request.shared_watch_id, _("Invalid watch ID format"))
            if request.shared_watch_id
            else None
        ),
        host_id=(
            _as_uuid(request.host_id, _("Invalid host ID format"))
            if request.host_id
            else None
        ),
        tag_id=(
            _as_uuid(request.tag_id, _("Invalid tag ID format"))
            if request.tag_id
            else None
        ),
        site_id=(
            _as_uuid(request.site_id, _("Invalid site ID format"))
            if request.site_id
            else None
        ),
        enabled=request.enabled,
        interval_minutes=interval,
        created_by=current_user.userid,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return _assignment_dict(assignment)


@router.delete("/file-watches/assignments/{assignment_id}")
async def delete_assignment(
    assignment_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, str]:
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    assignment = (
        db.query(models.FileWatchAssignment)
        .filter(
            models.FileWatchAssignment.id
            == _as_uuid(assignment_id, _("Invalid assignment ID format"))
        )
        .first()
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail=_("Assignment not found"))
    db.delete(assignment)
    db.commit()
    return {"status": "deleted"}
