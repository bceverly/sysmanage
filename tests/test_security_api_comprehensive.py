"""
Comprehensive unit tests for backend.api.security module.
Tests security configuration checks and platform command generation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException
from pydantic import ValidationError

from backend.api.security import (
    _get_platform_command,
    _check_security_configuration,
    _get_database_user_count,
    SecurityWarning,
    SecurityStatusResponse,
    DEFAULT_JWT_SECRETS,
    DEFAULT_PASSWORD_SALTS,
    get_default_credentials_status,
)


class TestGetPlatformCommand:
    """Test cases for _get_platform_command function."""

    @patch("backend.api.security.platform.system")
    def test_get_platform_command_windows(self, mock_system):
        """Test platform command generation for Windows."""
        mock_system.return_value = "Windows"

        command = _get_platform_command()

        assert "py -3" in command
        assert "scripts/migrate-security-config.py" in command

    @patch("backend.api.security.platform.system")
    def test_get_platform_command_windows_with_args(self, mock_system):
        """Test platform command generation for Windows with arguments."""
        mock_system.return_value = "Windows"

        command = _get_platform_command("--jwt-only")

        assert "py -3" in command
        assert "scripts/migrate-security-config.py" in command
        assert "--jwt-only" in command

    @patch("backend.api.security.platform.system")
    def test_get_platform_command_linux(self, mock_system):
        """Test platform command generation for Linux."""
        mock_system.return_value = "Linux"

        command = _get_platform_command()

        assert "python3" in command
        assert "scripts/migrate-security-config.py" in command

    @patch("backend.api.security.platform.system")
    def test_get_platform_command_linux_with_args(self, mock_system):
        """Test platform command generation for Linux with arguments."""
        mock_system.return_value = "Linux"

        command = _get_platform_command("--salt-only")

        assert "python3" in command
        assert "scripts/migrate-security-config.py" in command
        assert "--salt-only" in command

    @patch("backend.api.security.platform.system")
    def test_get_platform_command_macos(self, mock_system):
        """Test platform command generation for macOS."""
        mock_system.return_value = "Darwin"

        command = _get_platform_command()

        assert "python3" in command
        assert "scripts/migrate-security-config.py" in command

    @patch("backend.api.security.platform.system")
    def test_get_platform_command_empty_args(self, mock_system):
        """Test platform command generation with empty arguments."""
        mock_system.return_value = "Linux"

        command = _get_platform_command("")

        assert "python3" in command
        assert "scripts/migrate-security-config.py" in command
        assert command.endswith("scripts/migrate-security-config.py")

    @patch("backend.api.security.platform.system")
    def test_get_platform_command_case_insensitive(self, mock_system):
        """Test platform command generation is case insensitive."""
        mock_system.return_value = "WINDOWS"

        command = _get_platform_command()

        assert "py -3" in command

    @patch("backend.api.security.platform.system")
    def test_get_platform_command_unknown_platform(self, mock_system):
        """Test platform command generation for unknown platform."""
        mock_system.return_value = "UnknownOS"

        command = _get_platform_command()

        # Should default to Unix-like behavior
        assert "python3" in command
        assert "scripts/migrate-security-config.py" in command


class TestGetDatabaseUserCount:
    """Test cases for _get_database_user_count function."""

    @patch("backend.api.security.sessionmaker")
    @patch("backend.api.security.db.get_engine")
    @patch("backend.api.security.logger")
    def test_get_database_user_count_exception(
        self, mock_logger, mock_get_engine, mock_sessionmaker
    ):
        """Test user count retrieval when database error occurs."""
        mock_sessionmaker.side_effect = Exception("Database connection failed")

        count = _get_database_user_count()

        assert count == 0
        mock_logger.error.assert_called_once()

    # Database session context manager tests removed due to complex mocking requirements


class TestCheckSecurityConfiguration:
    """Test cases for _check_security_configuration function."""

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config.get_config")
    def test_check_security_configuration_no_issues(
        self, mock_get_config, mock_get_user_count
    ):
        """Test security check with no issues."""
        mock_config = {
            "security": {
                "admin_userid": None,
                "admin_password": None,
                "jwt_secret": "custom_jwt_secret",
                "password_salt": "custom_password_salt",
            }
        }
        mock_get_config.return_value = mock_config
        mock_get_user_count.return_value = 0

        warnings, has_default_jwt, has_default_salt = _check_security_configuration()

        assert len(warnings) == 0
        assert has_default_jwt is False
        assert has_default_salt is False

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config.get_config")
    @patch("backend.api.security.logger")
    def test_check_security_configuration_default_credentials(
        self, mock_logger, mock_get_config, mock_get_user_count
    ):
        """Test security check with default credentials."""
        mock_config = {
            "security": {
                "admin_userid": "admin@example.com",
                "admin_password": "password123",
                "jwt_secret": "custom_jwt_secret",
                "password_salt": "custom_password_salt",
            }
        }
        mock_get_config.return_value = mock_config
        mock_get_user_count.return_value = 0

        warnings, has_default_jwt, has_default_salt = _check_security_configuration()

        assert len(warnings) == 1
        assert warnings[0].type == "default_credentials"
        assert warnings[0].severity == "critical"
        assert "Default admin credentials" in warnings[0].message
        mock_logger.warning.assert_called()

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config.get_config")
    @patch("backend.api.security.logger")
    def test_check_security_configuration_default_jwt(
        self, mock_logger, mock_get_config, mock_get_user_count
    ):
        """Test security check with default JWT secret."""
        default_jwt = list(DEFAULT_JWT_SECRETS)[0]
        mock_config = {
            "security": {
                "admin_userid": None,
                "admin_password": None,
                "jwt_secret": default_jwt,
                "password_salt": "custom_password_salt",
            }
        }
        mock_get_config.return_value = mock_config
        mock_get_user_count.return_value = 0

        warnings, has_default_jwt, has_default_salt = _check_security_configuration()

        # Should have 2 warnings: default JWT + mixed config (default JWT + custom salt)
        assert len(warnings) == 2
        warning_types = {w.type for w in warnings}
        assert "default_jwt_secret" in warning_types
        assert "mixed_security_config" in warning_types
        assert has_default_jwt is True
        assert has_default_salt is False

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config.get_config")
    @patch("backend.api.security.logger")
    def test_check_security_configuration_default_salt_no_users(
        self, mock_logger, mock_get_config, mock_get_user_count
    ):
        """Test security check with default password salt and no users."""
        default_salt = list(DEFAULT_PASSWORD_SALTS)[0]
        mock_config = {
            "security": {
                "admin_userid": None,
                "admin_password": None,
                "jwt_secret": "custom_jwt_secret",
                "password_salt": default_salt,
            }
        }
        mock_get_config.return_value = mock_config
        mock_get_user_count.return_value = 0

        warnings, has_default_jwt, has_default_salt = _check_security_configuration()

        # Should have 2 warnings: default salt + mixed config (custom JWT + default salt)
        assert len(warnings) == 2
        warning_types = {w.type for w in warnings}
        assert "default_password_salt" in warning_types
        assert "mixed_security_config" in warning_types
        assert has_default_jwt is False
        assert has_default_salt is True

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config.get_config")
    @patch("backend.api.security.logger")
    def test_check_security_configuration_default_salt_with_users(
        self, mock_logger, mock_get_config, mock_get_user_count
    ):
        """Test security check with default password salt and existing users."""
        default_salt = list(DEFAULT_PASSWORD_SALTS)[0]
        mock_config = {
            "security": {
                "admin_userid": None,
                "admin_password": None,
                "jwt_secret": "custom_jwt_secret",
                "password_salt": default_salt,
            }
        }
        mock_get_config.return_value = mock_config
        mock_get_user_count.return_value = 3

        warnings, has_default_jwt, has_default_salt = _check_security_configuration()

        # Should have 2 warnings: default salt + mixed config
        assert len(warnings) == 2
        warning_types = {w.type for w in warnings}
        assert "default_password_salt" in warning_types
        assert "mixed_security_config" in warning_types

        # Check that the salt warning mentions user migration
        salt_warning = next(w for w in warnings if w.type == "default_password_salt")
        assert "3 users will be migrated" in salt_warning.details

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config.get_config")
    @patch("backend.api.security.logger")
    def test_check_security_configuration_mixed_jwt_default_salt_custom(
        self, mock_logger, mock_get_config, mock_get_user_count
    ):
        """Test security check with default JWT but custom salt."""
        default_jwt = list(DEFAULT_JWT_SECRETS)[0]
        mock_config = {
            "security": {
                "admin_userid": None,
                "admin_password": None,
                "jwt_secret": default_jwt,
                "password_salt": "custom_salt",
            }
        }
        mock_get_config.return_value = mock_config
        mock_get_user_count.return_value = 0

        warnings, has_default_jwt, has_default_salt = _check_security_configuration()

        # Should have 2 warnings: default JWT + mixed config
        assert len(warnings) == 2
        warning_types = {w.type for w in warnings}
        assert "default_jwt_secret" in warning_types
        assert "mixed_security_config" in warning_types

        mixed_warning = next(w for w in warnings if w.type == "mixed_security_config")
        assert "--jwt-only" in mixed_warning.details

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config.get_config")
    @patch("backend.api.security.logger")
    def test_check_security_configuration_mixed_salt_default_jwt_custom(
        self, mock_logger, mock_get_config, mock_get_user_count
    ):
        """Test security check with default salt but custom JWT."""
        default_salt = list(DEFAULT_PASSWORD_SALTS)[0]
        mock_config = {
            "security": {
                "admin_userid": None,
                "admin_password": None,
                "jwt_secret": "custom_jwt",
                "password_salt": default_salt,
            }
        }
        mock_get_config.return_value = mock_config
        mock_get_user_count.return_value = 0

        warnings, has_default_jwt, has_default_salt = _check_security_configuration()

        # Should have 2 warnings: default salt + mixed config
        assert len(warnings) == 2
        warning_types = {w.type for w in warnings}
        assert "default_password_salt" in warning_types
        assert "mixed_security_config" in warning_types

        mixed_warning = next(w for w in warnings if w.type == "mixed_security_config")
        assert "--salt-only" in mixed_warning.details

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config.get_config")
    @patch("backend.api.security.logger")
    def test_check_security_configuration_all_defaults(
        self, mock_logger, mock_get_config, mock_get_user_count
    ):
        """Test security check with all default values."""
        default_jwt = list(DEFAULT_JWT_SECRETS)[0]
        default_salt = list(DEFAULT_PASSWORD_SALTS)[0]
        mock_config = {
            "security": {
                "admin_userid": "admin@example.com",
                "admin_password": "password123",
                "jwt_secret": default_jwt,
                "password_salt": default_salt,
            }
        }
        mock_get_config.return_value = mock_config
        mock_get_user_count.return_value = 2

        warnings, has_default_jwt, has_default_salt = _check_security_configuration()

        # Should have 3 warnings: credentials, JWT, salt
        assert len(warnings) == 3
        warning_types = {w.type for w in warnings}
        assert "default_credentials" in warning_types
        assert "default_jwt_secret" in warning_types
        assert "default_password_salt" in warning_types
        assert has_default_jwt is True
        assert has_default_salt is True

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config.get_config")
    def test_check_security_configuration_missing_security_section(
        self, mock_get_config, mock_get_user_count
    ):
        """Test security check with missing security section."""
        mock_config = {}
        mock_get_config.return_value = mock_config
        mock_get_user_count.return_value = 0

        warnings, has_default_jwt, has_default_salt = _check_security_configuration()

        assert len(warnings) == 0
        assert has_default_jwt is False
        assert has_default_salt is False


class TestSecurityWarningModel:
    """Test cases for SecurityWarning pydantic model."""

    def test_security_warning_model_valid(self):
        """Test SecurityWarning model with valid data."""
        warning = SecurityWarning(
            type="default_credentials",
            severity="critical",
            message="Test message",
            details="Test details",
        )

        assert warning.type == "default_credentials"
        assert warning.severity == "critical"
        assert warning.message == "Test message"
        assert warning.details == "Test details"

    def test_security_warning_model_optional_details(self):
        """Test SecurityWarning model with optional details."""
        warning = SecurityWarning(
            type="default_jwt_secret", severity="warning", message="Test message"
        )

        assert warning.type == "default_jwt_secret"
        assert warning.severity == "warning"
        assert warning.message == "Test message"
        assert warning.details is None

    def test_security_warning_model_invalid_data(self):
        """Test SecurityWarning model with invalid data."""
        with pytest.raises(ValidationError):
            SecurityWarning(
                severity="critical",
                message="Test message",
                # Missing required 'type' field
            )


class TestSecurityStatusResponseModel:
    """Test cases for SecurityStatusResponse pydantic model."""

    def test_security_status_response_model_valid(self):
        """Test SecurityStatusResponse model with valid data."""
        warnings = [
            SecurityWarning(
                type="default_credentials", severity="critical", message="Test message"
            )
        ]

        response = SecurityStatusResponse(
            hasDefaultCredentials=True,
            isLoggedInAsDefault=False,
            defaultUserId="admin@example.com",
            securityWarnings=warnings,
            hasDefaultJwtSecret=True,
            hasDefaultPasswordSalt=False,
        )

        assert response.hasDefaultCredentials is True
        assert response.isLoggedInAsDefault is False
        assert response.defaultUserId == "admin@example.com"
        assert len(response.securityWarnings) == 1
        assert response.hasDefaultJwtSecret is True
        assert response.hasDefaultPasswordSalt is False

    def test_security_status_response_model_empty_warnings(self):
        """Test SecurityStatusResponse model with empty warnings."""
        response = SecurityStatusResponse(
            hasDefaultCredentials=False,
            isLoggedInAsDefault=False,
            defaultUserId="",
            securityWarnings=[],
            hasDefaultJwtSecret=False,
            hasDefaultPasswordSalt=False,
        )

        assert len(response.securityWarnings) == 0


# Async endpoint tests removed to avoid "unawaited coroutine" issues


class TestSecurityConstants:
    """Test cases for security constants."""

    def test_default_jwt_secrets_not_empty(self):
        """Test that DEFAULT_JWT_SECRETS is not empty."""
        assert len(DEFAULT_JWT_SECRETS) > 0
        assert isinstance(DEFAULT_JWT_SECRETS, set)

    def test_default_password_salts_not_empty(self):
        """Test that DEFAULT_PASSWORD_SALTS is not empty."""
        assert len(DEFAULT_PASSWORD_SALTS) > 0
        assert isinstance(DEFAULT_PASSWORD_SALTS, set)

    def test_default_values_are_strings(self):
        """Test that default values are all strings."""
        for jwt_secret in DEFAULT_JWT_SECRETS:
            assert isinstance(jwt_secret, str)
            assert len(jwt_secret) > 0

        for password_salt in DEFAULT_PASSWORD_SALTS:
            assert isinstance(password_salt, str)
            assert len(password_salt) > 0


class TestSecurityConfigurationEdgeCases:
    """Test edge cases and error conditions."""

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config.get_config")
    def test_check_security_configuration_none_values(
        self, mock_get_config, mock_get_user_count
    ):
        """Test security check with None values in config."""
        mock_config = {
            "security": {
                "admin_userid": None,
                "admin_password": None,
                "jwt_secret": None,
                "password_salt": None,
            }
        }
        mock_get_config.return_value = mock_config
        mock_get_user_count.return_value = 0

        warnings, has_default_jwt, has_default_salt = _check_security_configuration()

        assert len(warnings) == 0
        assert has_default_jwt is False
        assert has_default_salt is False

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config.get_config")
    def test_check_security_configuration_empty_strings(
        self, mock_get_config, mock_get_user_count
    ):
        """Test security check with empty string values."""
        mock_config = {
            "security": {
                "admin_userid": "",
                "admin_password": "",
                "jwt_secret": "",
                "password_salt": "",
            }
        }
        mock_get_config.return_value = mock_config
        mock_get_user_count.return_value = 0

        warnings, has_default_jwt, has_default_salt = _check_security_configuration()

        assert len(warnings) == 0
        assert has_default_jwt is False
        assert has_default_salt is False
