"""
Migration status — detect tenant databases that are behind the code (Phase 13.1).

After a package upgrade, the control-plane schema is migrated by the operator,
but each tenant database is migrated by the per-tenant fan-out
(``sysmanage-migrate``).  A tenant DB can silently lag the code (the server runs
fine against the control plane), so the UI surfaces a non-blocking banner.

This compares each tenant's recorded revision (``registry_tenant_db_version``)
to the tenant Alembic chain's code head.  Best-effort: never raises.
"""

import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)


def _tenant_chain_head() -> Optional[str]:
    """The tenant Alembic chain's head revision in the running code."""
    try:
        from alembic.config import Config  # noqa: PLC0415
        from alembic.script import ScriptDirectory  # noqa: PLC0415

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        cfg = Config(os.path.join(repo_root, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(repo_root, "alembic"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not resolve tenant chain head: %s", exc)
        return None


def pending_tenant_migrations() -> dict:
    """Return tenant DBs behind the code head.

    Shape: ``{"tenants_pending": int, "tenant_slugs": [...], "tenant_head": str}``.
    Empty/zero when multi-tenancy is disabled or nothing is behind.
    """
    result = {"tenants_pending": 0, "tenant_slugs": [], "tenant_head": None}
    try:
        from backend.config import config  # noqa: PLC0415

        if not config.is_multitenancy_enabled():
            return result

        head = _tenant_chain_head()
        result["tenant_head"] = head

        from backend.persistence.models.tenancy import (  # noqa: PLC0415
            RegistryTenant,
            RegistryTenantDbVersion,
        )
        from backend.persistence.partitions import (  # noqa: PLC0415
            PARTITION_REGISTRY,
            partition_session,
        )

        pending: List[str] = []
        with partition_session(partition=PARTITION_REGISTRY) as session:
            tenants = session.query(RegistryTenant).order_by(RegistryTenant.slug).all()
            for tenant in tenants:
                ver = (
                    session.query(RegistryTenantDbVersion)
                    .filter(
                        RegistryTenantDbVersion.tenant_id == tenant.id,
                        RegistryTenantDbVersion.chain == "tenant",
                    )
                    .first()
                )
                current = ver.revision if ver else None
                # A tenant is "behind" only if we know the head and its recorded
                # revision differs (or it was never recorded).  If head is
                # unknown, don't cry wolf.
                if head is not None and current != head:
                    pending.append(tenant.slug)
        result["tenants_pending"] = len(pending)
        result["tenant_slugs"] = pending
    except Exception as exc:  # noqa: BLE001 - status must never break the app
        logger.debug("pending_tenant_migrations failed: %s", exc)
    return result
