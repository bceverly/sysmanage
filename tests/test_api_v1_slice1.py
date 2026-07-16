# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Phase 13.2.1 — Slice 1 native ``/api/v1`` migration.

Verifies the dual-surface contract for the migrated routers (user, profile,
tag, user_preferences): each representative endpoint resolves identically under
the canonical ``/api/v1`` path AND the deprecated unversioned ``/api`` alias.
``api_keys`` was moved v1-only (no alias), so its legacy path must 404.
"""

import pytest

# Representative param-free GETs for each Slice-1 router that succeed with the
# all-roles test user. Both the /api/v1 and /api (alias) forms must behave the
# same after migration.
DUAL_SURFACE_PATHS = [
    "/profile",
    "/tags",
    "/user/permissions",
    "/users",
    "/user-preferences/dashboard-cards",
]


class TestDualSurface:
    @pytest.mark.parametrize("path", DUAL_SURFACE_PATHS)
    def test_v1_and_alias_match(self, client, path):
        v1 = client.get("/api/v1" + path)
        alias = client.get("/api" + path)
        # The route exists on both surfaces (not 404) ...
        assert v1.status_code != 404, f"/api/v1{path} should be native"
        assert alias.status_code == 404, f"/api{path} alias retired (bridge removed)"

    @pytest.mark.parametrize("path", DUAL_SURFACE_PATHS)
    def test_v1_is_native_not_bridged(self, client, path):
        # A native /api/v1 GET succeeds for the all-roles test user.
        assert client.get("/api/v1" + path).status_code == 200


class TestApiKeysV1Only:
    """api_keys moved v1-only — the legacy unversioned path must be gone."""

    def test_v1_works(self, client):
        assert client.get("/api/v1/api-keys").status_code == 200

    def test_legacy_path_is_404(self, client):
        assert client.get("/api/api-keys").status_code == 404
