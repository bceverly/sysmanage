"""
Config secrets accessor — Phase 13.1.H (config classification).

Implements the "**secrets go to OpenBAO by default**" rule from
``docs/planning/config-classification.md`` §1/§3.  B-bucket secrets
(``jwt_secret``, ``password_salt``, ``admin_password``, the DB password,
per-tenant SMTP password, license key, MaxMind key, …) are read from
OpenBAO; during the migration window the legacy ``sysmanage.yaml`` value is
honored as a fallback with a one-time deprecation warning.

This is the additive backbone: it changes no call sites on its own.  Each
option is migrated by switching its accessor to call :func:`get_secret`
with a ``yaml_getter`` that returns the legacy value — a one-line change
per secret — and then dropping the YAML key in a later major.

The OpenBAO read is best-effort and never raises: if vault is disabled or
unreachable, it returns ``None`` and the YAML fallback (or ``default``)
applies, so a deployment that hasn't migrated its secrets keeps working.
"""

import logging
import threading
import time
from typing import Any, Callable, Optional

from backend.config import config

logger = logging.getLogger(__name__)

# All SysManage config secrets live in one KV-v2 secret under the vault's
# configured mount, keyed by name (jwt_secret, password_salt, ...).  The
# secure-installation script primes this on a fresh install.
_CONFIG_SECRET_SUBPATH = "sysmanage/config"

# Track which secrets we've already warned about so the deprecation notice
# is logged once per process, not on every read.
_warned: set = set()

# In-process cache of the consolidated config secret bag.  OpenBAO is the
# source of truth but reading it per secret lookup is too costly, so we cache
# the whole bag for a short TTL.  Guarded by a lock for thread safety.
_CACHE_TTL_SECONDS = 30
_cache_lock = threading.Lock()
_cache_bag: Optional[dict] = None
_cache_expiry: float = 0.0


def _config_secret_path() -> str:
    """KV-v2 read path for the consolidated config secret."""
    mount = config.get_vault_mount_path()
    return f"{mount}/data/{_CONFIG_SECRET_SUBPATH}"


def invalidate_cache() -> None:
    """Drop the cached secret bag (call after writing secrets)."""
    global _cache_bag, _cache_expiry  # pylint: disable=global-statement
    with _cache_lock:
        _cache_bag = None
        _cache_expiry = 0.0


def get_config_secret_bag() -> Optional[dict]:
    """Return the full config-secret dict from OpenBAO (cached); None on miss.

    Best-effort and never raises: if vault is disabled or unreachable, returns
    ``None`` so callers fall back to YAML.
    """
    global _cache_bag, _cache_expiry  # pylint: disable=global-statement
    if not config.is_vault_enabled():
        return None
    now = time.time()
    with _cache_lock:
        if _cache_bag is not None and now < _cache_expiry:
            return _cache_bag
    bag = _read_bag_from_openbao()
    with _cache_lock:
        _cache_bag = bag
        _cache_expiry = now + _CACHE_TTL_SECONDS
    return bag


def _read_bag_from_openbao() -> Optional[dict]:
    """Uncached read of the config-secret bag; never raises."""
    try:
        # Late import: avoids an import cycle and keeps this module importable
        # where the vault service (and its deps) aren't needed.
        from backend.services.vault_service import VaultService  # noqa: PLC0415

        data = VaultService().retrieve_secret(_config_secret_path())
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001 - vault optional + best-effort
        logger.debug("OpenBAO config secret bag unavailable: %s", exc)
        return None


def _from_openbao(name: str) -> Optional[Any]:
    """Best-effort read of one secret from the cached bag; never raises."""
    bag = get_config_secret_bag()
    if not isinstance(bag, dict):
        return None
    value = bag.get(name)
    return value if value not in (None, "") else None


def store_config_secrets(secrets: dict) -> bool:
    """Write/merge ``secrets`` into the consolidated OpenBAO config secret.

    Used by the secure-installation flow to prime OpenBAO on a fresh install.
    Merges with any existing bag so individual secrets can be set without
    clobbering the rest.  Returns True on success.
    """
    if not config.is_vault_enabled():
        logger.warning("Cannot store config secrets: vault is disabled.")
        return False
    try:
        from backend.services.vault_service import VaultService  # noqa: PLC0415

        svc = VaultService()
        existing = _read_bag_from_openbao() or {}
        merged = {**existing, **{k: v for k, v in secrets.items() if v is not None}}
        # KV v2 write: POST {mount}/data/<subpath> with {"data": {...}}.
        svc._make_request(  # pylint: disable=protected-access
            "POST", _config_secret_path(), {"data": merged}
        )
        invalidate_cache()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to store config secrets in OpenBAO: %s", exc)
        return False


def get_secret(
    name: str,
    yaml_getter: Optional[Callable[[], Any]] = None,
    *,
    default: Any = None,
) -> Any:
    """Return secret ``name``, preferring OpenBAO over the YAML fallback.

    Args:
        name: the secret's key within the consolidated config secret.
        yaml_getter: zero-arg callable returning the legacy ``sysmanage.yaml``
            value (or a falsy value if absent).  When this supplies the
            value, a one-time deprecation warning is logged.
        default: returned when neither OpenBAO nor YAML has the secret.
    """
    value = _from_openbao(name)
    if value is not None:
        return value

    if yaml_getter is not None:
        try:
            legacy = yaml_getter()
        except Exception as exc:  # noqa: BLE001
            logger.debug("YAML fallback for secret %r failed: %s", name, exc)
            legacy = None
        if legacy:
            if name not in _warned:
                logger.warning(
                    "Secret '%s' is being read from sysmanage.yaml. Secrets should "
                    "live in OpenBAO — see docs/planning/config-classification.md "
                    "(Phase 13.1.H). The YAML fallback will be removed in a future "
                    "major.",
                    name,
                )
                _warned.add(name)
            return legacy

    return default
