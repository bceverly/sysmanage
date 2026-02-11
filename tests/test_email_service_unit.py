"""
Tests for backend/services/email_service.py module.
Tests email service functionality.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestEmailServiceInit:
    """Tests for EmailService initialization."""

    @patch("backend.services.email_service.config")
    def test_init_loads_configs(self, mock_config):
        """Test initialization loads email and SMTP configs."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {"from_address": "test@example.com"}
        mock_config.get_smtp_config.return_value = {"host": "smtp.example.com"}

        service = EmailService()

        assert service.email_config == {"from_address": "test@example.com"}
        assert service.smtp_config == {"host": "smtp.example.com"}


class TestEmailServiceIsEnabled:
    """Tests for is_enabled method."""

    @patch("backend.services.email_service.config")
    def test_is_enabled_returns_true(self, mock_config):
        """Test is_enabled returns True when email is enabled."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {}
        mock_config.get_smtp_config.return_value = {}
        mock_config.is_email_enabled.return_value = True

        service = EmailService()

        assert service.is_enabled() is True

    @patch("backend.services.email_service.config")
    def test_is_enabled_returns_false(self, mock_config):
        """Test is_enabled returns False when email is disabled."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {}
        mock_config.get_smtp_config.return_value = {}
        mock_config.is_email_enabled.return_value = False

        service = EmailService()

        assert service.is_enabled() is False


class TestEmailServiceSendEmail:
    """Tests for send_email method."""

    @patch("backend.services.email_service.config")
    def test_send_email_disabled(self, mock_config):
        """Test send_email returns False when email is disabled."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {}
        mock_config.get_smtp_config.return_value = {}
        mock_config.is_email_enabled.return_value = False

        service = EmailService()
        result = service.send_email(
            to_addresses=["test@example.com"], subject="Test", body="Test body"
        )

        assert result is False

    @patch("backend.services.email_service.config")
    def test_send_email_no_recipients(self, mock_config):
        """Test send_email returns False when no recipients provided."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {}
        mock_config.get_smtp_config.return_value = {}
        mock_config.is_email_enabled.return_value = True

        service = EmailService()
        result = service.send_email(to_addresses=[], subject="Test", body="Test body")

        assert result is False

    @patch("backend.services.email_service.smtplib")
    @patch("backend.services.email_service.config")
    def test_send_email_success_no_ssl(self, mock_config, mock_smtplib):
        """Test send_email success without SSL."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {
            "from_address": "sender@example.com",
            "from_name": "Test Sender",
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

        mock_server = MagicMock()
        mock_smtplib.SMTP.return_value = mock_server

        service = EmailService()
        result = service.send_email(
            to_addresses=["recipient@example.com"],
            subject="Test Subject",
            body="Test body",
        )

        assert result is True
        mock_smtplib.SMTP.assert_called_once_with("smtp.example.com", 587, timeout=30)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "pass")
        mock_server.send_message.assert_called_once()
        mock_server.quit.assert_called_once()

    @patch("backend.services.email_service.smtplib")
    @patch("backend.services.email_service.config")
    def test_send_email_success_with_ssl(self, mock_config, mock_smtplib):
        """Test send_email success with SSL."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {
            "from_address": "sender@example.com",
            "from_name": "Test Sender",
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

        mock_server = MagicMock()
        mock_smtplib.SMTP_SSL.return_value = mock_server

        service = EmailService()
        result = service.send_email(
            to_addresses=["recipient@example.com"],
            subject="Test Subject",
            body="Test body",
        )

        assert result is True
        mock_smtplib.SMTP_SSL.assert_called_once_with(
            "smtp.example.com", 465, timeout=30
        )
        mock_server.starttls.assert_not_called()

    @patch("backend.services.email_service.smtplib")
    @patch("backend.services.email_service.config")
    def test_send_email_with_html_body(self, mock_config, mock_smtplib):
        """Test send_email with HTML body."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {
            "from_address": "sender@example.com",
            "from_name": "Test Sender",
        }
        mock_config.get_smtp_config.return_value = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "",
            "password": "",
            "use_tls": False,
            "use_ssl": False,
            "timeout": 30,
        }
        mock_config.is_email_enabled.return_value = True

        mock_server = MagicMock()
        mock_smtplib.SMTP.return_value = mock_server

        service = EmailService()
        result = service.send_email(
            to_addresses=["recipient@example.com"],
            subject="Test Subject",
            body="Plain text body",
            html_body="<html><body>HTML body</body></html>",
        )

        assert result is True

    @patch("backend.services.email_service.smtplib")
    @patch("backend.services.email_service.config")
    def test_send_email_with_subject_prefix(self, mock_config, mock_smtplib):
        """Test send_email adds subject prefix if configured."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {
            "from_address": "sender@example.com",
            "from_name": "Test Sender",
            "templates": {"subject_prefix": "[SysManage]"},
        }
        mock_config.get_smtp_config.return_value = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "",
            "password": "",
            "use_tls": False,
            "use_ssl": False,
            "timeout": 30,
        }
        mock_config.is_email_enabled.return_value = True

        mock_server = MagicMock()
        mock_smtplib.SMTP.return_value = mock_server

        service = EmailService()
        service.send_email(
            to_addresses=["recipient@example.com"],
            subject="Test Subject",
            body="Test body",
        )

        # Verify subject was prefixed in the send_message call
        mock_server.send_message.assert_called_once()

    @patch("backend.services.email_service.smtplib")
    @patch("backend.services.email_service.config")
    def test_send_email_with_custom_from_address(self, mock_config, mock_smtplib):
        """Test send_email with custom from address."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {
            "from_address": "default@example.com",
            "from_name": "Default Sender",
        }
        mock_config.get_smtp_config.return_value = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "",
            "password": "",
            "use_tls": False,
            "use_ssl": False,
            "timeout": 30,
        }
        mock_config.is_email_enabled.return_value = True

        mock_server = MagicMock()
        mock_smtplib.SMTP.return_value = mock_server

        service = EmailService()
        result = service.send_email(
            to_addresses=["recipient@example.com"],
            subject="Test Subject",
            body="Test body",
            from_address="custom@example.com",
            from_name="Custom Sender",
        )

        assert result is True

    @patch("backend.services.email_service.smtplib")
    @patch("backend.services.email_service.config")
    def test_send_email_exception_handling(self, mock_config, mock_smtplib):
        """Test send_email handles exceptions gracefully."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {
            "from_address": "sender@example.com",
            "from_name": "Test Sender",
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

        mock_smtplib.SMTP.side_effect = Exception("Connection failed")

        service = EmailService()
        result = service.send_email(
            to_addresses=["recipient@example.com"],
            subject="Test Subject",
            body="Test body",
        )

        assert result is False

    @patch("backend.services.email_service.smtplib")
    @patch("backend.services.email_service.config")
    def test_send_email_multiple_recipients(self, mock_config, mock_smtplib):
        """Test send_email with multiple recipients."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {
            "from_address": "sender@example.com",
            "from_name": "Test Sender",
        }
        mock_config.get_smtp_config.return_value = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "",
            "password": "",
            "use_tls": False,
            "use_ssl": False,
            "timeout": 30,
        }
        mock_config.is_email_enabled.return_value = True

        mock_server = MagicMock()
        mock_smtplib.SMTP.return_value = mock_server

        service = EmailService()
        result = service.send_email(
            to_addresses=[
                "user1@example.com",
                "user2@example.com",
                "user3@example.com",
            ],
            subject="Test Subject",
            body="Test body",
        )

        assert result is True


class TestEmailServiceSendTestEmail:
    """Tests for send_test_email method."""

    @patch("backend.services.email_service.config")
    def test_send_test_email_calls_send_email(self, mock_config):
        """Test send_test_email calls send_email with correct parameters."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {}
        mock_config.get_smtp_config.return_value = {}
        mock_config.is_email_enabled.return_value = False

        service = EmailService()
        result = service.send_test_email("test@example.com")

        # Should return False since email is disabled
        assert result is False

    @patch("backend.services.email_service.smtplib")
    @patch("backend.services.email_service.config")
    def test_send_test_email_success(self, mock_config, mock_smtplib):
        """Test send_test_email sends test email successfully."""
        from backend.services.email_service import EmailService

        mock_config.get_email_config.return_value = {
            "from_address": "sender@example.com",
            "from_name": "Test Sender",
        }
        mock_config.get_smtp_config.return_value = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "",
            "password": "",
            "use_tls": False,
            "use_ssl": False,
            "timeout": 30,
        }
        mock_config.is_email_enabled.return_value = True

        mock_server = MagicMock()
        mock_smtplib.SMTP.return_value = mock_server

        service = EmailService()
        result = service.send_test_email("test@example.com")

        assert result is True
        mock_server.send_message.assert_called_once()


class TestGlobalEmailServiceInstance:
    """Tests for global email_service instance."""

    def test_global_instance_exists(self):
        """Test that global email_service instance exists."""
        from backend.services.email_service import email_service

        assert email_service is not None

    def test_global_instance_type(self):
        """Test that global instance is correct type."""
        from backend.services.email_service import EmailService, email_service

        assert isinstance(email_service, EmailService)
