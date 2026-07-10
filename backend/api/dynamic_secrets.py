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

from backend.auth.auth_bearer import (
    JWTBearer,
    require_authenticated_user,
)
from backend.i18n import _
from backend.licensing.feature_gate import require_module_loaded
from backend.licensing.features import ModuleCode
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
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


# Phase 12.5: gate the dynamic-secrets surface behind ``secrets_engine``.
# Static secret CRUD was already gated in Phase 2.3; the dynamic-lease
# half (this file) is the natural dependent and is folded in here so
# both halves move together.  The federation-aware lease channel
# (coordinator owns the master Vault; sites request leases via the
# downstream channel) lives in the engine module the Pro+ build wires
# in — this OSS gate just denies the route until that engine loads.
# Single Depends instance is shared across the router so the license
# probe happens once per request.
_SECRETS_GATE = Depends(require_module_loaded(ModuleCode.SECRETS_ENGINE))

router = APIRouter(
    prefix="/dynamic-secrets",
    tags=["dynamic-secrets"],
    dependencies=[Depends(JWTBearer()), _SECRETS_GATE],
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


def _parse_uuid_or_400(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid UUID for %(field)s: %(value)s")
            % {"field": field, "value": value},
        ) from exc


@router.post("/issue", response_model=IssueResponse)
async def issue(
    request: IssueRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Issue a new short-lived credential.  The plaintext secret is
    returned EXACTLY ONCE in this response;  the server never logs it
    and the DB never stores it.  Once the operator has it, only
    OpenBAO holds the value, and only until the TTL expires.

    Phase 13.1: lease data routes to the active tenant's database via
    ``db`` (``get_tenant_db``); authorization is resolved on the MAIN engine
    by ``require_authenticated_user`` (user identities are server-global).
    """
    if request.kind not in LEASE_KINDS:
        raise HTTPException(
            status_code=400,
            detail=_("Unknown kind: %(kind)s (allowed: %(allowed)s)")
            % {"kind": request.kind, "allowed": ", ".join(LEASE_KINDS)},
        )
    try:
        result = issue_lease(
            db,
            kind=request.kind,
            backend_role=request.backend_role,
            name=request.name,
            ttl_seconds=request.ttl_seconds,
            issued_by_user_id=current_user.id,
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
        description=_(
            "Issued dynamic secret '%(name)s' (kind=%(kind)s, role=%(role)s, ttl=%(ttl)ds)"
        )
        % {
            "name": result["lease"]["name"],
            "kind": request.kind,
            "role": request.backend_role,
            "ttl": request.ttl_seconds,
        },
        user_id=current_user.id,
        username=current_user.userid,
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
    db: Session = Depends(get_tenant_db),
):
    """List leases, optionally filtered by status (ACTIVE / REVOKED /
    EXPIRED / FAILED) and / or kind (token / database / ssh)."""
    if status is not None and status not in LEASE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=_("Unknown status: %(status)s (allowed: %(allowed)s)")
            % {"status": status, "allowed": ", ".join(LEASE_STATUSES)},
        )
    if kind is not None and kind not in LEASE_KINDS:
        raise HTTPException(
            status_code=400,
            detail=_("Unknown kind: %(kind)s (allowed: %(allowed)s)")
            % {"kind": kind, "allowed": ", ".join(LEASE_KINDS)},
        )

    q = db.query(models.DynamicSecretLease)
    if status:
        q = q.filter(models.DynamicSecretLease.status == status)
    if kind:
        q = q.filter(models.DynamicSecretLease.kind == kind)
    rows = q.order_by(models.DynamicSecretLease.issued_at.desc()).all()
    return [LeaseResponse(**r.to_dict()) for r in rows]


@router.get("/leases/{lease_id}", response_model=LeaseResponse)
async def get_lease(lease_id: str, db: Session = Depends(get_tenant_db)):
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
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
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
        user_id=current_user.id,
        username=current_user.userid,
        result=Result.SUCCESS,
        details={
            "lease_id": str(lid),
            "vault_revoked": result.get("vault_revoked", False),
        },
    )
    return result


@router.post("/reconcile")
async def reconcile(db: Session = Depends(get_tenant_db)):
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
