"""
Control-plane API skeleton — Phase 13.1.A.

This is the **management** API for multi-tenancy: it provisions tenants,
manages email→tenant grants, stores placement/IdP config, and (later)
brokers credentials and orchestrates migrations/backups.  It is a
security boundary distinct from the data-plane (the existing SysManage
API): high-privilege, operator-facing, and **never exposed to tenant
end-users**.

It is mounted **only** when ``multitenancy.enabled`` is true (see
``backend/startup/route_registration.py``).  In the default homelab /
on-prem / federated deployment this router does not exist on the app at
all — there is no new attack surface and no behavior change.

13.1.A ships the skeleton: a health/status endpoint and a read-only
tenant listing over the registry partition.  Tenant provisioning, grant
CRUD, and credential brokering arrive in 13.1.B/13.1.C.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import config as config_module
from backend.i18n import _
from backend.persistence.models.tenancy import (
    RegistryTenant,
    RegistryTenantEmailDomain,
    RegistryUser,
    RegistryUserTenantGrant,
    TENANT_STATUS_ACTIVE,
)
from backend.persistence.partitions import get_registry_db
from backend.services import registry_service

logger = logging.getLogger(__name__)

# All control-plane routes live under a dedicated prefix so they are
# trivially separable (reverse-proxy ACL, separate listener, etc.) from
# the data-plane ``/api`` surface.
router = APIRouter(prefix="/api/control-plane", tags=["control-plane"])


class ControlPlaneStatus(BaseModel):
    """Liveness + posture of the control plane."""

    multitenancy_enabled: bool
    tenant_count: int


class TenantSummary(BaseModel):
    """Non-secret summary of a registry tenant (no placement/credentials)."""

    id: str
    name: str
    slug: str
    status: str

    model_config = {"from_attributes": True}


class TenantListResponse(BaseModel):
    """Envelope for the tenant listing."""

    tenants: List[TenantSummary]
    total: int


@router.get("/status", response_model=ControlPlaneStatus)
def get_status(db: Session = Depends(get_registry_db)) -> ControlPlaneStatus:
    """Report that the control plane is mounted and how many tenants exist."""
    tenant_count = db.query(RegistryTenant).count()
    return ControlPlaneStatus(
        multitenancy_enabled=config_module.is_multitenancy_enabled(),
        tenant_count=tenant_count,
    )


@router.get("/tenants", response_model=TenantListResponse)
def list_tenants(
    status: Optional[str] = None,
    db: Session = Depends(get_registry_db),
) -> TenantListResponse:
    """List tenants in the registry (routing/authorization data only)."""
    query = db.query(RegistryTenant)
    if status:
        query = query.filter(RegistryTenant.status == status)
    rows = query.order_by(RegistryTenant.created_at).all()
    tenants = [
        TenantSummary(id=str(row.id), name=row.name, slug=row.slug, status=row.status)
        for row in rows
    ]
    return TenantListResponse(tenants=tenants, total=len(tenants))


# ---------------------------------------------------------------------
# Tenant provisioning
# ---------------------------------------------------------------------


class CreateTenantRequest(BaseModel):
    name: str
    slug: str


@router.post("/tenants", response_model=TenantSummary, status_code=201)
def create_tenant(
    payload: CreateTenantRequest, db: Session = Depends(get_registry_db)
) -> TenantSummary:
    """Provision a new tenant (account).  Slug must be unique."""
    tenant = RegistryTenant(
        name=payload.name, slug=payload.slug, status=TENANT_STATUS_ACTIVE
    )
    db.add(tenant)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=_("A tenant with that slug already exists.")
        ) from exc
    db.refresh(tenant)
    return TenantSummary(
        id=str(tenant.id), name=tenant.name, slug=tenant.slug, status=tenant.status
    )


# ---------------------------------------------------------------------
# Users (global identities)
# ---------------------------------------------------------------------


class CreateUserRequest(BaseModel):
    email: EmailStr


class UserSummary(BaseModel):
    id: str
    email: str
    is_active: bool


@router.post("/users", response_model=UserSummary, status_code=201)
def create_user(
    payload: CreateUserRequest, db: Session = Depends(get_registry_db)
) -> UserSummary:
    """Create a global (email-keyed) identity.  Email must be unique."""
    user = RegistryUser(email=str(payload.email).lower())
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=_("A user with that email already exists.")
        ) from exc
    db.refresh(user)
    return UserSummary(id=str(user.id), email=user.email, is_active=user.is_active)


# ---------------------------------------------------------------------
# Email→tenant grants (the least-privilege core)
# ---------------------------------------------------------------------


class CreateGrantRequest(BaseModel):
    user_id: str
    tenant_id: str
    role: str = "member"
    is_default: bool = False
    # ISO-8601 datetime; None = a permanent grant.  Time-boxed grants are
    # the basis for enforced vendor-support access (13.1.E).
    expires_at: Optional[str] = None


class GrantSummary(BaseModel):
    id: str
    user_id: str
    tenant_id: str
    role: str
    is_default: bool
    expires_at: Optional[str] = None


def _grant_summary(grant: RegistryUserTenantGrant) -> GrantSummary:
    return GrantSummary(
        id=str(grant.id),
        user_id=str(grant.user_id),
        tenant_id=str(grant.tenant_id),
        role=grant.role,
        is_default=grant.is_default,
        expires_at=grant.expires_at.isoformat() if grant.expires_at else None,
    )


@router.post("/grants", response_model=GrantSummary, status_code=201)
def create_grant(
    payload: CreateGrantRequest, db: Session = Depends(get_registry_db)
) -> GrantSummary:
    """Grant a user access to a tenant.

    Enforces the tenant's email-domain allowlist (design §10): a user whose
    email domain is not allowlisted for the tenant is rejected with 403.
    An empty allowlist means no restriction.
    """
    user = db.query(RegistryUser).filter(RegistryUser.id == payload.user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail=_("User not found."))
    tenant = (
        db.query(RegistryTenant).filter(RegistryTenant.id == payload.tenant_id).first()
    )
    if tenant is None:
        raise HTTPException(status_code=404, detail=_("Tenant not found."))

    if not registry_service.is_email_domain_allowed(db, payload.tenant_id, user.email):
        raise HTTPException(
            status_code=403,
            detail=_("This user's email domain is not allowed for this tenant."),
        )

    expires_at = None
    if payload.expires_at:
        from datetime import datetime  # noqa: PLC0415

        try:
            parsed = datetime.fromisoformat(payload.expires_at)
            expires_at = parsed.replace(tzinfo=None)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail=_("expires_at must be an ISO-8601 datetime.")
            ) from exc

    grant = RegistryUserTenantGrant(
        user_id=payload.user_id,
        tenant_id=payload.tenant_id,
        role=payload.role,
        is_default=payload.is_default,
        expires_at=expires_at,
    )
    db.add(grant)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=_("That user already has a grant to that tenant."),
        ) from exc
    db.refresh(grant)
    return _grant_summary(grant)


@router.get("/grants", response_model=List[GrantSummary])
def list_grants(
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    db: Session = Depends(get_registry_db),
) -> List[GrantSummary]:
    """List grants, optionally filtered by user and/or tenant."""
    query = db.query(RegistryUserTenantGrant)
    if user_id:
        query = query.filter(RegistryUserTenantGrant.user_id == user_id)
    if tenant_id:
        query = query.filter(RegistryUserTenantGrant.tenant_id == tenant_id)
    return [_grant_summary(g) for g in query.all()]


@router.delete("/grants/{grant_id}", status_code=204)
def delete_grant(grant_id: str, db: Session = Depends(get_registry_db)) -> None:
    """Revoke a grant."""
    grant = (
        db.query(RegistryUserTenantGrant)
        .filter(RegistryUserTenantGrant.id == grant_id)
        .first()
    )
    if grant is None:
        raise HTTPException(status_code=404, detail=_("Grant not found."))
    db.delete(grant)
    db.commit()


# ---------------------------------------------------------------------
# Per-tenant email-domain allowlist
# ---------------------------------------------------------------------


class CreateEmailDomainRequest(BaseModel):
    domain: str


class EmailDomainSummary(BaseModel):
    id: str
    tenant_id: str
    domain: str


@router.get(
    "/tenants/{tenant_id}/email-domains", response_model=List[EmailDomainSummary]
)
def list_tenant_email_domains(
    tenant_id: str, db: Session = Depends(get_registry_db)
) -> List[EmailDomainSummary]:
    """List a tenant's email-domain allowlist."""
    rows = registry_service.list_email_domains(db, tenant_id)
    return [
        EmailDomainSummary(id=str(r.id), tenant_id=str(r.tenant_id), domain=r.domain)
        for r in rows
    ]


@router.post(
    "/tenants/{tenant_id}/email-domains",
    response_model=EmailDomainSummary,
    status_code=201,
)
def add_tenant_email_domain(
    tenant_id: str,
    payload: CreateEmailDomainRequest,
    db: Session = Depends(get_registry_db),
) -> EmailDomainSummary:
    """Add an allowed email domain to a tenant (stored bare + lowercased)."""
    tenant = db.query(RegistryTenant).filter(RegistryTenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail=_("Tenant not found."))

    domain = registry_service.normalize_domain(payload.domain)
    if not domain:
        raise HTTPException(status_code=422, detail=_("A domain is required."))

    row = RegistryTenantEmailDomain(tenant_id=tenant_id, domain=domain)
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=_("That domain is already allowlisted.")
        ) from exc
    db.refresh(row)
    return EmailDomainSummary(
        id=str(row.id), tenant_id=str(row.tenant_id), domain=row.domain
    )


@router.delete("/tenants/{tenant_id}/email-domains/{domain_id}", status_code=204)
def delete_tenant_email_domain(
    tenant_id: str, domain_id: str, db: Session = Depends(get_registry_db)
) -> None:
    """Remove an email domain from a tenant's allowlist."""
    row = (
        db.query(RegistryTenantEmailDomain)
        .filter(
            RegistryTenantEmailDomain.id == domain_id,
            RegistryTenantEmailDomain.tenant_id == tenant_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=_("Email domain not found."))
    db.delete(row)
    db.commit()
