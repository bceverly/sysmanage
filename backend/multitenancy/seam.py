"""
Multi-tenancy engine seam — the OSS plug point for the licensed engine.

Phase 0 of the Pro+ relocation (see ``docs/multitenancy-proplus-relocation.md``).
Multi-tenancy is becoming a commercial-only capability implemented in a compiled,
license-gated Cython engine (``multitenancy_engine``).  This module is the single
place that engine registers itself, and the few OSS decision points that need
tenant behavior consult it here.

**Open-source safety invariant:** when no engine is registered, every consult
falls back to OSS's built-in behavior, so an OSS build (or the current
pre-relocation state) works *exactly* as before.  As the implementation moves
into the engine in later phases, those OSS fallbacks are removed — leaving the
licensed engine as the only provider.  That absence *is* the technical moat: a
fork of the public repo has the schema + seams but none of the tenant logic.

The engine object the engine registers is duck-typed to :class:`MultitenancyEngine`;
new hooks are added to that protocol as later phases move more logic across.
"""

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class MultitenancyEngine(Protocol):
    """What the licensed ``multitenancy_engine`` provides to OSS seam points."""

    def control_plane_router(self):
        """Return the FastAPI router for the control-plane API."""

    def resolve_tenant_engine(self, tenant_id):
        """Return the SQLAlchemy engine for ``tenant_id``'s database."""


_engine: Optional[MultitenancyEngine] = None
# The raw loaded engine module, exposed for OSS *service shims* (modules whose
# logic moved into the engine) that delegate to relocated functions by name —
# e.g. ``seam.engine_module().tenant_for_host(...)``.  Kept separate from the
# protocol adapter above so the growing set of relocated service functions
# doesn't bloat ``MultitenancyEngine``.
_engine_module = None


def register_engine(engine: MultitenancyEngine, module=None) -> None:
    """Register the licensed multi-tenancy engine (called on engine load).

    ``engine`` is the protocol adapter; ``module`` is the raw engine module that
    backs it (used by service shims).  ``module`` is optional so existing tests
    that register a bare stub keep working.
    """
    global _engine, _engine_module  # pylint: disable=global-statement
    _engine = engine
    _engine_module = module


def unregister_engine() -> None:
    """Clear the registered engine (engine unload / tests)."""
    global _engine, _engine_module  # pylint: disable=global-statement
    _engine = None
    _engine_module = None


def active_engine() -> Optional[MultitenancyEngine]:
    """Return the registered engine adapter, or None when running open-source."""
    return _engine


def engine_module():
    """Return the raw loaded engine module (for service-shim delegation), or
    None when running open-source."""
    return _engine_module


def is_engine_present() -> bool:
    """True when a licensed multi-tenancy engine is loaded."""
    return _engine is not None
