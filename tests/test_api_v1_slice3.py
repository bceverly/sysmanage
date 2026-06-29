"""
Phase 13.2.1 — Slice 3 native ``/api/v1`` migration (packages / updates / repos).

Dual-surface contract for the migrated routers: packages, updates, scripts,
third_party_repos, default_repositories, enabled_package_managers,
package_compliance (``/package-profiles``), upgrade_profiles. Each representative
endpoint resolves identically under ``/api/v1`` and the deprecated ``/api`` alias.
"""

import pytest

# All migrated endpoints — the v1 and the deprecated /api alias must behave
# identically (includes the Pro+ license-gated profile routers, which return
# 402 without a license but must do so on BOTH surfaces).
DUAL_SURFACE_PATHS = [
    "/packages/summary",
    "/scripts/",
    "/default-repositories/os-options",
    "/enabled-package-managers/os-options",
    "/package-profiles",
    "/upgrade-profiles",
]

# OSS endpoints that resolve to a 200 for the all-roles test user.
NATIVE_OK_PATHS = [
    "/packages/summary",
    "/scripts/",
    "/default-repositories/os-options",
    "/enabled-package-managers/os-options",
]


class TestDualSurface:
    @pytest.mark.parametrize("path", DUAL_SURFACE_PATHS)
    def test_v1_and_alias_match(self, client, path):
        v1 = client.get("/api/v1" + path)
        alias = client.get("/api" + path)
        assert v1.status_code != 404, f"/api/v1{path} should be native"
        assert alias.status_code != 404, f"/api{path} alias should still work"
        assert v1.status_code == alias.status_code

    @pytest.mark.parametrize("path", NATIVE_OK_PATHS)
    def test_v1_is_native(self, client, path):
        assert client.get("/api/v1" + path).status_code == 200
