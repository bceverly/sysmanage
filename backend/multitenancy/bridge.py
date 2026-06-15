"""
Bridge a loaded ``multitenancy_engine`` Pro+ module into the OSS seam.

The Pro+ engine follows the standard SysManage engine convention: it is a
*passive* compiled module that exports ``get_module_info()``, a
``get_multitenancy_engine_router(...)`` factory, and a ``resolve_tenant_engine``
hook — discovered and loaded by ``backend.licensing.module_loader`` like every
other engine.  Engines never register themselves.

This module is the OSS-side glue that *pulls* the loaded engine into the seam:
it wraps the engine's exported functions in an object satisfying the
:class:`~backend.multitenancy.seam.MultitenancyEngine` protocol and calls
``seam.register_engine(...)``.  Keeping the engine passive (OSS pulls) matches
how every other Pro+ engine integrates; keeping the seam as the internal plug
point is what lets the *data-plane resolver* defer to the engine — something a
plain router-factory mount cannot express.

Called once at server start, after ``module_loader`` has loaded modules (see
``backend/startup/lifecycle.py``).  With no engine loaded this is never called
and the OSS built-in path stays in effect — i.e. single-tenant behaviour.
"""

import logging

from backend.multitenancy import seam

logger = logging.getLogger(__name__)


class _EngineAdapter:
    """Adapt a loaded ``multitenancy_engine`` module to the seam protocol.

    Thin delegation only — the engine module holds the logic.  Imports of OSS
    dependencies for the control-plane router are deferred to call time so this
    adapter has no import-time coupling to FastAPI or the route layer.
    """

    def __init__(self, module):
        self._module = module

    def resolve_tenant_engine(self, tenant_id):
        """Data-plane hook: per-tenant engine resolution (runtime hot path)."""
        return self._module.resolve_tenant_engine(tenant_id)

    def control_plane_router(self):
        """Build the control-plane router from the engine's factory.

        Hands the engine the same dependency-injection arguments
        ``proplus_routes`` passes every engine, so the wiring is uniform.  Not
        used until the Phase 2 stub -> engine mount swap (this phase the OSS
        server still mounts the control plane itself), but implemented so the
        seam protocol is fully satisfied.
        """
        # Late imports: only pulled in if/when the router is actually built.
        from fastapi import Depends, HTTPException, status  # noqa: PLC0415

        from backend.api.proplus_routes import (  # noqa: PLC0415
            _feature_dependency,
            _module_dependency,
        )
        from backend.auth.auth_bearer import get_current_user  # noqa: PLC0415
        from backend.persistence import models  # noqa: PLC0415
        from backend.persistence.db import get_db  # noqa: PLC0415

        return self._module.get_multitenancy_engine_router(
            db_dependency=Depends(get_db),
            auth_dependency=Depends(get_current_user),
            feature_gate=_feature_dependency,
            module_gate=_module_dependency,
            models=models,
            http_exception=HTTPException,
            status_codes=status,
            logger=logger,
        )


def bridge_loaded_engine(module) -> bool:
    """Register a loaded ``multitenancy_engine`` module into the seam.

    Args:
        module: the loaded engine module (from ``module_loader.get_module(
            "multitenancy_engine")``), or ``None`` if it isn't loaded.

    Returns:
        True if an engine was bridged and registered; False otherwise (no
        engine loaded → OSS stays on its built-in single-tenant path).
    """
    if module is None:
        return False

    # Sanity-check the contract before registering, so a malformed/partial
    # module fails loudly here rather than at the first tenant resolution.
    for symbol in ("resolve_tenant_engine", "get_multitenancy_engine_router"):
        if not callable(getattr(module, symbol, None)):
            logger.error(
                "multitenancy_engine is loaded but missing required hook %r; "
                "NOT bridging — falling back to the OSS built-in path.",
                symbol,
            )
            return False

    seam.register_engine(_EngineAdapter(module))
    version = "unknown"
    try:
        version = module.get_module_info().get("version", "unknown")
    except Exception as exc:  # noqa: BLE001 - version is best-effort logging only
        logger.debug("Could not read multitenancy_engine module info: %s", exc)
    logger.info("Bridged multitenancy_engine v%s into the multi-tenancy seam.", version)
    return True
