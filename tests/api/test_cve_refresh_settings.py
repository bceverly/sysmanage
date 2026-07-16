# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the Phase 11.4 CVE refresh-settings API gate.

The CVE feed management routes are gated on the Pro+ ``vuln_engine``
module being loaded.  Without it, every route returns 402 — these tests
verify that gate using the same pattern as
``test_upgrade_profiles.TestUpgradeProfilesProplusGate``.

Engine-loaded behaviour (200 + delegate to engine helpers) is exercised
in the engine's own test suite under
``module-source/vuln_engine/test_vuln_engine_cve_refresh.py`` — there's
no DB-backed integration smoke here because the persisted-settings table
is intentionally not part of the OSS API conftest's manual model
mirror (Phase 11.4 keeps the schema unchanged, so DB-backed tests
would just duplicate the existing ``test_cve_refresh_service`` shape).
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name

from unittest.mock import patch

import pytest


class TestCveRefreshAuth:
    def test_sources_requires_auth(self, client):
        r = client.get("/api/v1/cve-refresh/sources")
        assert r.status_code in [401, 403]

    def test_settings_requires_auth(self, client):
        r = client.get("/api/v1/cve-refresh/settings")
        assert r.status_code in [401, 403]

    def test_refresh_requires_auth(self, client):
        r = client.post("/api/v1/cve-refresh/refresh")
        assert r.status_code in [401, 403]


class TestCveRefreshProplusGate:
    """When ``vuln_engine`` isn't loaded, every route returns 402."""

    @pytest.fixture
    def _engine_absent(self):
        with patch(
            "backend.api.cve_refresh_settings.module_loader.get_module",
            return_value=None,
        ):
            yield

    def test_sources_returns_402(self, client, auth_headers, _engine_absent):
        r = client.get("/api/v1/cve-refresh/sources", headers=auth_headers)
        assert r.status_code == 402

    def test_settings_get_returns_402(self, client, auth_headers, _engine_absent):
        r = client.get("/api/v1/cve-refresh/settings", headers=auth_headers)
        assert r.status_code == 402

    def test_settings_put_returns_402(self, client, auth_headers, _engine_absent):
        r = client.put(
            "/api/v1/cve-refresh/settings",
            json={"enabled": True},
            headers=auth_headers,
        )
        assert r.status_code == 402

    def test_stats_returns_402(self, client, auth_headers, _engine_absent):
        r = client.get("/api/v1/cve-refresh/stats", headers=auth_headers)
        assert r.status_code == 402

    def test_history_returns_402(self, client, auth_headers, _engine_absent):
        r = client.get("/api/v1/cve-refresh/history", headers=auth_headers)
        assert r.status_code == 402

    def test_refresh_returns_402(self, client, auth_headers, _engine_absent):
        r = client.post("/api/v1/cve-refresh/refresh", headers=auth_headers)
        assert r.status_code == 402

    def test_clear_nvd_api_key_returns_402(self, client, auth_headers, _engine_absent):
        r = client.delete("/api/v1/cve-refresh/nvd-api-key", headers=auth_headers)
        assert r.status_code == 402

    def test_402_carries_upgrade_message(self, client, auth_headers, _engine_absent):
        """The 402 detail must mention Professional+ so users know to upgrade."""
        r = client.get("/api/v1/cve-refresh/settings", headers=auth_headers)
        assert r.status_code == 402
        body = r.json()
        # detail wording is i18n'd but the English msgid contains "Professional+"
        assert "Professional+" in body["detail"]


class TestCveRefreshGateHelper:
    """Direct coverage of the ``_check_vuln_engine_module`` helper."""

    def test_helper_returns_engine_when_loaded(self):
        from unittest.mock import MagicMock

        from backend.api import cve_refresh_settings

        mock_engine = MagicMock()
        with patch(
            "backend.api.cve_refresh_settings.module_loader.get_module",
            return_value=mock_engine,
        ):
            result = cve_refresh_settings._check_vuln_engine_module()
        assert result is mock_engine

    def test_helper_raises_402_when_absent(self):
        from fastapi import HTTPException

        from backend.api import cve_refresh_settings

        with patch(
            "backend.api.cve_refresh_settings.module_loader.get_module",
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                cve_refresh_settings._check_vuln_engine_module()
        assert exc_info.value.status_code == 402
        assert "Professional+" in str(exc_info.value.detail)
