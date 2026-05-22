"""
Comprehensive unit tests for Pro+ route mounting functionality.

Tests cover:
- Health route mounting
- Vulnerability route mounting
- Compliance route mounting
- Alerting route mounting
- Module availability checks
- Error handling during route mounting
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import FastAPI

from backend.api.proplus_routes import (
    mount_alerting_routes,
    mount_compliance_routes,
    mount_federation_controller_routes,
    mount_federation_site_routes,
    mount_health_routes,
    mount_proplus_routes,
    mount_proplus_stub_routes,
    mount_vulnerability_routes,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_app():
    """Create a mock FastAPI application."""
    app = MagicMock(spec=FastAPI)
    return app


@pytest.fixture
def mock_module_with_routes():
    """Create a mock Cython module that provides routes."""
    mock_module = MagicMock()
    mock_module.get_module_info.return_value = {
        "provides_routes": True,
        "version": "1.0.0",
    }
    mock_router = MagicMock()
    return mock_module, mock_router


@pytest.fixture
def mock_module_without_routes():
    """Create a mock Cython module that does not provide routes."""
    mock_module = MagicMock()
    mock_module.get_module_info.return_value = {
        "provides_routes": False,
        "version": "1.0.0",
    }
    return mock_module


# =============================================================================
# mount_health_routes() TESTS
# =============================================================================


class TestMountHealthRoutes:
    """Test cases for mount_health_routes function."""

    def test_health_routes_module_not_loaded(self, mock_app):
        """Test mount_health_routes when health_engine is not loaded."""
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = None

            result = mount_health_routes(mock_app)

            assert result is False
            mock_loader.get_module.assert_called_once_with("health_engine")
            mock_app.include_router.assert_not_called()

    def test_health_routes_module_no_routes(self, mock_app, mock_module_without_routes):
        """Test mount_health_routes when module doesn't provide routes."""
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module_without_routes

            result = mount_health_routes(mock_app)

            assert result is False
            mock_app.include_router.assert_not_called()

    def test_health_routes_success(self, mock_app, mock_module_with_routes):
        """Test successful mounting of health routes."""
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_health_router.return_value = mock_router

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            result = mount_health_routes(mock_app)

            assert result is True
            mock_module.get_health_router.assert_called_once()
            mock_app.include_router.assert_called_once_with(mock_router, prefix="/api")

    def test_health_routes_exception(self, mock_app, mock_module_with_routes):
        """Test mount_health_routes handles exceptions gracefully."""
        mock_module, _ = mock_module_with_routes
        mock_module.get_health_router.side_effect = RuntimeError("Module error")

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            result = mount_health_routes(mock_app)

            assert result is False
            mock_app.include_router.assert_not_called()

    def test_health_routes_passes_dependencies(self, mock_app, mock_module_with_routes):
        """Test that mount_health_routes passes correct dependencies to router."""
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_health_router.return_value = mock_router

        # ``proplus_routes`` no longer re-exports ``requires_feature`` /
        # ``requires_module`` — the gates are inlined as
        # ``_feature_dependency`` / ``_module_dependency``.  Patching
        # only the symbols that actually exist on the module today.
        with patch("backend.api.proplus_routes.module_loader") as mock_loader, patch(
            "backend.api.proplus_routes.get_db"
        ), patch("backend.api.proplus_routes.get_current_user"), patch(
            "backend.api.proplus_routes.models"
        ):
            mock_loader.get_module.return_value = mock_module

            mount_health_routes(mock_app)

            # Verify get_health_router was called with expected kwargs
            call_kwargs = mock_module.get_health_router.call_args.kwargs
            assert "db_dependency" in call_kwargs
            assert "auth_dependency" in call_kwargs
            assert "feature_gate" in call_kwargs
            assert "module_gate" in call_kwargs
            assert "models" in call_kwargs
            assert "http_exception" in call_kwargs
            assert "status_codes" in call_kwargs
            assert "logger" in call_kwargs


# =============================================================================
# mount_vulnerability_routes() TESTS
# =============================================================================


class TestMountVulnerabilityRoutes:
    """Test cases for mount_vulnerability_routes function."""

    def test_vuln_routes_module_not_loaded(self, mock_app):
        """Test mount_vulnerability_routes when vuln_engine is not loaded."""
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = None

            result = mount_vulnerability_routes(mock_app)

            assert result is False
            mock_loader.get_module.assert_called_once_with("vuln_engine")

    def test_vuln_routes_module_no_routes(self, mock_app, mock_module_without_routes):
        """Test mount_vulnerability_routes when module doesn't provide routes."""
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module_without_routes

            result = mount_vulnerability_routes(mock_app)

            assert result is False

    def test_vuln_routes_success(self, mock_app, mock_module_with_routes):
        """Test successful mounting of vulnerability routes."""
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_vulnerability_router.return_value = mock_router

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            result = mount_vulnerability_routes(mock_app)

            assert result is True
            mock_app.include_router.assert_called_once_with(mock_router, prefix="/api")

    def test_vuln_routes_exception(self, mock_app, mock_module_with_routes):
        """Test mount_vulnerability_routes handles exceptions gracefully."""
        mock_module, _ = mock_module_with_routes
        mock_module.get_vulnerability_router.side_effect = RuntimeError("Error")

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            result = mount_vulnerability_routes(mock_app)

            assert result is False


# =============================================================================
# mount_compliance_routes() TESTS
# =============================================================================


class TestMountComplianceRoutes:
    """Test cases for mount_compliance_routes function."""

    def test_compliance_routes_module_not_loaded(self, mock_app):
        """Test mount_compliance_routes when compliance_engine is not loaded."""
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = None

            result = mount_compliance_routes(mock_app)

            assert result is False
            mock_loader.get_module.assert_called_once_with("compliance_engine")

    def test_compliance_routes_success(self, mock_app, mock_module_with_routes):
        """Test successful mounting of compliance routes."""
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_compliance_router.return_value = mock_router

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            result = mount_compliance_routes(mock_app)

            assert result is True
            mock_app.include_router.assert_called_once()


# =============================================================================
# mount_alerting_routes() TESTS
# =============================================================================


class TestMountAlertingRoutes:
    """Test cases for mount_alerting_routes function."""

    def test_alerting_routes_module_not_loaded(self, mock_app):
        """Test mount_alerting_routes when alerting_engine is not loaded."""
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = None

            result = mount_alerting_routes(mock_app)

            assert result is False
            mock_loader.get_module.assert_called_once_with("alerting_engine")

    def test_alerting_routes_success(self, mock_app, mock_module_with_routes):
        """Test successful mounting of alerting routes."""
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_alerting_router.return_value = mock_router

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            result = mount_alerting_routes(mock_app)

            assert result is True

    def test_alerting_routes_passes_email_service(
        self, mock_app, mock_module_with_routes
    ):
        """Test that mount_alerting_routes passes email_service dependency."""
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_alerting_router.return_value = mock_router

        with patch("backend.api.proplus_routes.module_loader") as mock_loader, patch(
            "backend.api.proplus_routes.email_service"
        ) as mock_email:
            mock_loader.get_module.return_value = mock_module

            mount_alerting_routes(mock_app)

            # Verify email_service was passed
            call_kwargs = mock_module.get_alerting_router.call_args.kwargs
            assert "email_service" in call_kwargs
            assert call_kwargs["email_service"] == mock_email


# =============================================================================
# mount_proplus_routes() TESTS
# =============================================================================


class TestMountProPlusRoutes:
    """Test cases for mount_proplus_routes function."""

    def test_mount_all_no_modules(self, mock_app):
        """Test mount_proplus_routes when no modules are loaded."""
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = None

            results = mount_proplus_routes(mock_app)

            assert results["vuln_engine"] is False
            assert results["health_engine"] is False
            assert results["compliance_engine"] is False
            assert results["alerting_engine"] is False

    def test_mount_all_all_modules(self, mock_app, mock_module_with_routes):
        """Test mount_proplus_routes when all modules are loaded."""
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_vulnerability_router.return_value = mock_router
        mock_module.get_health_router.return_value = mock_router
        mock_module.get_compliance_router.return_value = mock_router
        mock_module.get_alerting_router.return_value = mock_router

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            results = mount_proplus_routes(mock_app)

            assert results["vuln_engine"] is True
            assert results["health_engine"] is True
            assert results["compliance_engine"] is True
            assert results["alerting_engine"] is True

    def test_mount_all_partial_modules(self, mock_app, mock_module_with_routes):
        """Test mount_proplus_routes with only some modules loaded."""
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_health_router.return_value = mock_router

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            # Only return module for health_engine
            def get_module_side_effect(name):
                if name == "health_engine":
                    return mock_module
                return None

            mock_loader.get_module.side_effect = get_module_side_effect

            results = mount_proplus_routes(mock_app)

            assert results["vuln_engine"] is False
            assert results["health_engine"] is True
            assert results["compliance_engine"] is False
            assert results["alerting_engine"] is False

    def test_mount_all_returns_dict(self, mock_app):
        """Test mount_proplus_routes returns a dictionary with all module keys."""
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = None

            results = mount_proplus_routes(mock_app)

            assert isinstance(results, dict)
            assert "vuln_engine" in results
            assert "health_engine" in results
            assert "compliance_engine" in results
            assert "alerting_engine" in results
            # Phase 12.1.A
            assert "federation_controller_engine" in results


# =============================================================================
# mount_federation_controller_routes() TESTS  (Phase 12.1.A)
# =============================================================================


class TestMountFederationControllerRoutes:
    """Mount-function tests mirror the health/vuln pattern.

    The federation controller engine itself lives in the Pro+ source
    repo, NOT this OSS one, so on every OSS install ``get_module``
    returns ``None`` and the mount is a no-op.  The tests below pin
    that no-op behaviour and verify the wiring is symmetric with the
    other engines so a future engine-side route renderer plugs in
    without OSS-side surgery.
    """

    def test_routes_module_not_loaded(self, mock_app):
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = None

            result = mount_federation_controller_routes(mock_app)

            assert result is False
            mock_loader.get_module.assert_called_once_with(
                "federation_controller_engine"
            )
            mock_app.include_router.assert_not_called()

    def test_routes_module_no_routes(self, mock_app, mock_module_without_routes):
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module_without_routes

            result = mount_federation_controller_routes(mock_app)

            assert result is False
            mock_app.include_router.assert_not_called()

    def test_routes_success(self, mock_app, mock_module_with_routes):
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_federation_controller_router.return_value = mock_router

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            result = mount_federation_controller_routes(mock_app)

            assert result is True
            mock_module.get_federation_controller_router.assert_called_once()
            mock_app.include_router.assert_called_once_with(mock_router, prefix="/api")

    def test_routes_exception(self, mock_app, mock_module_with_routes):
        mock_module, _ = mock_module_with_routes
        mock_module.get_federation_controller_router.side_effect = RuntimeError(
            "engine boom"
        )

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            result = mount_federation_controller_routes(mock_app)

            assert result is False
            mock_app.include_router.assert_not_called()


# =============================================================================
# Federation stub-route surface (Phase 12.1.A)
# =============================================================================


class TestFederationControllerStubRoutes:
    """End-to-end via FastAPI TestClient: every federation endpoint
    must respond 200 with ``{"licensed": False, ...}`` when the
    ``federation_controller_engine`` module is not loaded.  Frontend
    (12.3) and 12.4's access-groups migration both depend on this
    surface existing in OSS so they can probe for the engine without
    having to handle 404s.
    """

    # All stub endpoints (method, path) — 22 in total.  When 12.1.B+
    # lands real handlers in the engine, this list stays the same;
    # only the response bodies change.
    STUB_ENDPOINTS = [
        ("GET", "/api/v1/federation/sites"),
        ("POST", "/api/v1/federation/sites"),
        ("POST", "/api/v1/federation/sites/enrollment/tok-abc/complete"),
        ("GET", "/api/v1/federation/sites/site-1"),
        ("PATCH", "/api/v1/federation/sites/site-1"),
        ("POST", "/api/v1/federation/sites/site-1/suspend"),
        ("POST", "/api/v1/federation/sites/site-1/resume"),
        ("DELETE", "/api/v1/federation/sites/site-1"),
        ("GET", "/api/v1/federation/sites/site-1/sync-status"),
        ("GET", "/api/v1/federation/hosts"),
        ("GET", "/api/v1/federation/hosts/host-1"),
        ("GET", "/api/v1/federation/rollups/dashboard"),
        ("GET", "/api/v1/federation/rollups/hosts"),
        ("GET", "/api/v1/federation/rollups/compliance"),
        ("GET", "/api/v1/federation/rollups/vulnerabilities"),
        ("GET", "/api/v1/federation/policies"),
        ("POST", "/api/v1/federation/policies"),
        ("GET", "/api/v1/federation/policies/policy-1"),
        ("PATCH", "/api/v1/federation/policies/policy-1"),
        ("DELETE", "/api/v1/federation/policies/policy-1"),
        ("POST", "/api/v1/federation/policies/policy-1/assign"),
        ("POST", "/api/v1/federation/policies/policy-1/push"),
        ("POST", "/api/v1/federation/commands/dispatch"),
        ("GET", "/api/v1/federation/commands"),
        ("GET", "/api/v1/federation/commands/cmd-1"),
        ("GET", "/api/v1/federation/audit"),
        ("GET", "/api/v1/federation/audit/entry-1"),
        # Phase 12.6 — sync ingest surface (site → coordinator).
        # These return 401 in the engine (no bearer token) but the
        # OSS stub layer returns 200 ``{licensed: false}`` uniformly
        # so callers can detect "module not licensed" without auth.
        ("POST", "/api/v1/federation/sites/site-1/rollups/hosts"),
        ("POST", "/api/v1/federation/sites/site-1/rollups/compliance"),
        ("POST", "/api/v1/federation/sites/site-1/rollups/vulnerabilities"),
        ("POST", "/api/v1/federation/sites/site-1/host-directory"),
        ("POST", "/api/v1/federation/sites/site-1/command-results"),
    ]

    @pytest.fixture
    def stub_only_app(self):
        """Build a fresh FastAPI app, mount federation stubs only.

        We bypass ``mount_proplus_routes`` so other engine stubs
        don't pollute the surface; this keeps the test focused on
        the federation block.  ``get_current_user`` is overridden
        with a no-op so the stubs don't need a real auth token.
        """
        from fastapi import FastAPI
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: "test-user"

        # results dict says federation engine NOT loaded -> stubs mount
        mount_proplus_stub_routes(app, {"federation_controller_engine": False})
        return app

    def test_all_federation_stubs_respond_licensed_false(self, stub_only_app):
        """Every stub endpoint returns 200 with ``licensed: False``.

        The shape is the contract for the frontend probe — if any
        endpoint regresses to a different shape (e.g. 404 from a
        prefix typo), the federation UI's "is this licensed?"
        detection breaks."""
        from fastapi.testclient import TestClient

        client = TestClient(stub_only_app)
        for method, path in self.STUB_ENDPOINTS:
            response = client.request(method, path, json={})
            assert response.status_code == 200, (
                f"{method} {path} returned {response.status_code} "
                f"(body={response.text[:200]})"
            )
            body = response.json()
            assert (
                body.get("licensed") is False
            ), f"{method} {path} body missing licensed=False: {body}"

    def test_federation_stub_count_locked(self, stub_only_app):
        """A safety net: the federation stub surface is exactly 32
        endpoint routes (matching ``STUB_ENDPOINTS``) — 27 from
        Phase 12.1/12.3 plus 5 ingest stubs from Phase 12.6.  If this
        count drifts unexpectedly, either someone added an endpoint
        without updating the test, or removed one — both should be a
        deliberate decision.

        Filter excludes ``/api/v1/federation/site/`` because Phase 12.2
        added a separate site-engine stub block at that prefix; those
        are counted by ``TestFederationSiteStubRoutes`` instead.
        """
        federation_routes = [
            r
            for r in stub_only_app.routes
            if hasattr(r, "path")
            and r.path.startswith("/api/v1/federation/")
            and not r.path.startswith("/api/v1/federation/site/")
        ]
        assert len(federation_routes) == len(self.STUB_ENDPOINTS)


# =============================================================================
# MODULE INFO TESTS
# =============================================================================


class TestModuleInfo:
    """Test cases for module info checking."""

    def test_module_info_version_logged(self, mock_app, mock_module_with_routes):
        """Test that module version is available in info."""
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_module_info.return_value = {
            "provides_routes": True,
            "version": "2.5.1",
        }
        mock_module.get_health_router.return_value = mock_router

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            result = mount_health_routes(mock_app)

            assert result is True
            mock_module.get_module_info.assert_called_once()

    def test_module_info_missing_provides_routes(self, mock_app):
        """Test handling when provides_routes key is missing."""
        mock_module = MagicMock()
        mock_module.get_module_info.return_value = {
            "version": "1.0.0",
            # 'provides_routes' key missing
        }

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            result = mount_health_routes(mock_app)

            # Should return False when provides_routes is not True
            assert result is False

    def test_module_info_provides_routes_false(self, mock_app):
        """Test handling when provides_routes is explicitly False."""
        mock_module = MagicMock()
        mock_module.get_module_info.return_value = {
            "provides_routes": False,
            "version": "1.0.0",
        }

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            result = mount_health_routes(mock_app)

            assert result is False


# =============================================================================
# ROUTER CONFIGURATION TESTS
# =============================================================================


class TestRouterConfiguration:
    """Test cases for router configuration."""

    def test_router_prefix_is_api(self, mock_app, mock_module_with_routes):
        """Test that routers are mounted with /api prefix."""
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_health_router.return_value = mock_router

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            mount_health_routes(mock_app)

            mock_app.include_router.assert_called_with(mock_router, prefix="/api")

    def test_all_routers_use_api_prefix(self, mock_app, mock_module_with_routes):
        """Test that all route types use /api prefix."""
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_vulnerability_router.return_value = mock_router
        mock_module.get_health_router.return_value = mock_router
        mock_module.get_compliance_router.return_value = mock_router
        mock_module.get_alerting_router.return_value = mock_router

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            mount_proplus_routes(mock_app)

            # All include_router calls should use /api prefix
            for call in mock_app.include_router.call_args_list:
                assert call.kwargs.get("prefix") == "/api"


# =============================================================================
# ERROR SCENARIO TESTS
# =============================================================================


class TestErrorScenarios:
    """Test cases for various error scenarios."""

    def test_get_module_info_raises(self, mock_app):
        """Test handling when get_module_info raises an exception."""
        mock_module = MagicMock()
        mock_module.get_module_info.side_effect = RuntimeError("Module error")

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            # Should catch exception and return False
            with pytest.raises(RuntimeError):
                mount_health_routes(mock_app)

    def test_include_router_raises(self, mock_app, mock_module_with_routes):
        """Test handling when include_router raises an exception."""
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_health_router.return_value = mock_router
        mock_app.include_router.side_effect = RuntimeError("Router error")

        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module

            result = mount_health_routes(mock_app)

            # Should catch exception and return False
            assert result is False

    def test_module_loader_exception(self, mock_app):
        """Test handling when module_loader.get_module raises."""
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.side_effect = RuntimeError("Loader error")

            with pytest.raises(RuntimeError):
                mount_health_routes(mock_app)


# =============================================================================
# mount_federation_site_routes() + stub surface (Phase 12.2)
# =============================================================================


class TestMountFederationSiteRoutes:
    """Mount-function tests for the site engine, mirroring
    ``TestMountFederationControllerRoutes``.  Site engine and
    controller engine are mutually exclusive in production but both
    mount paths exist on every binary."""

    def test_routes_module_not_loaded(self, mock_app):
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = None
            assert mount_federation_site_routes(mock_app) is False
            mock_loader.get_module.assert_called_once_with("federation_site_engine")
            mock_app.include_router.assert_not_called()

    def test_routes_module_no_routes(self, mock_app, mock_module_without_routes):
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module_without_routes
            assert mount_federation_site_routes(mock_app) is False
            mock_app.include_router.assert_not_called()

    def test_routes_success(self, mock_app, mock_module_with_routes):
        mock_module, mock_router = mock_module_with_routes
        mock_module.get_federation_site_router.return_value = mock_router
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module
            assert mount_federation_site_routes(mock_app) is True
            mock_app.include_router.assert_called_once_with(mock_router, prefix="/api")

    def test_routes_exception(self, mock_app, mock_module_with_routes):
        mock_module, _ = mock_module_with_routes
        mock_module.get_federation_site_router.side_effect = RuntimeError("boom")
        with patch("backend.api.proplus_routes.module_loader") as mock_loader:
            mock_loader.get_module.return_value = mock_module
            assert mount_federation_site_routes(mock_app) is False
            mock_app.include_router.assert_not_called()


class TestFederationSiteStubRoutes:
    """Every site stub endpoint returns 200 with ``{licensed: false, ...}``.
    Pinned so a future refactor that drops a stub gets caught."""

    STUB_ENDPOINTS = [
        ("POST", "/api/v1/federation/site/enroll"),
        ("GET", "/api/v1/federation/site/enrollment-status"),
        ("POST", "/api/v1/federation/site/policies"),
        ("POST", "/api/v1/federation/site/commands"),
        ("GET", "/api/v1/federation/site/sync-status"),
        ("GET", "/api/v1/federation/site/sync-queue/depth"),
        ("GET", "/api/v1/federation/site/received-policies"),
        ("GET", "/api/v1/federation/site/received-commands"),
    ]

    @pytest.fixture
    def stub_only_app(self):
        from fastapi import FastAPI
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: "test-user"
        # Mount both engine stubs as "not loaded".  Assertions below
        # focus on the site paths.
        mount_proplus_stub_routes(
            app,
            {
                "federation_site_engine": False,
                "federation_controller_engine": False,
            },
        )
        return app

    def test_all_site_stubs_respond_licensed_false(self, stub_only_app):
        from fastapi.testclient import TestClient

        client = TestClient(stub_only_app)
        for method, path in self.STUB_ENDPOINTS:
            response = client.request(method, path, json={})
            assert response.status_code == 200, (
                f"{method} {path} returned {response.status_code} "
                f"(body={response.text[:200]})"
            )
            assert response.json().get("licensed") is False

    def test_site_stub_count_locked(self, stub_only_app):
        """Trailing slash matters: the controller block's
        ``/api/v1/federation/sites`` (plural, registry of sites)
        would otherwise match ``startswith("/api/v1/federation/site")``
        too.  Require the trailing slash so we only match the
        site-engine prefix."""
        site_routes = [
            r
            for r in stub_only_app.routes
            if hasattr(r, "path") and r.path.startswith("/api/v1/federation/site/")
        ]
        assert len(site_routes) == len(self.STUB_ENDPOINTS)
