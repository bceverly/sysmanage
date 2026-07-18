# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the OSS ``tenant_edition`` shim (Phase 13.1.J).

The real per-tenant edition resolution lives in the licensed
``multitenancy_engine``; this shim just delegates through
``backend.multitenancy.seam`` and degrades to ``None`` when the engine is
absent or predates the seam.  All three degradation paths are exercised
here with the seam monkeypatched — no engine is actually loaded.
"""

# pylint: disable=missing-function-docstring

from unittest.mock import MagicMock

from backend.services import tenant_edition


def test_returns_none_when_engine_absent(monkeypatch):
    monkeypatch.setattr(tenant_edition.seam, "engine_module", lambda: None)
    assert tenant_edition.edition_for_active_tenant() is None


def test_returns_none_when_engine_lacks_resolver(monkeypatch):
    # An older engine that predates this seam has no
    # ``edition_for_active_tenant`` attribute.
    engine = object()
    monkeypatch.setattr(tenant_edition.seam, "engine_module", lambda: engine)
    assert tenant_edition.edition_for_active_tenant() is None


def test_returns_none_when_resolver_not_callable(monkeypatch):
    engine = MagicMock()
    engine.edition_for_active_tenant = "not-callable"
    monkeypatch.setattr(tenant_edition.seam, "engine_module", lambda: engine)
    assert tenant_edition.edition_for_active_tenant() is None


def test_delegates_to_engine_resolver(monkeypatch):
    engine = MagicMock()
    engine.edition_for_active_tenant = MagicMock(return_value="enterprise")
    monkeypatch.setattr(tenant_edition.seam, "engine_module", lambda: engine)
    assert tenant_edition.edition_for_active_tenant() == "enterprise"
    engine.edition_for_active_tenant.assert_called_once_with()


def test_passes_through_none_from_engine(monkeypatch):
    engine = MagicMock()
    engine.edition_for_active_tenant = MagicMock(return_value=None)
    monkeypatch.setattr(tenant_edition.seam, "engine_module", lambda: engine)
    assert tenant_edition.edition_for_active_tenant() is None
