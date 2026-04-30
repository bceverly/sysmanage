"""
Report branding API (Phase 8.7).

Singleton-row management for the org logo + header text that the Pro+
``reporting_engine`` injects into every generated PDF/HTML.

  GET  /api/report-branding              read singleton (no logo bytes)
  PUT  /api/report-branding              update name / header (and optionally clear logo)
  POST /api/report-branding/logo         upload logo (multipart)
  GET  /api/report-branding/logo         stream logo bytes (used by frontend preview + Pro+ renderer)
  DELETE /api/report-branding/logo       remove logo
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.persistence.models.report_branding import SINGLETON_BRANDING_ID
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/report-branding",
    tags=["report-branding"],
    dependencies=[Depends(JWTBearer())],
)


# Hard cap so a malicious user can't fill the row with a 50 MB logo
# and DoS the renderer.  1 MB is plenty for a PDF header.
_MAX_LOGO_BYTES = 1 * 1024 * 1024
_ALLOWED_MIME_PREFIXES = ("image/png", "image/jpeg", "image/svg+xml", "image/webp")


class BrandingUpdateRequest(BaseModel):
    company_name: Optional[str] = Field(None, max_length=255)
    header_text: Optional[str] = Field(None, max_length=500)


class BrandingResponse(BaseModel):
    company_name: Optional[str] = None
    header_text: Optional[str] = None
    has_logo: bool
    logo_mime_type: Optional[str] = None
    updated_at: Optional[str] = None


def _get_user(db: Session, current_user: str) -> models.User:
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_("User not found"))
    return user


def _get_or_create_branding(db: Session) -> models.ReportBranding:
    """Return the singleton row, creating it on first read.

    The singleton id is fixed (``SINGLETON_BRANDING_ID``) so we never
    end up with two rows even under concurrent first-access.  The
    DB-side primary-key constraint enforces it."""
    row = (
        db.query(models.ReportBranding)
        .filter(models.ReportBranding.id == SINGLETON_BRANDING_ID)
        .first()
    )
    if row is None:
        row = models.ReportBranding(id=SINGLETON_BRANDING_ID)
        db.add(row)
        db.flush()
    return row


@router.get("", response_model=BrandingResponse)
async def get_branding(db: Session = Depends(get_db)):
    """Return current branding (without logo bytes)."""
    row = _get_or_create_branding(db)
    return BrandingResponse(**row.to_dict())


@router.put("", response_model=BrandingResponse)
async def update_branding(
    request: BrandingUpdateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Update company name / header text.  Logo is managed via the
    separate ``/logo`` endpoints because multipart bodies don't mix
    well with JSON request bodies."""
    user = _get_user(db, current_user)
    row = _get_or_create_branding(db)
    if request.company_name is not None:
        row.company_name = request.company_name.strip() or None
    if request.header_text is not None:
        row.header_text = request.header_text.strip() or None
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    row.updated_by = user.id
    db.commit()
    db.refresh(row)

    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_id=str(row.id),
        entity_name="report_branding",
        description=_("Updated report branding"),
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return BrandingResponse(**row.to_dict())


@router.post("/logo", response_model=BrandingResponse)
async def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Upload (or replace) the org logo."""
    user = _get_user(db, current_user)

    if not file:
        raise HTTPException(status_code=400, detail=_("No file provided"))

    mime = (file.content_type or "").lower()
    if not any(mime.startswith(p) for p in _ALLOWED_MIME_PREFIXES):
        raise HTTPException(
            status_code=400,
            detail=_("Unsupported logo format (allowed: PNG, JPEG, SVG, WEBP)"),
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail=_("Empty file"))
    if len(contents) > _MAX_LOGO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=_("Logo too large; max 1 MB"),
        )

    row = _get_or_create_branding(db)
    row.logo_data = contents
    row.logo_mime_type = mime
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    row.updated_by = user.id
    db.commit()
    db.refresh(row)

    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_id=str(row.id),
        entity_name="report_branding_logo",
        description=_("Uploaded report branding logo (%d bytes, %s)")
        % (len(contents), mime),
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return BrandingResponse(**row.to_dict())


@router.get("/logo")
async def get_logo(db: Session = Depends(get_db)):
    """Stream the logo bytes.  Used by the frontend preview AND by the
    Pro+ reporting engine to embed the logo in PDFs/HTML."""
    row = (
        db.query(models.ReportBranding)
        .filter(models.ReportBranding.id == SINGLETON_BRANDING_ID)
        .first()
    )
    if not row or not row.logo_data:
        raise HTTPException(status_code=404, detail=_("No logo configured"))
    return Response(
        content=bytes(row.logo_data),
        media_type=row.logo_mime_type or "application/octet-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.delete("/logo", response_model=BrandingResponse)
async def delete_logo(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Remove the configured logo."""
    user = _get_user(db, current_user)
    row = _get_or_create_branding(db)
    row.logo_data = None
    row.logo_mime_type = None
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    row.updated_by = user.id
    db.commit()
    db.refresh(row)

    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_id=str(row.id),
        entity_name="report_branding_logo",
        description=_("Removed report branding logo"),
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return BrandingResponse(**row.to_dict())
