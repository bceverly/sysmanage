"""
Pytest configuration for service layer tests.

This conftest inherits fixtures from the parent tests/conftest.py.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Import fixtures from parent conftest - pytest will auto-discover them
# These fixtures are available: engine, db_session, session, client, mock_config


@pytest.fixture
def mock_smtp():
    """Mock SMTP connection for email service tests."""
    with patch("smtplib.SMTP") as mock:
        mock_instance = MagicMock()
        mock.return_value.__enter__ = MagicMock(return_value=mock_instance)
        mock.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_instance


@pytest.fixture
def mock_vault_client():
    """Mock HashiCorp Vault client for vault service tests."""
    with patch("hvac.Client") as mock:
        mock_instance = MagicMock()
        mock_instance.is_authenticated.return_value = True
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def email_config():
    """Email configuration for testing."""
    return {
        "email": {
            "smtp_host": "localhost",
            "smtp_port": 587,
            "smtp_user": "test@example.com",
            "smtp_password": "testpass",
            "from_address": "noreply@example.com",
            "use_tls": True,
        }
    }


@pytest.fixture
def vault_config():
    """Vault configuration for testing."""
    return {
        "vault": {
            "url": "http://localhost:8200",
            "token": "test-token",
            "mount_point": "secret",
        }
    }
