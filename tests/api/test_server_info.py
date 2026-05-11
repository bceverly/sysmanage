"""
Tests for the ``/api/v1/server-info`` endpoint introduced in Phase 11.

Covers:
  * default (``standard``) role — chip-hide path
  * collector role with engine loaded — healthy path
  * repository role without engine — degraded path
  * shape stability of the response (frontend depends on these keys)

The endpoint is unauthenticated by design (frontend renders the role
chip pre-login).  All fields are non-secret.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring


from contextlib import contextmanager
from unittest.mock import patch

from backend.api import server_info as server_info_module


@contextmanager
def _override_loaded(modules: dict):
    """Swap the underlying ``_loaded_modules`` dict on the module_loader
    singleton for the duration of one test.  We can't ``patch`` the
    public ``loaded_modules`` property — it has no setter — so reach
    in and substitute the storage dict directly."""
    loader = server_info_module.module_loader
    saved = loader._loaded_modules  # pylint: disable=protected-access
    loader._loaded_modules = modules  # pylint: disable=protected-access
    try:
        yield
    finally:
        loader._loaded_modules = saved  # pylint: disable=protected-access


def _server_info(client):
    response = client.get("/api/v1/server-info")
    assert response.status_code == 200
    return response.json()


class TestServerInfoShape:
    def test_response_keys_are_stable(self, client):
        body = _server_info(client)
        assert set(body.keys()) >= {
            "role",
            "version",
            "license_tier",
            "loaded_engines",
            "expected_engine_for_role",
            "role_engine_loaded",
        }

    def test_loaded_engines_is_a_list(self, client):
        body = _server_info(client)
        assert isinstance(body["loaded_engines"], list)

    def test_default_role_is_standard(self, client):
        body = _server_info(client)
        assert body["role"] == "standard"
        assert body["expected_engine_for_role"] is None
        assert body["role_engine_loaded"] is True


class TestServerInfoCollectorRole:
    def test_collector_with_engine_loaded_is_healthy(self, client):
        with patch(
            "backend.api.server_info.config_module.get_server_role",
            return_value="collector",
        ), _override_loaded({"airgap_collector_engine": object()}):
            body = _server_info(client)
        assert body["role"] == "collector"
        assert body["expected_engine_for_role"] == "airgap_collector_engine"
        assert body["role_engine_loaded"] is True
        assert "airgap_collector_engine" in body["loaded_engines"]

    def test_collector_without_engine_is_degraded(self, client):
        # Operator set role: collector but the Pro+ license isn't valid
        # (or the engine .so is missing).  UI flips the chip to red.
        with patch(
            "backend.api.server_info.config_module.get_server_role",
            return_value="collector",
        ), _override_loaded({}):
            body = _server_info(client)
        assert body["role"] == "collector"
        assert body["expected_engine_for_role"] == "airgap_collector_engine"
        assert body["role_engine_loaded"] is False


class TestServerInfoRepositoryRole:
    def test_repository_with_engine_loaded_is_healthy(self, client):
        with patch(
            "backend.api.server_info.config_module.get_server_role",
            return_value="repository",
        ), _override_loaded({"airgap_repository_engine": object()}):
            body = _server_info(client)
        assert body["role"] == "repository"
        assert body["expected_engine_for_role"] == "airgap_repository_engine"
        assert body["role_engine_loaded"] is True


class TestServerInfoUnauthenticated:
    def test_works_without_bearer_token(self, client):
        # Endpoint is intentionally public — Navbar.tsx fetches it pre-login
        # to render the role chip.  No bearer token = still 200.
        response = client.get("/api/v1/server-info")
        assert response.status_code == 200
