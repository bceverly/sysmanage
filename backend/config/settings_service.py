"""
Server-scoped settings accessor — Phase 13.1.H (config classification).

Implements the "**operational config goes to a Settings table**" rule from
``docs/planning/config-classification.md`` §1/§4 for **server-scoped**
options (jwt timeouts, cookie domain, message-queue tunables, monitoring
heartbeat, license phone-home, geo-lookup non-secrets, …).

Values live in the ``settings`` JSON bag on the ``server_configuration``
singleton, edited via the Settings UI.  During the migration window the
legacy ``sysmanage.yaml`` value is honored as a fallback with a one-time
deprecation warning, so a deployment that hasn't migrated keeps working.

This is the additive backbone: it changes no call sites on its own.  Each
option is migrated by switching its accessor to call :func:`get_setting`
with a ``yaml_getter`` that returns the legacy value, then dropping the
YAML key in a later major.  Tenant-scoped settings (email, password policy)
use ``registry_tenant.settings`` instead — added in a later slice.

All DB access is best-effort and never raises: if the DB/column isn't
available (e.g. before the n11cfgsettings migration runs), it returns the
YAML fallback or ``default``.
"""

import logging
import threading
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# One-time deprecation warning per key.
_warned: set = set()

# Short-TTL cache of the server settings bag so per-option reads don't hit the
# DB every time (e.g. on a request hot path).  Invalidated on write.
_CACHE_TTL_SECONDS = 30
_cache_lock = threading.Lock()
_cache_bag: Optional[dict] = None
_cache_expiry: float = 0.0


def invalidate_cache() -> None:
    """Drop the cached settings bag (call after writing a setting)."""
    global _cache_bag, _cache_expiry  # pylint: disable=global-statement
    with _cache_lock:
        _cache_bag = None
        _cache_expiry = 0.0


def _get_cached_settings_bag() -> Optional[dict]:
    """Return the settings bag, using a short-TTL cache.

    The cache is bypassed under the test harness, where each test gets its own
    fresh in-memory database — caching there would leak one test's settings
    into the next.
    """
    global _cache_bag, _cache_expiry  # pylint: disable=global-statement
    try:
        from backend.persistence import db  # noqa: PLC0415

        if getattr(db, "IS_TEST_MODE", False):
            return _read_settings_bag()
    except Exception:  # noqa: BLE001
        # Non-fatal: if the db module can't be probed, fall through to the
        # normal cached read path below.
        _ = None
    now = time.time()
    with _cache_lock:
        if _cache_bag is not None and now < _cache_expiry:
            return _cache_bag
    bag = _read_settings_bag()
    with _cache_lock:
        _cache_bag = bag
        _cache_expiry = now + _CACHE_TTL_SECONDS
    return bag


def _read_settings_bag() -> Optional[dict]:
    """Return the server_configuration.settings dict; None on any failure."""
    try:
        # Late imports avoid an import cycle (db/models) and keep this module
        # importable in contexts that never touch the DB.
        from backend.persistence.db import get_db  # noqa: PLC0415
        from backend.persistence.models.server_configuration import (  # noqa: PLC0415
            ServerConfiguration,
        )

        db_gen = get_db()
        session = next(db_gen)
        try:
            row = session.query(ServerConfiguration).first()
            if row is None:
                return None
            bag = getattr(row, "settings", None)
            return bag if isinstance(bag, dict) else None
        finally:
            db_gen.close()
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.debug("server settings unavailable: %s", exc)
        return None


def get_setting(
    key: str,
    yaml_getter: Optional[Callable[[], Any]] = None,
    *,
    default: Any = None,
) -> Any:
    """Return server setting ``key``, preferring the DB over the YAML fallback.

    Args:
        key: the setting's key within ``server_configuration.settings``.
        yaml_getter: zero-arg callable returning the legacy YAML value.  When
            it supplies the value, a one-time deprecation warning is logged.
        default: returned when neither the DB nor YAML has the setting.
    """
    bag = _get_cached_settings_bag()
    if bag is not None and key in bag and bag[key] is not None:
        return bag[key]

    if yaml_getter is not None:
        try:
            legacy = yaml_getter()
        except Exception as exc:  # noqa: BLE001
            logger.debug("YAML fallback for setting %r failed: %s", key, exc)
            legacy = None
        if legacy is not None:
            if key not in _warned:
                logger.warning(
                    "Setting '%s' is being read from sysmanage.yaml. Operational "
                    "config should live in the Settings DB — see "
                    "docs/planning/config-classification.md (Phase 13.1.H). The "
                    "YAML fallback will be removed in a future major.",
                    key,
                )
                _warned.add(key)
            return legacy

    return default


def set_setting(key: str, value: Any) -> bool:
    """Upsert ``key`` into the server_configuration settings bag.

    Returns True on success, False if the DB/column isn't available.  Creates
    the singleton row if it doesn't exist yet.
    """
    try:
        from backend.persistence.db import get_db  # noqa: PLC0415
        from backend.persistence.models.server_configuration import (  # noqa: PLC0415
            SINGLETON_SERVER_CONFIG_ID,
            ServerConfiguration,
        )

        db_gen = get_db()
        session = next(db_gen)
        try:
            row = session.query(ServerConfiguration).first()
            if row is None:
                row = ServerConfiguration(id=SINGLETON_SERVER_CONFIG_ID)
                session.add(row)
            bag = dict(row.settings) if isinstance(row.settings, dict) else {}
            bag[key] = value
            # Reassign (not in-place mutate) so SQLAlchemy detects the change
            # on the JSON column.
            row.settings = bag
            session.commit()
            invalidate_cache()
            return True
        finally:
            db_gen.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not persist server setting %r: %s", key, exc)
        return False


# ---------------------------------------------------------------------------
# Tenant-scoped settings (Phase 13.1) — per-tenant operational config (email,
# password policy, …) stored in ``registry_tenant.settings``.  Only meaningful
# when multi-tenancy is enabled; in single-tenant / collapsed mode callers use
# the server-scoped accessors above.  Not cached: tenant reads are far less hot
# than server reads, and a per-tenant cache would have to be keyed by tenant.
# ---------------------------------------------------------------------------


def _read_tenant_settings_bag(tenant_id: str) -> Optional[dict]:
    """Return ``registry_tenant.settings`` for ``tenant_id``; None on failure."""
    try:
        from backend.persistence.models.tenancy import (  # noqa: PLC0415
            RegistryTenant,
        )
        from backend.persistence.partitions import (  # noqa: PLC0415
            PARTITION_REGISTRY,
            partition_session,
        )

        with partition_session(partition=PARTITION_REGISTRY) as session:
            row = (
                session.query(RegistryTenant)
                .filter(RegistryTenant.id == tenant_id)
                .first()
            )
            if row is None:
                return None
            bag = getattr(row, "settings", None)
            return bag if isinstance(bag, dict) else None
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.debug("tenant settings unavailable for %s: %s", tenant_id, exc)
        return None


def get_tenant_setting(
    tenant_id: str,
    key: str,
    *,
    default: Any = None,
) -> Any:
    """Return tenant-scoped setting ``key`` for ``tenant_id``, else ``default``.

    No YAML fallback: per-tenant config has no YAML representation.  Callers
    that want "tenant value, else server value, else YAML" compose this with
    :func:`get_setting` (see ``config._db_setting``).
    """
    bag = _read_tenant_settings_bag(tenant_id)
    if bag is not None and key in bag and bag[key] is not None:
        return bag[key]
    return default


def set_tenant_setting(tenant_id: str, key: str, value: Any) -> bool:
    """Upsert ``key`` into ``registry_tenant.settings`` for ``tenant_id``.

    Returns True on success, False if the tenant row or registry isn't
    available.  Unlike the server settings, the tenant row must already exist
    (tenants are created via the control plane), so this never creates it.
    """
    try:
        from backend.persistence.models.tenancy import (  # noqa: PLC0415
            RegistryTenant,
        )
        from backend.persistence.partitions import (  # noqa: PLC0415
            PARTITION_REGISTRY,
            partition_session,
        )

        with partition_session(partition=PARTITION_REGISTRY) as session:
            row = (
                session.query(RegistryTenant)
                .filter(RegistryTenant.id == tenant_id)
                .first()
            )
            if row is None:
                logger.debug(
                    "cannot set tenant setting: tenant %s not found", tenant_id
                )
                return False
            bag = dict(row.settings) if isinstance(row.settings, dict) else {}
            bag[key] = value
            # Reassign so SQLAlchemy detects the JSON-column change.
            row.settings = bag
            session.commit()
            return True
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "could not persist tenant setting %r for %s: %s", key, tenant_id, exc
        )
        return False
