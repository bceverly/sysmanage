"""
Registry service layer — Phase 13.1.B.

Pure-ish query/validation helpers over the ``registry_*`` control-plane
tables: the email→tenant grant map, default-tenant resolution, grant
validity (active + non-expired), and the per-tenant email-domain
allowlist.  Kept free of FastAPI so they are unit-testable against a bare
session and reusable by both the control-plane API (grant CRUD) and the
data-plane (``get_current_tenant`` / account switching).

Identity note (13.1.B scope): a grant maps a ``registry_user`` to a
``registry_tenant``.  In multi-tenancy mode the authenticated principal's
``user_id`` claim is the ``registry_user.id``.  The bridge from a login /
SSO assertion to a ``registry_user`` row is delivered in 13.1.E (JIT /
SCIM); this layer operates on ``registry_user`` ids directly.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from backend.persistence.models.tenancy import (
    RegistryTenant,
    RegistryTenantEmailDomain,
    RegistryUser,
    RegistryUserTenantGrant,
    TENANT_STATUS_ACTIVE,
)


def _utcnow() -> datetime:
    """Naive-UTC now, matching how grant ``expires_at`` is stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def resolve_registry_user_id(session, principal: Optional[str]):
    """Bridge an authenticated principal to its ``registry_user.id``, or None.

    In production the JWT principal is the login userid (an email); grants
    reference ``registry_user.id`` (a UUID).  This maps email → id.  As a
    fallback it also accepts a principal that is *already* a registry_user id
    (a valid UUID) — but only attempts that lookup when the principal parses as
    a UUID, so we never feed a non-UUID string to a UUID column (which would
    error on PostgreSQL).  (Interim bridge until full JIT/SCIM in 13.1.E.)
    """
    if not principal:
        return None
    value = str(principal).strip()
    row = (
        session.query(RegistryUser).filter(RegistryUser.email == value.lower()).first()
    )
    if row:
        return row.id
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None
    row = session.query(RegistryUser).filter(RegistryUser.id == value).first()
    return row.id if row else None


def _grant_is_live(grant: RegistryUserTenantGrant, now: datetime) -> bool:
    """A grant is live when it has no expiry or the expiry is in the future."""
    return grant.expires_at is None or grant.expires_at > now


def normalize_domain(email_or_domain: str) -> str:
    """Return the bare, lowercased domain from an email or domain string."""
    value = (email_or_domain or "").strip().lower()
    if "@" in value:
        value = value.rsplit("@", 1)[-1]
    return value


def list_user_grants(
    session, user_id, *, include_expired: bool = False
) -> List[RegistryUserTenantGrant]:
    """Return a user's grants, optionally filtering out expired ones.

    Only grants to **active** tenants are returned — a suspended tenant is
    not switchable even if the grant itself is live.
    """
    now = _utcnow()
    query = (
        session.query(RegistryUserTenantGrant)
        .join(RegistryTenant, RegistryTenant.id == RegistryUserTenantGrant.tenant_id)
        .filter(RegistryUserTenantGrant.user_id == user_id)
        .filter(RegistryTenant.status == TENANT_STATUS_ACTIVE)
    )
    grants = query.all()
    if include_expired:
        return grants
    return [g for g in grants if _grant_is_live(g, now)]


def has_active_grant(session, user_id, tenant_id) -> bool:
    """True when ``user_id`` holds a live grant to an active ``tenant_id``."""
    now = _utcnow()
    grant = (
        session.query(RegistryUserTenantGrant)
        .join(RegistryTenant, RegistryTenant.id == RegistryUserTenantGrant.tenant_id)
        .filter(RegistryUserTenantGrant.user_id == user_id)
        .filter(RegistryUserTenantGrant.tenant_id == tenant_id)
        .filter(RegistryTenant.status == TENANT_STATUS_ACTIVE)
        .first()
    )
    return grant is not None and _grant_is_live(grant, now)


def get_default_tenant_id(session, user_id):
    """Resolve the user's default active tenant for initial login.

    Preference order: the grant flagged ``is_default``; otherwise, if the
    user has exactly one live grant, that one; otherwise ``None`` (the
    caller must prompt the user to pick via account switching).
    """
    grants = list_user_grants(session, user_id)
    if not grants:
        return None
    for grant in grants:
        if grant.is_default:
            return grant.tenant_id
    if len(grants) == 1:
        return grants[0].tenant_id
    return None


def is_email_domain_allowed(session, tenant_id, email: str) -> bool:
    """True when ``email``'s domain is permitted for ``tenant_id``.

    An empty allowlist (no rows for the tenant) means "no restriction" —
    every domain is allowed until the tenant configures its allowlist.
    """
    domain = normalize_domain(email)
    rows = (
        session.query(RegistryTenantEmailDomain)
        .filter(RegistryTenantEmailDomain.tenant_id == tenant_id)
        .all()
    )
    if not rows:
        return True
    allowed = {r.domain for r in rows}
    return domain in allowed


def list_email_domains(session, tenant_id) -> List[RegistryTenantEmailDomain]:
    """Return the email-domain allowlist rows for a tenant."""
    return (
        session.query(RegistryTenantEmailDomain)
        .filter(RegistryTenantEmailDomain.tenant_id == tenant_id)
        .order_by(RegistryTenantEmailDomain.domain)
        .all()
    )
