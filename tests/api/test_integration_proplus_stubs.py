"""
End-to-end coverage for the Pro+ stub-route layer.

The OSS server mounts placeholder routes for Pro+ engines that aren't
loaded so the frontend gets ``{"licensed": false}`` instead of 404.
These tests exercise the wiring through the auth layer:  unauthenticated
callers must be rejected, authenticated callers must get the
license-stub shape.

Without this coverage, a refactor that drops the
``mount_proplus_stub_routes`` call from main.py would only surface as a
404 in production after a release.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring,invalid-name


import pytest

# Endpoints the OSS server stubs out when their Pro+ module isn't loaded.
# Each entry is (method, path, expected_top_level_keys).  The test below
# walks every entry and asserts both auth-required behavior and shape.
STUB_ENDPOINTS = [
    ("GET", "/api/v1/automation/scripts", {"licensed", "scripts"}),
    ("GET", "/api/v1/fleet/groups", {"licensed", "groups"}),
    ("GET", "/api/v1/secrets/access-logs", {"licensed", "access_logs"}),
    ("GET", "/api/v1/secrets/rotation-schedules", {"licensed", "schedules"}),
    ("GET", "/api/v1/audit/statistics", {"licensed"}),
    ("GET", "/api/v1/secrets/statistics", {"licensed"}),
    ("GET", "/api/v1/containers/statistics", {"licensed"}),
]


@pytest.mark.integration
@pytest.mark.parametrize("method,path,expected_keys", STUB_ENDPOINTS)
def test_proplus_stub_requires_auth(
    client, method, path, expected_keys
):  # pylint: disable=unused-argument
    """Every Pro+ stub endpoint sits behind get_current_user — anonymous → 401/403."""
    resp = client.request(method, path)
    assert resp.status_code in (
        401,
        403,
    ), f"{method} {path} returned {resp.status_code} without auth (should be 401/403)"


@pytest.mark.integration
@pytest.mark.parametrize("method,path,expected_keys", STUB_ENDPOINTS)
def test_proplus_stub_returns_unlicensed_shape_when_authed(
    client, auth_headers, method, path, expected_keys
):
    """Authenticated callers should get the documented {licensed: false, ...} body."""
    resp = client.request(method, path, headers=auth_headers)
    # Some stubs may 404 if the Pro+ module is loaded in this test env;
    # tests/conftest.py mounts the stub layer with results={}, which
    # means every Pro+ module is treated as unloaded — so 404 here would
    # be a real wiring regression.
    assert resp.status_code == 200, (
        f"{method} {path} returned {resp.status_code} with auth; "
        f"body={resp.text[:200]!r}"
    )
    body = resp.json()
    assert isinstance(body, dict), f"{path} body not a dict: {body!r}"
    assert (
        body.get("licensed") is False
    ), f"{path} body missing 'licensed: false': {body!r}"
    # Each stub also publishes its expected secondary keys (scripts,
    # groups, etc.) — assert they're present so a future refactor that
    # drops them surfaces here.
    missing = expected_keys - set(body.keys())
    assert not missing, f"{path} body missing keys {missing}: {body!r}"
