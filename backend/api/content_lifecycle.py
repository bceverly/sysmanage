# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Content Lifecycle Management API (Phase 16, Enterprise).

Satellite-style content views + lifecycle environments + gated promotion.  Like
repository mirroring, the OSS layer owns the API and the content lives on the
mirror-hosting agents; the Enterprise ``content_lifecycle_engine`` supplies the
plan-builders (materialize / serve / repoint).  When that engine isn't loaded
EVERY endpoint returns a clean HTTP 402 (never a 500) so the frontend can render
a license-upgrade prompt.

Slice 0 exposes read-only stubs (list environments / content views) — enough to
prove the gate and drive the plugin shell.  CRUD, publish, and promotion arrive
in later slices.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import get_shared_db

logger = logging.getLogger(__name__)
router = APIRouter()


def _check_clm_module():
    """402 unless the Enterprise ``content_lifecycle_engine`` is loaded."""
    engine = module_loader.get_module("content_lifecycle_engine")
    if engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Content lifecycle management requires a SysManage Professional+ "
                "(Enterprise) license. Please upgrade to access this feature."
            ),
        )
    return engine


@router.get("/content-lifecycle/environments", dependencies=[Depends(JWTBearer())])
async def list_environments(db: Session = Depends(get_shared_db)):
    """List the lifecycle environments along the ordered path."""
    _check_clm_module()
    rows = (
        db.query(models.SharedLifecycleEnvironment)
        .order_by(models.SharedLifecycleEnvironment.position)
        .all()
    )
    return [r.to_dict() for r in rows]


@router.get("/content-lifecycle/content-views", dependencies=[Depends(JWTBearer())])
async def list_content_views(db: Session = Depends(get_shared_db)):
    """List the content views."""
    _check_clm_module()
    rows = (
        db.query(models.SharedContentView).order_by(models.SharedContentView.name).all()
    )
    return [r.to_dict() for r in rows]


# =============================================================================
# Lifecycle Environments — CRUD (Phase 16, Slice 1)
#
# Environments are the ordered promotion path (Library -> Dev -> Test -> Prod).
# They are platform truth (SHARED partition).  The Library is the path root /
# publish target: the very first environment created becomes the Library, it is
# always position 0, and it cannot be deleted.  Content bindings don't exist yet
# (promotion is Slice 4), so delete/reorder only guard the Library invariant.
# =============================================================================


class EnvironmentCreate(BaseModel):
    name: str
    description: Optional[str] = None


class EnvironmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class EnvironmentReorder(BaseModel):
    ordered_ids: List[str]


def _norm_name(name: Optional[str]) -> str:
    normalized = (name or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=_("Environment name is required"))
    if len(normalized) > 120:
        raise HTTPException(status_code=400, detail=_("Environment name is too long"))
    return normalized


def _get_env_or_404(db: Session, env_id: str):
    env = (
        db.query(models.SharedLifecycleEnvironment)
        .filter(models.SharedLifecycleEnvironment.id == env_id)
        .first()
    )
    if env is None:
        raise HTTPException(status_code=404, detail=_("Environment not found"))
    return env


@router.post("/content-lifecycle/environments", dependencies=[Depends(JWTBearer())])
async def create_environment(
    body: EnvironmentCreate, db: Session = Depends(get_shared_db)
):
    """Create an environment (appended to the path; the very first one becomes
    the Library — the publish target / path root)."""
    _check_clm_module()
    name = _norm_name(body.name)
    existing = db.query(models.SharedLifecycleEnvironment).all()
    if any(e.name == name for e in existing):
        raise HTTPException(
            status_code=409, detail=_("An environment with that name already exists")
        )
    is_first = len(existing) == 0
    env = models.SharedLifecycleEnvironment(
        name=name,
        description=body.description,
        is_library=is_first,
        position=0 if is_first else (max(e.position for e in existing) + 1),
    )
    db.add(env)
    db.commit()
    db.refresh(env)
    return env.to_dict()


@router.put(
    "/content-lifecycle/environments/{env_id}", dependencies=[Depends(JWTBearer())]
)
async def update_environment(
    env_id: str, body: EnvironmentUpdate, db: Session = Depends(get_shared_db)
):
    """Rename / re-describe an environment (position changes via reorder)."""
    _check_clm_module()
    env = _get_env_or_404(db, env_id)
    if body.name is not None:
        name = _norm_name(body.name)
        clash = (
            db.query(models.SharedLifecycleEnvironment)
            .filter(models.SharedLifecycleEnvironment.name == name)
            .filter(models.SharedLifecycleEnvironment.id != env.id)
            .first()
        )
        if clash is not None:
            raise HTTPException(
                status_code=409,
                detail=_("An environment with that name already exists"),
            )
        env.name = name
    if body.description is not None:
        env.description = body.description
    db.commit()
    db.refresh(env)
    return env.to_dict()


@router.delete(
    "/content-lifecycle/environments/{env_id}", dependencies=[Depends(JWTBearer())]
)
async def delete_environment(env_id: str, db: Session = Depends(get_shared_db)):
    """Delete an environment. The Library (path root) cannot be deleted."""
    _check_clm_module()
    env = _get_env_or_404(db, env_id)
    if env.is_library:
        raise HTTPException(
            status_code=400, detail=_("The Library environment cannot be deleted")
        )
    deleted_id = str(env.id)
    db.delete(env)
    db.commit()
    return {"deleted": True, "id": deleted_id}


@router.post(
    "/content-lifecycle/environments/reorder", dependencies=[Depends(JWTBearer())]
)
async def reorder_environments(
    body: EnvironmentReorder, db: Session = Depends(get_shared_db)
):
    """Reassign the ordered path. ``ordered_ids`` must list every environment
    exactly once, and the Library must remain first (it is the path root)."""
    _check_clm_module()
    envs = db.query(models.SharedLifecycleEnvironment).all()
    by_id = {str(e.id): e for e in envs}
    if not envs or set(body.ordered_ids) != set(by_id.keys()):
        raise HTTPException(
            status_code=400,
            detail=_("ordered_ids must list every environment exactly once"),
        )
    if not by_id[body.ordered_ids[0]].is_library:
        raise HTTPException(
            status_code=400, detail=_("The Library environment must remain first")
        )
    # Two-phase so we never transiently collide on the UNIQUE(position) index:
    # park everything at high offsets, flush, then assign the final 0..n-1.
    for offset, eid in enumerate(body.ordered_ids):
        by_id[eid].position = 1000 + offset
    db.flush()
    for idx, eid in enumerate(body.ordered_ids):
        by_id[eid].position = idx
    db.commit()
    rows = (
        db.query(models.SharedLifecycleEnvironment)
        .order_by(models.SharedLifecycleEnvironment.position)
        .all()
    )
    return [r.to_dict() for r in rows]
