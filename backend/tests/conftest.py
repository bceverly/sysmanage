# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Shared fixtures for the backend/tests tree (run as its own pytest process)."""

import pytest


@pytest.fixture(autouse=True)
def _no_real_email(monkeypatch):
    """No test may reach a real SMTP server -- see tests/smtp_guard.py."""
    from tests import smtp_guard  # noqa: PLC0415

    smtp_guard.install(monkeypatch)
    yield


@pytest.fixture(autouse=True)
def _single_tenant_unless_a_test_says_otherwise(monkeypatch):
    """Single-tenant, as CI runs, whatever the developer's sysmanage.yaml says
    -- see the same guard in tests/conftest.py (stray audit rows reached a
    real dev database, 2026-10-16).  A test that needs multi-tenancy patches
    it on itself."""
    from backend.config import config  # noqa: PLC0415

    section = dict(config.config.get("multitenancy") or {})
    section["enabled"] = False
    monkeypatch.setitem(config.config, "multitenancy", section)
    monkeypatch.delenv("SYSMANAGE_MULTITENANCY", raising=False)
    yield
