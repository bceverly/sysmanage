"""
Air-gap install bundle API.

Mounts under ``/api/airgap-bundles``.  Lets an admin trigger a build
(returns immediately with a job id), poll status, list past bundles,
download the resulting ISO, and delete bundles when no longer needed.

All endpoints require an authenticated user with the
``MANAGE_AIRGAP_BUNDLES`` role.  The config-admin recovery account is
allowed through for bootstrap.
"""

import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config import config
from backend.i18n import _
from backend.licensing.feature_gate import requires_pro_plus
from backend.persistence import db, models
from backend.services import airgap_bundle_builder
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.api.airgap_bundles")

router = APIRouter(
    prefix="/airgap-bundles",
    tags=["airgap-bundles"],
    dependencies=[Depends(JWTBearer())],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class BundleCreateRequest(BaseModel):
    product: str  # "server" or "agent"


class BundleResponse(BaseModel):
    id: str
    product: str
    status: str
    created_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    size_bytes: Optional[int]
    error_message: Optional[str]


def _row_to_response(row: models.AirGapBundle) -> BundleResponse:
    return BundleResponse(
        id=str(row.id),
        product=row.product,
        status=row.status,
        created_at=row.created_at.isoformat() + "Z" if row.created_at else None,
        started_at=row.started_at.isoformat() + "Z" if row.started_at else None,
        completed_at=(row.completed_at.isoformat() + "Z" if row.completed_at else None),
        size_bytes=row.size_bytes,
        error_message=row.error_message,
    )


# ---------------------------------------------------------------------------
# Authorization helper
# ---------------------------------------------------------------------------


def _resolve_caller_user_id(current_user: str) -> Optional[uuid.UUID]:
    """Return the calling user's User.id, or None for the config-admin.

    Allows the config-admin recovery account to trigger bundles (the
    initial bootstrap path) without needing a DB row.  Real users get
    their id stamped on the audit trail.
    """
    the_config = config.get_config()
    admin_userid = the_config.get("security", {}).get("admin_userid")
    if admin_userid and current_user == admin_userid:
        return None
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with SessionLocal() as session:
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        return user.id if user else None


# ---------------------------------------------------------------------------
# POST /airgap-bundles — start a build
# ---------------------------------------------------------------------------


@router.post("", response_model=BundleResponse, status_code=202)
@requires_pro_plus()
async def create_bundle(
    req: BundleCreateRequest, current_user: str = Depends(get_current_user)
) -> BundleResponse:
    if req.product not in models.BUNDLE_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=_("product must be one of: ") + ", ".join(models.BUNDLE_PRODUCTS),
        )

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with SessionLocal() as session:
        row = models.AirGapBundle(
            product=req.product,
            status=models.BUNDLE_STATUS_QUEUED,
            created_by_user_id=_resolve_caller_user_id(current_user),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        bundle_id = row.id
        response = _row_to_response(row)

    airgap_bundle_builder.start_build(bundle_id, req.product)
    logger.info(
        "airgap_bundle %s queued (product=%s, by=%s)",
        bundle_id,
        req.product,
        current_user,
    )
    return response


# ---------------------------------------------------------------------------
# GET /airgap-bundles — list (newest first)
# ---------------------------------------------------------------------------


@router.get("", response_model=List[BundleResponse])
@requires_pro_plus()
async def list_bundles(
    current_user: str = Depends(get_current_user),  # noqa: ARG001
) -> List[BundleResponse]:
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with SessionLocal() as session:
        rows = (
            session.query(models.AirGapBundle)
            .order_by(models.AirGapBundle.created_at.desc())
            .all()
        )
        return [_row_to_response(r) for r in rows]


# ---------------------------------------------------------------------------
# GET /airgap-bundles/{id} — one bundle's status
# ---------------------------------------------------------------------------


@router.get("/{bundle_id}", response_model=BundleResponse)
@requires_pro_plus()
async def get_bundle(
    bundle_id: uuid.UUID,
    current_user: str = Depends(get_current_user),  # noqa: ARG001
) -> BundleResponse:
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with SessionLocal() as session:
        row = (
            session.query(models.AirGapBundle)
            .filter(models.AirGapBundle.id == bundle_id)
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail=_("Bundle not found"))
        return _row_to_response(row)


# ---------------------------------------------------------------------------
# GET /airgap-bundles/{id}/download — stream the ISO
# ---------------------------------------------------------------------------


@router.get("/{bundle_id}/download")
@requires_pro_plus()
async def download_bundle(
    bundle_id: uuid.UUID,
    current_user: str = Depends(get_current_user),  # noqa: ARG001
):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with SessionLocal() as session:
        row = (
            session.query(models.AirGapBundle)
            .filter(models.AirGapBundle.id == bundle_id)
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail=_("Bundle not found"))
        if row.status != models.BUNDLE_STATUS_READY:
            raise HTTPException(
                status_code=409,
                detail=_("Bundle is not ready yet (status: %s)") % row.status,
            )
        if not row.file_path or not os.path.isfile(row.file_path):
            raise HTTPException(
                status_code=410, detail=_("Bundle file is no longer on disk")
            )
        return FileResponse(
            row.file_path,
            media_type="application/octet-stream",
            filename=os.path.basename(row.file_path),
        )


# ---------------------------------------------------------------------------
# DELETE /airgap-bundles/{id} — remove file + row
# ---------------------------------------------------------------------------


@router.delete("/{bundle_id}", status_code=204)
@requires_pro_plus()
async def delete_bundle(
    bundle_id: uuid.UUID,
    current_user: str = Depends(get_current_user),  # noqa: ARG001
):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())
    with SessionLocal() as session:
        row = (
            session.query(models.AirGapBundle)
            .filter(models.AirGapBundle.id == bundle_id)
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail=_("Bundle not found"))
        # Remove on-disk artifact + log (best effort).
        for path_attr in ("file_path", "log_path"):
            p = getattr(row, path_attr, None)
            if p and os.path.isfile(p):
                try:
                    os.unlink(p)
                except OSError as exc:
                    logger.warning("couldn't unlink %s: %s", p, exc)
        session.delete(row)
        session.commit()
