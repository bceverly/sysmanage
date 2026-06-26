"""
Host→tenant index — OSS shim (Pro+ relocation, Phase 2).

The server-global map from a host id to the tenant whose database owns that
host's data.  The implementation moved into the licensed ``multitenancy_engine``
(the OSS build has no copy), so these are thin delegators: with no engine loaded
they degrade to the best-effort no-op contract (writes return False, the read
returns None) — which is correct for a single-tenant / unlicensed deployment
where there is no host→tenant binding to record or look up.
"""

from typing import Optional

from backend.multitenancy import seam


def bind_host_to_tenant(host_id, tenant_id) -> bool:
    """Record (or update) the host→tenant binding.  Returns True on success.

    Returns False when the multi-tenancy engine isn't loaded (nothing to bind).
    """
    engine = seam.engine_module()
    if engine is None:
        return False
    return engine.bind_host_to_tenant(host_id, tenant_id)


def tenant_for_host(host_id) -> Optional[str]:
    """Return the tenant id that owns ``host_id``, or None.  Never raises.

    Returns None when multi-tenancy isn't active — the data plane then treats
    the host as server-scoped, which is the single-tenant behavior.
    """
    engine = seam.engine_module()
    if engine is None:
        return None
    return engine.tenant_for_host(host_id)


def unbind_host(host_id) -> bool:
    """Remove a host's binding.  No-op (False) when the engine isn't loaded."""
    engine = seam.engine_module()
    if engine is None:
        return False
    return engine.unbind_host(host_id)
