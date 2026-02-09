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
    mount_health_routes,
    mount_proplus_routes,
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

        with patch("backend.api.proplus_routes.module_loader") as mock_loader, patch(
            "backend.api.proplus_routes.get_db"
        ), patch("backend.api.proplus_routes.get_current_user"), patch(
            "backend.api.proplus_routes.requires_feature"
        ), patch(
            "backend.api.proplus_routes.requires_module"
        ), patch(
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
