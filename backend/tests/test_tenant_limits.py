# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 13.1.F — per-tenant quota seam (``backend.services.tenant_limits``).

Resolution of a tenant's numeric limits lives in the licensed
multitenancy_engine; this OSS seam delegates to it and must degrade to ``None``
(unlimited) whenever the engine is absent, predates the seam, or returns no
value.  Enforcement call-sites (host registration) rely on that fail-open
contract so a single-tenant / unlicensed deployment is never quota-limited.
"""

from types import SimpleNamespace

from backend.services import tenant_limits


def _patch_engine(monkeypatch, engine):
    monkeypatch.setattr(tenant_limits.seam, "engine_module", lambda: engine)


def test_no_engine_is_unlimited(monkeypatch):
    """OSS / single-tenant build: no engine registered → no limit."""
    _patch_engine(monkeypatch, None)
    assert tenant_limits.limit_for_tenant("t1", "max_hosts") is None


def test_old_engine_without_resolver_is_unlimited(monkeypatch):
    """An engine that predates this seam (no ``tenant_limit``) degrades cleanly."""
    _patch_engine(monkeypatch, SimpleNamespace())
    assert tenant_limits.limit_for_tenant("t1", "max_hosts") is None


def test_engine_value_is_returned(monkeypatch):
    calls = {}

    def fake_limit(tenant_id, key):
        calls["args"] = (tenant_id, key)
        return 50

    _patch_engine(monkeypatch, SimpleNamespace(tenant_limit=fake_limit))
    assert tenant_limits.limit_for_tenant("t1", "max_hosts") == 50
    assert calls["args"] == ("t1", "max_hosts")


def test_engine_none_value_is_unlimited(monkeypatch):
    """The engine reporting ``None`` for an unset key stays unlimited."""
    _patch_engine(monkeypatch, SimpleNamespace(tenant_limit=lambda t, k: None))
    assert tenant_limits.limit_for_tenant("t1", "max_hosts") is None


def test_active_tenant_passthrough(monkeypatch):
    """A ``None`` tenant id is forwarded verbatim so the engine resolves the
    active-tenant ContextVar (the in-request enforcement path)."""
    seen = {}

    def fake_limit(tenant_id, key):
        seen["tenant_id"] = tenant_id
        return 10

    _patch_engine(monkeypatch, SimpleNamespace(tenant_limit=fake_limit))
    assert tenant_limits.limit_for_tenant(None, "max_hosts") == 10
    assert seen["tenant_id"] is None
