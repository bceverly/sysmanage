#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="immediately revoke the grant (expire it now + tear down its "
        "OpenBAO lease) instead of issuing one",
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

        if args.revoke:
            grant = registry_service.revoke_support_grant(session, user.id, tenant.id)
            session.commit()
            if grant is None:
                logger.error(
                    "No grant to revoke for user=%s tenant=%s", args.email, tenant.slug
                )
                return 1
            logger.warning(
                "BREAK-GLASS GRANT revoked: user=%s tenant=%s(%s) operator=%s "
                "reason=%r",
                args.email,
                tenant.slug,
                str(tenant.id),
                operator,
                args.reason,
            )
            print(
                f"Revoked access on tenant '{tenant.slug}' for {args.email} "
                "(grant expired now; any OpenBAO lease torn down)."
            )
            return 0

        grant = registry_service.create_support_grant(
            session, user.id, tenant.id, ttl_seconds, role=role
        )
        # Bind the grant to a live OpenBAO lease (best-effort; no-op when vault
        # is disabled — expires_at still enforces the window).
        accessor = registry_service.bind_support_lease(
            grant,
            ttl_seconds,
            metadata={
                "email": args.email,
                "tenant": tenant.slug,
                "role": role,
                "operator": operator,
            },
        )
        expires_at = grant.expires_at
        session.commit()

    # Audit — break-glass access must always be logged.
    logger.warning(
        "BREAK-GLASS GRANT issued: user=%s tenant=%s(%s) role=%s expires_at=%s "
        "ttl_hours=%.2f operator=%s lease=%s reason=%r",
        args.email,
        tenant.slug,
        str(tenant.id),
        role,
        expires_at.isoformat() if expires_at else "?",
        ttl_seconds / 3600.0,
        operator,
        accessor or "none",
        args.reason,
    )
    lease_note = (
        f" OpenBAO lease={accessor}." if accessor else " (no OpenBAO lease bound.)"
    )
    print(
        f"Granted '{role}' on tenant '{tenant.slug}' to {args.email} until "
        f"{expires_at.isoformat() if expires_at else '?'} (auto-expires; revoke "
        f"early with --revoke).{lease_note}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
