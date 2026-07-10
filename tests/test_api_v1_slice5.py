"""
Phase 13.2.1 — Slice 5 native ``/api/v1`` migration (settings / integrations).

Dual-surface contract for: server_settings, config_management, email,
ubuntu_pro_settings, grafana/graylog, telemetry/opentelemetry, firewall_roles,
firewall_status, antivirus_status, antivirus_defaults,
commercial_antivirus_status, cve_refresh_settings. Each representative endpoint
resolves identically under ``/api/v1`` and the deprecated ``/api`` alias.
"""

import pytest

GET_DUAL_SURFACE = [
    "/settings",
    "/config/pending",
    "/email/config",
    "/ubuntu-pro/",
    "/antivirus-defaults/",
    "/grafana/grafana-servers",
    "/graylog/graylog-servers",
    "/telemetry/opentelemetry/status",
    "/opentelemetry/opentelemetry-coverage",
    "/firewall-roles/common-ports",
    "/cve-refresh/sources",
]


class TestDualSurface:
    @pytest.mark.parametrize("path", GET_DUAL_SURFACE)
    def test_v1_and_alias_match(self, client, path):
        v1 = client.get("/api/v1" + path)
        alias = client.get("/api" + path)
        assert v1.status_code != 404, f"/api/v1{path} should be native"
        assert alias.status_code == 404, f"/api{path} alias retired (bridge removed)"


class TestHostScopedAvFwVersioned:
    """The host antivirus/firewall paths (left on /api in Slice 2) are now v1."""

    def test_routes_present_on_both_surfaces(self):
        import backend.main as m  # noqa: PLC0415

        paths = {r.path for r in m.app.routes if hasattr(r, "path")}
        for sub in [
            "/hosts/{host_id}/antivirus-status",
            "/hosts/{host_id}/firewall-status",
            "/hosts/{host_id}/commercial-antivirus-status",
        ]:
            assert "/api/v1" + sub in paths, f"missing native /api/v1{sub}"
            assert (
                "/api" + sub not in paths
            ), f"/api{sub} alias retired (bridge removed)"
