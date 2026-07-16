# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Migration status — OSS shim (Pro+ relocation, Phase 2).

Detects tenant databases that lag the tenant Alembic chain's code head (drives
the non-blocking UI banner).  The detection logic moved into the licensed
engine; this shim returns the empty/zero result when the engine isn't loaded —
single-tenant / unlicensed servers have no tenant databases to be behind.
"""

from backend.multitenancy import seam


def pending_tenant_migrations() -> dict:
    """Return tenant DBs behind the code head.

    Shape: ``{"tenants_pending": int, "tenant_slugs": [...], "tenant_head": str}``.
    Empty/zero when the multi-tenancy engine isn't loaded.
    """
    engine = seam.engine_module()
    if engine is None:
        return {"tenants_pending": 0, "tenant_slugs": [], "tenant_head": None}
    return engine.pending_tenant_migrations()
