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

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config import config as config_module
from backend.i18n import _
from backend.security.roles import SecurityRoles
from backend.persistence.models.tenancy import (
    RegistryTenant,
    RegistryTenantEmailDomain,
    RegistryTenantPlacement,
    RegistryUser,
    RegistryUserTenantGrant,
    TENANT_STATUS_ACTIVE,
    TENANT_TIER_SILO,
    TENANT_TIERS,
)
from backend.persistence.partitions import get_registry_db
from backend.services import registry_service
from backend.utils.log_sanitize import scrub

logger = logging.getLogger(__name__)

# All control-plane routes live under a dedicated prefix so they are
# trivially separable (reverse-proxy ACL, separate listener, etc.) from
# the data-plane ``/api`` surface.  Every route requires a valid bearer
# token — these are highly privileged operations (create tenants, grant
# cross-tenant access, set DB placement), so the whole router is gated.
router = APIRouter(
    prefix="/api/control-plane",
    tags=["control-plane"],
    dependencies=[Depends(JWTBearer())],
)


def _tenant_not_found() -> HTTPException:
    """The 404 raised when a tenant id does not resolve — single source of truth
    so the (translated) message is defined once."""
    return HTTPException(status_code=404, detail=_("Tenant not found."))


class ControlPlaneStatus(BaseModel):
    """Liveness + posture of the control plane."""

    multitenancy_enabled: bool
    tenant_count: int
    # Phase 13.1 self-service provisioning posture.
    self_service_provisioning: bool = False
    # Whether the operator-run bootstrap has stored the provisioner credential
    # in OpenBAO (so the UI knows whether auto-provision can succeed).
    provisioner_configured: bool = False


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


@router.get("/status")
def get_status(db: Session = Depends(get_registry_db)) -> ControlPlaneStatus:
    """Report that the control plane is mounted and how many tenants exist."""
    tenant_count = db.query(RegistryTenant).count()
    self_service = config_module.is_self_service_provisioning_enabled()
    provisioner_configured = False
    if self_service:
        # Only probe OpenBAO when self-service is on (avoids a needless lookup).
        from backend.services import tenant_orchestration  # noqa: PLC0415

        provisioner_configured = tenant_orchestration.is_provisioner_configured()
    return ControlPlaneStatus(
        multitenancy_enabled=config_module.is_multitenancy_enabled(),
        tenant_count=tenant_count,
        self_service_provisioning=self_service,
        provisioner_configured=provisioner_configured,
    )


class MigrationStatus(BaseModel):
    tenants_pending: int = 0
    tenant_slugs: List[str] = []
    tenant_head: Optional[str] = None


@router.get("/migration-status")
def migration_status() -> MigrationStatus:
    """Tenant databases that are behind the code head (drives the UI banner).

    Read-only status for any authenticated user — no admin gate.
    """
    from backend.services import migration_status as svc  # noqa: PLC0415

    return MigrationStatus(**svc.pending_tenant_migrations())


@router.get("/tenants")
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


@router.post("/tenants", status_code=201)
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


@router.get("/users")
def list_users(
    email: Optional[str] = None,
    db: Session = Depends(get_registry_db),
) -> List[UserSummary]:
    """List global identities, optionally filtered by exact (lowercased) email.

    Backs the "add member" flow in the UI: look up a user's id by email so a
    grant can be created without first knowing the id.
    """
    query = db.query(RegistryUser)
    if email:
        query = query.filter(RegistryUser.email == email.strip().lower())
    rows = query.order_by(RegistryUser.email).all()
    return [
        UserSummary(id=str(r.id), email=r.email, is_active=r.is_active) for r in rows
    ]


@router.post("/users", status_code=201)
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


@router.post("/grants", status_code=201)
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
        raise _tenant_not_found()

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


@router.get("/grants")
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


@router.get("/tenants/{tenant_id}/email-domains")
def list_tenant_email_domains(
    tenant_id: str, db: Session = Depends(get_registry_db)
) -> List[EmailDomainSummary]:
    """List a tenant's email-domain allowlist."""
    rows = registry_service.list_email_domains(db, tenant_id)
    return [
        EmailDomainSummary(id=str(r.id), tenant_id=str(r.tenant_id), domain=r.domain)
        for r in rows
    ]


@router.post("/tenants/{tenant_id}/email-domains", status_code=201)
def add_tenant_email_domain(
    tenant_id: str,
    payload: CreateEmailDomainRequest,
    db: Session = Depends(get_registry_db),
) -> EmailDomainSummary:
    """Add an allowed email domain to a tenant (stored bare + lowercased)."""
    tenant = db.query(RegistryTenant).filter(RegistryTenant.id == tenant_id).first()
    if tenant is None:
        raise _tenant_not_found()

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


# ---------------------------------------------------------------------
# Tenant enrollment tokens (Phase 13.1 data plane) — admin-gated; agents
# present a token at registration to enroll into the tenant.
# ---------------------------------------------------------------------


class CreateEnrollmentTokenRequest(BaseModel):
    label: Optional[str] = None
    expires_in_days: Optional[int] = None
    max_uses: Optional[int] = None


class EnrollmentTokenSummary(BaseModel):
    id: str
    tenant_id: str
    label: Optional[str] = None
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    max_uses: Optional[int] = None
    use_count: int = 0
    last_used_at: Optional[str] = None
    revoked: bool = False


class CreateEnrollmentTokenResponse(BaseModel):
    # The plaintext token — shown ONCE, never retrievable again.
    token: str
    summary: EnrollmentTokenSummary


def _iso(value):
    return value.isoformat() if value else None


def _token_summary(row) -> EnrollmentTokenSummary:
    return EnrollmentTokenSummary(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        label=row.label,
        created_at=_iso(row.created_at),
        expires_at=_iso(row.expires_at),
        max_uses=row.max_uses,
        use_count=row.use_count or 0,
        last_used_at=_iso(row.last_used_at),
        revoked=bool(row.revoked),
    )


@router.get("/tenants/{tenant_id}/enrollment-tokens")
def list_enrollment_tokens(
    tenant_id: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_registry_db),
) -> List[EnrollmentTokenSummary]:
    """List a tenant's enrollment tokens (never the plaintext)."""
    _require_provision_admin(current_user)
    from backend.services import enrollment_service  # noqa: PLC0415

    return [_token_summary(r) for r in enrollment_service.list_tokens(db, tenant_id)]


@router.post("/tenants/{tenant_id}/enrollment-tokens", status_code=201)
def create_enrollment_token(
    tenant_id: str,
    payload: CreateEnrollmentTokenRequest,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_registry_db),
) -> CreateEnrollmentTokenResponse:
    """Generate a tenant enrollment token.  The plaintext is returned ONCE."""
    _require_provision_admin(current_user)

    tenant = db.query(RegistryTenant).filter(RegistryTenant.id == tenant_id).first()
    if tenant is None:
        raise _tenant_not_found()

    expires_at = None
    if payload.expires_in_days and payload.expires_in_days > 0:
        from datetime import datetime, timedelta, timezone  # noqa: PLC0415

        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
            days=payload.expires_in_days
        )

    from backend.services import enrollment_service  # noqa: PLC0415

    plaintext, row = enrollment_service.generate_token(
        db,
        tenant_id,
        label=payload.label,
        expires_at=expires_at,
        max_uses=payload.max_uses,
        created_by=current_user,
    )
    return CreateEnrollmentTokenResponse(token=plaintext, summary=_token_summary(row))


@router.delete("/tenants/{tenant_id}/enrollment-tokens/{token_id}", status_code=204)
def revoke_enrollment_token(
    tenant_id: str,
    token_id: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_registry_db),
) -> None:
    """Revoke an enrollment token (disables it immediately)."""
    _require_provision_admin(current_user)
    from backend.services import enrollment_service  # noqa: PLC0415

    if not enrollment_service.revoke_token(db, tenant_id, token_id):
        raise HTTPException(status_code=404, detail=_("Enrollment token not found."))


# ---------------------------------------------------------------------
# Per-tenant placement (DB coordinates — NEVER credentials) + provisioning
# ---------------------------------------------------------------------


class PlacementRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    dbname: Optional[str] = None
    region: Optional[str] = None
    tier: str = TENANT_TIER_SILO
    openbao_role: Optional[str] = None


class PlacementSummary(BaseModel):
    tenant_id: str
    host: Optional[str] = None
    port: Optional[int] = None
    dbname: Optional[str] = None
    region: Optional[str] = None
    tier: str
    openbao_role: Optional[str] = None


def _placement_summary(p: RegistryTenantPlacement) -> PlacementSummary:
    return PlacementSummary(
        tenant_id=str(p.tenant_id),
        host=p.host,
        port=p.port,
        dbname=p.dbname,
        region=p.region,
        tier=p.tier,
        openbao_role=p.openbao_role,
    )


@router.put("/tenants/{tenant_id}/placement")
def upsert_placement(
    tenant_id: str,
    payload: PlacementRequest,
    db: Session = Depends(get_registry_db),
) -> PlacementSummary:
    """Set a tenant's DB coordinates (creates or updates).  No credentials.

    The ``openbao_role`` names the OpenBAO database-secrets role that brokers
    this tenant's dynamic credentials — the password itself is never stored.
    """
    if payload.tier not in TENANT_TIERS:
        raise HTTPException(status_code=422, detail=_("Unknown placement tier."))
    tenant = db.query(RegistryTenant).filter(RegistryTenant.id == tenant_id).first()
    if tenant is None:
        raise _tenant_not_found()

    placement = (
        db.query(RegistryTenantPlacement)
        .filter(RegistryTenantPlacement.tenant_id == tenant_id)
        .first()
    )
    if placement is None:
        placement = RegistryTenantPlacement(tenant_id=tenant_id)
        db.add(placement)
    placement.host = payload.host
    placement.port = payload.port
    placement.dbname = payload.dbname
    placement.region = payload.region
    placement.tier = payload.tier
    placement.openbao_role = payload.openbao_role
    db.commit()
    db.refresh(placement)
    return _placement_summary(placement)


@router.get("/tenants/{tenant_id}/placement")
def get_placement(
    tenant_id: str, db: Session = Depends(get_registry_db)
) -> PlacementSummary:
    """Read a tenant's DB coordinates (never credentials)."""
    placement = (
        db.query(RegistryTenantPlacement)
        .filter(RegistryTenantPlacement.tenant_id == tenant_id)
        .first()
    )
    if placement is None:
        raise HTTPException(status_code=404, detail=_("Placement not found."))
    return _placement_summary(placement)


class ProvisionResponse(BaseModel):
    tenant_id: str
    revision: Optional[str] = None
    status: str


@router.post("/tenants/{tenant_id}/provision")
def provision_tenant(
    tenant_id: str, db: Session = Depends(get_registry_db)
) -> ProvisionResponse:
    """Run the tenant Alembic chain against the tenant DB + record its revision.

    Requires a placement with an ``openbao_role`` so the per-tenant engine can
    lease credentials.  Staged tenant-by-tenant; a bad migration's blast radius
    is one tenant.
    """
    placement = (
        db.query(RegistryTenantPlacement)
        .filter(RegistryTenantPlacement.tenant_id == tenant_id)
        .first()
    )
    if placement is None:
        raise HTTPException(
            status_code=400,
            detail=_("Tenant has no placement; set one before provisioning."),
        )

    from backend.services import tenant_provisioning  # noqa: PLC0415

    try:
        revision = tenant_provisioning.provision_tenant_database(tenant_id)
    except Exception as exc:  # noqa: BLE001
        # Log the full traceback for operators (was previously a one-line
        # message with no stack, which buried the real cause).
        logger.exception("Provisioning tenant %s failed: %s", scrub(tenant_id), exc)
        # Surface the underlying cause to the (authenticated, admin-only)
        # caller so the UI shows *why* it failed instead of a generic message.
        # Prefer the DB driver's ``orig`` error, whose message is just the
        # database error (e.g. "permission denied for table alembic_version")
        # without the SQL text or bound parameters — so we don't leak data.
        cause = getattr(exc, "orig", None) or exc
        detail = _("Tenant database provisioning failed.")
        raise HTTPException(
            status_code=502,
            detail=f"{detail} {type(cause).__name__}: {cause}".strip(),
        ) from exc

    return ProvisionResponse(
        tenant_id=str(tenant_id), revision=revision, status="provisioned"
    )


# ---------------------------------------------------------------------
# Self-service provisioning (Phase 13.1) — create the tenant DB + OpenBAO
# role from the UI.  Gated by the self_service_provisioning flag + an admin
# role, and audited.
# ---------------------------------------------------------------------

# Tenant provisioning/deletion is an administrative super-power, gated on the
# dedicated MANAGE_TENANTS role (seeded + backfilled to admins by migration
# o12mgttenant).
_PROVISION_ROLE = SecurityRoles.MANAGE_TENANTS


def _require_provision_admin(current_user: str):
    """Load the caller and require the admin-tier provisioning role.

    Users/roles live in the main application DB (not the registry), so this
    opens its own session.  Raises 401 if unknown, 403 if not authorized.
    """
    from backend.persistence import db as app_db  # noqa: PLC0415
    from backend.persistence import models as models_module  # noqa: PLC0415

    session_local = app_db.get_session_local()
    with session_local() as session:
        user = (
            session.query(models_module.User)
            .filter(models_module.User.userid == current_user)
            .first()
        )
        if user is None:
            raise HTTPException(status_code=401, detail=_("User not found."))
        if getattr(user, "_role_cache", None) is None:
            user.load_role_cache(session)
        if not user.has_role(_PROVISION_ROLE):
            raise HTTPException(
                status_code=403,
                detail=_("You are not authorized to provision tenants."),
            )
        return user


class AutoProvisionRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    region: Optional[str] = None
    tier: str = TENANT_TIER_SILO


class AutoProvisionResponse(BaseModel):
    tenant_id: str
    dbname: str
    openbao_role: str
    revision: Optional[str] = None
    status: str


@router.post("/tenants/{tenant_id}/auto-provision")
def auto_provision_tenant(
    tenant_id: str,
    payload: AutoProvisionRequest,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_registry_db),
) -> AutoProvisionResponse:
    """Create the tenant DB + OpenBAO role, set placement, and run migrations.

    Requires ``multitenancy.self_service_provisioning`` and an admin role.
    Every attempt (success or failure) is audited.
    """
    if not config_module.is_self_service_provisioning_enabled():
        raise HTTPException(
            status_code=403,
            detail=_("Self-service provisioning is disabled on this server."),
        )
    _require_provision_admin(current_user)

    tenant = db.query(RegistryTenant).filter(RegistryTenant.id == tenant_id).first()
    if tenant is None:
        raise _tenant_not_found()

    from backend.services import tenant_orchestration  # noqa: PLC0415

    try:
        result = tenant_orchestration.auto_provision_tenant(
            tenant_id,
            slug=tenant.slug,
            host=payload.host,
            port=payload.port,
            region=payload.region,
            tier=payload.tier,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Auto-provisioning tenant %s failed: %s", scrub(tenant_id), exc
        )
        _audit_provision(current_user, tenant, success=False, error=str(exc))
        cause = getattr(exc, "orig", None) or exc
        detail = _("Tenant provisioning failed.")
        raise HTTPException(
            status_code=502,
            detail=f"{detail} {type(cause).__name__}: {cause}".strip(),
        ) from exc

    _audit_provision(current_user, tenant, success=True, detail=result)
    return AutoProvisionResponse(**result)


def _audit_provision(current_user, tenant, *, success, detail=None, error=None):
    """Write an audit-log entry for a provisioning attempt (best-effort)."""
    try:
        from backend.persistence import db as app_db  # noqa: PLC0415
        from backend.services.audit_service import (  # noqa: PLC0415
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        session_local = app_db.get_session_local()
        with session_local() as session:
            AuditService.log(
                session,
                action_type=ActionType.CREATE,
                entity_type=EntityType.TENANT,
                description=(
                    f"Self-service provisioning of tenant '{tenant.slug}' "
                    f"{'succeeded' if success else 'failed'}"
                ),
                result=Result.SUCCESS if success else Result.FAILURE,
                username=current_user,
                entity_id=str(tenant.id),
                entity_name=tenant.slug,
                details=detail if success else None,
                error_message=error,
            )
    except Exception as exc:  # noqa: BLE001 - auditing must never break the op
        logger.warning("Could not write provisioning audit entry: %s", exc)


# ---------------------------------------------------------------------
# Delete a tenant — destructive teardown (registry rows always; OpenBAO
# role/config always; the database only on explicit opt-in).  Admin-gated,
# requires typed confirmation, and audited.
# ---------------------------------------------------------------------


class DeleteTenantRequest(BaseModel):
    # The caller must echo the tenant's slug to confirm — guards against
    # deleting the wrong tenant.
    confirm: str
    # Opt-in to also DROP the tenant's database (irreversible data loss).
    drop_database: bool = False


@router.delete("/tenants/{tenant_id}")
def delete_tenant(
    tenant_id: str,
    payload: DeleteTenantRequest,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_registry_db),
) -> dict:
    """Delete a tenant and tear down its OpenBAO role/config (+ optionally DB).

    Requires an admin role and a typed slug confirmation.  Audited.
    """
    _require_provision_admin(current_user)

    tenant = db.query(RegistryTenant).filter(RegistryTenant.id == tenant_id).first()
    if tenant is None:
        raise _tenant_not_found()
    if payload.confirm != tenant.slug:
        raise HTTPException(
            status_code=400,
            detail=_("Confirmation does not match the tenant slug."),
        )

    slug = tenant.slug
    from backend.services import tenant_orchestration  # noqa: PLC0415

    try:
        result = tenant_orchestration.deprovision_tenant(
            tenant_id, slug=slug, drop_database=payload.drop_database
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Deleting tenant %s failed: %s", scrub(tenant_id), exc)
        _audit_delete(current_user, tenant_id, slug, success=False, error=str(exc))
        cause = getattr(exc, "orig", None) or exc
        detail = _("Tenant deletion failed.")
        raise HTTPException(
            status_code=502,
            detail=f"{detail} {type(cause).__name__}: {cause}".strip(),
        ) from exc

    _audit_delete(current_user, tenant_id, slug, success=True, detail=result)
    return result


def _audit_delete(current_user, tenant_id, slug, *, success, detail=None, error=None):
    """Write an audit-log entry for a tenant deletion (best-effort)."""
    try:
        from backend.persistence import db as app_db  # noqa: PLC0415
        from backend.services.audit_service import (  # noqa: PLC0415
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        session_local = app_db.get_session_local()
        with session_local() as session:
            AuditService.log(
                session,
                action_type=ActionType.DELETE,
                entity_type=EntityType.TENANT,
                description=(
                    f"Deletion of tenant '{slug}' "
                    f"{'succeeded' if success else 'failed'}"
                ),
                result=Result.SUCCESS if success else Result.FAILURE,
                username=current_user,
                entity_id=str(tenant_id),
                entity_name=slug,
                details=detail if success else None,
                error_message=error,
            )
    except Exception as exc:  # noqa: BLE001 - auditing must never break the op
        logger.warning("Could not write deletion audit entry: %s", exc)
