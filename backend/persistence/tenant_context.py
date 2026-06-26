"""
Active-tenant request context — Phase 13.1 (per-tenant config resolution).

A process-wide :class:`contextvars.ContextVar` holding the *active tenant* for
the current request/task.  It lets request-agnostic code (e.g. the email
sender in ``backend/config/config.py``) resolve per-tenant configuration
without threading a ``tenant_id`` through every call site.

Set per request by ``backend.startup.tenant_middleware`` from the JWT's
``tenant_id`` claim (only when multi-tenancy is enabled).  When unset — the
single-tenant / collapsed default — it is ``None`` and callers use the
server-scoped configuration, so behavior is unchanged.

ContextVars do not automatically propagate into threads spawned by a request,
and out-of-request work (background tasks, scheduled jobs, pre-auth flows like
password reset) has no JWT to bind from.  Such code establishes the tenant
explicitly with the :func:`tenant_scope` contextmanager (or
:func:`set_active_tenant`).
"""

import contextvars
from contextlib import contextmanager
from typing import Optional

_active_tenant: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "sysmanage_active_tenant", default=None
)


def set_active_tenant(tenant_id: Optional[str]):
    """Set the active tenant; returns a token for :func:`reset_active_tenant`."""
    return _active_tenant.set(str(tenant_id) if tenant_id else None)


def get_active_tenant() -> Optional[str]:
    """Return the active tenant id for this context, or None."""
    return _active_tenant.get()


def reset_active_tenant(token) -> None:
    """Restore the previous active-tenant value (pair with set_active_tenant)."""
    if token is None:
        return
    try:
        _active_tenant.reset(token)
    except (ValueError, LookupError, TypeError):
        # Stale/foreign token (the ContextVar was set in another context or
        # already reset) — nothing to restore, so leave the active tenant as-is.
        pass


@contextmanager
def tenant_scope(tenant_id: Optional[str]):
    """Bind ``tenant_id`` as the active tenant for the duration of the block.

    The explicit primitive for code that runs *outside* a request — background
    tasks, scheduled jobs, threads, or pre-auth flows (e.g. password reset) —
    where the request middleware hasn't bound a tenant.

    ``tenant_id=None`` is a true no-op: it **preserves** whatever tenant is
    already active (it does not clear it), so it's always safe to wrap a send
    in ``tenant_scope`` even when the tenant is unknown or multi-tenancy is
    disabled, and nested scopes compose cleanly.
    """
    if tenant_id is None:
        yield
        return
    token = set_active_tenant(tenant_id)
    try:
        yield
    finally:
        reset_active_tenant(token)
