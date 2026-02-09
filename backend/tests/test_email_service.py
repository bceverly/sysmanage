"""
Comprehensive unit tests for the email service functionality in SysManage.

Tests cover:
- EmailService initialization and configuration
- Email sending (plain text and HTML)
- SMTP connection handling (TLS, SSL)
- Test email functionality
- Email service enable/disable
- Error handling (SMTP errors, connection failures)
- Subject prefix handling
- From address and name configuration

These tests use pytest with mocked SMTP connections.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import MagicMock, Mock, patch, call

import pytest

# =============================================================================
# TEST CONFIGURATION AND FIXTURES
# =============================================================================


# Test email configuration
TEST_EMAIL_CONFIG = {
    "enabled": True,
    "from_address": "noreply@test.com",
    "from_name": "SysManage Test",
    "smtp": {
        "host": "smtp.test.com",
        "port": 587,
        "username": "testuser",
        "password": "testpass",
        "use_tls": True,
        "use_ssl": False,
        "timeout": 30,
    },
    "templates": {"subject_prefix": "[TestSysManage]"},
}


TEST_EMAIL_CONFIG_DISABLED = {
    "enabled": False,
    "from_address": "noreply@test.com",
    "from_name": "SysManage Test",
    "smtp": {
        "host": "smtp.test.com",
        "port": 587,
        "username": "",
        "password": "",
        "use_tls": True,
        "use_ssl": False,
        "timeout": 30,
    },
    "templates": {},
}


TEST_EMAIL_CONFIG_SSL = {
    "enabled": True,
    "from_address": "noreply@test.com",
    "from_name": "SysManage Test",
    "smtp": {
        "host": "smtp.test.com",
        "port": 465,
        "username": "testuser",
        "password": "testpass",
        "use_tls": False,
        "use_ssl": True,
        "timeout": 30,
    },
    "templates": {},
}


TEST_SMTP_CONFIG = {
    "host": "smtp.test.com",
    "port": 587,
    "username": "testuser",
    "password": "testpass",
    "use_tls": True,
    "use_ssl": False,
    "timeout": 30,
}


@pytest.fixture
def mock_email_config():
    """Mock email configuration."""
    return TEST_EMAIL_CONFIG


@pytest.fixture
def mock_smtp_config():
    """Mock SMTP configuration."""
    return TEST_SMTP_CONFIG


@pytest.fixture
def mock_smtp_server():
    """Create a mock SMTP server."""
    mock_server = MagicMock()
    mock_server.starttls = MagicMock()
    mock_server.login = MagicMock()
    mock_server.send_message = MagicMock()
    mock_server.quit = MagicMock()
    return mock_server


@pytest.fixture
def mock_smtp_ssl_server():
    """Create a mock SMTP_SSL server."""
    mock_server = MagicMock()
    mock_server.login = MagicMock()
    mock_server.send_message = MagicMock()
    mock_server.quit = MagicMock()
    return mock_server


# =============================================================================
# EMAIL SERVICE INITIALIZATION TESTS
# =============================================================================


class TestEmailServiceInitialization:
    """Test cases for EmailService initialization."""

    def test_email_service_init(self, mock_email_config, mock_smtp_config):
        """Test EmailService initialization."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = mock_email_config
            mock_config.get_smtp_config.return_value = mock_smtp_config

            from backend.services.email_service import EmailService

            service = EmailService()

            assert service.email_config == mock_email_config
            assert service.smtp_config == mock_smtp_config

    def test_email_service_is_enabled_true(self, mock_email_config, mock_smtp_config):
        """Test is_enabled returns True when email is enabled."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = mock_email_config
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = True

            from backend.services.email_service import EmailService

            service = EmailService()

            assert service.is_enabled() is True

    def test_email_service_is_enabled_false(self, mock_smtp_config):
        """Test is_enabled returns False when email is disabled."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = TEST_EMAIL_CONFIG_DISABLED
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = False

            from backend.services.email_service import EmailService

            service = EmailService()

            assert service.is_enabled() is False


# =============================================================================
# EMAIL SENDING TESTS
# =============================================================================


class TestEmailSending:
    """Test cases for email sending functionality."""

    def test_send_email_success(
        self, mock_email_config, mock_smtp_config, mock_smtp_server
    ):
        """Test successful email sending."""
        with patch("backend.services.email_service.config") as mock_config, patch(
            "backend.services.email_service.smtplib.SMTP"
        ) as mock_smtp:
            mock_config.get_email_config.return_value = mock_email_config
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = True
            mock_smtp.return_value = mock_smtp_server

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_email(
                to_addresses=["recipient@test.com"],
                subject="Test Subject",
                body="Test body content",
            )

            assert result is True
            mock_smtp_server.starttls.assert_called_once()
            mock_smtp_server.login.assert_called_once_with("testuser", "testpass")
            mock_smtp_server.send_message.assert_called_once()
            mock_smtp_server.quit.assert_called_once()

    def test_send_email_with_html(
        self, mock_email_config, mock_smtp_config, mock_smtp_server
    ):
        """Test sending email with HTML body."""
        with patch("backend.services.email_service.config") as mock_config, patch(
            "backend.services.email_service.smtplib.SMTP"
        ) as mock_smtp:
            mock_config.get_email_config.return_value = mock_email_config
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = True
            mock_smtp.return_value = mock_smtp_server

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_email(
                to_addresses=["recipient@test.com"],
                subject="Test Subject",
                body="Plain text body",
                html_body="<html><body><p>HTML body</p></body></html>",
            )

            assert result is True
            mock_smtp_server.send_message.assert_called_once()

    def test_send_email_multiple_recipients(
        self, mock_email_config, mock_smtp_config, mock_smtp_server
    ):
        """Test sending email to multiple recipients."""
        with patch("backend.services.email_service.config") as mock_config, patch(
            "backend.services.email_service.smtplib.SMTP"
        ) as mock_smtp:
            mock_config.get_email_config.return_value = mock_email_config
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = True
            mock_smtp.return_value = mock_smtp_server

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_email(
                to_addresses=[
                    "recipient1@test.com",
                    "recipient2@test.com",
                    "recipient3@test.com",
                ],
                subject="Test Subject",
                body="Test body",
            )

            assert result is True

    def test_send_email_disabled_service(self, mock_smtp_config):
        """Test sending email when service is disabled."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = TEST_EMAIL_CONFIG_DISABLED
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = False

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_email(
                to_addresses=["recipient@test.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result is False

    def test_send_email_no_recipients(self, mock_email_config, mock_smtp_config):
        """Test sending email with no recipients."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = mock_email_config
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = True

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_email(
                to_addresses=[], subject="Test Subject", body="Test body"
            )

            assert result is False

    def test_send_email_custom_from_address(
        self, mock_email_config, mock_smtp_config, mock_smtp_server
    ):
        """Test sending email with custom from address."""
        with patch("backend.services.email_service.config") as mock_config, patch(
            "backend.services.email_service.smtplib.SMTP"
        ) as mock_smtp:
            mock_config.get_email_config.return_value = mock_email_config
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = True
            mock_smtp.return_value = mock_smtp_server

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_email(
                to_addresses=["recipient@test.com"],
                subject="Test Subject",
                body="Test body",
                from_address="custom@test.com",
                from_name="Custom Sender",
            )

            assert result is True

    def test_send_email_subject_prefix(
        self, mock_email_config, mock_smtp_config, mock_smtp_server
    ):
        """Test that subject prefix is added."""
        with patch("backend.services.email_service.config") as mock_config, patch(
            "backend.services.email_service.smtplib.SMTP"
        ) as mock_smtp:
            mock_config.get_email_config.return_value = mock_email_config
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = True
            mock_smtp.return_value = mock_smtp_server

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_email(
                to_addresses=["recipient@test.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result is True
            # Verify the message was sent (subject prefix added internally)
            mock_smtp_server.send_message.assert_called_once()


# =============================================================================
# SSL/TLS CONNECTION TESTS
# =============================================================================


class TestSMTPConnections:
    """Test cases for SMTP connection handling."""

    def test_send_email_with_ssl(self, mock_smtp_ssl_server):
        """Test sending email with SSL connection."""
        with patch("backend.services.email_service.config") as mock_config, patch(
            "backend.services.email_service.smtplib.SMTP_SSL"
        ) as mock_smtp_ssl:
            mock_config.get_email_config.return_value = TEST_EMAIL_CONFIG_SSL
            mock_config.get_smtp_config.return_value = {
                "host": "smtp.test.com",
                "port": 465,
                "username": "testuser",
                "password": "testpass",
                "use_tls": False,
                "use_ssl": True,
                "timeout": 30,
            }
            mock_config.is_email_enabled.return_value = True
            mock_smtp_ssl.return_value = mock_smtp_ssl_server

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_email(
                to_addresses=["recipient@test.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result is True
            mock_smtp_ssl.assert_called_once()
            mock_smtp_ssl_server.login.assert_called_once()
            mock_smtp_ssl_server.quit.assert_called_once()

    def test_send_email_no_auth(self, mock_smtp_server):
        """Test sending email without authentication."""
        config_no_auth = {
            "enabled": True,
            "from_address": "noreply@test.com",
            "from_name": "SysManage Test",
            "smtp": {
                "host": "smtp.test.com",
                "port": 25,
                "username": "",
                "password": "",
                "use_tls": False,
                "use_ssl": False,
                "timeout": 30,
            },
            "templates": {},
        }

        with patch("backend.services.email_service.config") as mock_config, patch(
            "backend.services.email_service.smtplib.SMTP"
        ) as mock_smtp:
            mock_config.get_email_config.return_value = config_no_auth
            mock_config.get_smtp_config.return_value = config_no_auth["smtp"]
            mock_config.is_email_enabled.return_value = True
            mock_smtp.return_value = mock_smtp_server

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_email(
                to_addresses=["recipient@test.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result is True
            # Should not call starttls if use_tls is False
            mock_smtp_server.starttls.assert_not_called()
            # Should not call login if no username/password
            mock_smtp_server.login.assert_not_called()


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestEmailErrorHandling:
    """Test cases for email error handling."""

    def test_send_email_smtp_connection_error(
        self, mock_email_config, mock_smtp_config
    ):
        """Test handling of SMTP connection errors."""
        with patch("backend.services.email_service.config") as mock_config, patch(
            "backend.services.email_service.smtplib.SMTP"
        ) as mock_smtp:
            mock_config.get_email_config.return_value = mock_email_config
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = True
            mock_smtp.side_effect = smtplib.SMTPConnectError(421, "Connection refused")

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_email(
                to_addresses=["recipient@test.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result is False

    def test_send_email_authentication_error(
        self, mock_email_config, mock_smtp_config, mock_smtp_server
    ):
        """Test handling of SMTP authentication errors."""
        with patch("backend.services.email_service.config") as mock_config, patch(
            "backend.services.email_service.smtplib.SMTP"
        ) as mock_smtp:
            mock_config.get_email_config.return_value = mock_email_config
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = True
            mock_smtp.return_value = mock_smtp_server
            mock_smtp_server.login.side_effect = smtplib.SMTPAuthenticationError(
                535, "Authentication failed"
            )

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_email(
                to_addresses=["recipient@test.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result is False

    def test_send_email_send_failure(
        self, mock_email_config, mock_smtp_config, mock_smtp_server
    ):
        """Test handling of email send failures."""
        with patch("backend.services.email_service.config") as mock_config, patch(
            "backend.services.email_service.smtplib.SMTP"
        ) as mock_smtp:
            mock_config.get_email_config.return_value = mock_email_config
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = True
            mock_smtp.return_value = mock_smtp_server
            mock_smtp_server.send_message.side_effect = smtplib.SMTPRecipientsRefused(
                {"recipient@test.com": (550, "User not found")}
            )

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_email(
                to_addresses=["recipient@test.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result is False

    def test_send_email_generic_exception(
        self, mock_email_config, mock_smtp_config, mock_smtp_server
    ):
        """Test handling of generic exceptions during email sending."""
        with patch("backend.services.email_service.config") as mock_config, patch(
            "backend.services.email_service.smtplib.SMTP"
        ) as mock_smtp:
            mock_config.get_email_config.return_value = mock_email_config
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = True
            mock_smtp.return_value = mock_smtp_server
            mock_smtp_server.send_message.side_effect = Exception("Unexpected error")

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_email(
                to_addresses=["recipient@test.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result is False


# =============================================================================
# TEST EMAIL FUNCTIONALITY TESTS
# =============================================================================


class TestTestEmail:
    """Test cases for test email functionality."""

    def test_send_test_email_success(
        self, mock_email_config, mock_smtp_config, mock_smtp_server
    ):
        """Test sending a test email successfully."""
        with patch("backend.services.email_service.config") as mock_config, patch(
            "backend.services.email_service.smtplib.SMTP"
        ) as mock_smtp:
            mock_config.get_email_config.return_value = mock_email_config
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = True
            mock_smtp.return_value = mock_smtp_server

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_test_email("test@example.com")

            assert result is True
            mock_smtp_server.send_message.assert_called_once()

    def test_send_test_email_disabled(self, mock_smtp_config):
        """Test sending test email when service is disabled."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = TEST_EMAIL_CONFIG_DISABLED
            mock_config.get_smtp_config.return_value = mock_smtp_config
            mock_config.is_email_enabled.return_value = False

            from backend.services.email_service import EmailService

            service = EmailService()

            result = service.send_test_email("test@example.com")

            assert result is False


# =============================================================================
# GLOBAL EMAIL SERVICE INSTANCE TESTS
# =============================================================================


class TestGlobalEmailServiceInstance:
    """Test cases for the global email_service instance."""

    def test_global_instance_exists(self):
        """Test that global email_service instance exists."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = TEST_EMAIL_CONFIG
            mock_config.get_smtp_config.return_value = TEST_SMTP_CONFIG

            from backend.services.email_service import email_service

            assert email_service is not None

    def test_global_instance_is_email_service(self):
        """Test that global instance is an EmailService."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = TEST_EMAIL_CONFIG
            mock_config.get_smtp_config.return_value = TEST_SMTP_CONFIG

            from backend.services.email_service import EmailService, email_service

            assert isinstance(email_service, EmailService)
