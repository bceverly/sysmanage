# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for backend/api/v1/security.py module.
Tests security configuration checks and platform command generation.
"""

from unittest.mock import MagicMock, patch


class TestGetPlatformCommand:
    """Tests for _get_platform_command.

    The contract changed on 2026-08-11.  It used to emit a bare
    ``python3 scripts/migrate-security-config.py`` -- correct only for a reader
    sitting in a source checkout with the right interpreter first on PATH.  A
    packaged install has neither, and the web UI prints this command verbatim
    for the administrator to run, so on the BSD ports / Homebrew / Windows it
    was instructing people to run something that could not work.

    It now derives an absolute, runnable command from ``sys.executable`` (by
    definition the interpreter running this server) and the install root.  What
    ``platform.system()`` still decides is the sudo prefix: editing the config
    needs root everywhere except Windows, which has no sudo.
    """

    def test_windows_has_no_sudo_prefix(self):
        """Windows elevates differently; prefixing sudo would be nonsense."""
        from backend.api.security import _get_platform_command

        with patch("backend.api.security.platform.system", return_value="Windows"):
            result = _get_platform_command()

        assert not result.startswith("sudo")
        assert "migrate-security-config.py" in result

    def test_posix_platforms_prefix_sudo(self):
        """Linux, macOS and the BSDs all need root to rewrite the config."""
        from backend.api.security import _get_platform_command

        for system in ("Linux", "Darwin", "FreeBSD", "NetBSD", "OpenBSD"):
            with patch("backend.api.security.platform.system", return_value=system):
                result = _get_platform_command()
            assert result.startswith("sudo "), system

    def test_command_is_absolute_and_runnable(self):
        """Both the interpreter and the script must be absolute paths.

        This is the whole point of the change: a relative path is only valid
        from one working directory, and "python3" is only valid if the right
        interpreter happens to be first on PATH.
        """
        import os
        import sys

        from backend.api.security import _get_platform_command

        with patch("backend.api.security.platform.system", return_value="Linux"):
            result = _get_platform_command()

        parts = result.split()
        assert parts[0] == "sudo"
        assert parts[1] == sys.executable
        assert os.path.isabs(parts[2])
        # Compare path COMPONENTS, not a substring with a hardcoded separator:
        # on Windows this is D:\\a\\...\\scripts\\migrate-security-config.py
        # and an endswith("scripts/...") check fails there.
        assert os.path.basename(parts[2]) == "migrate-security-config.py"
        assert os.path.basename(os.path.dirname(parts[2])) == "scripts"

    def test_script_args_are_appended(self):
        """--jwt-only / --salt-only reach the command line."""
        from backend.api.security import _get_platform_command

        with patch("backend.api.security.platform.system", return_value="Linux"):
            assert _get_platform_command("--jwt-only").endswith("--jwt-only")
            assert _get_platform_command("--salt-only").endswith("--salt-only")

    def test_empty_script_args_leave_no_trailing_space(self):
        """No args must not produce a dangling separator."""
        from backend.api.security import _get_platform_command

        with patch("backend.api.security.platform.system", return_value="Linux"):
            result = _get_platform_command("")

        assert result.endswith(".py")
        assert "  " not in result

    def test_config_path_is_pinned_when_known(self):
        """SYSMANAGE_CONFIG_PATH must be passed through as --config.

        The script's own autodetection prefers /etc/sysmanage.yaml, so on a
        host that also has a development config there it would rewrite the
        wrong file and report success.
        """
        import os

        from backend.api.security import _get_platform_command

        with patch("backend.api.security.platform.system", return_value="Linux"):
            with patch.dict(
                os.environ, {"SYSMANAGE_CONFIG_PATH": "/usr/local/etc/sysmanage.yaml"}
            ):
                result = _get_platform_command("--jwt-only")

        assert "--config /usr/local/etc/sysmanage.yaml" in result
        assert result.endswith("--jwt-only")


class TestGetRestartCommand:
    """The UI used to tell every platform to run ``./run.sh``."""

    def test_each_platform_gets_its_own_service_manager(self):
        from backend.api.security import _get_restart_command

        expected = {
            "FreeBSD": "service sysmanage restart",
            "NetBSD": "service sysmanage restart",
            "OpenBSD": "service sysmanage restart",
            "Linux": "systemctl restart sysmanage",
            "Darwin": "brew services restart sysmanage",
            "Windows": "Restart-Service sysmanage",
        }
        for system, fragment in expected.items():
            with patch("backend.api.security.platform.system", return_value=system):
                assert fragment in _get_restart_command(), system

    def test_no_platform_is_told_to_run_run_sh(self):
        """``./run.sh`` is a developer command that exists in no package."""
        from backend.api.security import _get_restart_command

        for system in ("Linux", "Darwin", "FreeBSD", "NetBSD", "OpenBSD", "Windows"):
            with patch("backend.api.security.platform.system", return_value=system):
                assert "run.sh" not in _get_restart_command(), system


class TestSecurityWarning:
    """Tests for SecurityWarning model."""

    def test_security_warning_creation(self):
        """Test creating a SecurityWarning instance."""
        from backend.api.security import SecurityWarning

        warning = SecurityWarning(
            type="default_credentials",
            severity="critical",
            message="Default admin credentials configured",
            details="Remove from config file",
        )

        assert warning.type == "default_credentials"
        assert warning.severity == "critical"
        assert warning.message == "Default admin credentials configured"
        assert warning.details == "Remove from config file"

    def test_security_warning_without_details(self):
        """Test creating a SecurityWarning without details."""
        from backend.api.security import SecurityWarning

        warning = SecurityWarning(
            type="test_warning", severity="warning", message="Test message"
        )

        assert warning.type == "test_warning"
        assert warning.severity == "warning"
        assert warning.details is None


class TestSecurityStatusResponse:
    """Tests for SecurityStatusResponse model."""

    def test_security_status_response_creation(self):
        """Test creating a SecurityStatusResponse instance."""
        from backend.api.security import SecurityStatusResponse, SecurityWarning

        warnings = [
            SecurityWarning(type="test", severity="warning", message="Test warning")
        ]

        response = SecurityStatusResponse(
            hasDefaultCredentials=True,
            isLoggedInAsDefault=True,
            defaultUserId="admin",
            securityWarnings=warnings,
            hasDefaultJwtSecret=True,
            hasDefaultPasswordSalt=False,
        )

        assert response.hasDefaultCredentials is True
        assert response.isLoggedInAsDefault is True
        assert response.defaultUserId == "admin"
        assert len(response.securityWarnings) == 1
        assert response.hasDefaultJwtSecret is True
        assert response.hasDefaultPasswordSalt is False

    def test_security_status_response_empty_warnings(self):
        """Test SecurityStatusResponse with empty warnings list."""
        from backend.api.security import SecurityStatusResponse

        response = SecurityStatusResponse(
            hasDefaultCredentials=False,
            isLoggedInAsDefault=False,
            defaultUserId="",
            securityWarnings=[],
            hasDefaultJwtSecret=False,
            hasDefaultPasswordSalt=False,
        )

        assert len(response.securityWarnings) == 0


class TestDefaultSecrets:
    """Tests for default secrets constants."""

    def test_default_jwt_secrets_set(self):
        """Test DEFAULT_JWT_SECRETS is a set."""
        from backend.api.security import DEFAULT_JWT_SECRETS

        assert isinstance(DEFAULT_JWT_SECRETS, set)
        assert len(DEFAULT_JWT_SECRETS) > 0

    def test_default_password_salts_set(self):
        """Test DEFAULT_PASSWORD_SALTS is a set."""
        from backend.api.security import DEFAULT_PASSWORD_SALTS

        assert isinstance(DEFAULT_PASSWORD_SALTS, set)
        assert len(DEFAULT_PASSWORD_SALTS) > 0

    def test_known_default_jwt_secret(self):
        """Test known default JWT secret is in the set."""
        from backend.api.security import DEFAULT_JWT_SECRETS

        known_default = "I+Z74n/CFHser01E47pyrL91OuonEX9hNSvVFr/KLi4="
        assert known_default in DEFAULT_JWT_SECRETS

    def test_known_default_password_salt(self):
        """Test known default password salt is in the set."""
        from backend.api.security import DEFAULT_PASSWORD_SALTS

        known_default = "6/InQvDb8f3cM6sao8kWzIiYVHKGH9sqkEJ3uZhIo9Q="
        assert known_default in DEFAULT_PASSWORD_SALTS


class TestGetDatabaseUserCount:
    """Tests for _get_database_user_count function."""

    def test_returns_count(self):
        """Test _get_database_user_count returns a count."""
        from backend.api.security import _get_database_user_count

        # Mock the database session
        mock_session = MagicMock()
        mock_session.query.return_value.count.return_value = 5

        with patch("backend.api.security.sessionmaker") as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )

            result = _get_database_user_count()

        # The function should handle database connections
        assert isinstance(result, int)

    def test_handles_exception(self):
        """Test _get_database_user_count handles exceptions."""
        from backend.api.security import _get_database_user_count

        with patch("backend.api.security.sessionmaker") as mock_sessionmaker:
            mock_sessionmaker.side_effect = Exception("Database error")

            result = _get_database_user_count()

        # Should return 0 on error
        assert result == 0


class TestCheckSecurityConfiguration:
    """Tests for _check_security_configuration function."""

    def test_no_warnings_with_secure_config(self):
        """Test no warnings with secure configuration."""
        from backend.api.security import _check_security_configuration

        secure_config = {
            "email": {"enabled": True},
            "security": {
                "jwt_secret": "unique-secure-jwt-secret-key-for-testing-32bytes",
                "password_salt": "unique-secure-password-salt",
            },
        }

        with patch(
            "backend.api.security.config.get_config", return_value=secure_config
        ):
            with patch("backend.api.security._get_database_user_count", return_value=0):
                warnings, has_default_jwt, has_default_salt = (
                    _check_security_configuration()
                )

        # No default credentials warnings
        assert has_default_jwt is False
        assert has_default_salt is False

    def test_default_jwt_secret_warning(self):
        """Test warning for default JWT secret."""
        from backend.api.security import _check_security_configuration

        insecure_config = {
            "email": {"enabled": True},
            "security": {
                "jwt_secret": "I+Z74n/CFHser01E47pyrL91OuonEX9hNSvVFr/KLi4=",
                "password_salt": "unique-secure-password-salt",
            },
        }

        with patch(
            "backend.api.security.config.get_config", return_value=insecure_config
        ):
            with patch("backend.api.security._get_database_user_count", return_value=0):
                warnings, has_default_jwt, has_default_salt = (
                    _check_security_configuration()
                )

        assert has_default_jwt is True
        assert has_default_salt is False
        assert any(w.type == "default_jwt_secret" for w in warnings)

    def test_default_password_salt_warning(self):
        """Test warning for default password salt."""
        from backend.api.security import _check_security_configuration

        insecure_config = {
            "email": {"enabled": True},
            "security": {
                "jwt_secret": "unique-secure-jwt-secret-key-for-testing-32bytes",
                "password_salt": "6/InQvDb8f3cM6sao8kWzIiYVHKGH9sqkEJ3uZhIo9Q=",
            },
        }

        with patch(
            "backend.api.security.config.get_config", return_value=insecure_config
        ):
            with patch("backend.api.security._get_database_user_count", return_value=0):
                warnings, has_default_jwt, has_default_salt = (
                    _check_security_configuration()
                )

        assert has_default_jwt is False
        assert has_default_salt is True
        assert any(w.type == "default_password_salt" for w in warnings)

    def test_default_credentials_warning(self):
        """Test warning for default admin credentials."""
        from backend.api.security import _check_security_configuration

        insecure_config = {
            "email": {"enabled": True},
            "security": {
                "admin_userid": "admin",
                "admin_password": "password123",
                "jwt_secret": "unique-jwt-secret-key-for-testing-32bytes",
                "password_salt": "unique-salt",
            },
        }

        with patch(
            "backend.api.security.config.get_config", return_value=insecure_config
        ):
            with patch("backend.api.security._get_database_user_count", return_value=0):
                warnings, has_default_jwt, has_default_salt = (
                    _check_security_configuration()
                )

        assert any(w.type == "default_credentials" for w in warnings)
        assert any(w.severity == "critical" for w in warnings)

    def test_email_not_enabled_warning(self):
        """Test warning when email is not enabled."""
        from backend.api.security import _check_security_configuration

        config_no_email = {
            "email": {"enabled": False},
            "security": {
                "jwt_secret": "unique-jwt-secret-key-for-testing-32bytes",
                "password_salt": "unique-salt",
            },
        }

        with patch(
            "backend.api.security.config.get_config", return_value=config_no_email
        ):
            with patch("backend.api.security._get_database_user_count", return_value=0):
                warnings, _, _ = _check_security_configuration()

        assert any(w.type == "email_integration_required" for w in warnings)

    def test_mixed_security_config_jwt_default(self):
        """Test warning for mixed security config (JWT default, salt custom)."""
        from backend.api.security import _check_security_configuration

        mixed_config = {
            "email": {"enabled": True},
            "security": {
                "jwt_secret": "I+Z74n/CFHser01E47pyrL91OuonEX9hNSvVFr/KLi4=",
                "password_salt": "unique-custom-salt",
            },
        }

        with patch("backend.api.security.config.get_config", return_value=mixed_config):
            with patch("backend.api.security._get_database_user_count", return_value=0):
                warnings, _, _ = _check_security_configuration()

        assert any(w.type == "mixed_security_config" for w in warnings)

    def test_mixed_security_config_salt_default(self):
        """Test warning for mixed security config (salt default, JWT custom)."""
        from backend.api.security import _check_security_configuration

        mixed_config = {
            "email": {"enabled": True},
            "security": {
                "jwt_secret": "unique-custom-jwt-secret-key-for-testing-32bytes",
                "password_salt": "6/InQvDb8f3cM6sao8kWzIiYVHKGH9sqkEJ3uZhIo9Q=",
            },
        }

        with patch("backend.api.security.config.get_config", return_value=mixed_config):
            with patch("backend.api.security._get_database_user_count", return_value=0):
                warnings, _, _ = _check_security_configuration()

        assert any(w.type == "mixed_security_config" for w in warnings)

    def test_user_count_in_salt_warning_details(self):
        """Test user count appears in password salt warning details."""
        from backend.api.security import _check_security_configuration

        insecure_config = {
            "email": {"enabled": True},
            "security": {
                "jwt_secret": "unique-jwt-secret-key-for-testing-32bytes",
                "password_salt": "6/InQvDb8f3cM6sao8kWzIiYVHKGH9sqkEJ3uZhIo9Q=",
            },
        }

        with patch(
            "backend.api.security.config.get_config", return_value=insecure_config
        ):
            with patch(
                "backend.api.security._get_database_user_count", return_value=10
            ):
                warnings, _, _ = _check_security_configuration()

        salt_warning = next(
            (w for w in warnings if w.type == "default_password_salt"), None
        )
        assert salt_warning is not None
        assert "10 users" in salt_warning.details


class TestRouter:
    """Tests for security router."""

    def test_router_exists(self):
        """Test that security router is created."""
        from backend.api.security import router

        assert router is not None
        assert router.prefix == "/security"
        assert "security" in router.tags
