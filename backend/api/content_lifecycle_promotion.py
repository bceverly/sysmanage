# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Content Lifecycle Management — promotion + rollback API (Phase 16, Slice 4).

The content-lifecycle state machine.  Promotion rebinds an environment to a
published content-view version.  In this release an environment is served by a
SINGLE mirror host (design decision #1), so promote/rollback move NO bytes --
they are pure binding rebinds in the TENANT partition (the shared version store
already holds every version's bytes, pinned so a bound version is never
reclaimed).  Only forward promotion along the ordered path is allowed; rollback
rebinds to the immediately-prior version.

Split out of ``backend.api.content_lifecycle`` (which owns environment + content
-view CRUD + publish) to keep each module under the line-count cap; it reuses
that module's gate + lookup helpers and mounts on its own router.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.content_lifecycle import (
    _check_clm_module,
    _get_cv_or_404,
    _get_env_or_404,
)
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.models.content_lifecycle import (
    CVV_DEPRECATED,
    CVV_PUBLISHED,
    PROMOTION_PROMOTE,
    PROMOTION_ROLLBACK,
)
from backend.persistence.partitions import get_shared_db, get_tenant_db

router = APIRouter()


def _now_naive() -> datetime:
    """Naive-UTC now, matching the shared/tenant timestamp convention."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PromoteRequest(BaseModel):
    from_environment_id: str
    to_environment_id: str
    note: Optional[str] = None


class RollbackRequest(BaseModel):
    environment_id: str
    note: Optional[str] = None


def _binding_for(tenant_db: Session, env_id, cv_id):
    """The current env->CVV binding for one CV in one environment (or None)."""
    return (
        tenant_db.query(models.EnvironmentContentBinding)
        .filter(models.EnvironmentContentBinding.environment_id == env_id)
        .filter(models.EnvironmentContentBinding.content_view_id == cv_id)
        .first()
    )


def _published_cvv_or_400(shared_db: Session, cvv_id):
    """Resolve a version and require it be ``published`` (the promotion gate)."""
    cvv = (
        shared_db.query(models.SharedContentViewVersion)
        .filter(models.SharedContentViewVersion.id == cvv_id)
        .first()
    )
    if cvv is None or cvv.status != CVV_PUBLISHED:
        raise HTTPException(
            status_code=400,
            detail=_("Only a published content-view version can be promoted"),
        )
    return cvv


def _rebind_environment(tenant_db: Session, env_id, cv_id, new_cvv_id, actor):
    """Point env's binding at ``new_cvv_id``, preserving the displaced version as
    ``previous_version_id`` (enables instant rollback).  Upserts the binding."""
    binding = _binding_for(tenant_db, env_id, cv_id)
    if binding is None:
        binding = models.EnvironmentContentBinding(
            environment_id=env_id,
            content_view_id=cv_id,
            content_view_version_id=new_cvv_id,
            promoted_by=actor,
        )
        tenant_db.add(binding)
    else:
        if str(binding.content_view_version_id) != str(new_cvv_id):
            binding.previous_version_id = binding.content_view_version_id
        binding.content_view_version_id = new_cvv_id
        binding.promoted_by = actor
        binding.promoted_at = _now_naive()
    tenant_db.flush()
    return binding


def _write_promotion_audit(  # pylint: disable=too-many-arguments
    tenant_db: Session,
    cv_id,
    from_env_id,
    to_env_id,
    cvv_id,
    action: str,
    actor,
    note: Optional[str],
) -> None:
    """Append one row to the tenant promotion audit log."""
    tenant_db.add(
        models.ContentPromotionAudit(
            content_view_id=cv_id,
            from_environment_id=from_env_id,
            to_environment_id=to_env_id,
            content_view_version_id=cvv_id,
            action=action,
            actor=actor,
            note=note,
            at=_now_naive(),
        )
    )


def _binding_lane_entry(env, binding, versions: dict) -> dict:
    """One environment's lane entry: env metadata + its bound version (if any),
    enriched with the version number/status the UI needs."""
    entry = {
        "environment_id": str(env.id),
        "environment_name": env.name,
        "position": env.position,
        "is_library": env.is_library,
        "binding": None,
    }
    if binding is None:
        return entry
    cvv = versions.get(str(binding.content_view_version_id))
    prev = (
        versions.get(str(binding.previous_version_id))
        if binding.previous_version_id
        else None
    )
    entry["binding"] = {
        "id": str(binding.id),
        "content_view_version_id": str(binding.content_view_version_id),
        "version": cvv.version if cvv else None,
        "status": cvv.status if cvv else None,
        "previous_version_id": (
            str(binding.previous_version_id) if binding.previous_version_id else None
        ),
        "previous_version": prev.version if prev else None,
        "promoted_at": (
            binding.promoted_at.isoformat() if binding.promoted_at else None
        ),
    }
    return entry


@router.get(
    "/content-lifecycle/content-views/{cv_id}/bindings",
    dependencies=[Depends(JWTBearer())],
)
async def list_content_view_bindings(
    cv_id: str,
    shared_db: Session = Depends(get_shared_db),
    tenant_db: Session = Depends(get_tenant_db),
):
    """Per-environment view of which version a CV currently occupies — one entry
    per environment along the ordered path (drives the promotion lane UI)."""
    _check_clm_module()
    cv = _get_cv_or_404(shared_db, cv_id)
    envs = (
        shared_db.query(models.SharedLifecycleEnvironment)
        .order_by(models.SharedLifecycleEnvironment.position)
        .all()
    )
    bindings = {
        str(b.environment_id): b
        for b in tenant_db.query(models.EnvironmentContentBinding)
        .filter(models.EnvironmentContentBinding.content_view_id == cv.id)
        .all()
    }
    versions = {str(v.id): v for v in cv.versions}
    return [
        _binding_lane_entry(env, bindings.get(str(env.id)), versions) for env in envs
    ]


@router.post(
    "/content-lifecycle/content-views/{cv_id}/promote",
    dependencies=[Depends(JWTBearer())],
)
async def promote_content_view(
    cv_id: str,
    body: PromoteRequest,
    shared_db: Session = Depends(get_shared_db),
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Promote the version currently in ``from_environment`` into
    ``to_environment`` (forward-only along the path). Pure binding rebind — no
    bytes move — plus an audit row."""
    _check_clm_module()
    cv = _get_cv_or_404(shared_db, cv_id)
    from_env = _get_env_or_404(shared_db, body.from_environment_id)
    to_env = _get_env_or_404(shared_db, body.to_environment_id)
    if str(from_env.id) == str(to_env.id):
        raise HTTPException(
            status_code=400,
            detail=_("Source and target environments must differ"),
        )
    if to_env.position <= from_env.position:
        raise HTTPException(
            status_code=400,
            detail=_("Content can only be promoted forward along the lifecycle path"),
        )
    source = _binding_for(tenant_db, from_env.id, cv.id)
    if source is None:
        raise HTTPException(
            status_code=400,
            detail=_(
                "The source environment has no content for this content view to promote"
            ),
        )
    cvv = _published_cvv_or_400(shared_db, source.content_view_version_id)
    binding = _rebind_environment(tenant_db, to_env.id, cv.id, cvv.id, current_user.id)
    _write_promotion_audit(
        tenant_db,
        cv.id,
        from_env.id,
        to_env.id,
        cvv.id,
        PROMOTION_PROMOTE,
        current_user.id,
        body.note,
    )
    tenant_db.commit()
    tenant_db.refresh(binding)
    return binding.to_dict()


@router.post(
    "/content-lifecycle/content-views/{cv_id}/rollback",
    dependencies=[Depends(JWTBearer())],
)
async def rollback_environment(
    cv_id: str,
    body: RollbackRequest,
    shared_db: Session = Depends(get_shared_db),
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Roll an environment back to the version bound before its current one. The
    prior version's bytes are retained (pinned), so this is instant; the swap is
    reversible (the version rolled off becomes the new rollback target)."""
    _check_clm_module()
    cv = _get_cv_or_404(shared_db, cv_id)
    env = _get_env_or_404(shared_db, body.environment_id)
    binding = _binding_for(tenant_db, env.id, cv.id)
    if binding is None or binding.previous_version_id is None:
        raise HTTPException(
            status_code=400,
            detail=_("This environment has no previous version to roll back to"),
        )
    prev = (
        shared_db.query(models.SharedContentViewVersion)
        .filter(models.SharedContentViewVersion.id == binding.previous_version_id)
        .first()
    )
    if prev is None or prev.status == CVV_DEPRECATED or not prev.store_path:
        raise HTTPException(
            status_code=409,
            detail=_(
                "The previous version has been reclaimed and can no longer be restored"
            ),
        )
    binding.previous_version_id = binding.content_view_version_id
    binding.content_view_version_id = prev.id
    binding.promoted_by = current_user.id
    binding.promoted_at = _now_naive()
    _write_promotion_audit(
        tenant_db,
        cv.id,
        env.id,
        env.id,
        prev.id,
        PROMOTION_ROLLBACK,
        current_user.id,
        body.note,
    )
    tenant_db.commit()
    tenant_db.refresh(binding)
    return binding.to_dict()


@router.get(
    "/content-lifecycle/content-views/{cv_id}/audit",
    dependencies=[Depends(JWTBearer())],
)
async def list_content_view_audit(
    cv_id: str,
    shared_db: Session = Depends(get_shared_db),
    tenant_db: Session = Depends(get_tenant_db),
):
    """The append-only publish/promote/rollback history for a content view."""
    _check_clm_module()
    cv = _get_cv_or_404(shared_db, cv_id)
    rows = (
        tenant_db.query(models.ContentPromotionAudit)
        .filter(models.ContentPromotionAudit.content_view_id == cv.id)
        .order_by(models.ContentPromotionAudit.at.desc())
        .limit(200)
        .all()
    )
    return [r.to_dict() for r in rows]
