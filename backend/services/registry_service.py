# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from backend.persistence.models.tenancy import (
    RegistryTenant,
    RegistryTenantEmailDomain,
    RegistryUser,
    RegistryUserTenantGrant,
    TENANT_STATUS_ACTIVE,
)

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Phase 13.1.E — JIT (just-in-time) provisioning support.
#
# These are deliberately FAIL-CLOSED and stricter than the general
# ``is_email_domain_allowed`` check: auto-creating an account from an SSO login
# is far more sensitive than letting an admin grant an existing user, so JIT
# refuses unless the tenant has an EXPLICIT allowlist that the email matches.
# ---------------------------------------------------------------------------


def jit_domain_permitted(session, tenant_id, email: str) -> bool:
    """True only when the tenant has a NON-EMPTY allowlist that ``email`` matches.

    Unlike :func:`is_email_domain_allowed` (which treats an empty allowlist as
    "no restriction"), JIT fails closed: with no allowlist configured, no SSO
    identity may self-provision into the tenant.
    """
    domain = normalize_domain(email)
    if not domain:
        return False
    rows = (
        session.query(RegistryTenantEmailDomain)
        .filter(RegistryTenantEmailDomain.tenant_id == tenant_id)
        .all()
    )
    if not rows:
        return False
    return domain in {r.domain for r in rows}


def ensure_registry_user(session, email: str) -> RegistryUser:
    """Find-or-create the global identity for ``email`` (lower-cased)."""
    normalized = (email or "").strip().lower()
    user = session.query(RegistryUser).filter(RegistryUser.email == normalized).first()
    if user is None:
        user = RegistryUser(email=normalized)
        session.add(user)
        session.flush()  # populate user.id
    return user


def ensure_grant(session, user_id, tenant_id, role: str = "member"):
    """Find-or-create a (user, tenant) grant; returns the grant row.

    Idempotent on the unique (user_id, tenant_id) constraint — a returning SSO
    user keeps their existing grant rather than duplicating it.
    """
    grant = (
        session.query(RegistryUserTenantGrant)
        .filter(
            RegistryUserTenantGrant.user_id == user_id,
            RegistryUserTenantGrant.tenant_id == tenant_id,
        )
        .first()
    )
    if grant is None:
        grant = RegistryUserTenantGrant(
            user_id=user_id, tenant_id=tenant_id, role=role or "member"
        )
        session.add(grant)
        session.flush()
    return grant


# ---------------------------------------------------------------------------
# Phase 13.1.E — vendor-support / break-glass grants.
#
# A support grant is a deliberately SHORT-LIVED, time-boxed grant for external
# support or break-glass access.  Its enforcement is the existing expiry check
# in ``has_active_grant``: once ``expires_at`` passes, the grant is dead and the
# request-time gate refuses it — no separate revocation sweep is needed.  The
# TTL is hard-capped so an operator can't accidentally mint a long-lived
# backdoor; binding the window to a live OpenBAO lease object is a deeper
# follow-on, but the grant's own expiry already auto-revokes access.
# ---------------------------------------------------------------------------

SUPPORT_GRANT_ROLE = "support"
SUPPORT_GRANT_MAX_TTL_SECONDS = 72 * 3600  # 72h hard cap


def create_support_grant(
    session,
    user_id,
    tenant_id,
    ttl_seconds: int,
    *,
    role: str = SUPPORT_GRANT_ROLE,
    max_ttl_seconds: int = SUPPORT_GRANT_MAX_TTL_SECONDS,
) -> RegistryUserTenantGrant:
    """Create or refresh a TIME-BOXED grant (vendor support / break-glass).

    ``ttl_seconds`` is clamped to ``[1, max_ttl_seconds]`` so a support window can
    never be unbounded.  Sets ``expires_at = now + ttl`` (naive-UTC, matching how
    the grant store records expiry), so the existing request-time expiry gate
    auto-revokes it.  Returns the grant row.  The CALLER must audit who issued it,
    for which tenant, and why — these grants must always be logged.
    """
    ttl = max(1, min(int(ttl_seconds), int(max_ttl_seconds)))
    grant = (
        session.query(RegistryUserTenantGrant)
        .filter(
            RegistryUserTenantGrant.user_id == user_id,
            RegistryUserTenantGrant.tenant_id == tenant_id,
        )
        .first()
    )
    if grant is None:
        grant = RegistryUserTenantGrant(user_id=user_id, tenant_id=tenant_id)
        session.add(grant)
    grant.role = role or SUPPORT_GRANT_ROLE
    grant.expires_at = _utcnow() + timedelta(seconds=ttl)
    session.flush()
    return grant


def bind_support_lease(grant, ttl_seconds, *, metadata=None):
    """Bind a support grant to a live OpenBAO lease object (Phase 13.1.E).

    Best-effort: mints an OpenBAO token whose TTL mirrors the grant window and
    records its accessor on ``grant.support_lease_accessor``.  Returns the
    accessor, or ``None`` when OpenBAO is disabled/unreachable or lease creation
    isn't permitted — in which case the grant's ``expires_at`` alone enforces the
    window (unchanged single-tenant / vault-less behaviour).  The caller must
    flush/commit to persist the accessor.
    """
    try:
        from backend.services.vault_service import VaultService  # noqa: PLC0415

        accessor = VaultService().create_support_lease(
            ttl_seconds=ttl_seconds, metadata=metadata
        )
    except Exception:  # noqa: BLE001 - vault optional + best-effort
        accessor = None
    if accessor:
        grant.support_lease_accessor = accessor
    return accessor


def revoke_support_grant(session, user_id, tenant_id):
    """Immediately revoke a (user, tenant) grant — kill-the-break-glass.

    Expires the grant *now* (the request-time ``has_active_grant`` gate refuses
    it on the next call) AND, if a support lease was bound, revokes that live
    OpenBAO lease so it cannot linger until its TTL.  ``expires_at`` is the
    app-level enforcement; the lease revocation additionally tears down the
    vault-side object.  Returns the revoked grant row, or ``None`` when no grant
    exists for the pair.
    """
    grant = (
        session.query(RegistryUserTenantGrant)
        .filter(
            RegistryUserTenantGrant.user_id == user_id,
            RegistryUserTenantGrant.tenant_id == tenant_id,
        )
        .first()
    )
    if grant is None:
        return None
    # Backdate so the grant is unambiguously in the past (no equal-timestamp
    # edge against a same-instant has_active_grant check).
    grant.expires_at = _utcnow() - timedelta(seconds=1)
    accessor = grant.support_lease_accessor
    if accessor:
        try:
            from backend.services.vault_service import VaultService  # noqa: PLC0415

            VaultService().revoke_support_lease(accessor)
        except Exception as exc:  # noqa: BLE001 - best-effort vault teardown
            # The lease auto-expires at its TTL anyway; log so an operator can
            # see a stuck-lease teardown rather than swallowing it silently.
            logger.debug("support-lease revoke failed (best-effort): %s", exc)
        grant.support_lease_accessor = None
    session.flush()
    return grant
