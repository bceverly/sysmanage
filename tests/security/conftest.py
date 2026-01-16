"""
Pytest configuration for security tests.

This conftest inherits fixtures from the parent tests/conftest.py.
"""

import pytest
from unittest.mock import MagicMock, patch

# Import fixtures from parent conftest - pytest will auto-discover them
# These fixtures are available: engine, db_session, session, client, mock_config


@pytest.fixture
def sample_security_roles():
    """Sample security roles for testing."""
    from backend.security.roles import SecurityRoles

    return [
        SecurityRoles.APPROVE_HOST_REGISTRATION,
        SecurityRoles.DELETE_HOST,
        SecurityRoles.VIEW_HOST_DETAILS,
        SecurityRoles.REBOOT_HOST,
        SecurityRoles.ADD_PACKAGE,
    ]


@pytest.fixture
def mock_certificate_manager():
    """Mock certificate manager for testing."""
    with patch("backend.security.certificate_manager.certificate_manager") as mock:
        mock.generate_client_certificate.return_value = (
            b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
            b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
        )
        mock.verify_client_certificate.return_value = True
        yield mock
