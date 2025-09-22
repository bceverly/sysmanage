"""
Unit tests for password reset API endpoints and email service functionality.
Tests forgot password, reset password, token validation, and email sending.
"""

# pylint: disable=invalid-name,too-many-positional-arguments

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from argon2 import PasswordHasher

from backend.persistence import models

argon2_hasher = PasswordHasher()


class TestForgotPassword:
    """Test cases for POST /forgot-password endpoint."""

    @patch("backend.api.password_reset.send_password_reset_email")
    @patch("backend.api.password_reset.create_password_reset_token")
    def test_forgot_password_success_existing_user(
        self, mock_create_token, mock_send_email, client, session
    ):
        """Test forgot password for existing user."""
        # Create test user
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("password123"),
            active=True,
            first_name="Test",
            last_name="User",
        )
        session.add(user)
        session.commit()

        # Mock token creation and email sending
        mock_create_token.return_value = "test-token-123"
        mock_send_email.return_value = True

        response = client.post("/forgot-password", json={"email": "test@example.com"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "password reset link has been sent" in data["message"]

        # Verify token creation was called with user ID
        mock_create_token.assert_called_once()
        call_args = mock_create_token.call_args[0]
        assert call_args[0] == user.id  # First argument should be user.id
        # Verify email sending was called
        mock_send_email.assert_called_once()

    @patch("backend.api.password_reset.send_password_reset_email")
    @patch("backend.api.password_reset.create_password_reset_token")
    def test_forgot_password_nonexistent_user(
        self, mock_create_token, mock_send_email, client, session
    ):
        """Test forgot password for non-existent user - should still return success for security."""
        response = client.post(
            "/forgot-password", json={"email": "nonexistent@example.com"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "password reset link has been sent" in data["message"]

        # Verify no token was created or email sent
        mock_create_token.assert_not_called()
        mock_send_email.assert_not_called()

    @patch("backend.api.password_reset.send_password_reset_email")
    @patch("backend.api.password_reset.create_password_reset_token")
    def test_forgot_password_email_failure(
        self, mock_create_token, mock_send_email, client, session
    ):
        """Test forgot password when email sending fails."""
        # Create test user
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("password123"),
            active=True,
        )
        session.add(user)
        session.commit()

        # Mock email sending failure
        mock_create_token.return_value = "test-token-123"
        mock_send_email.return_value = False

        response = client.post("/forgot-password", json={"email": "test@example.com"})

        # Should still return success for security (don't reveal email delivery status)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_forgot_password_invalid_email(self, client):
        """Test forgot password with invalid email format."""
        response = client.post("/forgot-password", json={"email": "invalid-email"})

        assert response.status_code == 422  # Validation error


class TestResetPassword:
    """Test cases for POST /reset-password endpoint."""

    def test_reset_password_success(self, client, session):
        """Test successful password reset with valid token."""
        # Create test user
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("oldpassword"),
            active=True,
        )
        session.add(user)
        session.flush()  # To get the user ID

        # Create password reset token
        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token="valid-token-123",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            used_at=None,
        )
        session.add(reset_token)
        session.commit()

        response = client.post(
            "/reset-password",
            json={
                "token": "valid-token-123",
                "password": "newpassword123",
                "confirm_password": "newpassword123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "successfully reset" in data["message"]

        # Verify password was updated
        session.refresh(user)
        assert argon2_hasher.verify(user.hashed_password, "newpassword123")

        # Verify token was marked as used
        session.refresh(reset_token)
        assert reset_token.used_at is not None

    def test_reset_password_invalid_token(self, client):
        """Test password reset with invalid token."""
        response = client.post(
            "/reset-password",
            json={
                "token": "invalid-token",
                "password": "newpassword123",
                "confirm_password": "newpassword123",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid or expired" in data["detail"]

    def test_reset_password_expired_token(self, client, session):
        """Test password reset with expired token."""
        # Create test user
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("oldpassword"),
            active=True,
        )
        session.add(user)
        session.flush()

        # Create expired token
        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token="expired-token-123",
            created_at=datetime.now(timezone.utc) - timedelta(hours=25),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            used_at=None,
        )
        session.add(reset_token)
        session.commit()

        response = client.post(
            "/reset-password",
            json={
                "token": "expired-token-123",
                "password": "newpassword123",
                "confirm_password": "newpassword123",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid or expired" in data["detail"]

    def test_reset_password_used_token(self, client, session):
        """Test password reset with already used token."""
        # Create test user
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("oldpassword"),
            active=True,
        )
        session.add(user)
        session.flush()

        # Create used token
        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token="used-token-123",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            used_at=datetime.now(timezone.utc),
        )
        session.add(reset_token)
        session.commit()

        response = client.post(
            "/reset-password",
            json={
                "token": "used-token-123",
                "password": "newpassword123",
                "confirm_password": "newpassword123",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid or expired" in data["detail"]

    def test_reset_password_mismatch(self, client, session):
        """Test password reset with mismatched passwords."""
        # Create test user and valid token
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("oldpassword"),
            active=True,
        )
        session.add(user)
        session.flush()

        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token="valid-token-123",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            used_at=None,
        )
        session.add(reset_token)
        session.commit()

        response = client.post(
            "/reset-password",
            json={
                "token": "valid-token-123",
                "password": "newpassword123",
                "confirm_password": "differentpassword",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "Passwords do not match" in data["detail"]

    def test_reset_password_too_short(self, client, session):
        """Test password reset with password too short."""
        # Create test user and valid token
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("oldpassword"),
            active=True,
        )
        session.add(user)
        session.flush()

        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token="valid-token-123",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            used_at=None,
        )
        session.add(reset_token)
        session.commit()

        response = client.post(
            "/reset-password",
            json={
                "token": "valid-token-123",
                "password": "short",
                "confirm_password": "short",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "at least 8 characters" in data["detail"]

    def test_reset_password_orphaned_token(self, client, session):
        """Test password reset with token that has no associated user."""
        # Create a reset token without an associated user
        reset_token = models.PasswordResetToken(
            user_id="550e8400-e29b-41d4-a716-446655440999",  # User ID that doesn't exist
            token=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            used_at=None,
        )
        session.add(reset_token)
        session.commit()

        # Try to reset password using the orphaned token
        response = client.post(
            "/reset-password",
            json={
                "token": reset_token.token,
                "password": "newpassword123",
                "confirm_password": "newpassword123",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "User not found" in data["detail"]


class TestValidateResetToken:
    """Test cases for GET /validate-reset-token/{token} endpoint."""

    def test_validate_reset_token_valid(self, client, session):
        """Test validating a valid token."""
        # Create test user and valid token
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("password123"),
            active=True,
        )
        session.add(user)
        session.flush()

        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token="valid-token-123",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            used_at=None,
        )
        session.add(reset_token)
        session.commit()

        response = client.get("/validate-reset-token/valid-token-123")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Token is valid" in data["message"]

    def test_validate_reset_token_invalid(self, client):
        """Test validating an invalid token."""
        response = client.get("/validate-reset-token/invalid-token")

        assert response.status_code == 400
        data = response.json()
        assert "Invalid or expired" in data["detail"]

    def test_validate_reset_token_expired(self, client, session):
        """Test validating an expired token."""
        # Create test user and expired token
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("password123"),
            active=True,
        )
        session.add(user)
        session.flush()

        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token="expired-token-123",
            created_at=datetime.now(timezone.utc) - timedelta(hours=25),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            used_at=None,
        )
        session.add(reset_token)
        session.commit()

        response = client.get("/validate-reset-token/expired-token-123")

        assert response.status_code == 400
        data = response.json()
        assert "Invalid or expired" in data["detail"]


class TestAdminResetUserPassword:
    """Test cases for POST /admin/reset-user-password/{user_id} endpoint."""

    @patch("backend.api.password_reset.send_password_reset_email")
    @patch("backend.api.password_reset.create_password_reset_token")
    def test_admin_reset_user_password_success(
        self, mock_create_token, mock_send_email, client, session, auth_headers
    ):
        """Test admin triggering password reset for user."""
        # Create test user
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("password123"),
            active=True,
        )
        session.add(user)
        session.commit()

        # Mock token creation and email sending
        mock_create_token.return_value = "admin-token-123"
        mock_send_email.return_value = True

        response = client.post(
            f"/api/admin/reset-user-password/{user.id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Password reset email has been sent" in data["message"]
        assert user.userid in data["message"]

        # Verify token creation and email sending were called
        mock_create_token.assert_called_once()
        call_args = mock_create_token.call_args[0]
        assert call_args[0] == user.id  # First argument should be user.id
        mock_send_email.assert_called_once()

    def test_admin_reset_user_password_not_found(self, client, auth_headers):
        """Test admin reset for non-existent user."""
        response = client.post(
            "/api/admin/reset-user-password/999", headers=auth_headers
        )

        assert response.status_code == 404
        data = response.json()
        assert "User not found" in data["detail"]

    @patch("backend.api.password_reset.send_password_reset_email")
    @patch("backend.api.password_reset.create_password_reset_token")
    def test_admin_reset_user_password_email_failure(
        self, mock_create_token, mock_send_email, client, session, auth_headers
    ):
        """Test admin reset when email sending fails."""
        # Create test user
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("password123"),
            active=True,
        )
        session.add(user)
        session.commit()

        # Mock email sending failure
        mock_create_token.return_value = "admin-token-123"
        mock_send_email.return_value = False

        response = client.post(
            f"/api/admin/reset-user-password/{user.id}", headers=auth_headers
        )

        assert response.status_code == 500
        data = response.json()
        assert "Failed to send password reset email" in data["detail"]

    def test_admin_reset_user_password_unauthorized(self, client, session):
        """Test admin reset without authentication."""
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("password123"),
            active=True,
        )
        session.add(user)
        session.commit()

        response = client.post(f"/api/admin/reset-user-password/{user.id}")
        assert response.status_code == 403


class TestPasswordResetUtilityFunctions:
    """Test cases for password reset utility functions."""

    def test_generate_reset_token(self):
        """Test reset token generation."""
        from backend.api.password_reset import generate_reset_token

        token1 = generate_reset_token()
        token2 = generate_reset_token()

        # Should generate valid UUIDs
        assert len(token1) == 36  # UUID4 length
        assert len(token2) == 36
        assert token1 != token2  # Should be unique

        # Should be valid UUID format
        try:
            uuid.UUID(token1)
            uuid.UUID(token2)
        except ValueError:
            pytest.fail("Generated tokens are not valid UUIDs")

    def test_create_password_reset_token(self, session):
        """Test password reset token creation."""
        from backend.api.password_reset import create_password_reset_token

        # Create test user
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("password123"),
            active=True,
        )
        session.add(user)
        session.commit()

        token = create_password_reset_token(user.id, session)

        # Verify token was created
        assert token is not None
        assert len(token) == 36  # UUID4 length

        # Verify token record was created in database
        db_token = (
            session.query(models.PasswordResetToken)
            .filter(models.PasswordResetToken.token == token)
            .first()
        )
        assert db_token is not None
        assert db_token.user_id == user.id
        assert db_token.used_at is None
        # Compare without timezone for SQLite compatibility
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_naive = (
            db_token.expires_at.replace(tzinfo=None)
            if db_token.expires_at.tzinfo
            else db_token.expires_at
        )
        assert expires_naive > now_naive

    def test_get_valid_reset_token(self, session):
        """Test getting valid reset token."""
        from backend.api.password_reset import get_valid_reset_token

        # Create test user
        user = models.User(
            userid="test@example.com",
            hashed_password=argon2_hasher.hash("password123"),
            active=True,
        )
        session.add(user)
        session.flush()

        # Create valid token
        valid_token = models.PasswordResetToken(
            user_id=user.id,
            token="valid-token-123",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            used_at=None,
        )
        session.add(valid_token)
        session.commit()

        # Test getting valid token
        retrieved_token = get_valid_reset_token("valid-token-123", session)
        assert retrieved_token is not None
        assert retrieved_token.token == "valid-token-123"

        # Test getting non-existent token
        retrieved_token = get_valid_reset_token("nonexistent-token", session)
        assert retrieved_token is None

    def test_get_dynamic_hostname(self):
        """Test dynamic hostname detection."""
        from backend.api.password_reset import get_dynamic_hostname

        with patch("socket.getfqdn") as mock_fqdn, patch(
            "socket.gethostname"
        ) as mock_hostname:
            # Test successful FQDN
            mock_fqdn.return_value = "server.example.com"
            hostname = get_dynamic_hostname()
            assert hostname == "server.example.com"

            # Test FQDN failure, fallback to hostname
            mock_fqdn.side_effect = Exception("DNS failure")
            mock_hostname.return_value = "server"
            hostname = get_dynamic_hostname()
            assert hostname == "server"

            # Test both failure, fallback to localhost
            mock_hostname.side_effect = Exception("System failure")
            hostname = get_dynamic_hostname()
            assert hostname == "localhost"


class TestEmailService:
    """Test cases for email service functionality."""

    @patch("backend.config.config.get_email_config")
    @patch("backend.config.config.get_smtp_config")
    @patch("backend.config.config.is_email_enabled")
    def test_email_service_init(self, mock_enabled, mock_smtp, mock_email):
        """Test email service initialization."""
        from backend.services.email_service import EmailService

        mock_enabled.return_value = True
        mock_email.return_value = {"from_address": "test@example.com"}
        mock_smtp.return_value = {"host": "smtp.example.com"}

        service = EmailService()
        assert service.is_enabled() is True

    @patch("backend.config.config.is_email_enabled")
    def test_email_service_disabled(self, mock_enabled):
        """Test email service when disabled."""
        from backend.services.email_service import EmailService

        mock_enabled.return_value = False
        service = EmailService()

        result = service.send_email(
            to_addresses=["test@example.com"], subject="Test", body="Test message"
        )
        assert result is False

    @patch("smtplib.SMTP")
    @patch("backend.config.config.get_email_config")
    @patch("backend.config.config.get_smtp_config")
    @patch("backend.config.config.is_email_enabled")
    def test_send_email_success(
        self, mock_enabled, mock_smtp_config, mock_email_config, mock_smtp
    ):
        """Test successful email sending."""
        from backend.services.email_service import EmailService

        # Mock configuration
        mock_enabled.return_value = True
        mock_email_config.return_value = {
            "from_address": "sender@example.com",
            "from_name": "Test Sender",
            "templates": {"subject_prefix": "[TEST]"},
        }
        mock_smtp_config.return_value = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "smtp_user",
            "password": "smtp_pass",
            "use_tls": True,
            "use_ssl": False,
            "timeout": 30,
        }

        # Mock SMTP server
        mock_server = Mock()
        mock_smtp.return_value = mock_server

        service = EmailService()
        result = service.send_email(
            to_addresses=["recipient@example.com"],
            subject="Test Subject",
            body="Test message",
            html_body="<p>Test message</p>",
        )

        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("smtp_user", "smtp_pass")
        mock_server.send_message.assert_called_once()
        mock_server.quit.assert_called_once()

    @patch("smtplib.SMTP_SSL")
    @patch("backend.config.config.get_email_config")
    @patch("backend.config.config.get_smtp_config")
    @patch("backend.config.config.is_email_enabled")
    def test_send_email_ssl(
        self, mock_enabled, mock_smtp_config, mock_email_config, mock_smtp_ssl
    ):
        """Test email sending with SSL."""
        from backend.services.email_service import EmailService

        # Mock configuration for SSL
        mock_enabled.return_value = True
        mock_email_config.return_value = {
            "from_address": "sender@example.com",
            "from_name": "Test Sender",
            "templates": {},
        }
        mock_smtp_config.return_value = {
            "host": "smtp.example.com",
            "port": 465,
            "username": "smtp_user",
            "password": "smtp_pass",
            "use_tls": False,
            "use_ssl": True,
            "timeout": 30,
        }

        # Mock SMTP_SSL server
        mock_server = Mock()
        mock_smtp_ssl.return_value = mock_server

        service = EmailService()
        result = service.send_email(
            to_addresses=["recipient@example.com"],
            subject="Test Subject",
            body="Test message",
        )

        assert result is True
        mock_server.starttls.assert_not_called()  # No STARTTLS with SSL
        mock_server.login.assert_called_once_with("smtp_user", "smtp_pass")

    @patch("backend.config.config.get_email_config")
    @patch("backend.config.config.get_smtp_config")
    @patch("backend.config.config.is_email_enabled")
    def test_send_email_no_recipients(
        self, mock_enabled, mock_smtp_config, mock_email_config
    ):
        """Test email sending with no recipients."""
        from backend.services.email_service import EmailService

        mock_enabled.return_value = True
        mock_email_config.return_value = {"from_address": "sender@example.com"}
        mock_smtp_config.return_value = {"host": "smtp.example.com"}

        service = EmailService()
        result = service.send_email(
            to_addresses=[], subject="Test Subject", body="Test message"
        )

        assert result is False

    @patch("smtplib.SMTP")
    @patch("backend.config.config.get_email_config")
    @patch("backend.config.config.get_smtp_config")
    @patch("backend.config.config.is_email_enabled")
    def test_send_email_smtp_failure(
        self, mock_enabled, mock_smtp_config, mock_email_config, mock_smtp
    ):
        """Test email sending SMTP failure."""
        from backend.services.email_service import EmailService

        mock_enabled.return_value = True
        mock_email_config.return_value = {
            "from_address": "sender@example.com",
            "from_name": "Test Sender",
            "templates": {},
        }
        mock_smtp_config.return_value = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "smtp_user",
            "password": "smtp_pass",
            "use_tls": True,
            "use_ssl": False,
            "timeout": 30,
        }

        # Mock SMTP server failure
        mock_smtp.side_effect = Exception("SMTP connection failed")

        service = EmailService()
        result = service.send_email(
            to_addresses=["recipient@example.com"],
            subject="Test Subject",
            body="Test message",
        )

        assert result is False

    @patch("backend.services.email_service.email_service.send_email")
    def test_send_test_email(self, mock_send_email):
        """Test sending test email."""
        from backend.services.email_service import email_service

        mock_send_email.return_value = True

        result = email_service.send_test_email("test@example.com")

        assert result is True
        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args
        assert call_args[1]["to_addresses"] == ["test@example.com"]
        assert "Test Email" in call_args[1]["subject"]
        assert "test email from SysManage" in call_args[1]["body"]
        assert call_args[1]["html_body"] is not None


class TestEmailTemplateGeneration:
    """Test cases for email template generation in password reset."""

    @patch("backend.api.password_reset.get_dynamic_hostname")
    @patch("backend.api.password_reset.email_service.is_enabled")
    @patch("backend.api.password_reset.email_service.send_email")
    @patch("backend.config.config.get_config")
    def test_send_password_reset_email(
        self, mock_config, mock_send_email, mock_is_enabled, mock_hostname
    ):
        """Test password reset email generation."""
        from backend.api.password_reset import send_password_reset_email
        from fastapi import Request

        # Mock email service and hostname
        mock_is_enabled.return_value = True
        mock_hostname.return_value = "test.example.com"
        mock_send_email.return_value = True

        # Mock configuration
        mock_config.return_value = {
            "api": {"certFile": "/path/to/cert.pem"},
            "webui": {"port": 3000},
            "email": {
                "templates": {
                    "password_reset": {
                        "subject": "Custom Reset Subject",
                        "text_body": "Reset your password: {reset_url}",
                        "html_body": "<p>Reset: <a href='{reset_url}'>Click here</a></p>",
                    }
                }
            },
        }

        # Create mock request
        mock_request = Mock(spec=Request)

        result = send_password_reset_email("test@example.com", "token123", mock_request)

        assert result is True
        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[1]
        assert call_args["subject"] == "Custom Reset Subject"
        assert "token123" in call_args["body"]
        assert "token123" in call_args["html_body"]

    @patch("backend.api.password_reset.get_dynamic_hostname")
    @patch("backend.api.password_reset.email_service.is_enabled")
    @patch("backend.api.password_reset.email_service.send_email")
    @patch("backend.config.config.get_config")
    def test_send_initial_setup_email(
        self, mock_config, mock_send_email, mock_is_enabled, mock_hostname
    ):
        """Test initial setup email generation."""
        from backend.api.password_reset import send_initial_setup_email
        from fastapi import Request

        # Mock email service and hostname
        mock_is_enabled.return_value = True
        mock_hostname.return_value = "test.example.com"
        mock_send_email.return_value = True

        # Mock configuration
        mock_config.return_value = {
            "api": {"certFile": ""},  # No TLS
            "webui": {"port": 3000},
            "email": {
                "templates": {
                    "initial_setup": {
                        "subject": "Welcome to SysManage",
                        "text_body": "Setup your account: {setup_url}",
                        "html_body": "<p>Setup: <a href='{setup_url}'>Click here</a></p>",
                    }
                }
            },
        }

        # Create mock request
        mock_request = Mock(spec=Request)

        result = send_initial_setup_email(
            "newuser@example.com", "setup-token", mock_request
        )

        assert result is True
        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[1]
        assert call_args["subject"] == "Welcome to SysManage"
        assert "setup-token" in call_args["body"]
        assert "http://" in call_args["body"]  # Should use HTTP when no cert

    @patch("backend.api.password_reset.email_service.is_enabled")
    def test_email_disabled_fallback(self, mock_enabled):
        """Test email sending when service is disabled."""
        from backend.api.password_reset import (
            send_password_reset_email,
            send_initial_setup_email,
        )
        from fastapi import Request

        mock_enabled.return_value = False
        mock_request = Mock(spec=Request)

        result = send_password_reset_email("test@example.com", "token123", mock_request)
        assert result is False

        result = send_initial_setup_email("test@example.com", "token123", mock_request)
        assert result is False
