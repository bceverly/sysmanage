"""
Comprehensive unit tests for the license management API endpoints.

Tests cover:
- License info endpoint
- License installation endpoint
- Authentication requirements
- Admin privilege checks
- Error handling
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.userid = "admin-user"
    user.username = "Admin User"
    user.email = "admin@example.com"
    user.is_admin = True
    return user


@pytest.fixture
def mock_regular_user():
    """Create a mock regular (non-admin) user."""
    user = MagicMock()
    user.userid = "regular-user"
    user.username = "Regular User"
    user.email = "user@example.com"
    user.is_admin = False
    return user


# =============================================================================
# LicenseInfoResponse TESTS
# =============================================================================


class TestLicenseInfoResponse:
    """Test cases for LicenseInfoResponse schema."""

    def test_license_info_inactive(self):
        """Test LicenseInfoResponse for inactive license."""
        from backend.api.license_management import LicenseInfoResponse

        response = LicenseInfoResponse(active=False)
        assert response.active is False
        assert response.tier is None
        assert response.license_id is None

    def test_license_info_active(self):
        """Test LicenseInfoResponse for active license."""
        from backend.api.license_management import LicenseInfoResponse

        response = LicenseInfoResponse(
            active=True,
            tier="professional",
            license_id="LIC-123-456",
            features=["health", "vuln"],
            modules=["health_engine", "vuln_engine"],
            expires_at="2025-12-31T23:59:59Z",
            customer_name="Test Company",
            parent_hosts=10,
            child_hosts=100,
        )
        assert response.active is True
        assert response.tier == "professional"
        assert response.license_id == "LIC-123-456"
        assert len(response.features) == 2
        assert len(response.modules) == 2
        assert response.parent_hosts == 10
        assert response.child_hosts == 100


# =============================================================================
# LicenseInstallRequest TESTS
# =============================================================================


class TestLicenseInstallRequest:
    """Test cases for LicenseInstallRequest schema."""

    def test_install_request_valid(self):
        """Test LicenseInstallRequest with valid key."""
        from backend.api.license_management import LicenseInstallRequest

        request = LicenseInstallRequest(license_key="VALID-LICENSE-KEY-123")
        assert request.license_key == "VALID-LICENSE-KEY-123"

    def test_install_request_required_field(self):
        """Test LicenseInstallRequest requires license_key."""
        from backend.api.license_management import LicenseInstallRequest

        with pytest.raises(Exception):  # Pydantic validation error
            LicenseInstallRequest()


# =============================================================================
# LicenseInstallResponse TESTS
# =============================================================================


class TestLicenseInstallResponse:
    """Test cases for LicenseInstallResponse schema."""

    def test_install_response_success(self):
        """Test LicenseInstallResponse for successful installation."""
        from backend.api.license_management import (
            LicenseInfoResponse,
            LicenseInstallResponse,
        )

        license_info = LicenseInfoResponse(
            active=True,
            tier="professional",
            license_id="LIC-123",
        )
        response = LicenseInstallResponse(
            success=True,
            message="License installed successfully",
            license_info=license_info,
        )
        assert response.success is True
        assert response.license_info.active is True

    def test_install_response_failure(self):
        """Test LicenseInstallResponse for failed installation."""
        from backend.api.license_management import LicenseInstallResponse

        response = LicenseInstallResponse(
            success=False,
            message="Invalid license key",
            license_info=None,
        )
        assert response.success is False
        assert response.license_info is None


# =============================================================================
# get_license_info ENDPOINT TESTS
# =============================================================================


class TestGetLicenseInfoEndpoint:
    """Test cases for get_license_info API endpoint."""

    @pytest.mark.asyncio
    async def test_get_license_info_no_proplus(self):
        """Test get_license_info when Pro+ is not active."""
        from backend.api.license_management import get_license_info

        with patch(
            "backend.api.license_management.license_service"
        ) as mock_license_service:
            mock_license_service.is_pro_plus_active = False

            result = await get_license_info(current_user="test-user")

            assert result.active is False
            assert result.tier is None

    @pytest.mark.asyncio
    async def test_get_license_info_with_proplus(self):
        """Test get_license_info when Pro+ is active."""
        from backend.api.license_management import get_license_info

        mock_info = {
            "tier": "enterprise",
            "license_id": "LIC-ENT-001",
            "features": ["health", "vuln", "compliance"],
            "modules": ["health_engine", "vuln_engine"],
            "expires_at": "2025-12-31T23:59:59Z",
            "customer_name": "Enterprise Corp",
            "parent_hosts": 50,
            "child_hosts": 500,
        }

        with patch(
            "backend.api.license_management.license_service"
        ) as mock_license_service:
            mock_license_service.is_pro_plus_active = True
            mock_license_service.get_license_info.return_value = mock_info

            result = await get_license_info(current_user="test-user")

            assert result.active is True
            assert result.tier == "enterprise"
            assert result.license_id == "LIC-ENT-001"
            assert "health" in result.features
            assert result.parent_hosts == 50

    @pytest.mark.asyncio
    async def test_get_license_info_partial_info(self):
        """Test get_license_info with partial license info."""
        from backend.api.license_management import get_license_info

        mock_info = {
            "tier": "professional",
            "license_id": "LIC-PRO-001",
            # Missing other fields
        }

        with patch(
            "backend.api.license_management.license_service"
        ) as mock_license_service:
            mock_license_service.is_pro_plus_active = True
            mock_license_service.get_license_info.return_value = mock_info

            result = await get_license_info(current_user="test-user")

            assert result.active is True
            assert result.tier == "professional"
            assert result.features is None
            assert result.modules is None


# =============================================================================
# install_license ENDPOINT TESTS
# =============================================================================


class TestInstallLicenseEndpoint:
    """Test cases for install_license API endpoint."""

    @pytest.mark.asyncio
    async def test_install_license_user_not_found(self, mock_db):
        """Test install_license when user is not found."""
        from backend.api.license_management import (
            LicenseInstallRequest,
            install_license,
        )

        request = LicenseInstallRequest(license_key="TEST-KEY")

        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("backend.api.license_management.db_module") as mock_db_module, patch(
            "backend.api.license_management.sessionmaker"
        ) as mock_sessionmaker:
            mock_db_module.get_engine.return_value = mock_engine
            mock_sessionmaker.return_value.return_value = mock_session

            with pytest.raises(HTTPException) as exc_info:
                await install_license(
                    request=request,
                    db=mock_db,
                    current_user="unknown-user",
                )

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_install_license_not_admin(self, mock_db, mock_regular_user):
        """Test install_license when user is not admin."""
        from backend.api.license_management import (
            LicenseInstallRequest,
            install_license,
        )

        request = LicenseInstallRequest(license_key="TEST-KEY")

        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_regular_user
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("backend.api.license_management.db_module") as mock_db_module, patch(
            "backend.api.license_management.sessionmaker"
        ) as mock_sessionmaker:
            mock_db_module.get_engine.return_value = mock_engine
            mock_sessionmaker.return_value.return_value = mock_session

            with pytest.raises(HTTPException) as exc_info:
                await install_license(
                    request=request,
                    db=mock_db,
                    current_user="regular-user",
                )

            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_install_license_success(self, mock_db, mock_admin_user):
        """Test successful license installation."""
        from backend.api.license_management import (
            LicenseInstallRequest,
            install_license,
        )

        request = LicenseInstallRequest(license_key="VALID-LICENSE-KEY")

        mock_result = MagicMock()
        mock_result.valid = True

        mock_info = {
            "tier": "professional",
            "license_id": "LIC-NEW-001",
            "features": ["health"],
            "modules": ["health_engine"],
            "expires_at": "2025-12-31T23:59:59Z",
            "customer_name": "New Customer",
            "parent_hosts": 10,
            "child_hosts": 100,
        }

        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_admin_user
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("backend.api.license_management.db_module") as mock_db_module, patch(
            "backend.api.license_management.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.license_management.license_service"
        ) as mock_license_service:
            mock_db_module.get_engine.return_value = mock_engine
            mock_sessionmaker.return_value.return_value = mock_session
            mock_license_service.install_license = AsyncMock(return_value=mock_result)
            mock_license_service.get_license_info.return_value = mock_info

            result = await install_license(
                request=request,
                db=mock_db,
                current_user="admin-user",
            )

            assert result.success is True
            assert result.license_info.active is True
            assert result.license_info.tier == "professional"

    @pytest.mark.asyncio
    async def test_install_license_validation_failed(self, mock_db, mock_admin_user):
        """Test license installation with validation failure."""
        from backend.api.license_management import (
            LicenseInstallRequest,
            install_license,
        )

        request = LicenseInstallRequest(license_key="INVALID-KEY")

        mock_result = MagicMock()
        mock_result.valid = False
        mock_result.error = "Invalid license signature"

        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_admin_user
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("backend.api.license_management.db_module") as mock_db_module, patch(
            "backend.api.license_management.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.license_management.license_service"
        ) as mock_license_service:
            mock_db_module.get_engine.return_value = mock_engine
            mock_sessionmaker.return_value.return_value = mock_session
            mock_license_service.install_license = AsyncMock(return_value=mock_result)

            result = await install_license(
                request=request,
                db=mock_db,
                current_user="admin-user",
            )

            assert result.success is False
            assert result.message == "Invalid license signature"

    @pytest.mark.asyncio
    async def test_install_license_exception(self, mock_db, mock_admin_user):
        """Test license installation with exception."""
        from backend.api.license_management import (
            LicenseInstallRequest,
            install_license,
        )

        request = LicenseInstallRequest(license_key="TEST-KEY")

        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_admin_user
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("backend.api.license_management.db_module") as mock_db_module, patch(
            "backend.api.license_management.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.license_management.license_service"
        ) as mock_license_service:
            mock_db_module.get_engine.return_value = mock_engine
            mock_sessionmaker.return_value.return_value = mock_session
            mock_license_service.install_license = AsyncMock(
                side_effect=Exception("Network error")
            )

            with pytest.raises(HTTPException) as exc_info:
                await install_license(
                    request=request,
                    db=mock_db,
                    current_user="admin-user",
                )

            assert exc_info.value.status_code == 500
            assert "Network error" in exc_info.value.detail


# =============================================================================
# ROUTER TESTS
# =============================================================================


class TestLicenseManagementRouter:
    """Test cases for the license management router configuration."""

    def test_router_exists(self):
        """Test that router is defined."""
        from backend.api.license_management import router

        assert router is not None

    def test_router_routes(self):
        """Test that expected routes are registered."""
        from backend.api.license_management import router

        routes = [route.path for route in router.routes]
        assert "/license" in routes


# =============================================================================
# INTEGRATION TESTS (with mocked external dependencies)
# =============================================================================


class TestLicenseManagementIntegration:
    """Integration-style tests for license management API."""

    @pytest.mark.asyncio
    async def test_full_license_check_flow(self):
        """Test complete license check flow."""
        from backend.api.license_management import get_license_info

        # Simulate Pro+ license check flow
        with patch(
            "backend.api.license_management.license_service"
        ) as mock_license_service:
            # First check - no license
            mock_license_service.is_pro_plus_active = False
            result1 = await get_license_info(current_user="test-user")
            assert result1.active is False

            # Second check - license installed
            mock_license_service.is_pro_plus_active = True
            mock_license_service.get_license_info.return_value = {
                "tier": "professional",
                "license_id": "LIC-001",
            }
            result2 = await get_license_info(current_user="test-user")
            assert result2.active is True
            assert result2.tier == "professional"

    @pytest.mark.asyncio
    async def test_license_tier_values(self):
        """Test various license tier values."""
        from backend.api.license_management import get_license_info

        tiers = ["professional", "enterprise"]

        for tier in tiers:
            with patch(
                "backend.api.license_management.license_service"
            ) as mock_license_service:
                mock_license_service.is_pro_plus_active = True
                mock_license_service.get_license_info.return_value = {
                    "tier": tier,
                    "license_id": f"LIC-{tier.upper()}",
                }

                result = await get_license_info(current_user="test-user")

                assert result.tier == tier

    @pytest.mark.asyncio
    async def test_license_features_list(self):
        """Test license with various feature combinations."""
        from backend.api.license_management import get_license_info

        feature_sets = [
            ["health"],
            ["health", "vuln"],
            ["health", "vuln", "compliance", "alerts"],
        ]

        for features in feature_sets:
            with patch(
                "backend.api.license_management.license_service"
            ) as mock_license_service:
                mock_license_service.is_pro_plus_active = True
                mock_license_service.get_license_info.return_value = {
                    "tier": "professional",
                    "license_id": "LIC-001",
                    "features": features,
                }

                result = await get_license_info(current_user="test-user")

                assert result.features == features
                assert len(result.features) == len(features)
