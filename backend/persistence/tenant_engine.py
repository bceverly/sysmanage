"""
Per-tenant engine manager — Phase 13.1.C (design §8).

Routes a ``tenant_id`` to a SQLAlchemy engine bound to that tenant's database,
using **dynamic, short-lived credentials leased from OpenBAO** rather than any
stored password.  Hitting OpenBAO per request would be fatal for latency, so:

  * the lease is cached **in process memory only** (never disk, never logs),
    keyed by tenant;
  * a **per-tenant warm connection pool** hangs off the cached credential;
  * the lease is **proactively renewed** before it expires (renewal keeps the
    same DB user, so the engine stays valid);
  * once a lease passes its hard expiry it is **re-acquired** (new credential →
    new engine);
  * on a DB **auth failure** (credential rotated/revoked under us) the entry is
    **evicted and re-leased** — that is the revocation path.

Blast radius of a process-memory compromise is limited to the tenants that
process is actively serving.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.services import openbao_db_secrets
from backend.utils.log_sanitize import scrub

logger = logging.getLogger(__name__)

# Renew the lease once two-thirds of its lifetime has elapsed.
_RENEW_FRACTION = 2.0 / 3.0


@dataclass
class _Entry:
    engine: Engine
    lease: openbao_db_secrets.DbLease
    acquired_at: float
    renew_at: float
    hard_expiry: float
    last_used: float = field(default_factory=time.time)


class TenantEngineManager:
    """In-process cache of per-tenant engines backed by OpenBAO DB leases."""

    def __init__(self):
        self._entries: Dict[str, _Entry] = {}
        self._lock = threading.Lock()

    # -- public API --------------------------------------------------------

    def get_engine(self, tenant_id, *, force_refresh: bool = False) -> Engine:
        """Return a live engine for ``tenant_id``, leasing/renewing as needed."""
        key = str(tenant_id)
        if force_refresh:
            self._evict(key)

        with self._lock:
            entry = self._entries.get(key)
            now = time.time()
            if entry is not None and now < entry.hard_expiry:
                entry.last_used = now
                if now >= entry.renew_at:
                    self._try_renew(entry)
                return entry.engine

        # Cache miss or hard-expired: acquire outside the lock (network I/O),
        # then install.
        entry = self._acquire(key)
        with self._lock:
            # Another thread may have raced us; keep the first one installed.
            existing = self._entries.get(key)
            if existing is not None and time.time() < existing.hard_expiry:
                self._dispose(entry)
                return existing.engine
            self._entries[key] = entry
            return entry.engine

    def handle_auth_failure(self, tenant_id) -> None:
        """Evict + revoke a tenant's lease after a DB auth failure.

        The next :meth:`get_engine` re-leases fresh credentials.  This is the
        path taken when OpenBAO rotated/revoked the credential under us.
        """
        self._evict(str(tenant_id), revoke=True)

    def invalidate(self, tenant_id) -> None:
        """Drop a tenant's cached engine + lease (e.g. on tenant suspend)."""
        self._evict(str(tenant_id), revoke=True)

    def shutdown(self) -> None:
        """Dispose all engines + revoke all leases (process shutdown)."""
        with self._lock:
            keys = list(self._entries)
        for key in keys:
            self._evict(key, revoke=True)

    # -- internals ---------------------------------------------------------

    def _acquire(self, key: str) -> _Entry:
        placement = _load_placement(key)
        if placement is None:
            raise LookupError(f"No placement registered for tenant {key}")
        if not placement.openbao_role:
            raise LookupError(
                f"Tenant {key} placement has no openbao_role to lease credentials"
            )

        lease = openbao_db_secrets.lease_credentials(placement.openbao_role)
        url = _build_url(placement, lease)
        engine = create_engine(
            url,
            pool_pre_ping=True,  # detect a revoked cred before handing out a conn
            pool_size=5,
            max_overflow=5,
            pool_recycle=max(60, lease.lease_duration - 30),
            echo=False,
        )
        now = time.time()
        ttl = max(60, lease.lease_duration)
        entry = _Entry(
            engine=engine,
            lease=lease,
            acquired_at=now,
            renew_at=now + ttl * _RENEW_FRACTION,
            hard_expiry=now + ttl,
        )
        # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        # Logs the tenant id + TTL only — never the leased credential itself.
        logger.info("Leased DB credentials for tenant %s (ttl=%ss)", scrub(key), ttl)
        return entry

    def _try_renew(self, entry: _Entry) -> None:
        """Best-effort lease renewal; same credential, so the engine stays."""
        new_ttl = openbao_db_secrets.renew_lease(entry.lease.lease_id)
        if new_ttl > 0:
            now = time.time()
            entry.renew_at = now + new_ttl * _RENEW_FRACTION
            entry.hard_expiry = now + new_ttl
            logger.debug("Renewed tenant lease (ttl=%ss)", new_ttl)
        # If renew failed, hard_expiry stands; the entry re-acquires when it
        # passes hard_expiry.

    def _evict(self, key: str, *, revoke: bool = False) -> None:
        with self._lock:
            entry = self._entries.pop(key, None)
        if entry is None:
            return
        if revoke and entry.lease.lease_id:
            openbao_db_secrets.revoke_lease(entry.lease.lease_id)
        self._dispose(entry)

    @staticmethod
    def _dispose(entry: _Entry) -> None:
        try:
            entry.engine.dispose()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Engine dispose failed: %s", exc)


def _load_placement(tenant_id: str):
    """Look up a tenant's placement row from the registry partition."""
    # Late imports avoid a cycle (partitions -> tenant_engine -> partitions).
    from backend.persistence.models.tenancy import (  # noqa: PLC0415
        RegistryTenantPlacement,
    )
    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_REGISTRY,
        partition_session,
    )

    with partition_session(partition=PARTITION_REGISTRY) as session:
        return (
            session.query(RegistryTenantPlacement)
            .filter(RegistryTenantPlacement.tenant_id == tenant_id)
            .first()
        )


def _build_url(placement, lease: openbao_db_secrets.DbLease) -> str:
    """Build a PostgreSQL URL from placement coordinates + leased credentials."""
    host = placement.host or "localhost"
    port = placement.port or 5432
    dbname = placement.dbname or "sysmanage"
    return f"postgresql://{lease.username}:{lease.password}@{host}:{port}/{dbname}"


# Process-wide singleton.
_manager: Optional[TenantEngineManager] = None
_manager_lock = threading.Lock()


def get_manager() -> TenantEngineManager:
    """Return the process-wide tenant engine manager."""
    global _manager  # pylint: disable=global-statement
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = TenantEngineManager()
    return _manager
