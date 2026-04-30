"""
Dynamic-secret leases API (Phase 8.7).

Operator-facing CRUD on short-lived OpenBAO-backed credentials.

  POST   /api/dynamic-secrets/issue                    issue a new lease
  GET    /api/dynamic-secrets/leases                   list leases (filter by status)
  GET    /api/dynamic-secrets/leases/{id}              get one lease
  POST   /api/dynamic-secrets/leases/{id}/revoke       revoke
  POST   /api/dynamic-secrets/reconcile                sweeper hook → mark expired
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.persistence.models.dynamic_secrets import (
    LEASE_KIND_DATABASE,
    LEASE_KIND_SSH,
    LEASE_KIND_TOKEN,
    LEASE_KINDS,
    LEASE_STATUSES,
)
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.services.dynamic_secrets import (
    DynamicSecretError,
    TTL_DEFAULT_SECONDS,
    TTL_MAX_SECONDS,
    TTL_MIN_SECONDS,
    issue_lease,
    reconcile_expired,
    revoke_lease,
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/dynamic-secrets",
    tags=["dynamic-secrets"],
    dependencies=[Depends(JWTBearer())],
)


class IssueRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    kind: str = Field(LEASE_KIND_TOKEN, description="One of: token, database, ssh")
    backend_role: str = Field(..., min_length=1, max_length=255)
    ttl_seconds: int = Field(
        TTL_DEFAULT_SECONDS, ge=TTL_MIN_SECONDS, le=TTL_MAX_SECONDS
    )
    note: Optional[str] = None


class IssueResponse(BaseModel):
    lease: Dict[str, Any]
    # Plaintext secret value — surfaced exactly ONCE in this response.
    secret: str


class LeaseResponse(BaseModel):
    id: str
    name: str
    kind: str
    backend_role: str
    vault_lease_id: Optional[str] = None
    ttl_seconds: Optional[int] = None
    issued_at: Optional[str] = None
    expires_at: Optional[str] = None
    revoked_at: Optional[str] = None
    status: str
    secret_metadata: Dict[str, Any] = {}
    note: Optional[str] = None


def _get_user(db: Session, current_user: str) -> models.User:
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_("User not found"))
    return user


def _parse_uuid_or_400(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid UUID for %s: %s") % (field, value),
        ) from exc


@router.post("/issue", response_model=IssueResponse)
async def issue(
    request: IssueRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Issue a new short-lived credential.  The plaintext secret is
    returned EXACTLY ONCE in this response;  the server never logs it
    and the DB never stores it.  Once the operator has it, only
    OpenBAO holds the value, and only until the TTL expires."""
    user = _get_user(db, current_user)
    if request.kind not in LEASE_KINDS:
        raise HTTPException(
            status_code=400,
            detail=_("Unknown kind: %s (allowed: %s)")
            % (request.kind, ", ".join(LEASE_KINDS)),
        )
    try:
        result = issue_lease(
            db,
            kind=request.kind,
            backend_role=request.backend_role,
            name=request.name,
            ttl_seconds=request.ttl_seconds,
            issued_by_user_id=user.id,
            note=request.note,
        )
    except DynamicSecretError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    AuditService.log(
        db=db,
        action_type=ActionType.CREATE,
        entity_type=EntityType.SETTING,
        entity_id=result["lease"]["id"],
        entity_name=result["lease"]["name"],
        description=_("Issued dynamic secret '%s' (kind=%s, role=%s, ttl=%ds)")
        % (
            result["lease"]["name"],
            request.kind,
            request.backend_role,
            request.ttl_seconds,
        ),
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
        details={
            "lease_id": result["lease"]["id"],
            "kind": request.kind,
            "backend_role": request.backend_role,
            "ttl_seconds": request.ttl_seconds,
            "expires_at": result["lease"]["expires_at"],
        },
    )
    return IssueResponse(**result)


@router.get("/leases", response_model=List[LeaseResponse])
async def list_leases(
    status: Optional[str] = Query(None, description="Filter by status"),
    kind: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List leases, optionally filtered by status (ACTIVE / REVOKED /
    EXPIRED / FAILED) and / or kind (token / database / ssh)."""
    if status is not None and status not in LEASE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=_("Unknown status: %s (allowed: %s)")
            % (status, ", ".join(LEASE_STATUSES)),
        )
    if kind is not None and kind not in LEASE_KINDS:
        raise HTTPException(
            status_code=400,
            detail=_("Unknown kind: %s (allowed: %s)") % (kind, ", ".join(LEASE_KINDS)),
        )

    q = db.query(models.DynamicSecretLease)
    if status:
        q = q.filter(models.DynamicSecretLease.status == status)
    if kind:
        q = q.filter(models.DynamicSecretLease.kind == kind)
    rows = q.order_by(models.DynamicSecretLease.issued_at.desc()).all()
    return [LeaseResponse(**r.to_dict()) for r in rows]


@router.get("/leases/{lease_id}", response_model=LeaseResponse)
async def get_lease(lease_id: str, db: Session = Depends(get_db)):
    lid = _parse_uuid_or_400(lease_id, "lease_id")
    lease = (
        db.query(models.DynamicSecretLease)
        .filter(models.DynamicSecretLease.id == lid)
        .first()
    )
    if not lease:
        raise HTTPException(status_code=404, detail=_("Lease not found"))
    return LeaseResponse(**lease.to_dict())


@router.post("/leases/{lease_id}/revoke")
async def revoke(
    lease_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    user = _get_user(db, current_user)
    lid = _parse_uuid_or_400(lease_id, "lease_id")
    try:
        result = revoke_lease(db, lease_id=lid)
    except DynamicSecretError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_id=str(lid),
        entity_name=result["lease"]["name"],
        description=_("Revoked dynamic secret lease '%s'") % result["lease"]["name"],
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
        details={
            "lease_id": str(lid),
            "vault_revoked": result.get("vault_revoked", False),
        },
    )
    return result


@router.post("/reconcile")
async def reconcile(db: Session = Depends(get_db)):
    """Mark any ACTIVE leases whose expiry has passed as EXPIRED.
    Safe to call repeatedly.  Intended for cron / scheduler hook."""
    transitioned = reconcile_expired(db)
    return {"transitioned_count": transitioned}


@router.get("/kinds")
async def list_kinds():
    """Return the supported lease kinds + their human-readable hints."""
    return {
        "kinds": [
            {"kind": LEASE_KIND_TOKEN, "label": "Token"},
            {"kind": LEASE_KIND_DATABASE, "label": "Database Credential"},
            {"kind": LEASE_KIND_SSH, "label": "SSH One-Time Key"},
        ],
        "ttl": {
            "min": TTL_MIN_SECONDS,
            "max": TTL_MAX_SECONDS,
            "default": TTL_DEFAULT_SECONDS,
        },
    }
