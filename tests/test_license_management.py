"""
Tests for backend/api/license_management.py module.
Tests Pro+ license management API endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestLicenseInfoResponse:
    """Tests for LicenseInfoResponse model."""

    def test_inactive_license(self):
        """Test inactive license response."""
        from backend.api.license_management import LicenseInfoResponse

        response = LicenseInfoResponse(active=False)
        assert response.active is False
        assert response.tier is None
        assert response.features is None

    def test_active_license(self):
        """Test active license response."""
        from backend.api.license_management import LicenseInfoResponse

        response = LicenseInfoResponse(
            active=True,
            tier="enterprise",
            license_id="lic-123",
            features=["health", "vuln"],
            modules=["health_engine", "vuln_engine"],
            expires_at="2025-12-31",
            customer_name="Test Corp",
            parent_hosts=100,
            child_hosts=500,
        )

        assert response.active is True
        assert response.tier == "enterprise"
        assert response.license_id == "lic-123"
        assert len(response.features) == 2
        assert len(response.modules) == 2
        assert response.parent_hosts == 100
        assert response.child_hosts == 500


class TestLicenseInstallRequest:
    """Tests for LicenseInstallRequest model."""

    def test_valid_request(self):
        """Test valid license install request."""
        from backend.api.license_management import LicenseInstallRequest

        request = LicenseInstallRequest(license_key="ABC123XYZ")
        assert request.license_key == "ABC123XYZ"


class TestLicenseInstallResponse:
    """Tests for LicenseInstallResponse model."""

    def test_success_response(self):
        """Test successful install response."""
        from backend.api.license_management import (
            LicenseInfoResponse,
            LicenseInstallResponse,
        )

        license_info = LicenseInfoResponse(active=True, tier="professional")
        response = LicenseInstallResponse(
            success=True,
            message="License installed successfully",
            license_info=license_info,
        )

        assert response.success is True
        assert response.license_info.tier == "professional"

    def test_failure_response(self):
        """Test failed install response."""
        from backend.api.license_management import LicenseInstallResponse

        response = LicenseInstallResponse(
            success=False,
            message="Invalid license key",
            license_info=None,
        )

        assert response.success is False
        assert response.license_info is None


class TestGetLicenseInfo:
    """Tests for get_license_info endpoint."""

    @patch("backend.api.license_management.license_service")
    def test_get_license_inactive(self, mock_license_service):
        """Test getting license info when Pro+ is inactive."""
        from backend.api.license_management import router
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.include_router(router, prefix="/api/proplus")

        mock_license_service.is_pro_plus_active = False

        app.dependency_overrides[get_current_user] = lambda: "test@example.com"

        client = TestClient(app)
        response = client.get("/api/proplus/license")

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False

    @patch("backend.api.license_management.license_service")
    def test_get_license_active(self, mock_license_service):
        """Test getting license info when Pro+ is active."""
        from backend.api.license_management import router
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.include_router(router, prefix="/api/proplus")

        mock_license_service.is_pro_plus_active = True
        mock_license_service.get_license_info.return_value = {
            "tier": "enterprise",
            "license_id": "lic-456",
            "features": ["health", "vuln", "compliance"],
            "modules": ["health_engine"],
            "expires_at": "2026-01-01",
            "customer_name": "Acme Inc",
            "parent_hosts": 50,
            "child_hosts": 200,
        }

        app.dependency_overrides[get_current_user] = lambda: "test@example.com"

        client = TestClient(app)
        response = client.get("/api/proplus/license")

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is True
        assert data["tier"] == "enterprise"
        assert data["customer_name"] == "Acme Inc"
        assert data["parent_hosts"] == 50


class TestInstallLicense:
    """Tests for install_license endpoint."""

    @patch("backend.api.license_management.license_service")
    @patch("backend.api.license_management.db_module")
    @patch("backend.api.license_management.sessionmaker")
    def test_install_license_success(
        self, mock_sessionmaker, mock_db_module, mock_license_service
    ):
        """Test successful license installation."""
        from backend.api.license_management import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router, prefix="/api/proplus")

        # Mock user as admin
        mock_user = MagicMock()
        mock_user.userid = "admin@example.com"
        mock_user.is_admin = True

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        # Mock license installation result
        mock_result = MagicMock()
        mock_result.valid = True
        mock_license_service.install_license = AsyncMock(return_value=mock_result)
        mock_license_service.get_license_info.return_value = {
            "tier": "professional",
            "license_id": "lic-new",
            "features": ["health"],
            "modules": ["health_engine"],
            "expires_at": "2025-06-30",
            "customer_name": "New Customer",
            "parent_hosts": 25,
            "child_hosts": 100,
        }

        mock_db = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: "admin@example.com"
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post(
            "/api/proplus/license",
            json={"license_key": "VALID-LICENSE-KEY"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["license_info"]["tier"] == "professional"

    @patch("backend.api.license_management.db_module")
    @patch("backend.api.license_management.sessionmaker")
    def test_install_license_user_not_found(self, mock_sessionmaker, mock_db_module):
        """Test license installation when user not found."""
        from backend.api.license_management import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router, prefix="/api/proplus")

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        mock_db = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: "unknown@example.com"
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post(
            "/api/proplus/license",
            json={"license_key": "SOME-KEY"},
        )

        assert response.status_code == 401

    @patch("backend.api.license_management.db_module")
    @patch("backend.api.license_management.sessionmaker")
    def test_install_license_not_admin(self, mock_sessionmaker, mock_db_module):
        """Test license installation when user is not admin."""
        from backend.api.license_management import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router, prefix="/api/proplus")

        mock_user = MagicMock()
        mock_user.userid = "user@example.com"
        mock_user.is_admin = False

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        mock_db = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: "user@example.com"
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post(
            "/api/proplus/license",
            json={"license_key": "SOME-KEY"},
        )

        assert response.status_code == 403

    @patch("backend.api.license_management.license_service")
    @patch("backend.api.license_management.db_module")
    @patch("backend.api.license_management.sessionmaker")
    def test_install_license_invalid_key(
        self, mock_sessionmaker, mock_db_module, mock_license_service
    ):
        """Test license installation with invalid key."""
        from backend.api.license_management import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router, prefix="/api/proplus")

        mock_user = MagicMock()
        mock_user.userid = "admin@example.com"
        mock_user.is_admin = True

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        mock_result = MagicMock()
        mock_result.valid = False
        mock_result.error = "Invalid license format"
        mock_license_service.install_license = AsyncMock(return_value=mock_result)

        mock_db = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: "admin@example.com"
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post(
            "/api/proplus/license",
            json={"license_key": "INVALID-KEY"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Invalid license format" in data["message"]

    @patch("backend.api.license_management.license_service")
    @patch("backend.api.license_management.db_module")
    @patch("backend.api.license_management.sessionmaker")
    def test_install_license_exception(
        self, mock_sessionmaker, mock_db_module, mock_license_service
    ):
        """Test license installation with exception."""
        from backend.api.license_management import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router, prefix="/api/proplus")

        mock_user = MagicMock()
        mock_user.userid = "admin@example.com"
        mock_user.is_admin = True

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        mock_license_service.install_license = AsyncMock(
            side_effect=Exception("Network error")
        )

        mock_db = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: "admin@example.com"
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.post(
            "/api/proplus/license",
            json={"license_key": "SOME-KEY"},
        )

        assert response.status_code == 500


class TestRouterConfiguration:
    """Tests for router configuration."""

    def test_router_exists(self):
        """Test router is created."""
        from backend.api.license_management import router

        assert router is not None
