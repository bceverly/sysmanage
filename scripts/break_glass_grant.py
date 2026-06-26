#!/usr/bin/env python3
"""Break-glass / vendor-support grant tool (Phase 13.1.E).

Mint a deliberately SHORT-LIVED, time-boxed grant that lets a user (a support
engineer, a vendor, or an operator recovering access) reach ONE tenant for a
bounded window.  This is the emergency / support path:

  * The grant's ``expires_at`` is the enforcement — the request-time gate
    (``registry_service.has_active_grant``) refuses it the moment it lapses, so
    there is no lingering backdoor and no separate revocation step required.
  * The TTL is HARD-CAPPED (72h) — you cannot mint an unbounded grant.
  * Every issuance is logged with the operator, target tenant, TTL, and reason,
    so break-glass access is always auditable.

Usage::

    python scripts/break_glass_grant.py --email vendor@acme.com \\
        --tenant acme --ttl-hours 4 --reason "INC-1234 DB investigation"

``--tenant`` accepts either the tenant slug or its UUID.  ``--reason`` is
mandatory — break-glass access without a stated reason is not allowed.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("break-glass")


def _resolve_tenant(session, tenant_ref):
    """Look up a tenant by slug first, then by UUID."""
    from backend.persistence.models.tenancy import RegistryTenant  # noqa: PLC0415

    row = (
        session.query(RegistryTenant).filter(RegistryTenant.slug == tenant_ref).first()
    )
    if row is None:
        row = (
            session.query(RegistryTenant)
            .filter(RegistryTenant.id == tenant_ref)
            .first()
        )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="user to grant access to")
    parser.add_argument("--tenant", required=True, help="tenant slug or UUID")
    parser.add_argument(
        "--ttl-hours",
        type=float,
        default=4.0,
        help="grant lifetime in hours (capped at 72h)",
    )
    parser.add_argument(
        "--role",
        default=None,
        help="grant role (default: support)",
    )
    parser.add_argument(
        "--reason",
        required=True,
        help="why this break-glass access is needed (audited)",
    )
    args = parser.parse_args()

    if not args.reason.strip():
        parser.error("--reason must not be empty (break-glass access is audited)")

    from backend.config import config as app_config  # noqa: PLC0415
    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_REGISTRY,
        partition_session,
    )
    from backend.services import registry_service  # noqa: PLC0415

    if not app_config.is_multitenancy_enabled():
        logger.error(
            "Multi-tenancy is not enabled; tenant grants do not apply in "
            "single-tenant mode."
        )
        return 2

    operator = os.environ.get("SUDO_USER") or os.environ.get("USER") or "unknown"
    ttl_seconds = int(args.ttl_hours * 3600)
    role = args.role or registry_service.SUPPORT_GRANT_ROLE

    with partition_session(partition=PARTITION_REGISTRY) as session:
        tenant = _resolve_tenant(session, args.tenant)
        if tenant is None:
            logger.error("Tenant not found: %s", args.tenant)
            return 1
        user = registry_service.ensure_registry_user(session, args.email)
        grant = registry_service.create_support_grant(
            session, user.id, tenant.id, ttl_seconds, role=role
        )
        expires_at = grant.expires_at
        session.commit()

    # Audit — break-glass access must always be logged.
    logger.warning(
        "BREAK-GLASS GRANT issued: user=%s tenant=%s(%s) role=%s expires_at=%s "
        "ttl_hours=%.2f operator=%s reason=%r",
        args.email,
        tenant.slug,
        str(tenant.id),
        role,
        expires_at.isoformat() if expires_at else "?",
        ttl_seconds / 3600.0,
        operator,
        args.reason,
    )
    print(
        f"Granted '{role}' on tenant '{tenant.slug}' to {args.email} until "
        f"{expires_at.isoformat() if expires_at else '?'} (auto-expires; "
        "no manual revocation needed)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
