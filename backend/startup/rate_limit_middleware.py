# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Rate-limiting middleware — Phase 13.2 (API Completeness).

A lightweight, in-process fixed-window limiter that caps requests per client
over a sliding-reset window and returns ``429 Too Many Requests`` (with a
``Retry-After`` header) when the cap is exceeded.

Design choices, made deliberately to avoid regressions:

  * **Opt-in (disabled by default).** Naive per-IP limiting can throttle every
    user behind a shared reverse-proxy IP, or break the app's own polling UI.
    So the middleware ships present + wired + tested but inert until an operator
    enables it (``api.rate_limit.enabled`` in config, or the
    ``SYSMANAGE_RATE_LIMIT_ENABLED`` env var) and tunes the limits for their
    deployment.
  * **Exemptions.** WebSockets, the health check, the root, and the agent
    comms path are never limited — store-and-forward agent traffic must not be
    throttled.  Starlette's ``TestClient`` (client host ``testclient``) is
    exempt so the suite is unaffected.
  * **Proxy-aware keying.** Honours the first ``X-Forwarded-For`` hop when
    present so a reverse-proxy deployment keys on the real client, not the proxy.
  * **Config read off the hot path's DB.** Limits come from the in-memory YAML
    config / env (not a per-request DB lookup), so enabling it adds no query.

This limits *request volume*; it is independent of the auth-specific limiters
already in place for login (``login_security``) and agent WebSocket connects
(``communication_security``).
"""

import time

from starlette.responses import JSONResponse

from backend.config import config
from backend.i18n import _

# Paths never subject to volume limiting (matched after version rewrite, so the
# unversioned form covers ``/api/v1/...`` too).
_EXEMPT_EXACT = frozenset({"/", "/api/health", "/api/health/db"})
_EXEMPT_PREFIXES = ("/api/agent",)
# Purge stale buckets once the table grows past this many distinct clients.
_PURGE_THRESHOLD = 10_000


class RateLimitMiddleware:
    """Fixed-window per-client request limiter (opt-in)."""

    def __init__(self, app, *, enabled=None, requests=None, window_seconds=None):
        self.app = app
        # Explicit overrides take precedence over config (used by tests); when
        # None, each is resolved from config per-request so live config edits
        # take effect without a restart.
        self._enabled_override = enabled
        self._requests_override = requests
        self._window_override = window_seconds
        # client-key -> (window_start_monotonic, count)
        self._buckets = {}

    # -- config resolution -------------------------------------------------
    def _enabled(self) -> bool:
        if self._enabled_override is not None:
            return self._enabled_override
        return config.get_rate_limit_enabled()

    def _limit(self) -> int:
        if self._requests_override is not None:
            return self._requests_override
        return config.get_rate_limit_requests()

    def _window(self) -> int:
        if self._window_override is not None:
            return self._window_override
        return config.get_rate_limit_window_seconds()

    # -- ASGI --------------------------------------------------------------
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self._enabled():
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if _is_exempt(path):
            await self.app(scope, receive, send)
            return

        client_key = _client_key(scope)
        if client_key == "testclient":  # Starlette TestClient — never limited
            await self.app(scope, receive, send)
            return

        allowed, retry_after = self._record(client_key)
        if not allowed:
            response = JSONResponse(
                {"detail": _("Rate limit exceeded. Please retry later.")},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _record(self, key):
        """Count one request for ``key``; return ``(allowed, retry_after)``."""
        now = time.monotonic()
        limit = self._limit()
        window = self._window()
        start, count = self._buckets.get(key, (now, 0))
        if now - start >= window:
            start, count = now, 0
        count += 1
        self._buckets[key] = (start, count)
        if len(self._buckets) > _PURGE_THRESHOLD:
            self._purge(now, window)
        if count > limit:
            retry_after = max(1, int(window - (now - start)))
            return False, retry_after
        return True, 0

    def _purge(self, now, window):
        """Drop buckets whose window has fully elapsed (bounds memory)."""
        stale = [k for k, (start, _c) in self._buckets.items() if now - start >= window]
        for k in stale:
            self._buckets.pop(k, None)


def _is_exempt(path: str) -> bool:
    if path in _EXEMPT_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)


def _client_key(scope) -> str:
    """Best client identifier: first X-Forwarded-For hop, else the socket IP."""
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            forwarded = value.decode("latin-1").split(",")[0].strip()
            if forwarded:
                return forwarded
    client = scope.get("client")
    return client[0] if client else "unknown"
