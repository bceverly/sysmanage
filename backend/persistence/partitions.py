"""
Partition resolver + tenant-aware session factory — Phase 13.1.A.

Data is split into logical **partitions**: ``registry`` (control plane),
``shared`` (reference data), and one ``tenant`` partition per customer.
The same model definitions deploy across a spectrum of physical layouts,
chosen by **config, not code** (design doc §5):

  * **Homelab / OSS (default, ``multitenancy.enabled`` false).**  All
    partitions collapse into ONE database, distinguished only by the
    ``registry_*`` / ``shared_*`` / unprefixed table-name prefixes.
    There is **no ``schema_translate_map`` and no engine indirection**
    in this mode — the resolver simply always returns the single
    application engine (Bryan, June 2026 — open decision #1).

  * **Scale-out (``multitenancy.enabled`` true).**  The ``registry`` and
    ``shared`` partitions resolve to their own engines, and each
    ``tenant`` partition resolves to its own per-customer database whose
    credentials are brokered dynamically by OpenBAO.  Per-tenant engine
    construction + the OpenBAO lease cache land in **Phase 13.1.C**; this
    module raises a clear, explicit error if a tenant engine is requested
    before that machinery exists, rather than silently misrouting.

Because the resolver is the single chokepoint for "which engine serves
this partition?", turning multi-tenancy on later is a config flip, not a
code change at every call site.
"""

from contextlib import contextmanager

from sqlalchemy.orm import sessionmaker

from backend.config import config
from backend.persistence import db

# Logical partition tokens.
PARTITION_REGISTRY = "registry"
PARTITION_SHARED = "shared"
PARTITION_TENANT = "tenant"
PARTITIONS = (PARTITION_REGISTRY, PARTITION_SHARED, PARTITION_TENANT)


def resolve_engine(partition: str = PARTITION_TENANT, tenant_id=None):
    """Return the SQLAlchemy engine that serves ``partition``.

    Args:
        partition: one of :data:`PARTITIONS`.
        tenant_id: required only when ``partition`` is ``tenant`` and
            multi-tenancy is enabled (selects the customer database).

    In collapsed/homelab mode (``multitenancy.enabled`` false) every
    partition maps to the one application engine — including under the
    test harness, where ``db.get_engine()`` returns the in-memory test
    engine.  This is the path exercised by the default deployment and the
    whole test suite.
    """
    if partition not in PARTITIONS:
        raise ValueError(f"Unknown partition: {partition!r}")

    # Collapsed mode: one engine for everything (prefix-only namespacing).
    if not config.is_multitenancy_enabled():
        return db.get_engine()

    # Multi-tenancy enabled.  The registry and shared partitions are
    # reachable from the bootstrap config; per-tenant engines need the
    # OpenBAO-brokered credential path that lands in Phase 13.1.C.
    if partition in (PARTITION_REGISTRY, PARTITION_SHARED):
        # For now both still collapse onto the bootstrap engine; dedicated
        # registry/shared engines are wired in 13.1.C/13.1.D alongside the
        # placement-driven routing.  Kept explicit so the seam is visible.
        return db.get_engine()

    # partition == PARTITION_TENANT
    if tenant_id is None:
        raise ValueError("tenant_id is required to resolve a tenant engine")

    # Per-tenant routing is licensed-engine territory (Pro+ relocation, Phase 0):
    # defer to the multi-tenancy engine when one is loaded.  The OSS fallback
    # below is the built-in implementation that moves into the engine in a later
    # phase; until then it keeps the open-source build working as today.
    from backend.multitenancy import seam  # noqa: PLC0415

    engine = seam.active_engine()
    if engine is not None:
        return engine.resolve_tenant_engine(tenant_id)

    # OSS fallback: the OpenBAO-leased per-tenant engine (moves to the engine
    # in a later phase).  Late import avoids an import cycle.
    from backend.persistence.tenant_engine import get_manager  # noqa: PLC0415

    return get_manager().get_engine(tenant_id)


def get_sessionmaker(partition: str = PARTITION_TENANT, tenant_id=None):
    """Build a sessionmaker bound to the engine for ``partition``."""
    engine = resolve_engine(partition=partition, tenant_id=tenant_id)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def partition_session(partition: str = PARTITION_TENANT, tenant_id=None):
    """Context-managed session bound to ``partition``'s engine."""
    session_local = get_sessionmaker(partition=partition, tenant_id=tenant_id)
    session = session_local()
    try:
        yield session
    finally:
        session.close()


def get_registry_db():
    """FastAPI dependency yielding a session on the ``registry`` partition.

    Used by the control-plane API (Phase 13.1.A+).  In collapsed mode the
    registry tables live in the one application database, so this is just
    a session on the single engine; in scale-out mode it targets the
    dedicated registry database.
    """
    session_local = get_sessionmaker(partition=PARTITION_REGISTRY)
    session = session_local()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Data-plane request routing (Phase 13.1) — route a request's queries to the
# active tenant's database.  This is the seam that turns multi-tenancy from a
# control-plane concept into per-tenant *data* isolation: a data-plane endpoint
# swaps ``db.get_engine()`` for ``get_request_engine()`` and is then
# automatically tenant-scoped.  Server-global data (auth/users, registry,
# server config) keeps using ``db.get_engine()`` and stays central.
# ---------------------------------------------------------------------------


def get_request_engine(tenant_id=None):
    """Return the engine serving the current request's data.

    The active tenant's engine when multi-tenancy is enabled and a tenant is
    in scope; otherwise the single application engine — identical to
    ``db.get_engine()`` in single-tenant / collapsed mode or server scope.

    ``tenant_id`` may be passed explicitly.  This is REQUIRED when the caller
    runs outside the request's async context — e.g. in a thread-pool executor
    — because the active-tenant ContextVar does not propagate across threads.
    Capture it in the request handler and pass it down.  When omitted, the
    active-tenant ContextVar (bound by the middleware) is consulted.
    """
    if not config.is_multitenancy_enabled():
        return db.get_engine()
    if tenant_id is None:
        from backend.persistence.tenant_context import (  # noqa: PLC0415
            get_active_tenant,
        )

        tenant_id = get_active_tenant()
    if not tenant_id:
        return db.get_engine()
    return resolve_engine(partition=PARTITION_TENANT, tenant_id=tenant_id)


def request_sessionmaker(tenant_id=None):
    """A sessionmaker bound to the current request's engine (see above)."""
    return sessionmaker(
        autocommit=False, autoflush=False, bind=get_request_engine(tenant_id)
    )


def get_tenant_db():
    """FastAPI dependency yielding a session on the active tenant's engine.

    Drop-in for ``Depends(get_db)`` on data-plane endpoints that should be
    tenant-scoped.  Resolves from the active-tenant ContextVar, so it only
    works for handlers that run in the request's async context (not thread-pool
    offloads — those must capture the tenant and use ``request_sessionmaker``).
    """
    session = request_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
