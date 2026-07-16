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

import logging
from contextlib import contextmanager

from sqlalchemy.orm import sessionmaker

from backend.config import config
from backend.persistence import db
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)

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

    # Per-tenant routing is licensed-engine territory (Pro+ relocation, Phase 2):
    # the per-tenant engine cache + OpenBAO dynamic-credential leasing live in
    # the compiled ``multitenancy_engine`` — the OSS build has NO copy of that
    # logic.  With no engine registered there is no fallback: resolving a tenant
    # database is impossible without the licensed engine.  This is the moat.
    from backend.multitenancy import seam  # noqa: PLC0415

    engine = seam.active_engine()
    if engine is None:
        raise RuntimeError(
            "Per-tenant database routing requires the licensed multi-tenancy "
            "engine, which is not loaded. Multi-tenancy is a Pro+ "
            "MULTITENANT_SAAS capability."
        )
    return engine.resolve_tenant_engine(tenant_id)


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


def shared_sessionmaker():
    """A sessionmaker bound to the ``shared`` partition's engine.

    Use this to read/write canonical reference data (``shared_*`` tables, e.g.
    the mirror version catalog) regardless of which tenant is active.  In
    collapsed / single-tenant mode this resolves to the one application engine,
    so it is behaviourally identical to a normal session; in multi-tenant mode it
    routes to the shared engine rather than the active tenant's database, where
    the shared tables do not live.
    """
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=resolve_engine(partition=PARTITION_SHARED),
    )


def get_shared_db():
    """FastAPI dependency yielding a session on the ``shared`` partition.

    Drop-in for endpoints that read shared reference data (the version catalog).
    """
    session = shared_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def _open_bootstrap_session():
    """Open a session on the bootstrap / main database.

    Kept as its own (non-generator) function so ``next(get_db())``'s
    ``StopIteration`` can't leak into the ``iter_host_databases`` generator
    frame and turn into a ``RuntimeError`` (PEP 479)."""
    # Imported here to avoid a module-level import cycle (db imports models).
    from backend.persistence.db import get_db  # noqa: PLC0415

    return next(get_db())


def iter_host_databases(bootstrap_session=None):
    """Yield ``(label, tenant_id, session)`` for the bootstrap database and
    every provisioned tenant database.

    Once a host is bound to a tenant (Phase 13.1) its row lives in that tenant's
    database, so any *server-wide* operation that must reach every host — the
    heartbeat sweep, a fleet broadcast, fleet-role discovery — has to visit each
    host-bearing database, not just the bootstrap one.  In single-tenant /
    ``multitenancy.enabled`` false mode this yields ONLY the bootstrap database,
    identical to the prior single-DB behaviour, so callers are inert until
    multi-tenancy is actually turned on.

    ``tenant_id`` is ``None`` for the bootstrap database and the tenant's id for
    each tenant database.  Each tenant is resolved independently: if the tenant
    list or one tenant's engine can't be resolved it is logged and skipped, so
    one bad tenant (or an unreachable registry) can't stall the whole sweep — the
    bootstrap database is always visited.

    ``bootstrap_session``: a request-context caller (e.g. the broadcast endpoint)
    that already holds the request's ``Depends(get_db)`` session should pass it
    here so the bootstrap leg runs on the SAME session — both to avoid opening a
    second connection and, critically, so the request's database (including a
    test's dependency-injected one) is the one visited rather than a freshly
    opened module-global session.  When passed, the caller owns it and must NOT
    close it (it is closed by the dependency); compare yielded sessions by
    identity to skip closing it.  Background sweeps that have no request session
    omit it and ``iter_host_databases`` opens (and the caller closes) its own.
    """
    if bootstrap_session is not None:
        yield ("bootstrap", None, bootstrap_session)
    else:
        try:
            bootstrap = _open_bootstrap_session()
        except Exception:  # noqa: BLE001
            logger.exception(
                "iter_host_databases: failed to open the bootstrap session"
            )
            return
        yield ("bootstrap", None, bootstrap)

    if not config.is_multitenancy_enabled():
        return

    from backend.persistence.models import RegistryTenantPlacement  # noqa: PLC0415

    try:
        with partition_session(partition=PARTITION_REGISTRY) as registry_session:
            rows = (
                registry_session.query(RegistryTenantPlacement.tenant_id)
                .distinct()
                .all()
            )
        tenant_ids = [str(tenant_id) for (tenant_id,) in rows]
    except Exception:  # noqa: BLE001
        logger.exception(
            "iter_host_databases: could not list provisioned tenants; visiting the "
            "bootstrap database only this pass",
        )
        return

    for tenant_id in tenant_ids:
        try:
            engine = resolve_engine(partition=PARTITION_TENANT, tenant_id=tenant_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "iter_host_databases: could not resolve the engine for tenant %s; "
                "skipping its hosts this pass",
                sanitize_log(tenant_id),
            )
            continue
        yield (
            f"tenant {tenant_id}",
            tenant_id,
            sessionmaker(autocommit=False, autoflush=False, bind=engine)(),
        )


def provisioned_tenant_ids():
    """Return the ids of every tenant that has a provisioned database (a
    placement row in the registry), or ``[]`` when multi-tenancy is off or the
    registry can't be read (logged, never silently swallowed).

    Use this to fan a *worker-thread / background* read out across tenants where
    the active-tenant ContextVar isn't available (e.g. a report built in a
    ``run_in_executor`` thread): the request handler decides the scope and
    threads an explicit tenant-id list down, since
    :func:`iter_request_host_databases` reads a ContextVar that doesn't cross the
    thread boundary.
    """
    if not config.is_multitenancy_enabled():
        return []
    from backend.persistence.models import RegistryTenantPlacement  # noqa: PLC0415

    try:
        with partition_session(partition=PARTITION_REGISTRY) as registry_session:
            rows = (
                registry_session.query(RegistryTenantPlacement.tenant_id)
                .distinct()
                .all()
            )
        return [str(tenant_id) for (tenant_id,) in rows]
    except Exception:  # noqa: BLE001
        logger.exception(
            "provisioned_tenant_ids: could not list provisioned tenants from the "
            "registry",
        )
        return []


def iter_request_host_databases():
    """Yield ``(label, tenant_id, session)`` for a fleet-wide READ, honouring the
    request's tenant scope.

    This is the read-side companion to :func:`iter_host_databases` (which always
    visits every database — correct for server-wide *operations* like the
    heartbeat sweep or a broadcast).  Fleet-wide *reads* (a fleet list, a
    compliance/AV summary, a multi-host report) instead respect who is asking:

      * **An active tenant is set** (a tenant-scoped view) → yields ONLY that
        tenant's database, so a tenant user sees just their own fleet — tenant
        isolation is preserved.
      * **No active tenant** (a server-admin / all-tenants view, or multi-tenancy
        disabled) → yields the bootstrap database AND every provisioned tenant
        database, so an operator sees the whole fleet aggregated.

    The CALLER MUST ``close()`` every yielded session (matches
    :func:`iter_host_databases`).
    """
    from backend.persistence.tenant_context import (  # noqa: PLC0415
        get_active_tenant,
    )

    active = get_active_tenant()
    if active and config.is_multitenancy_enabled():
        yield ("active-tenant", active, request_sessionmaker()())
        return
    yield from iter_host_databases()


def tenant_engine_for_host(host_id):
    """Return the TENANT engine serving ``host_id``'s data, or ``None``.

    ``None`` means "this host is not tenant-scoped here — use the default
    application session" (single-tenant/collapsed mode, multi-tenancy disabled,
    or a host not yet bound to a tenant).  A non-``None`` engine is returned only
    when multi-tenancy is enabled AND the host has a tenant binding.

    This is the resolver for the store-and-forward queue + background message
    processors (Phase 13.1 #2 — per-tenant queues): they run OUTSIDE any
    request's active-tenant context, so they must resolve the tenant from the
    host→tenant binding rather than the ContextVar.  Returning ``None`` for the
    common case keeps callers on their existing ``get_db()`` path, so the change
    is fully inert until a host is actually bound to a tenant.
    """
    if host_id is None or not config.is_multitenancy_enabled():
        return None
    from backend.services import host_tenant_index  # noqa: PLC0415

    from backend.persistence.db_retry import run_with_db_retry  # noqa: PLC0415

    try:
        # Idempotent, fresh-session read → safe to retry through the brief
        # PostgreSQL-failover window (Phase 15.1) rather than routing this
        # host's data to the wrong place because the primary was mid-promotion.
        tenant_id = run_with_db_retry(host_tenant_index.tenant_for_host, host_id)
    except Exception:  # noqa: BLE001
        # The host→tenant lookup itself failed (e.g. registry unreachable, or the
        # licensed engine that backs the index isn't loaded).  Do NOT silently
        # fall through to the bootstrap DB — that would route this host's data to
        # the wrong database.  Log loudly with context and re-raise.
        # logger.exception (not error+exc_info) and sanitize the agent-supplied
        # host_id before logging it (it is user-controlled → log-injection guard).
        logger.exception(
            "tenant routing FAILED: host→tenant lookup errored for host %s; "
            "cannot determine the tenant database (multi-tenancy is enabled)",
            sanitize_log(host_id),
        )
        raise
    if not tenant_id:
        # MT is on but this host has no tenant binding → its data goes to the
        # bootstrap database, not a tenant DB.  Routine (server-scoped host or a
        # not-yet-bound agent), but log at DEBUG so the fallback is never a black
        # box when diagnosing "why is this host's data in the wrong place".
        logger.debug(
            "tenant routing: host %s has no tenant binding; using the bootstrap "
            "database (multi-tenancy enabled)",
            sanitize_log(host_id),
        )
        return None
    try:
        engine = resolve_engine(partition=PARTITION_TENANT, tenant_id=tenant_id)
    except Exception:  # noqa: BLE001
        logger.exception(
            "tenant routing FAILED: could not resolve the database engine for "
            "host %s → tenant %s; the message/data cannot reach the tenant "
            "database (is the licensed engine loaded / the tenant provisioned?)",
            sanitize_log(host_id),
            sanitize_log(tenant_id),
        )
        raise
    logger.debug(
        "tenant routing: host %s → tenant %s",
        sanitize_log(host_id),
        sanitize_log(tenant_id),
    )
    return engine
