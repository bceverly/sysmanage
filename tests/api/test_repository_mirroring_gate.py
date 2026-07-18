# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Phase 15 exit item: the repository-mirroring surface is gated behind the
Pro+ ``repository_mirroring_engine``.  When that engine isn't loaded EVERY
endpoint must return a clean HTTP 402 (Payment Required) — never a 500 or a
crash — so the frontend can render a license-upgrade prompt.

The router is mounted at ``/api/v1`` (native) with a retired ``/api`` alias,
so all paths here use the ``/api/v1`` surface.  The single gate helper
``_check_mirror_module`` short-circuits with 402 by inspecting
``module_loader.get_module("repository_mirroring_engine")``; we patch that to
return ``None`` to simulate an unlicensed / engine-absent deployment.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name

from unittest.mock import patch

import pytest


@pytest.fixture
def _engine_absent():
    """Patch ``module_loader.get_module`` so ``_check_mirror_module`` sees no
    ``repository_mirroring_engine`` and raises 402."""
    with patch(
        "backend.api.repository_mirroring.module_loader.get_module",
        return_value=None,
    ):
        yield


class TestRepositoryMirroringProplusGate:
    """When ``repository_mirroring_engine`` isn't loaded, every route 402s."""

    _MIRROR_ID = "00000000-0000-0000-0000-000000000000"
    _CFG_ID = "00000000-0000-0000-0000-000000000001"

    def _assert_402(self, resp):
        assert resp.status_code == 402, resp.text
        body = resp.json()
        # Clean JSON body with an upgrade message — not a 500 stacktrace.
        assert "Professional" in body["detail"]

    def test_list_mirrors_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.get("/api/v1/mirror-repositories", headers=auth_headers)
        )

    def test_create_mirror_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.post(
                "/api/v1/mirror-repositories",
                json={
                    "name": "x",
                    "package_manager": "apt",
                    "upstream_url": "http://example.test/ubuntu",
                    "host_id": self._MIRROR_ID,
                },
                headers=auth_headers,
            )
        )

    def test_get_mirror_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.get(
                f"/api/v1/mirror-repositories/{self._MIRROR_ID}",
                headers=auth_headers,
            )
        )

    def test_update_mirror_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.put(
                f"/api/v1/mirror-repositories/{self._MIRROR_ID}",
                json={"name": "y"},
                headers=auth_headers,
            )
        )

    def test_delete_mirror_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.delete(
                f"/api/v1/mirror-repositories/{self._MIRROR_ID}",
                headers=auth_headers,
            )
        )

    def test_sync_mirror_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.post(
                f"/api/v1/mirror-repositories/{self._MIRROR_ID}/sync",
                headers=auth_headers,
            )
        )

    def test_snapshot_mirror_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.post(
                f"/api/v1/mirror-repositories/{self._MIRROR_ID}/snapshot",
                headers=auth_headers,
            )
        )

    def test_list_snapshots_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.get(
                f"/api/v1/mirror-repositories/{self._MIRROR_ID}/snapshots",
                headers=auth_headers,
            )
        )

    def test_get_mirror_settings_returns_402(
        self, client, auth_headers, _engine_absent
    ):
        self._assert_402(client.get("/api/v1/settings/mirror", headers=auth_headers))

    def test_update_mirror_settings_returns_402(
        self, client, auth_headers, _engine_absent
    ):
        self._assert_402(
            client.put(
                "/api/v1/settings/mirror",
                json={},
                headers=auth_headers,
            )
        )

    def test_list_platform_configs_returns_402(
        self, client, auth_headers, _engine_absent
    ):
        self._assert_402(
            client.get("/api/v1/mirror-platform-configs", headers=auth_headers)
        )

    def test_known_versions_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.get("/api/v1/mirror-known-versions", headers=auth_headers)
        )

    def test_host_default_mirrors_returns_402(
        self, client, auth_headers, _engine_absent
    ):
        self._assert_402(
            client.get("/api/v1/host-defaults/mirrors", headers=auth_headers)
        )
