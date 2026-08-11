# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for backend/api/v1/security.py module.
Tests security status API endpoints.
"""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestSecurityWarning:
    """Tests for SecurityWarning model."""

    def test_warning_structure(self):
        """Test SecurityWarning model structure."""
        from backend.api.security import SecurityWarning

        warning = SecurityWarning(
            type="default_credentials",
            severity="critical",
            message="Default credentials detected",
            details="Change your credentials",
        )

        assert warning.type == "default_credentials"
        assert warning.severity == "critical"
        assert warning.message == "Default credentials detected"
        assert warning.details == "Change your credentials"

    def test_warning_without_details(self):
        """Test SecurityWarning without details."""
        from backend.api.security import SecurityWarning

        warning = SecurityWarning(
            type="email_integration_required",
            severity="warning",
            message="Email not configured",
        )

        assert warning.details is None


class TestSecurityStatusResponse:
    """Tests for SecurityStatusResponse model."""

    def test_response_structure(self):
        """Test SecurityStatusResponse model structure."""
        from backend.api.security import SecurityStatusResponse, SecurityWarning

        warning = SecurityWarning(
            type="test",
            severity="warning",
            message="Test warning",
        )

        response = SecurityStatusResponse(
            hasDefaultCredentials=True,
            isLoggedInAsDefault=True,
            defaultUserId="admin",
            securityWarnings=[warning],
            hasDefaultJwtSecret=True,
            hasDefaultPasswordSalt=False,
        )

        assert response.hasDefaultCredentials is True
        assert response.isLoggedInAsDefault is True
        assert response.defaultUserId == "admin"
        assert len(response.securityWarnings) == 1
        assert response.hasDefaultJwtSecret is True
        assert response.hasDefaultPasswordSalt is False


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


class TestGetDatabaseUserCount:
    """Tests for _get_database_user_count function."""

    @patch("backend.api.security.db")
    @patch("backend.api.security.sessionmaker")
    def test_get_user_count_success(self, mock_sessionmaker, mock_db):
        """Test successful user count retrieval."""
        from backend.api.security import _get_database_user_count

        mock_session = MagicMock()
        mock_session.query.return_value.count.return_value = 5
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        result = _get_database_user_count()
        assert result == 5

    @patch("backend.api.security.db")
    @patch("backend.api.security.sessionmaker")
    def test_get_user_count_exception(self, mock_sessionmaker, mock_db):
        """Test user count retrieval with exception."""
        from backend.api.security import _get_database_user_count

        mock_db.get_engine.side_effect = Exception("Database error")

        result = _get_database_user_count()
        assert result == 0


class TestCheckSecurityConfiguration:
    """Tests for _check_security_configuration function."""

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config")
    def test_check_no_issues(self, mock_config, mock_user_count):
        """Test check with no security issues."""
        from backend.api.security import _check_security_configuration

        mock_config.get_config.return_value = {
            "email": {"enabled": True},
            "security": {
                "jwt_secret": "custom-secret-key-that-is-not-default",
                "password_salt": "custom-salt-that-is-not-default",
            },
        }
        mock_user_count.return_value = 0

        warnings, has_jwt, has_salt = _check_security_configuration()

        assert has_jwt is False
        assert has_salt is False

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config")
    def test_check_email_not_enabled(self, mock_config, mock_user_count):
        """Test check when email is not enabled."""
        from backend.api.security import _check_security_configuration

        mock_config.get_config.return_value = {
            "email": {"enabled": False},
            "security": {
                "jwt_secret": "custom-secret-key-for-testing-purposes-32bytes",
                "password_salt": "custom-salt",
            },
        }
        mock_user_count.return_value = 0

        warnings, _, _ = _check_security_configuration()

        email_warning = next(
            (w for w in warnings if w.type == "email_integration_required"), None
        )
        assert email_warning is not None
        assert email_warning.severity == "warning"

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config")
    def test_check_default_credentials(self, mock_config, mock_user_count):
        """Test check with default credentials configured."""
        from backend.api.security import _check_security_configuration

        mock_config.get_config.return_value = {
            "email": {"enabled": True},
            "security": {
                "admin_userid": "admin",
                "admin_password": "password123",
                "jwt_secret": "custom-secret-key-for-testing-purposes-32bytes",
                "password_salt": "custom-salt",
            },
        }
        mock_user_count.return_value = 0

        warnings, _, _ = _check_security_configuration()

        cred_warning = next(
            (w for w in warnings if w.type == "default_credentials"), None
        )
        assert cred_warning is not None
        assert cred_warning.severity == "critical"

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config")
    def test_check_default_jwt_secret(self, mock_config, mock_user_count):
        """Test check with default JWT secret."""
        from backend.api.security import _check_security_configuration

        mock_config.get_config.return_value = {
            "email": {"enabled": True},
            "security": {
                "jwt_secret": "I+Z74n/CFHser01E47pyrL91OuonEX9hNSvVFr/KLi4=",
                "password_salt": "custom-salt",
            },
        }
        mock_user_count.return_value = 0

        warnings, has_jwt, _ = _check_security_configuration()

        assert has_jwt is True
        jwt_warning = next(
            (w for w in warnings if w.type == "default_jwt_secret"), None
        )
        assert jwt_warning is not None

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config")
    def test_check_default_password_salt(self, mock_config, mock_user_count):
        """Test check with default password salt."""
        from backend.api.security import _check_security_configuration

        mock_config.get_config.return_value = {
            "email": {"enabled": True},
            "security": {
                "jwt_secret": "custom-secret-key-for-testing-purposes-32bytes",
                "password_salt": "6/InQvDb8f3cM6sao8kWzIiYVHKGH9sqkEJ3uZhIo9Q=",
            },
        }
        mock_user_count.return_value = 5

        warnings, _, has_salt = _check_security_configuration()

        assert has_salt is True
        salt_warning = next(
            (w for w in warnings if w.type == "default_password_salt"), None
        )
        assert salt_warning is not None
        assert "5 users will be migrated" in salt_warning.details

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config")
    def test_check_mixed_security_jwt_default(self, mock_config, mock_user_count):
        """Test check with mixed security - JWT default, salt custom."""
        from backend.api.security import _check_security_configuration

        mock_config.get_config.return_value = {
            "email": {"enabled": True},
            "security": {
                "jwt_secret": "I+Z74n/CFHser01E47pyrL91OuonEX9hNSvVFr/KLi4=",
                "password_salt": "custom-salt",
            },
        }
        mock_user_count.return_value = 0

        warnings, _, _ = _check_security_configuration()

        mixed_warning = next(
            (w for w in warnings if w.type == "mixed_security_config"), None
        )
        assert mixed_warning is not None
        assert "--jwt-only" in mixed_warning.details

    @patch("backend.api.security._get_database_user_count")
    @patch("backend.api.security.config")
    def test_check_mixed_security_salt_default(self, mock_config, mock_user_count):
        """Test check with mixed security - salt default, JWT custom."""
        from backend.api.security import _check_security_configuration

        mock_config.get_config.return_value = {
            "email": {"enabled": True},
            "security": {
                "jwt_secret": "custom-secret-key-for-testing-purposes-32bytes",
                "password_salt": "6/InQvDb8f3cM6sao8kWzIiYVHKGH9sqkEJ3uZhIo9Q=",
            },
        }
        mock_user_count.return_value = 0

        warnings, _, _ = _check_security_configuration()

        mixed_warning = next(
            (w for w in warnings if w.type == "mixed_security_config"), None
        )
        assert mixed_warning is not None
        assert "--salt-only" in mixed_warning.details


class TestGetDefaultCredentialsStatus:
    """Tests for get_default_credentials_status endpoint."""

    @patch("backend.api.security._check_security_configuration")
    @patch("backend.api.security.config")
    def test_get_status_no_default_credentials(self, mock_config, mock_check_security):
        """Test status when no default credentials configured."""
        from backend.api.security import router
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        mock_config.get_config.return_value = {
            "security": {},
        }
        mock_check_security.return_value = ([], False, False)

        app.dependency_overrides[get_current_user] = lambda: "user@example.com"

        client = TestClient(app)
        response = client.get("/api/v1/security/default-credentials-status")

        assert response.status_code == 200
        data = response.json()
        assert data["hasDefaultCredentials"] is False
        assert data["isLoggedInAsDefault"] is False

    @patch("backend.api.security._check_security_configuration")
    @patch("backend.api.security.config")
    def test_get_status_with_default_credentials(
        self, mock_config, mock_check_security
    ):
        """Test status with default credentials configured."""
        from backend.api.security import router
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        mock_config.get_config.return_value = {
            "security": {
                "admin_userid": "admin",
                "admin_password": "password123",
            },
        }
        mock_check_security.return_value = ([], False, False)

        app.dependency_overrides[get_current_user] = lambda: "admin"

        client = TestClient(app)
        response = client.get("/api/v1/security/default-credentials-status")

        assert response.status_code == 200
        data = response.json()
        assert data["hasDefaultCredentials"] is True
        assert data["isLoggedInAsDefault"] is True
        assert data["defaultUserId"] == "admin"

    @patch("backend.api.security._check_security_configuration")
    @patch("backend.api.security.config")
    def test_get_status_with_warnings(self, mock_config, mock_check_security):
        """Test status with security warnings."""
        from backend.api.security import SecurityWarning, router
        from backend.auth.auth_bearer import get_current_user

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        mock_config.get_config.return_value = {
            "security": {},
        }

        warnings = [
            SecurityWarning(
                type="default_jwt_secret",
                severity="warning",
                message="Default JWT secret",
            )
        ]
        mock_check_security.return_value = (warnings, True, False)

        app.dependency_overrides[get_current_user] = lambda: "user@example.com"

        client = TestClient(app)
        response = client.get("/api/v1/security/default-credentials-status")

        assert response.status_code == 200
        data = response.json()
        assert data["hasDefaultJwtSecret"] is True
        assert data["hasDefaultPasswordSalt"] is False
        assert len(data["securityWarnings"]) == 1


class TestRouterConfiguration:
    """Tests for router configuration."""

    def test_router_prefix(self):
        """Test router has correct prefix."""
        from backend.api.security import router

        assert router.prefix == "/security"

    def test_router_tags(self):
        """Test router has correct tags."""
        from backend.api.security import router

        assert "security" in router.tags


class TestDefaultSecretConstants:
    """Tests for default secret constants."""

    def test_default_jwt_secrets_set(self):
        """Test DEFAULT_JWT_SECRETS is a set."""
        from backend.api.security import DEFAULT_JWT_SECRETS

        assert isinstance(DEFAULT_JWT_SECRETS, set)
        assert len(DEFAULT_JWT_SECRETS) == 1

    def test_default_password_salts_set(self):
        """Test DEFAULT_PASSWORD_SALTS is a set."""
        from backend.api.security import DEFAULT_PASSWORD_SALTS

        assert isinstance(DEFAULT_PASSWORD_SALTS, set)
        assert len(DEFAULT_PASSWORD_SALTS) == 1
