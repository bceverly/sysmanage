"""
Active-tenant middleware — Phase 13.1 (per-tenant config resolution).

When multi-tenancy is enabled, sets the request's active tenant (from the JWT
``tenant_id`` claim) into the :mod:`backend.persistence.tenant_context`
ContextVar so per-tenant configuration (e.g. each tenant's SMTP settings)
resolves for the duration of the request.

In single-tenant / collapsed mode (the default) this is a no-op — the active
tenant stays ``None`` and the server-scoped configuration is used, so behavior
is unchanged.
"""

from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import config
from backend.persistence.tenant_context import (
    reset_active_tenant,
    set_active_tenant,
)


class ActiveTenantMiddleware(BaseHTTPMiddleware):
    """Bind the request's active tenant from its bearer token."""

    async def dispatch(self, request, call_next):
        token = None
        if config.is_multitenancy_enabled():
            tenant_id = _tenant_from_request(request)
            if tenant_id:
                token = set_active_tenant(tenant_id)
        try:
            return await call_next(request)
        finally:
            if token is not None:
                reset_active_tenant(token)


def _tenant_from_request(request):
    """Best-effort extraction of the tenant_id claim from the bearer token."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        from backend.auth.auth_handler import decode_jwt  # noqa: PLC0415

        payload = decode_jwt(auth[len("Bearer ") :]) or {}
        return payload.get("tenant_id")
    except Exception:  # noqa: BLE001 - best-effort; never block the request
        return None
