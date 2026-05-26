"""
Air-gap collector one-shot runs API (Phase 11).

Companion to ``airgap_collection_schedule.py`` (which handles cron-driven
recurring runs).  This module exposes the surface the operator UI needs:
create a one-shot collection run, list / inspect prior runs, fetch the
produced media manifests, and stream the signed ISO back to the browser.

Routes are gated on ``airgap_collector_engine`` being loaded — the engine
being available is the Pro+ + role-collector check.  The actual run
processing (mirroring, ISO build, signing) is handled by the engine's
background worker; this module only manages the row lifecycle and serves
the artifact.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db
from backend.services.audit_service import (
    ActionType,
    AuditService,
    EntityType,
    Result,
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/v1/airgap/collector",
    tags=["airgap-collector-runs"],
    dependencies=[Depends(JWTBearer())],
)


_ERR_RUN_NOT_FOUND = "Air-gap collection run not found"
_ERR_MANIFEST_NOT_FOUND = "Air-gap media manifest not found"
_ERR_INVALID_RUN_UUID = "Invalid UUID for run_id: %s"
_ERR_INVALID_MANIFEST_UUID = "Invalid UUID for manifest_id: %s"


def _check_collector_module():
    engine = module_loader.get_module("airgap_collector_engine")
    if engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Air-gap collection runs require a SysManage Professional+ "
                "license with the air-gap collector engine. Please upgrade to "
                "access this feature."
            ),
        )
    return engine


def _get_user(db: Session, current_user: str) -> models.User:
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_("User not found"))
    return user


def _parse_run_uuid(run_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_(_ERR_INVALID_RUN_UUID) % run_id,
        ) from exc


def _parse_manifest_uuid(manifest_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(manifest_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_(_ERR_INVALID_MANIFEST_UUID) % manifest_id,
        ) from exc


class RunCreateRequest(BaseModel):
    iso_label: str = Field(..., min_length=1, max_length=80)
    # 4.7 GB DVD-5 default — the engine's media-size ceiling for the
    # single-disc happy path.  Operators can drop to CD-700M or jump
    # to BD-25 by passing this explicitly.
    media_size_bytes: int = Field(default=4_700_000_000, gt=0)
    include_cve: bool = True
    include_compliance: bool = True


class RunResponse(BaseModel):
    id: str
    iso_label: str
    media_size_bytes: int
    include_cve: bool
    include_compliance: bool
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    cron_schedule: Optional[str] = None
    parent_run_id: Optional[str] = None
    created_at: Optional[str] = None


class ManifestResponse(BaseModel):
    id: str
    disc_index: int
    disc_count: int
    iso_path: str
    iso_sha256: str
    iso_size_bytes: int
    signer_fingerprint: str
    signature_algorithm: str
    format_version: int
    created_at: Optional[str] = None


@router.post("/runs", response_model=RunResponse)
async def create_run(
    request: RunCreateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Create a one-shot collection run.

    ``cron_schedule`` is left NULL — recurring runs go through
    ``airgap_collection_schedule.py``'s tick mechanism; this endpoint
    is strictly for ad-hoc UI-triggered runs.  The background worker
    picks the row up from ``status='QUEUED'`` and drives it through
    the lifecycle.
    """
    _check_collector_module()
    user = _get_user(db, current_user)
    run = models.AirgapCollectionRun(
        iso_label=request.iso_label,
        media_size_bytes=request.media_size_bytes,
        include_cve=request.include_cve,
        include_compliance=request.include_compliance,
        status="QUEUED",
        cron_schedule=None,
        created_by=user.id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    AuditService.log(
        db=db,
        action_type=ActionType.CREATE,
        entity_type=EntityType.SETTING,
        entity_id=str(run.id),
        entity_name=run.iso_label,
        description=_("Created one-shot air-gap collection run '%s'") % run.iso_label,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return RunResponse(**run.to_dict())


@router.get("/runs", response_model=List[RunResponse])
async def list_runs(db: Session = Depends(get_db)):
    _check_collector_module()
    rows = (
        db.query(models.AirgapCollectionRun)
        .order_by(models.AirgapCollectionRun.created_at.desc())
        .all()
    )
    return [RunResponse(**r.to_dict()) for r in rows]


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, db: Session = Depends(get_db)):
    _check_collector_module()
    rid = _parse_run_uuid(run_id)
    run = (
        db.query(models.AirgapCollectionRun)
        .filter(models.AirgapCollectionRun.id == rid)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail=_(_ERR_RUN_NOT_FOUND))
    return RunResponse(**run.to_dict())


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    _check_collector_module()
    user = _get_user(db, current_user)
    rid = _parse_run_uuid(run_id)
    run = (
        db.query(models.AirgapCollectionRun)
        .filter(models.AirgapCollectionRun.id == rid)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail=_(_ERR_RUN_NOT_FOUND))
    label = run.iso_label
    # Cascade handles targets + manifests rows; the ISO file on disk
    # is the engine's responsibility to clean up out of band.
    db.delete(run)
    db.commit()
    AuditService.log(
        db=db,
        action_type=ActionType.DELETE,
        entity_type=EntityType.SETTING,
        entity_id=str(rid),
        entity_name=label,
        description=_("Deleted air-gap collection run '%s'") % label,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return None


@router.get("/runs/{run_id}/manifests", response_model=List[ManifestResponse])
async def list_manifests(run_id: str, db: Session = Depends(get_db)):
    _check_collector_module()
    rid = _parse_run_uuid(run_id)
    run = (
        db.query(models.AirgapCollectionRun)
        .filter(models.AirgapCollectionRun.id == rid)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail=_(_ERR_RUN_NOT_FOUND))
    manifests = (
        db.query(models.AirgapMediaManifest)
        .filter(models.AirgapMediaManifest.run_id == rid)
        .order_by(models.AirgapMediaManifest.disc_index)
        .all()
    )
    return [
        ManifestResponse(
            id=str(m.id),
            disc_index=m.disc_index,
            disc_count=m.disc_count,
            iso_path=m.iso_path,
            iso_sha256=m.iso_sha256,
            iso_size_bytes=m.iso_size_bytes,
            signer_fingerprint=m.signer_fingerprint,
            signature_algorithm=m.signature_algorithm,
            format_version=m.format_version,
            created_at=m.created_at.isoformat() if m.created_at else None,
        )
        for m in manifests
    ]


@router.get("/manifests/{manifest_id}/download")
async def download_manifest_iso(
    manifest_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),  # noqa: ARG001
):
    """Stream the signed ISO referenced by ``manifest.iso_path``.

    The endpoint is wired here (rather than on the manifest's own
    sub-resource) so it cleanly maps to "one ISO per manifest row" —
    multi-disc runs produce N manifest rows and the UI can hit this
    endpoint once per row to pull each disc.
    """
    _check_collector_module()
    mid = _parse_manifest_uuid(manifest_id)
    manifest = (
        db.query(models.AirgapMediaManifest)
        .filter(models.AirgapMediaManifest.id == mid)
        .first()
    )
    if not manifest:
        raise HTTPException(status_code=404, detail=_(_ERR_MANIFEST_NOT_FOUND))
    run = (
        db.query(models.AirgapCollectionRun)
        .filter(models.AirgapCollectionRun.id == manifest.run_id)
        .first()
    )
    if run is None or run.status != "COMPLETE":
        raise HTTPException(
            status_code=409,
            detail=_("Run is not COMPLETE yet (status: %s)")
            % (run.status if run else "UNKNOWN"),
        )
    if not manifest.iso_path or not os.path.isfile(manifest.iso_path):
        raise HTTPException(
            status_code=410,
            detail=_("ISO file is no longer on disk: %s") % (manifest.iso_path or ""),
        )
    return FileResponse(
        manifest.iso_path,
        media_type="application/octet-stream",
        filename=os.path.basename(manifest.iso_path),
    )
