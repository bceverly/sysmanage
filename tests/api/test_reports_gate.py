# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Phase 15 exit item: the OSS reports surface (``/api/v1/reporting/*``) delegates
report rendering to the Pro+ ``reporting_engine``.  When that engine isn't
loaded, ``view`` and ``generate`` must return a clean HTTP 402 (Payment
Required) with an upgrade message — never a 500 or a crash.

The gate lives in ``_check_reporting_module`` which inspects
``module_loader.get_module("reporting_engine")``; we patch that to return
``None`` to simulate an unlicensed deployment.  The router is mounted at the
native ``/api/v1/reporting`` prefix (the Pro+ engine owns ``/api/v1/reports``).
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name

from unittest.mock import patch

import pytest


@pytest.fixture
def _engine_absent():
    """Patch ``module_loader.get_module`` so ``_check_reporting_module`` sees no
    ``reporting_engine`` and raises 402."""
    with patch(
        "backend.api.reports.endpoints.module_loader.get_module",
        return_value=None,
    ):
        yield


class TestReportsProplusGate:
    """When ``reporting_engine`` isn't loaded, view/generate 402 cleanly."""

    def _assert_402(self, resp):
        assert resp.status_code == 402, resp.text
        body = resp.json()
        assert "Professional" in body["detail"]

    def test_view_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.get("/api/v1/reporting/view/registered-hosts", headers=auth_headers)
        )

    def test_generate_returns_402(self, client, auth_headers, _engine_absent):
        self._assert_402(
            client.get(
                "/api/v1/reporting/generate/registered-hosts", headers=auth_headers
            )
        )

    def test_view_other_report_type_returns_402(
        self, client, auth_headers, _engine_absent
    ):
        # A server-global report type (audit-log) gates identically.
        self._assert_402(
            client.get("/api/v1/reporting/view/audit-log", headers=auth_headers)
        )
