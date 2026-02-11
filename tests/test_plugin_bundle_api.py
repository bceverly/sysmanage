"""
Tests for backend/api/plugin_bundle.py module.
Tests plugin bundle serving endpoints.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestPluginBundleConstants:
    """Tests for module constants."""

    def test_default_modules_path(self):
        """Test DEFAULT_MODULES_PATH constant."""
        from backend.api.plugin_bundle import DEFAULT_MODULES_PATH

        assert DEFAULT_MODULES_PATH == "/var/lib/sysmanage/modules"

    def test_invalid_bundle_filename_msg(self):
        """Test _INVALID_BUNDLE_FILENAME_MSG constant."""
        from backend.api.plugin_bundle import _INVALID_BUNDLE_FILENAME_MSG

        assert _INVALID_BUNDLE_FILENAME_MSG == "Invalid bundle filename"


class TestPluginBundleListResponse:
    """Tests for PluginBundleListResponse model."""

    def test_model_structure(self):
        """Test PluginBundleListResponse model structure."""
        from backend.api.plugin_bundle import PluginBundleListResponse

        response = PluginBundleListResponse(bundles=["/api/plugins/bundle/test.js"])

        assert response.bundles == ["/api/plugins/bundle/test.js"]

    def test_empty_bundles(self):
        """Test PluginBundleListResponse with empty bundles."""
        from backend.api.plugin_bundle import PluginBundleListResponse

        response = PluginBundleListResponse(bundles=[])

        assert response.bundles == []


class TestGetModulesPath:
    """Tests for _get_modules_path function."""

    @patch("backend.config.config.get_config")
    def test_get_modules_path_default(self, mock_get_config):
        """Test _get_modules_path returns default when not configured."""
        from backend.api.plugin_bundle import _get_modules_path

        mock_get_config.return_value = {"license": {}}

        path = _get_modules_path()

        assert path == "/var/lib/sysmanage/modules"

    @patch("backend.config.config.get_config")
    def test_get_modules_path_configured(self, mock_get_config):
        """Test _get_modules_path returns configured value."""
        from backend.api.plugin_bundle import _get_modules_path

        mock_get_config.return_value = {"license": {"modules_path": "/custom/path"}}

        path = _get_modules_path()

        assert path == "/custom/path"


class TestListPluginBundles:
    """Tests for list_plugin_bundles endpoint."""

    @patch("backend.api.plugin_bundle._get_modules_path")
    @patch("backend.api.plugin_bundle.glob.glob")
    def test_list_plugin_bundles_empty(self, mock_glob, mock_path):
        """Test list_plugin_bundles returns empty list when no bundles."""
        from backend.api.plugin_bundle import router
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.include_router(router, prefix="/api")

        mock_path.return_value = "/var/lib/sysmanage/modules"
        mock_glob.return_value = []

        app.dependency_overrides[get_current_user] = lambda: "test@example.com"

        client = TestClient(app)
        response = client.get("/api/plugins/bundles")

        assert response.status_code == 200
        assert response.json()["bundles"] == []

    @patch("backend.api.plugin_bundle._get_modules_path")
    @patch("backend.api.plugin_bundle.glob.glob")
    def test_list_plugin_bundles_with_bundles(self, mock_glob, mock_path):
        """Test list_plugin_bundles returns bundle URLs."""
        from backend.api.plugin_bundle import router
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.include_router(router, prefix="/api")

        mock_path.return_value = "/modules"
        mock_glob.return_value = [
            "/modules/health_engine-plugin.iife.js",
            "/modules/vuln_engine-plugin.iife.js",
        ]

        app.dependency_overrides[get_current_user] = lambda: "test@example.com"

        client = TestClient(app)
        response = client.get("/api/plugins/bundles")

        assert response.status_code == 200
        bundles = response.json()["bundles"]
        assert len(bundles) == 2
        assert "/api/plugins/bundle/health_engine-plugin.iife.js" in bundles
        assert "/api/plugins/bundle/vuln_engine-plugin.iife.js" in bundles


class TestGetPluginBundle:
    """Tests for get_plugin_bundle endpoint."""

    def test_get_plugin_bundle_non_js_file(self):
        """Test get_plugin_bundle rejects non-JS files."""
        from backend.api.plugin_bundle import router
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.include_router(router, prefix="/api")

        app.dependency_overrides[get_current_user] = lambda: "test@example.com"

        client = TestClient(app)
        response = client.get("/api/plugins/bundle/evil.txt")

        assert response.status_code == 400
        assert "Invalid bundle filename" in response.json()["error"]

    def test_get_plugin_bundle_path_traversal_backslash(self):
        """Test get_plugin_bundle rejects path traversal with backslash."""
        from backend.api.plugin_bundle import router
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.include_router(router, prefix="/api")

        app.dependency_overrides[get_current_user] = lambda: "test@example.com"

        client = TestClient(app)
        # Test backslash in filename
        response = client.get("/api/plugins/bundle/test\\evil.js")

        # Should reject filenames containing backslashes
        assert response.status_code == 400

    def test_get_plugin_bundle_path_traversal_dotdot(self):
        """Test get_plugin_bundle rejects path traversal with ..."""
        from backend.api.plugin_bundle import router
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.include_router(router, prefix="/api")

        app.dependency_overrides[get_current_user] = lambda: "test@example.com"

        client = TestClient(app)
        response = client.get("/api/plugins/bundle/..evil.js")

        assert response.status_code == 400

    @patch("backend.api.plugin_bundle._get_modules_path")
    @patch("backend.api.plugin_bundle.os.path.isfile")
    @patch("backend.api.plugin_bundle.os.path.realpath")
    def test_get_plugin_bundle_not_found(self, mock_realpath, mock_isfile, mock_path):
        """Test get_plugin_bundle returns 404 when file not found."""
        from backend.api.plugin_bundle import router
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.include_router(router, prefix="/api")

        mock_path.return_value = "/modules"
        mock_realpath.side_effect = lambda x: x  # Return path as-is
        mock_isfile.return_value = False

        app.dependency_overrides[get_current_user] = lambda: "test@example.com"

        client = TestClient(app)
        response = client.get("/api/plugins/bundle/nonexistent.js")

        assert response.status_code == 404
        assert "not found" in response.json()["error"]

    @patch("backend.api.plugin_bundle._get_modules_path")
    @patch("backend.api.plugin_bundle.os.path.isfile")
    @patch("backend.api.plugin_bundle.os.path.realpath")
    def test_get_plugin_bundle_path_escape_attempt(
        self, mock_realpath, mock_isfile, mock_path
    ):
        """Test get_plugin_bundle blocks path escape attempts."""
        from backend.api.plugin_bundle import router
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.include_router(router, prefix="/api")

        mock_path.return_value = "/modules"
        # Simulate realpath resolving to outside modules dir
        mock_realpath.side_effect = lambda x: (
            "/modules" if x == "/modules" else "/etc/passwd"
        )
        mock_isfile.return_value = True

        app.dependency_overrides[get_current_user] = lambda: "test@example.com"

        client = TestClient(app)
        response = client.get("/api/plugins/bundle/symlink.js")

        assert response.status_code == 400


class TestRouterConfiguration:
    """Tests for router configuration."""

    def test_router_exists(self):
        """Test router exists."""
        from backend.api.plugin_bundle import router

        assert router is not None
