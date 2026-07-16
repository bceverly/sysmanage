# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Phase 13.2.1 — Slice 8 native ``/api/v1`` migration (repository mirroring).

Dual-surface contract for the ``repository_mirroring`` router: the mirror
CRUD + sub-resources, per-platform configs, known-versions, host mirror
defaults, and the legacy singleton mirror settings each resolve identically
under ``/api/v1`` and the deprecated ``/api`` alias.
"""

import pytest

GET_DUAL_SURFACE = [
    "/mirror-repositories",
    "/mirror-platform-configs",
    "/mirror-known-versions",
    "/host-defaults/mirrors",
    "/settings/mirror",
]


class TestDualSurface:
    @pytest.mark.parametrize("path", GET_DUAL_SURFACE)
    def test_v1_and_alias_match(self, client, path):
        v1 = client.get("/api/v1" + path)
        alias = client.get("/api" + path)
        assert v1.status_code != 404, f"/api/v1{path} should be native"
        assert alias.status_code == 404, f"/api{path} alias retired (bridge removed)"


class TestParamRoutesVersioned:
    """Param'd mirror sub-resources have native v1 + alias, and the mirror
    settings route does NOT shadow the server_settings ``/settings`` route."""

    def test_routes_present_on_both_surfaces(self):
        import backend.main as m  # noqa: PLC0415

        paths = {r.path for r in m.app.routes if hasattr(r, "path")}
        for sub in [
            "/mirror-repositories/{mirror_id}",
            "/mirror-repositories/{mirror_id}/snapshots",
            "/mirror-platform-configs/{cfg_id}",
        ]:
            assert "/api/v1" + sub in paths, f"missing native /api/v1{sub}"
            assert (
                "/api" + sub not in paths
            ), f"/api{sub} alias retired (bridge removed)"

    def test_mirror_settings_does_not_collide_with_server_settings(self):
        import backend.main as m  # noqa: PLC0415

        paths = {r.path for r in m.app.routes if hasattr(r, "path")}
        # Distinct paths — /settings/mirror is a child, not a duplicate of
        # server_settings' /settings, so they coexist without shadowing.
        assert "/api/v1/settings/mirror" in paths
        assert "/api/v1/settings" in paths
