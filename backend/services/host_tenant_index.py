"""
Host→tenant index (Phase 13.1 data plane).

The server-global map from a host id to the tenant whose database owns that
host's data.  Written at enrollment; read by the data plane (websocket / queue
processors) to route a host's operations to the right tenant database — they
can't discover the tenant by querying the per-tenant DBs without first knowing
which one to look in.

Lives in the **registry** partition.  All operations open their own registry
session so callers don't have to thread one through, and are best-effort
(never raise) on the read path.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def bind_host_to_tenant(host_id, tenant_id) -> bool:
    """Record (or update) the host→tenant binding.  Returns True on success."""
    try:
        from backend.persistence.models.tenancy import (  # noqa: PLC0415
            RegistryHostTenant,
        )
        from backend.persistence.partitions import (  # noqa: PLC0415
            PARTITION_REGISTRY,
            partition_session,
        )

        with partition_session(partition=PARTITION_REGISTRY) as session:
            row = (
                session.query(RegistryHostTenant)
                .filter(RegistryHostTenant.host_id == host_id)
                .first()
            )
            if row is None:
                row = RegistryHostTenant(host_id=host_id, tenant_id=tenant_id)
                session.add(row)
            else:
                row.tenant_id = tenant_id
            session.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to bind host %s to tenant %s: %s", host_id, tenant_id, exc)
        return False


def tenant_for_host(host_id) -> Optional[str]:
    """Return the tenant id that owns ``host_id``, or None.  Never raises."""
    if host_id is None:
        return None
    try:
        from backend.persistence.models.tenancy import (  # noqa: PLC0415
            RegistryHostTenant,
        )
        from backend.persistence.partitions import (  # noqa: PLC0415
            PARTITION_REGISTRY,
            partition_session,
        )

        with partition_session(partition=PARTITION_REGISTRY) as session:
            row = (
                session.query(RegistryHostTenant)
                .filter(RegistryHostTenant.host_id == host_id)
                .first()
            )
            return str(row.tenant_id) if row else None
    except Exception as exc:  # noqa: BLE001 - best-effort lookup
        logger.debug("tenant_for_host(%s) failed: %s", host_id, exc)
        return None


def unbind_host(host_id) -> bool:
    """Remove a host's binding (e.g. when the host is deleted)."""
    try:
        from backend.persistence.models.tenancy import (  # noqa: PLC0415
            RegistryHostTenant,
        )
        from backend.persistence.partitions import (  # noqa: PLC0415
            PARTITION_REGISTRY,
            partition_session,
        )

        with partition_session(partition=PARTITION_REGISTRY) as session:
            session.query(RegistryHostTenant).filter(
                RegistryHostTenant.host_id == host_id
            ).delete(synchronize_session=False)
            session.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to unbind host %s: %s", host_id, exc)
        return False
