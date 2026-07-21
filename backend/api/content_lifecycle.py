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
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.models.content_lifecycle import (
    CVV_PUBLISHED,
    CVV_PUBLISHING,
    DEFAULT_KEEP_VERSIONS,
    MAX_KEEP_VERSIONS,
)
from backend.persistence.partitions import get_shared_db, get_tenant_db

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
    """List the content views (with a lightweight version summary each)."""
    _check_clm_module()
    rows = (
        db.query(models.SharedContentView).order_by(models.SharedContentView.name).all()
    )
    return [_cv_summary_dict(cv) for cv in rows]


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


# =============================================================================
# Content Views — CRUD (Phase 16, Slice 2)
#
# A content view is a named selection of repository mirrors (SHARED partition).
# ``repos`` are soft refs to tenant ``mirror_repository`` rows (mirror_id) or,
# for a composite CV, intra-shared refs to component CVs. Membership is replaced
# wholesale on update. Publishing a CV (materialize -> immutable version) is
# handled in the publish section below.
# =============================================================================


class ContentViewRepoIn(BaseModel):
    mirror_id: Optional[str] = None
    component_content_view_id: Optional[str] = None
    position: int = 0


class ContentViewCreate(BaseModel):
    name: str
    description: Optional[str] = None
    composite: bool = False
    keep_versions: int = DEFAULT_KEEP_VERSIONS
    repos: List[ContentViewRepoIn] = []


class ContentViewUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    keep_versions: Optional[int] = None
    repos: Optional[List[ContentViewRepoIn]] = None


def _norm_cv_name(name: Optional[str]) -> str:
    normalized = (name or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=_("Content view name is required"))
    if len(normalized) > 120:
        raise HTTPException(status_code=400, detail=_("Content view name is too long"))
    return normalized


def _clamp_keep_versions(value: Optional[int]) -> int:
    """Retention override, clamped to [1, MAX_KEEP_VERSIONS] (design doc §8)."""
    if value is None:
        return DEFAULT_KEEP_VERSIONS
    return max(1, min(int(value), MAX_KEEP_VERSIONS))


def _get_cv_or_404(db: Session, cv_id: str):
    cv = (
        db.query(models.SharedContentView)
        .filter(models.SharedContentView.id == cv_id)
        .first()
    )
    if cv is None:
        raise HTTPException(status_code=404, detail=_("Content view not found"))
    return cv


def _cv_repo_rows(cv, body_repos: List[ContentViewRepoIn]):
    """Build SharedContentViewRepo rows from the request; reject empty members."""
    rows = []
    for idx, member in enumerate(body_repos):
        if not member.mirror_id and not member.component_content_view_id:
            raise HTTPException(
                status_code=400,
                detail=_("Each content-view member needs a mirror or component CV"),
            )
        rows.append(
            models.SharedContentViewRepo(
                content_view_id=cv.id,
                mirror_id=member.mirror_id,
                component_content_view_id=member.component_content_view_id,
                position=member.position if member.position else idx,
            )
        )
    return rows


def _cv_repos_list(cv) -> list:
    return [
        {
            "id": str(m.id),
            "mirror_id": str(m.mirror_id) if m.mirror_id else None,
            "component_content_view_id": (
                str(m.component_content_view_id)
                if m.component_content_view_id
                else None
            ),
            "position": m.position,
        }
        for m in sorted(cv.repos, key=lambda m: m.position)
    ]


def _cv_summary_dict(cv) -> dict:
    """List-view shape: base fields + counts + latest published version."""
    published = [v for v in cv.versions if v.status == CVV_PUBLISHED]
    latest = max((v.version for v in published), default=None)
    data = cv.to_dict()
    data["repo_count"] = len(cv.repos)
    data["version_count"] = len(cv.versions)
    data["latest_published_version"] = latest
    return data


def _cv_detail_dict(cv) -> dict:
    """Detail-view shape: base + membership + full version history."""
    data = cv.to_dict()
    data["repos"] = _cv_repos_list(cv)
    data["versions"] = [
        v.to_dict() for v in sorted(cv.versions, key=lambda v: v.version, reverse=True)
    ]
    return data


@router.post("/content-lifecycle/content-views", dependencies=[Depends(JWTBearer())])
async def create_content_view(
    body: ContentViewCreate, db: Session = Depends(get_shared_db)
):
    """Create a content view (a named selection of repository mirrors)."""
    _check_clm_module()
    name = _norm_cv_name(body.name)
    if (
        db.query(models.SharedContentView)
        .filter(models.SharedContentView.name == name)
        .first()
        is not None
    ):
        raise HTTPException(
            status_code=409, detail=_("A content view with that name already exists")
        )
    cv = models.SharedContentView(
        name=name,
        description=body.description,
        composite=bool(body.composite),
        keep_versions=_clamp_keep_versions(body.keep_versions),
    )
    db.add(cv)
    db.flush()  # assign cv.id before building the membership rows
    for row in _cv_repo_rows(cv, body.repos):
        db.add(row)
    db.commit()
    db.refresh(cv)
    return _cv_detail_dict(cv)


@router.get(
    "/content-lifecycle/content-views/{cv_id}", dependencies=[Depends(JWTBearer())]
)
async def get_content_view(cv_id: str, db: Session = Depends(get_shared_db)):
    """Content-view detail: membership + published-version history."""
    _check_clm_module()
    return _cv_detail_dict(_get_cv_or_404(db, cv_id))


@router.put(
    "/content-lifecycle/content-views/{cv_id}", dependencies=[Depends(JWTBearer())]
)
async def update_content_view(
    cv_id: str, body: ContentViewUpdate, db: Session = Depends(get_shared_db)
):
    """Update a content view. ``repos``, when provided, replaces membership."""
    _check_clm_module()
    cv = _get_cv_or_404(db, cv_id)
    if body.name is not None:
        name = _norm_cv_name(body.name)
        clash = (
            db.query(models.SharedContentView)
            .filter(models.SharedContentView.name == name)
            .filter(models.SharedContentView.id != cv.id)
            .first()
        )
        if clash is not None:
            raise HTTPException(
                status_code=409,
                detail=_("A content view with that name already exists"),
            )
        cv.name = name
    if body.description is not None:
        cv.description = body.description
    if body.keep_versions is not None:
        cv.keep_versions = _clamp_keep_versions(body.keep_versions)
    if body.repos is not None:
        for existing in list(cv.repos):
            db.delete(existing)
        db.flush()
        for row in _cv_repo_rows(cv, body.repos):
            db.add(row)
    db.commit()
    db.refresh(cv)
    return _cv_detail_dict(cv)


@router.delete(
    "/content-lifecycle/content-views/{cv_id}", dependencies=[Depends(JWTBearer())]
)
async def delete_content_view(cv_id: str, db: Session = Depends(get_shared_db)):
    """Delete a content view (cascades to its members, filters, and versions)."""
    _check_clm_module()
    cv = _get_cv_or_404(db, cv_id)
    deleted_id = str(cv.id)
    db.delete(cv)
    db.commit()
    return {"deleted": True, "id": deleted_id}


# =============================================================================
# Publish (Phase 16, Slice 2) — the immutability core.
#
# Publishing snapshots the CV's mirrors into an immutable, physically-
# materialized version on the mirror host, via an async agent plan (the engine
# supplies the plan-builder; the agent runs it; a result handler stamps the
# version published/failed).  Filters are pass-through here (full content); S3
# inserts the filter step into the same materialize job.
#
# Release constraint (single-mirror-host, per the design doc): every mirror in a
# content view must live on the same host; we merge each mirror's materialize
# commands into ONE plan dispatched to that host, tracked by one version row.
# =============================================================================


def _resolve_cv_publish_targets(cv, tenant_db: Session):
    """Resolve a CV's members to (host_id, mirror_root, [(mirror_config, snap)]).

    Enforces the S2 constraints loudly (never a silent skip): not composite,
    has publishable mirrors, all on one host, each with an existing snapshot.
    """
    if cv.composite:
        raise HTTPException(
            status_code=400,
            detail=_("Composite content views cannot be published yet"),
        )
    members = [m for m in cv.repos if m.mirror_id]
    if not members:
        raise HTTPException(
            status_code=400, detail=_("Content view has no repositories to publish")
        )
    settings = tenant_db.query(models.MirrorSettings).first()
    if settings is None:
        raise HTTPException(
            status_code=400, detail=_("Mirror settings are not configured")
        )

    host_id = None
    targets = []
    for member in sorted(members, key=lambda m: m.position):
        mirror = (
            tenant_db.query(models.MirrorRepository)
            .filter(models.MirrorRepository.id == member.mirror_id)
            .first()
        )
        if mirror is None:
            raise HTTPException(
                status_code=400, detail=_("A referenced mirror no longer exists")
            )
        if mirror.host_id is None:
            raise HTTPException(
                status_code=400,
                detail=_("Mirror '%s' has no host assigned") % mirror.name,
            )
        if host_id is None:
            host_id = mirror.host_id
        elif str(mirror.host_id) != str(host_id):
            raise HTTPException(
                status_code=400,
                detail=_(
                    "All mirrors in a content view must share one host in this release"
                ),
            )
        snapshot = (
            tenant_db.query(models.MirrorSnapshot)
            .filter(models.MirrorSnapshot.repository_id == mirror.id)
            .order_by(models.MirrorSnapshot.taken_at.desc())
            .first()
        )
        if snapshot is None:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Mirror '%s' has no snapshot yet; snapshot it before publishing"
                )
                % mirror.name,
            )
        targets.append(
            (
                {"name": mirror.name, "package_manager": mirror.package_manager},
                snapshot.snapshot_id,
            )
        )
    return host_id, settings.mirror_root_path, targets


def _dispatch_publish_plan(plan: dict, host_id, cv_version_id: str) -> str:
    """Enqueue the combined materialize plan and register the result correlation
    so the agent's command_result lands back on this version row."""
    from backend.services.proplus_dispatch import (
        enqueue_apply_plan,
        register_content_lifecycle_correlation,
    )

    # Large mirror trees take a while to rsync + regen metadata; give it room.
    msg_id = enqueue_apply_plan(host_id=str(host_id), plan=plan, timeout=7200)
    register_content_lifecycle_correlation(
        msg_id, "publish_materialize", str(host_id), str(cv_version_id)
    )
    return msg_id


@router.post(
    "/content-lifecycle/content-views/{cv_id}/publish",
    dependencies=[Depends(JWTBearer())],
)
async def publish_content_view(
    cv_id: str,
    shared_db: Session = Depends(get_shared_db),
    tenant_db: Session = Depends(get_tenant_db),
):
    """Publish an immutable version of a content view (async materialize job).

    Returns the new version at status ``publishing``; the result handler flips
    it to ``published`` / ``failed`` when the mirror host finishes the plan.
    """
    engine = _check_clm_module()
    cv = _get_cv_or_404(shared_db, cv_id)
    host_id, mirror_root, targets = _resolve_cv_publish_targets(cv, tenant_db)

    next_version = 1 + max((v.version for v in cv.versions), default=0)
    cvv = models.SharedContentViewVersion(
        content_view_id=cv.id, version=next_version, status=CVV_PUBLISHING
    )
    shared_db.add(cvv)
    shared_db.flush()  # assign cvv.id before dispatch/correlation

    # Merge each mirror's per-mirror materialize commands into ONE host plan.
    commands: List[dict] = []
    store_parent = None
    for mirror_config, snapshot_id in targets:
        plan = engine.build_publish_materialize_plan(
            mirror_config, mirror_root, snapshot_id, str(cv.id), next_version
        )
        commands.extend(plan.get("commands", []))
        if store_parent is None:
            store_parent = os.path.dirname(plan.get("store_path", "")) or None

    combined_plan = {
        "engine": "content_lifecycle_engine",
        "action": "publish_materialize",
        "cv_id": str(cv.id),
        "version": next_version,
        "commands": commands,
    }
    cvv.store_path = store_parent
    _dispatch_publish_plan(combined_plan, host_id, str(cvv.id))
    shared_db.commit()
    shared_db.refresh(cvv)
    return cvv.to_dict()


@router.get(
    "/content-lifecycle/content-views/{cv_id}/versions",
    dependencies=[Depends(JWTBearer())],
)
async def list_content_view_versions(cv_id: str, db: Session = Depends(get_shared_db)):
    """List a content view's versions, newest first (drives the version history
    + the in-flight publish spinner)."""
    _check_clm_module()
    cv = _get_cv_or_404(db, cv_id)
    return [
        v.to_dict() for v in sorted(cv.versions, key=lambda v: v.version, reverse=True)
    ]
