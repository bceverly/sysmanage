"""
Tenant directory lookups — Phase 13.1.

Resolve which tenant an out-of-request operation belongs to, so background /
pre-auth flows (password reset, MFA challenges, scheduled notifications) can
scope per-tenant config (email, …) correctly instead of falling back to the
server scope.

All lookups are best-effort and never raise: in single-tenant / collapsed mode
(or on any error) they return ``None``, which callers treat as "server scope".
"""

import logging
from typing import Optional

from backend.config import config

logger = logging.getLogger(__name__)


def resolve_tenant_for_email(email: Optional[str]) -> Optional[str]:
    """Return the tenant id whose allowlist contains ``email``'s domain, or None.

    Uses the per-tenant email-domain allowlist
    (``registry_tenant_email_domain``).  Returns ``None`` when multi-tenancy is
    disabled, the email is malformed, no tenant claims the domain, or the
    domain is claimed by more than one tenant (ambiguous → server scope).
    """
    if not config.is_multitenancy_enabled():
        return None
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].strip().lower()
    if not domain:
        return None
    try:
        from backend.persistence.models.tenancy import (  # noqa: PLC0415
            RegistryTenantEmailDomain,
        )
        from backend.persistence.partitions import (  # noqa: PLC0415
            PARTITION_REGISTRY,
            partition_session,
        )

        with partition_session(partition=PARTITION_REGISTRY) as session:
            rows = (
                session.query(RegistryTenantEmailDomain.tenant_id)
                .filter(RegistryTenantEmailDomain.domain == domain)
                .limit(2)
                .all()
            )
        if len(rows) == 1:
            return str(rows[0][0])
        # 0 matches → unknown domain; 2+ → ambiguous.  Either way, server scope.
        return None
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.debug("tenant lookup for email domain %r failed: %s", domain, exc)
        return None
