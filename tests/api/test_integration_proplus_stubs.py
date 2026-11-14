# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
End-to-end coverage for the Pro+ stub-route layer.

The OSS server mounts placeholder routes for Pro+ engines that aren't
loaded so the frontend gets a 402 (``pro_plus_required``) instead of a
404.  These tests exercise the wiring through the auth layer:
unauthenticated callers must be rejected, authenticated callers must get
the license-required answer.

Without this coverage, a refactor that drops the
``mount_proplus_stub_routes`` call from main.py would only surface as a
404 in production after a release.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring,invalid-name


import pytest

# Endpoints the OSS server stubs out when their Pro+ module isn't loaded.
# Each entry is (method, path, engine module named in the 402).  The test
# below walks every entry and asserts both auth-required behavior and the
# license answer.
STUB_ENDPOINTS = [
    ("GET", "/api/v1/automation/scripts", "automation_engine"),
    ("GET", "/api/v1/fleet/groups", "fleet_engine"),
    ("GET", "/api/v1/secrets/access-logs", "secrets_engine"),
    ("GET", "/api/v1/secrets/rotation-schedules", "secrets_engine"),
    ("GET", "/api/v1/audit/statistics", "audit_engine"),
    ("GET", "/api/v1/secrets/statistics", "secrets_engine"),
    ("GET", "/api/v1/containers/statistics", "container_engine"),
]


@pytest.mark.integration
@pytest.mark.parametrize("method,path,module", STUB_ENDPOINTS)
def test_proplus_stub_requires_auth(
    client, method, path, module
):  # pylint: disable=unused-argument
    """Every Pro+ stub endpoint sits behind get_current_user -- anonymous → 401/403."""
    resp = client.request(method, path)
    assert resp.status_code in (
        401,
        403,
    ), f"{method} {path} returned {resp.status_code} without auth (should be 401/403)"


@pytest.mark.integration
@pytest.mark.parametrize("method,path,module", STUB_ENDPOINTS)
def test_proplus_stub_returns_402_when_authed(
    client, auth_headers, method, path, module
):
    """Authenticated callers get 402 naming the missing engine -- reads as
    well as writes (they answered 200 {licensed: false} until the Phase 25
    edition audit)."""
    resp = client.request(method, path, headers=auth_headers)
    # tests/conftest.py mounts the stub layer with results={}, which means
    # every Pro+ module is treated as unloaded -- so a 404 here would be a
    # real wiring regression.
    assert resp.status_code == 402, (
        f"{method} {path} returned {resp.status_code} with auth; "
        f"body={resp.text[:200]!r}"
    )
    detail = resp.json()["detail"]
    assert detail["error"] == "pro_plus_required", detail
    assert detail["module"] == module, detail
