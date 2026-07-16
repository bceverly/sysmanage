# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Per-tenant database provisioning — OSS shim (Pro+ relocation, Phase 2).

Runs the tenant Alembic chain against a tenant's database (via the OpenBAO-leased
per-tenant engine) and records the revision in ``registry_tenant_db_version``.
The provisioning logic moved into the licensed engine — there is no OSS copy —
so this raises a clear error without the engine (provisioning a tenant database
is impossible without it).
"""

from backend.multitenancy import seam


def provision_tenant_database(tenant_id) -> str:
    """Bring a tenant DB to the tenant chain's head; return the revision.

    Raises when the multi-tenancy engine isn't loaded.
    """
    engine = seam.engine_module()
    if engine is None:
        raise RuntimeError(
            "Provisioning a tenant database requires the licensed multi-tenancy "
            "engine, which is not loaded. Multi-tenancy is a Pro+ "
            "MULTITENANT_SAAS capability."
        )
    return engine.provision_tenant_database(tenant_id)
