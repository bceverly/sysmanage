"""
Tests for the email service module.

This module tests the EmailService class which provides functionality
for sending emails via SMTP.
"""

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from backend.services.email_service import EmailService, email_service


class TestEmailServiceInit:
    """Test cases for EmailService initialization."""

    def test_email_service_creates_instance(self):
        """Test that EmailService can be instantiated."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "test@example.com",
                "from_name": "Test",
            }
            mock_config.get_smtp_config.return_value = {
                "host": "localhost",
                "port": 25,
                "username": None,
                "password": None,
                "use_tls": False,
                "use_ssl": False,
                "timeout": 30,
            }
            service = EmailService()
            assert service.email_config is not None
            assert service.smtp_config is not None

    def test_global_email_service_instance_exists(self):
        """Test that a global email_service instance exists."""
        assert email_service is not None
        assert isinstance(email_service, EmailService)


class TestEmailServiceIsEnabled:
    """Test cases for EmailService.is_enabled method."""

    def test_is_enabled_returns_true_when_enabled(self):
        """Test is_enabled returns True when email is enabled."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "test@example.com",
                "from_name": "Test",
            }
            mock_config.get_smtp_config.return_value = {}
            mock_config.is_email_enabled.return_value = True
            service = EmailService()
            assert service.is_enabled() is True

    def test_is_enabled_returns_false_when_disabled(self):
        """Test is_enabled returns False when email is disabled."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "test@example.com",
                "from_name": "Test",
            }
            mock_config.get_smtp_config.return_value = {}
            mock_config.is_email_enabled.return_value = False
            service = EmailService()
            assert service.is_enabled() is False


class TestEmailServiceSendEmail:
    """Test cases for EmailService.send_email method."""

    def test_send_email_returns_false_when_disabled(self):
        """Test send_email returns False when email is disabled."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "test@example.com",
                "from_name": "Test",
            }
            mock_config.get_smtp_config.return_value = {}
            mock_config.is_email_enabled.return_value = False
            service = EmailService()
            result = service.send_email(
                to_addresses=["recipient@example.com"],
                subject="Test",
                body="Test body",
            )
            assert result is False

    def test_send_email_returns_false_when_no_recipients(self):
        """Test send_email returns False when no recipients provided."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "test@example.com",
                "from_name": "Test",
            }
            mock_config.get_smtp_config.return_value = {}
            mock_config.is_email_enabled.return_value = True
            service = EmailService()
            result = service.send_email(
                to_addresses=[],
                subject="Test",
                body="Test body",
            )
            assert result is False

    @patch("backend.services.email_service.smtplib.SMTP")
    def test_send_email_success_without_tls(self, mock_smtp_class):
        """Test send_email succeeds with basic SMTP connection."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "sender@example.com",
                "from_name": "Sender",
                "templates": {"subject_prefix": ""},
            }
            mock_config.get_smtp_config.return_value = {
                "host": "localhost",
                "port": 25,
                "username": None,
                "password": None,
                "use_tls": False,
                "use_ssl": False,
                "timeout": 30,
            }
            mock_config.is_email_enabled.return_value = True

            service = EmailService()
            result = service.send_email(
                to_addresses=["recipient@example.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result is True
            mock_smtp.send_message.assert_called_once()
            mock_smtp.quit.assert_called_once()

    @patch("backend.services.email_service.smtplib.SMTP")
    def test_send_email_with_tls(self, mock_smtp_class):
        """Test send_email succeeds with TLS connection."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "sender@example.com",
                "from_name": "Sender",
                "templates": {"subject_prefix": ""},
            }
            mock_config.get_smtp_config.return_value = {
                "host": "smtp.example.com",
                "port": 587,
                "username": "user",
                "password": "pass",
                "use_tls": True,
                "use_ssl": False,
                "timeout": 30,
            }
            mock_config.is_email_enabled.return_value = True

            service = EmailService()
            result = service.send_email(
                to_addresses=["recipient@example.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result is True
            mock_smtp.starttls.assert_called_once()
            mock_smtp.login.assert_called_once_with("user", "pass")

    @patch("backend.services.email_service.smtplib.SMTP_SSL")
    def test_send_email_with_ssl(self, mock_smtp_ssl_class):
        """Test send_email succeeds with SSL connection."""
        mock_smtp = MagicMock()
        mock_smtp_ssl_class.return_value = mock_smtp

        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "sender@example.com",
                "from_name": "Sender",
                "templates": {"subject_prefix": ""},
            }
            mock_config.get_smtp_config.return_value = {
                "host": "smtp.example.com",
                "port": 465,
                "username": "user",
                "password": "pass",
                "use_tls": False,
                "use_ssl": True,
                "timeout": 30,
            }
            mock_config.is_email_enabled.return_value = True

            service = EmailService()
            result = service.send_email(
                to_addresses=["recipient@example.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result is True
            mock_smtp_ssl_class.assert_called_once()

    @patch("backend.services.email_service.smtplib.SMTP")
    def test_send_email_with_html_body(self, mock_smtp_class):
        """Test send_email includes HTML body when provided."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "sender@example.com",
                "from_name": "Sender",
                "templates": {"subject_prefix": ""},
            }
            mock_config.get_smtp_config.return_value = {
                "host": "localhost",
                "port": 25,
                "username": None,
                "password": None,
                "use_tls": False,
                "use_ssl": False,
                "timeout": 30,
            }
            mock_config.is_email_enabled.return_value = True

            service = EmailService()
            result = service.send_email(
                to_addresses=["recipient@example.com"],
                subject="Test Subject",
                body="Plain text body",
                html_body="<html><body>HTML body</body></html>",
            )

            assert result is True

    @patch("backend.services.email_service.smtplib.SMTP")
    def test_send_email_adds_subject_prefix(self, mock_smtp_class):
        """Test send_email adds subject prefix when configured."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "sender@example.com",
                "from_name": "Sender",
                "templates": {"subject_prefix": "[SysManage]"},
            }
            mock_config.get_smtp_config.return_value = {
                "host": "localhost",
                "port": 25,
                "username": None,
                "password": None,
                "use_tls": False,
                "use_ssl": False,
                "timeout": 30,
            }
            mock_config.is_email_enabled.return_value = True

            service = EmailService()
            result = service.send_email(
                to_addresses=["recipient@example.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result is True

    @patch("backend.services.email_service.smtplib.SMTP")
    def test_send_email_returns_false_on_exception(self, mock_smtp_class):
        """Test send_email returns False when SMTP connection fails."""
        mock_smtp_class.side_effect = Exception("Connection refused")

        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "sender@example.com",
                "from_name": "Sender",
                "templates": {"subject_prefix": ""},
            }
            mock_config.get_smtp_config.return_value = {
                "host": "localhost",
                "port": 25,
                "username": None,
                "password": None,
                "use_tls": False,
                "use_ssl": False,
                "timeout": 30,
            }
            mock_config.is_email_enabled.return_value = True

            service = EmailService()
            result = service.send_email(
                to_addresses=["recipient@example.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result is False

    @patch("backend.services.email_service.smtplib.SMTP")
    def test_send_email_with_custom_from_address(self, mock_smtp_class):
        """Test send_email uses custom from address when provided."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "default@example.com",
                "from_name": "Default",
                "templates": {"subject_prefix": ""},
            }
            mock_config.get_smtp_config.return_value = {
                "host": "localhost",
                "port": 25,
                "username": None,
                "password": None,
                "use_tls": False,
                "use_ssl": False,
                "timeout": 30,
            }
            mock_config.is_email_enabled.return_value = True

            service = EmailService()
            result = service.send_email(
                to_addresses=["recipient@example.com"],
                subject="Test Subject",
                body="Test body",
                from_address="custom@example.com",
                from_name="Custom Sender",
            )

            assert result is True


class TestEmailServiceSendTestEmail:
    """Test cases for EmailService.send_test_email method."""

    def test_send_test_email_calls_send_email(self):
        """Test send_test_email calls send_email with correct parameters."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "sender@example.com",
                "from_name": "Sender",
                "templates": {},
            }
            mock_config.get_smtp_config.return_value = {}
            mock_config.is_email_enabled.return_value = False

            service = EmailService()
            with patch.object(service, "send_email", return_value=True) as mock_send:
                result = service.send_test_email("test@example.com")

                mock_send.assert_called_once()
                call_args = mock_send.call_args
                assert call_args[1]["to_addresses"] == ["test@example.com"]
                assert "Test Email" in call_args[1]["subject"]
                assert "test email" in call_args[1]["body"].lower()
                assert call_args[1]["html_body"] is not None
                assert result is True

    def test_send_test_email_returns_false_on_failure(self):
        """Test send_test_email returns False when send_email fails."""
        with patch("backend.services.email_service.config") as mock_config:
            mock_config.get_email_config.return_value = {
                "from_address": "sender@example.com",
                "from_name": "Sender",
                "templates": {},
            }
            mock_config.get_smtp_config.return_value = {}

            service = EmailService()
            with patch.object(service, "send_email", return_value=False):
                result = service.send_test_email("test@example.com")
                assert result is False
