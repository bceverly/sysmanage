# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Self-service tenant provisioning orchestration — OSS shim (Pro+ relocation,
Phase 2).

Creating a tenant's database + OpenBAO dynamic-creds role, recording placement,
running the tenant migration chain, and tearing it all down moved into the
licensed engine — the OSS build has no copy.  This module keeps the public
``OrchestrationError`` (so callers/tests catch the same class the engine raises)
and thin delegators: provisioning ops raise without the engine; the
``is_provisioner_configured`` probe degrades to False.
"""

from typing import Optional

from backend.multitenancy import seam


class OrchestrationError(RuntimeError):
    """Raised when self-service provisioning can't proceed.

    Defined in OSS (part of the public contract) and imported + raised by the
    licensed engine, so ``except OrchestrationError`` works across the boundary.
    """


def _engine_or_raise():
    engine = seam.engine_module()
    if engine is None:
        raise OrchestrationError(
            "Self-service provisioning requires the licensed multi-tenancy "
            "engine, which is not loaded. Multi-tenancy is a Pro+ "
            "MULTITENANT_SAAS capability."
        )
    return engine


def is_provisioner_configured() -> bool:
    """True when the provisioner credential is available.  False without the
    engine (a server with no multi-tenancy can't provision)."""
    engine = seam.engine_module()
    if engine is None:
        return False
    return engine.is_provisioner_configured()


def auto_provision_tenant(
    tenant_id: str,
    *,
    slug: str,
    host: Optional[str] = None,
    port: Optional[int] = None,
    region: Optional[str] = None,
    tier: str = "silo",
) -> dict:
    """End-to-end self-service provisioning for one tenant.  Idempotent."""
    return _engine_or_raise().auto_provision_tenant(
        tenant_id, slug=slug, host=host, port=port, region=region, tier=tier
    )


def deprovision_tenant(tenant_id, *, slug: str, drop_database: bool = False) -> dict:
    """Tear down a tenant: OpenBAO role/config, (optionally) the DB, registry rows."""
    return _engine_or_raise().deprovision_tenant(
        tenant_id, slug=slug, drop_database=drop_database
    )
