# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Per-tenant quota/limit resolution — OSS shim (Phase 13.1.F; engine-backed).

Each tenant may be assigned numeric **limits** (e.g. ``max_hosts``) stored in the
``registry_tenant.limits`` JSON bag.  Enforcement call-sites in the OSS code
(host registration, etc.) ask this seam for the active or a named tenant's limit
and reject the operation when it is exceeded.

Per the multi-tenancy moat, the actual resolution — reading the registry, and the
Platform-Operator authorization to *change* a limit — lives in the licensed
``multitenancy_engine``.  This OSS shim is the seam enforcement code calls: it
delegates to the engine when present and degrades to ``None`` when it isn't.
``None`` means *no limit is in scope* (unlimited): single-tenant / unlicensed
deployments, an engine that predates this seam, or a tenant with no value set for
that key — all the cases where the pre-13.1.F behaviour (no quota) must hold.
"""

from typing import Optional

from backend.multitenancy import seam


def limit_for_tenant(tenant_id: Optional[str], key: str) -> Optional[int]:
    """Return the numeric limit ``key`` for ``tenant_id``, or ``None`` (unlimited).

    ``tenant_id`` of ``None`` resolves against the active-tenant ContextVar.
    ``None`` is returned when the licensed engine is absent, no tenant is in
    scope, or the tenant has no value for ``key`` — callers must treat that as
    "no limit".  Lookup failures degrade to ``None`` (fail open) rather than
    raising, so a registry hiccup never blocks an enrollment.
    """
    engine = seam.engine_module()
    if engine is None:
        return None
    resolver = getattr(engine, "tenant_limit", None)
    if not callable(resolver):
        return None
    return resolver(tenant_id, key)  # pylint: disable=not-callable  # narrowed above
