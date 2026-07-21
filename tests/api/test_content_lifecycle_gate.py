# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
The content-lifecycle surface is gated behind the Enterprise
``content_lifecycle_engine``.  When that engine isn't loaded EVERY endpoint must
return a clean HTTP 402 (Payment Required) — never a 500 or a crash — so the
frontend can render a license-upgrade prompt.

The router is mounted at ``/api/v1`` (native).  The single gate helper
``_check_clm_module`` short-circuits with 402 by inspecting
``module_loader.get_module("content_lifecycle_engine")``; we patch that to
return ``None`` to simulate an unlicensed / engine-absent deployment.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name

from unittest.mock import patch

import pytest


@pytest.fixture
def _engine_absent():
    """Patch ``module_loader.get_module`` so ``_check_clm_module`` sees no
    ``content_lifecycle_engine`` and raises 402."""
    with patch(
        "backend.api.content_lifecycle.module_loader.get_module",
        return_value=None,
    ):
        yield


class TestContentLifecycleProplusGate:
    """When ``content_lifecycle_engine`` isn't loaded, every route 402s."""

    def _assert_402(self, resp):
        assert resp.status_code == 402, resp.text
        body = resp.json()
        # Clean JSON body with an upgrade message — not a 500 stacktrace.
        assert "Professional" in body["detail"]

    def test_list_environments_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.get("/api/v1/content-lifecycle/environments", headers=auth_headers)
        )

    def test_list_content_views_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.get("/api/v1/content-lifecycle/content-views", headers=auth_headers)
        )

    def test_create_content_view_returns_402(
        self, client, auth_headers, _engine_absent
    ):
        self._assert_402(
            client.post(
                "/api/v1/content-lifecycle/content-views",
                json={"name": "x"},
                headers=auth_headers,
            )
        )

    def test_publish_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.post(
                "/api/v1/content-lifecycle/content-views/"
                "00000000-0000-0000-0000-000000000000/publish",
                headers=auth_headers,
            )
        )

    def test_list_versions_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.get(
                "/api/v1/content-lifecycle/content-views/"
                "00000000-0000-0000-0000-000000000000/versions",
                headers=auth_headers,
            )
        )
