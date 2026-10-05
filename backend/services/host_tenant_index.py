# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Host→tenant index -- OSS shim (Pro+ relocation, Phase 2).

The server-global map from a host id to the tenant whose database owns that
host's data.  The implementation moved into the licensed ``multitenancy_engine``
(the OSS build has no copy), so these are thin delegators: with no engine loaded
they degrade to the best-effort no-op contract (writes return False, the read
returns None) -- which is correct for a single-tenant / unlicensed deployment
where there is no host→tenant binding to record or look up.

Phase 22 (multi-tenant scale): ``tenant_for_host`` is on the path of every
inbound and outbound message, so a 10k-agent storm across 20 tenants made it the
most-called statement on the server (~520k registry lookups).  Found bindings
are cached per process.  A miss is never cached: a host being enrolled right
now must not be pinned to the bootstrap database.  Binding or unbinding a host
drops its entry in this process at once.

Other workers learn of a change by asking the engine, at most every
``POLL_SECONDS``, which bindings changed since they last asked
(``rebound_hosts``), and dropping those -- so a host moved to another tenant is
re-routed within seconds, and an entry can live for ``LONG_TTL_SECONDS``.  A
60 s TTL was not enough: an agent's WebSocket stays on one worker and
heartbeats every 60 s, so its entry had always just expired (2026-10-04
profile: the lookup still filled the bootstrap pool).  An engine without
``rebound_hosts`` keeps the short TTL.  If the poll fails, the whole cache is
dropped rather than trusted.
"""

import logging
import random
import threading
import time
from typing import Any, Dict, Optional, Tuple

from backend.multitenancy import seam

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60.0  # an engine that cannot report changed bindings
LONG_TTL_SECONDS = 1800.0  # one that can: a backstop, not the invalidation
POLL_SECONDS = 5.0
CACHE_MAX_ENTRIES = 200_000

_cache: Dict[str, Tuple[str, float]] = {}
_cache_lock = threading.Lock()
_poll_lock = threading.Lock()
_poll: Dict[str, Any] = {"at": float("-inf"), "since": None}


def _forget(host_id) -> None:
    with _cache_lock:
        _cache.pop(str(host_id), None)


def clear_cache() -> None:
    """Drop every cached binding (tests; tenant deprovisioning)."""
    with _cache_lock:
        _cache.clear()
    with _poll_lock:
        _poll["at"], _poll["since"] = float("-inf"), None


def _ttl(engine) -> float:
    """How long a found binding may be served from the cache."""
    if getattr(engine, "rebound_hosts", None) is None:
        return CACHE_TTL_SECONDS
    # Spread so a cache filled during a storm does not expire all at once.
    return LONG_TTL_SECONDS * random.uniform(0.9, 1.1)  # nosec B311 - load spread


def _drop_rebound(engine, now: float) -> None:
    """At most every POLL_SECONDS: drop the bindings that changed elsewhere."""
    poll = getattr(engine, "rebound_hosts", None)
    if poll is None or now - _poll["at"] < POLL_SECONDS:
        return
    # Non-blocking: a thread that finds the poll running skips it rather than
    # wait (``with`` cannot acquire without blocking); released in finally.
    if not _poll_lock.acquire(blocking=False):  # pylint: disable=consider-using-with
        return  # another thread is polling right now
    try:
        if now - _poll["at"] < POLL_SECONDS:
            return
        _poll["at"] = now
        try:
            hosts, _poll["since"] = poll(_poll["since"])
        except Exception as exc:  # noqa: BLE001 -- never break routing
            logger.warning(
                "host->tenant cache: could not read changed bindings (%s); "
                "dropping the whole cache",
                exc,
            )
            with _cache_lock:
                _cache.clear()
            _poll["since"] = None
            return
        if hosts:
            with _cache_lock:
                for host in hosts:
                    _cache.pop(str(host), None)
    finally:
        _poll_lock.release()


def bind_host_to_tenant(host_id, tenant_id) -> bool:
    """Record (or update) the host→tenant binding.  Returns True on success.

    Returns False when the multi-tenancy engine isn't loaded (nothing to bind).
    """
    engine = seam.engine_module()
    if engine is None:
        return False
    try:
        return engine.bind_host_to_tenant(host_id, tenant_id)
    finally:
        _forget(host_id)


def tenant_for_host(host_id) -> Optional[str]:
    """Return the tenant id that owns ``host_id``, or None.  Never raises.

    Returns None when multi-tenancy isn't active -- the data plane then treats
    the host as server-scoped, which is the single-tenant behavior.
    """
    engine = seam.engine_module()
    if engine is None:
        return None
    if host_id is None:
        return None
    key = str(host_id)
    now = time.monotonic()
    _drop_rebound(engine, now)
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None and hit[1] > now:
        return hit[0]
    tenant_id = engine.tenant_for_host(host_id)
    if tenant_id:
        with _cache_lock:
            if len(_cache) >= CACHE_MAX_ENTRIES:
                _cache.clear()
            _cache[key] = (tenant_id, now + _ttl(engine))
    return tenant_id


def unbind_host(host_id) -> bool:
    """Remove a host's binding.  No-op (False) when the engine isn't loaded."""
    engine = seam.engine_module()
    if engine is None:
        return False
    try:
        return engine.unbind_host(host_id)
    finally:
        _forget(host_id)
