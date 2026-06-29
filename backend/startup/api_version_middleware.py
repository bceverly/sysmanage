"""
API version middleware — Phase 13.2 (API Completeness).

Unifies the API under an explicit ``/api/v1`` namespace without breaking any
existing client.  The codebase is mid-migration: newer routers (server-info,
air-gap, federation, Pro+ stubs) already serve **natively** under ``/api/v1``,
while older routers still serve under the unversioned ``/api``.  This middleware
completes the v1 namespace so that *every* endpoint is reachable under
``/api/v1`` — without disturbing either existing surface:

  * A request that already matches a native ``/api/v1`` route is passed through
    untouched (so the newer endpoints keep working exactly as before).
  * Otherwise, a ``/api/v1/<rest>`` request is rewritten to the legacy
    ``/api/<rest>`` route, so the older unversioned endpoints are *also*
    reachable under v1.
  * The unversioned ``/api/...`` surface is never altered, so the agent, the
    web UI, and Pro+ engines keep working unchanged (zero regression).

``/api/v2/...`` is intentionally unmapped — it 404s until a real v2 ships,
reserving the namespace for a future, deliberately-introduced breaking version.

Implemented as pure ASGI (not ``BaseHTTPMiddleware``) so it covers the
WebSocket scope too — e.g. ``/api/v1/agent/connect`` resolves to the native
``/api/agent/connect`` upgrade endpoint.
"""

import logging

from starlette.routing import Match

logger = logging.getLogger(__name__)

_VERSIONED_PREFIX = "/api/v1"


class ApiVersionMiddleware:
    """Make ``/api/v1`` a complete alias namespace over the canonical routes."""

    def __init__(self, app, fastapi_app=None):
        self.app = app
        # The FastAPI instance, used to consult the real route table so we never
        # rewrite a path that a native ``/api/v1`` route already serves.  Passed
        # explicitly because the ASGI ``app`` above is the next middleware layer,
        # not the router.
        self._fastapi_app = fastapi_app
        self._v1_routes = None  # lazily populated on first request

    def _native_v1_routes(self):
        """Routes whose path template already lives under ``/api/v1`` (cached)."""
        if self._v1_routes is None:
            routes = (
                getattr(self._fastapi_app, "routes", []) if self._fastapi_app else []
            )
            self._v1_routes = [
                r
                for r in routes
                if getattr(r, "path", "").startswith(_VERSIONED_PREFIX)
                and hasattr(r, "matches")
            ]
        return self._v1_routes

    def _matches_native_v1(self, scope) -> bool:
        """True when the request already matches a native ``/api/v1`` route."""
        for route in self._native_v1_routes():
            try:
                match, _child = route.matches(scope)
            except Exception as exc:  # noqa: BLE001 - matching must never 500 a request
                logger.debug("v1 route match failed (skipping route): %s", exc)
                match = Match.NONE
            if match != Match.NONE:
                return True
        return False

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if (
                path == _VERSIONED_PREFIX or path.startswith(_VERSIONED_PREFIX + "/")
            ) and not self._matches_native_v1(scope):
                rewritten = "/api" + path[len(_VERSIONED_PREFIX) :]
                scope = dict(scope)
                scope["path"] = rewritten
                if scope.get("raw_path"):
                    scope["raw_path"] = rewritten.encode("latin-1")
        await self.app(scope, receive, send)
