"""Per-tenant edition resolution — OSS shim (Phase 13.1.J; engine-backed).

Each tenant is independently assigned a feature surface — ``community`` |
``professional`` | ``enterprise`` — stored in ``registry_tenant.edition``.  Module
and feature gating should resolve against the **active tenant's** edition rather
than one global license tier.

Per the multi-tenancy moat, the actual resolution (which tenant is active, and
its edition) — and the Platform-Operator authorization to change it — live in the
licensed ``multitenancy_engine``.  This OSS shim is the seam the gating layer
calls: it delegates to the engine when present and degrades to ``None`` when it
isn't.  ``None`` means *no per-tenant edition is in scope* — gating then falls
back to the global license tier, exactly the single-tenant / unlicensed behaviour
callers already expect (multi-tenancy is exclusive to the top SaaS tier).
"""

from typing import Optional

from backend.multitenancy import seam


def edition_for_active_tenant() -> Optional[str]:
    """Return the active tenant's edition, or ``None`` for server/global scope.

    ``None`` is returned when the licensed engine is absent (single-tenant or
    unlicensed) or when no tenant is in scope; callers must treat it as "use the
    global license tier".  An older engine that predates this seam also yields
    ``None`` (graceful degradation), never an error.
    """
    engine = seam.engine_module()
    if engine is None:
        return None
    resolver = getattr(engine, "edition_for_active_tenant", None)
    if not callable(resolver):
        return None
    return resolver()  # pylint: disable=not-callable  # narrowed by callable() above
