"""
Unit tests for backend.api.email module.
Tests email configuration and testing endpoints.
"""

from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from backend.api.email import EmailConfigResponse, EmailTestRequest, router


class TestEmailModels:
    """Test cases for email API models."""

    def test_email_test_request_model(self):
        """Test EmailTestRequest model validation."""
        request = EmailTestRequest(to_address="test@example.com")
        assert request.to_address == "test@example.com"

    def test_email_test_request_invalid_email(self):
        """Test EmailTestRequest with invalid email."""
        with pytest.raises(ValueError):
            EmailTestRequest(to_address="invalid-email")

    def test_email_config_response_model(self):
        """Test EmailConfigResponse model."""
        response = EmailConfigResponse(
            enabled=True,
            smtp_host="smtp.example.com",
            smtp_port=587,
            from_address="from@example.com",
            from_name="Test System",
            subject_prefix="[SysManage]",
            configured=True,
        )
        assert response.enabled is True
        assert response.smtp_host == "smtp.example.com"
        assert response.smtp_port == 587
        assert response.from_address == "from@example.com"
        assert response.from_name == "Test System"
        assert response.subject_prefix == "[SysManage]"
        assert response.configured is True


class TestEmailRoutes:
    """Test cases for email API routes."""

    def setup_method(self):
        """Set up test fixtures."""
        self.router = router

    @patch("backend.api.email.config")
    async def test_get_email_config_enabled(self, mock_config):
        """Test getting email configuration when enabled."""
        # Mock config values
        mock_config.get_email_config.return_value = {
            "enabled": True,
            "from_address": "noreply@test.com",
            "from_name": "Test System",
            "templates": {"subject_prefix": "[Test]"},
        }
        mock_config.get_smtp_config.return_value = {
            "host": "smtp.test.com",
            "port": 587,
            "username": "testuser",
            "password": "testpass",
        }

        # Import and call the function directly
        from backend.api.email import get_email_config

        # Mock current user
        mock_user = Mock()
        result = await get_email_config(current_user=mock_user)

        assert result.enabled is True
        assert result.smtp_host == "smtp.test.com"
        assert result.smtp_port == 587
        assert result.from_address == "noreply@test.com"
        assert result.from_name == "Test System"
        assert result.subject_prefix == "[Test]"
        assert result.configured is True

    @patch("backend.api.email.config")
    async def test_get_email_config_disabled(self, mock_config):
        """Test getting email configuration when disabled."""
        # Mock config values for disabled email
        mock_config.get_email_config.return_value = {
            "enabled": False,
            "from_address": "",
            "from_name": "",
            "templates": {"subject_prefix": ""},
        }
        mock_config.get_smtp_config.return_value = {
            "host": "",
            "port": 587,
            "username": "",
            "password": "",
        }

        from backend.api.email import get_email_config

        # Mock current user
        mock_user = Mock()
        result = await get_email_config(current_user=mock_user)

        assert result.enabled is False
        assert result.smtp_host == ""
        assert result.smtp_port == 587
        assert result.from_address == ""
        assert result.from_name == ""

    @patch("backend.api.email.config")
    async def test_get_email_config_exception(self, mock_config):
        """Test get_email_config with exception handling."""
        # Mock config to raise an exception
        mock_config.get_email_config.side_effect = Exception("Configuration error")

        # Mock current user
        mock_user = Mock()
        mock_user.email = "admin@test.com"

        from backend.api.email import get_email_config

        # Should raise HTTPException due to configuration error
        with pytest.raises(HTTPException) as exc_info:
            await get_email_config(current_user=mock_user)

        assert exc_info.value.status_code == 500
        assert "Failed to get email configuration" in str(exc_info.value.detail)

    @patch("backend.api.email.email_service")
    async def test_test_email_success(self, mock_email_service):
        """Test successful email test."""
        # Mock email service enabled
        mock_email_service.is_enabled.return_value = True
        # Mock successful email send
        mock_email_service.send_test_email.return_value = True

        # Mock current user
        mock_user = Mock()
        mock_user.email = "admin@test.com"

        from backend.api.email import test_email_config

        request = EmailTestRequest(to_address="recipient@test.com")
        result = await test_email_config(request, current_user=mock_user)

        assert result.success is True
        assert "Test email sent successfully" in result.message
        mock_email_service.send_test_email.assert_called_once_with("recipient@test.com")

    @patch("backend.api.email.email_service")
    async def test_test_email_disabled(self, mock_email_service):
        """Test email test when email is disabled."""
        # Mock email service disabled
        mock_email_service.is_enabled.return_value = False

        # Mock current user
        mock_user = Mock()
        mock_user.email = "admin@test.com"

        from backend.api.email import test_email_config

        request = EmailTestRequest(to_address="recipient@test.com")
        result = await test_email_config(request, current_user=mock_user)

        assert result.success is False
        assert "Email service is disabled" in result.message

    @patch("backend.api.email.email_service")
    async def test_test_email_send_failure(self, mock_email_service):
        """Test email test when sending fails."""
        # Mock email service enabled but send fails
        mock_email_service.is_enabled.return_value = True
        mock_email_service.send_test_email.return_value = False

        # Mock current user
        mock_user = Mock()
        mock_user.email = "admin@test.com"

        from backend.api.email import test_email_config

        request = EmailTestRequest(to_address="recipient@test.com")
        result = await test_email_config(request, current_user=mock_user)

        assert result.success is False
        assert "Failed to send test email" in result.message

    @patch("backend.api.email.email_service")
    async def test_test_email_exception(self, mock_email_service):
        """Test email test when an exception occurs."""
        # Mock email service enabled but exception occurs
        mock_email_service.is_enabled.return_value = True
        mock_email_service.send_test_email.side_effect = Exception(
            "SMTP connection failed"
        )

        # Mock current user
        mock_user = Mock()
        mock_user.email = "admin@test.com"

        from backend.api.email import test_email_config

        request = EmailTestRequest(to_address="recipient@test.com")
        result = await test_email_config(request, current_user=mock_user)

        assert result.success is False
        assert "Error sending test email" in result.message


class TestEmailAPI:
    """Integration tests for email API."""

    def test_router_exists(self):
        """Test that router is properly configured."""
        assert router is not None
        assert hasattr(router, "routes")

        # Check that routes are registered
        route_paths = [route.path for route in router.routes]
        assert len(route_paths) >= 2  # Should have at least config and test routes


class TestEmailValidation:
    """Test email validation and edge cases."""

    def test_email_test_request_with_various_valid_emails(self):
        """Test EmailTestRequest with various valid email formats."""
        valid_emails = [
            "user@example.com",
            "user.name@example.com",
            "user+tag@example.com",
            "user@subdomain.example.com",
            "123@example.com",
            "test@example-domain.com",
        ]

        for email in valid_emails:
            request = EmailTestRequest(to_address=email)
            assert request.to_address == email

    def test_email_test_request_with_invalid_emails(self):
        """Test EmailTestRequest with invalid email formats."""
        invalid_emails = [
            "plainaddress",
            "@missingdomain.com",
            "missing@.com",
            "spaces @example.com",
            "double@@example.com",
            "user@",
            "",
        ]

        for email in invalid_emails:
            with pytest.raises(ValueError):
                EmailTestRequest(to_address=email)

    def test_email_config_response_with_defaults(self):
        """Test EmailConfigResponse with default values."""
        response = EmailConfigResponse(
            enabled=False,
            smtp_host="",
            smtp_port=25,
            from_address="",
            from_name="",
            subject_prefix="",
            configured=False,
        )
        assert response.enabled is False
        assert response.smtp_host == ""
        assert response.smtp_port == 25
        assert response.from_address == ""
        assert response.from_name == ""
        assert response.subject_prefix == ""
        assert response.configured is False

    def test_email_config_response_with_ssl_port(self):
        """Test EmailConfigResponse with SSL port."""
        response = EmailConfigResponse(
            enabled=True,
            smtp_host="smtp.gmail.com",
            smtp_port=465,
            from_address="system@company.com",
            from_name="Company System",
            subject_prefix="[System]",
            configured=True,
        )
        assert response.enabled is True
        assert response.smtp_host == "smtp.gmail.com"
        assert response.smtp_port == 465
        assert response.from_address == "system@company.com"
        assert response.from_name == "Company System"
        assert response.subject_prefix == "[System]"
        assert response.configured is True
