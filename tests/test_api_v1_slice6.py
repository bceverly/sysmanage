"""
Phase 13.2.1 — Slice 6 native ``/api/v1`` migration (reports / audit / misc).

Dual-surface contract for: reports, report_branding, report_templates,
audit_log, broadcast, queue, diagnostics, license_management, plugin_bundle,
access_groups (+ registration_keys), dynamic_secrets, airgap_bundles.
"""

import pytest

GET_DUAL_SURFACE = [
    "/access-groups",
    "/registration-keys",
    "/airgap-bundles/docker-status",
    "/report-branding",
    "/report-templates",
    "/dynamic-secrets/leases",
    "/queue/failed",
    "/audit-log/list",
    "/license",
    "/plugins/bundles",
]


class TestDualSurface:
    @pytest.mark.parametrize("path", GET_DUAL_SURFACE)
    def test_v1_and_alias_match(self, client, path):
        v1 = client.get("/api/v1" + path)
        alias = client.get("/api" + path)
        assert v1.status_code != 404, f"/api/v1{path} should be native"
        assert alias.status_code != 404, f"/api{path} alias should still work"
        assert v1.status_code == alias.status_code


class TestParamRoutesVersioned:
    """Param'd diagnostics route has native v1 + alias.

    (OSS ``reports`` was renamed to /api/v1/reporting — see
    test_api_v1_secrets_reports_rename.py — since the Pro+ reporting_engine owns
    /api/v1/reports.)
    """

    def test_diagnostics_versioned(self):
        import backend.main as m  # noqa: PLC0415

        paths = {r.path for r in m.app.routes if hasattr(r, "path")}
        sub = "/host/{host_id}/diagnostics"
        assert "/api/v1" + sub in paths, f"missing native /api/v1{sub}"
        assert "/api" + sub in paths, f"missing alias /api{sub}"
