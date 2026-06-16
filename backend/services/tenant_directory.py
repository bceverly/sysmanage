"""
Tenant directory lookups — OSS shim (Pro+ relocation, Phase 2).

Resolve which tenant an out-of-request flow (password reset, MFA, scheduled
notifications) belongs to, via the per-tenant email-domain allowlist.  The
lookup logic moved into the licensed engine; this shim degrades to ``None``
(server scope) when multi-tenancy isn't active — the single-tenant behavior the
pre-auth callers already expect.
"""

from typing import Optional

from backend.multitenancy import seam


def resolve_tenant_for_email(email: Optional[str]) -> Optional[str]:
    """Return the tenant id whose allowlist contains ``email``'s domain, or None.

    Returns None (server scope) when the engine isn't loaded — i.e. single-tenant
    or unlicensed, where there is no per-tenant email-domain allowlist.
    """
    engine = seam.engine_module()
    if engine is None:
        return None
    return engine.resolve_tenant_for_email(email)
