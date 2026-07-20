# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Unit tests for the user management API: JWT token handling, login,
logout, and token refresh.

Split from test_user_management_api.py.
"""

import time
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import HTTPException

from backend.api.auth import login, logout, refresh
from backend.auth.auth_handler import decode_jwt, sign_jwt, sign_refresh_token

argon2_hasher = PasswordHasher()


# =============================================================================
# TEST CONFIGURATION AND FIXTURES
# =============================================================================


# Test configuration
TEST_CONFIG = {
    "api": {
        "host": "localhost",
        "port": 9443,
        "certFile": None,
    },
    "webui": {"host": "localhost", "port": 9080},
    "monitoring": {"heartbeat_timeout": 5},
    "security": {
        "password_salt": "test_salt",
        "admin_userid": "admin@test.com",
        "admin_password": "testadminpass",
        "jwt_secret": "test_secret_key_for_testing_only",
        "jwt_algorithm": "HS256",
        "jwt_auth_timeout": 3600,
        "jwt_refresh_timeout": 86400,
        "max_failed_logins": 5,
        "account_lockout_duration": 15,
    },
}


def _stub_auth_config_getters(mock_config_module):
    """Stub the config getters auth.py reads (Phase 13.1.H).

    The login path no longer reads ``the_config["security"][...]`` directly for
    the recovery password / JWT refresh timeout / cookie domain — it goes through
    ``config.get_admin_password`` / ``get_jwt_refresh_timeout`` / ``get_cookie_domain``
    (DB/OpenBAO-first, YAML fallback).  Under a wholesale ``backend.api.auth.config``
    mock these would return MagicMocks, so resolve them to the TEST_CONFIG values.
    """
    sec = TEST_CONFIG["security"]
    mock_config_module.get_config.return_value = TEST_CONFIG
    mock_config_module.get_admin_password.return_value = sec["admin_password"]
    mock_config_module.get_jwt_refresh_timeout.return_value = sec["jwt_refresh_timeout"]
    mock_config_module.get_cookie_domain.return_value = None


@pytest.fixture
def mock_config():
    """Mock the configuration system to use test config."""
    with patch("backend.config.config.get_config", return_value=TEST_CONFIG):
        with patch("backend.auth.auth_handler.the_config", TEST_CONFIG):
            with patch(
                "backend.auth.auth_handler.JWT_SECRET",
                TEST_CONFIG["security"]["jwt_secret"],
            ):
                with patch(
                    "backend.auth.auth_handler.JWT_ALGORITHM",
                    TEST_CONFIG["security"]["jwt_algorithm"],
                ):
                    yield TEST_CONFIG


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    mock_session = MagicMock()
    mock_session.query.return_value = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()
    mock_session.rollback = MagicMock()
    mock_session.close = MagicMock()
    return mock_session


@pytest.fixture
def mock_user():
    """Create a mock user object."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.userid = "test@example.com"
    user.active = True
    user.first_name = "Test"
    user.last_name = "User"
    user.hashed_password = argon2_hasher.hash("TestPassword123!")
    user.is_locked = False
    user.failed_login_attempts = 0
    user.locked_at = None
    user.is_admin = False
    user.last_access = datetime.now(timezone.utc)
    user._role_cache = None
    user.load_role_cache = MagicMock()
    user.has_role = MagicMock(return_value=True)
    return user


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user object."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.userid = "admin@example.com"
    user.active = True
    user.first_name = "Admin"
    user.last_name = "User"
    user.hashed_password = argon2_hasher.hash("AdminPassword123!")
    user.is_locked = False
    user.failed_login_attempts = 0
    user.locked_at = None
    user.is_admin = True
    user.last_access = datetime.now(timezone.utc)
    user._role_cache = MagicMock()
    user.load_role_cache = MagicMock()
    user.has_role = MagicMock(return_value=True)
    return user


@pytest.fixture
def mock_request():
    """Create a mock FastAPI Request object."""
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {"user-agent": "TestClient/1.0", "Authorization": ""}
    request.cookies = {}
    return request


@pytest.fixture
def mock_response():
    """Create a mock FastAPI Response object."""
    response = MagicMock()
    response.set_cookie = MagicMock()
    return response


# =============================================================================
# JWT TOKEN TESTS
# =============================================================================


class TestJWTTokenHandling:
    """Test cases for JWT token creation and validation."""

    def test_sign_jwt_creates_valid_token(self, mock_config):
        """Test that sign_jwt creates a valid JWT token."""
        user_id = "test@example.com"
        token = sign_jwt(user_id)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_sign_jwt_contains_user_id(self, mock_config):
        """Test that signed JWT contains the user ID."""
        user_id = "test@example.com"
        token = sign_jwt(user_id)

        decoded = jwt.decode(
            token,
            TEST_CONFIG["security"]["jwt_secret"],
            algorithms=[TEST_CONFIG["security"]["jwt_algorithm"]],
        )

        assert decoded["user_id"] == user_id

    def test_sign_jwt_contains_expiration(self, mock_config):
        """Test that signed JWT contains an expiration time."""
        user_id = "test@example.com"
        token = sign_jwt(user_id)

        decoded = jwt.decode(
            token,
            TEST_CONFIG["security"]["jwt_secret"],
            algorithms=[TEST_CONFIG["security"]["jwt_algorithm"]],
        )

        assert "expires" in decoded
        assert decoded["expires"] > time.time()

    def test_sign_refresh_token_creates_valid_token(self, mock_config):
        """Test that sign_refresh_token creates a valid JWT token."""
        user_id = "test@example.com"
        token = sign_refresh_token(user_id)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_jwt_returns_payload_for_valid_token(self, mock_config):
        """Test that decode_jwt returns the payload for a valid token."""
        user_id = "test@example.com"
        token = sign_jwt(user_id)

        result = decode_jwt(token)

        assert result is not None
        assert result["user_id"] == user_id

    def test_decode_jwt_returns_none_for_expired_token(self, mock_config):
        """Test that decode_jwt returns None for an expired token."""
        # Create an expired token manually
        payload = {
            "user_id": "test@example.com",
            "expires": time.time() - 3600,  # Expired 1 hour ago
        }
        token = jwt.encode(
            payload,
            TEST_CONFIG["security"]["jwt_secret"],
            algorithm=TEST_CONFIG["security"]["jwt_algorithm"],
        )

        result = decode_jwt(token)

        assert result is None

    def test_decode_jwt_returns_empty_dict_for_invalid_token(self, mock_config):
        """Test that decode_jwt returns empty dict for an invalid token."""
        result = decode_jwt("invalid.token.here")

        assert result == {}


# =============================================================================
# USER LOGIN TESTS
# =============================================================================


class TestUserLogin:
    """Test cases for user login functionality."""

    @pytest.mark.asyncio
    async def test_login_with_valid_credentials(
        self, mock_config, mock_user, mock_request, mock_response
    ):
        """Test successful login with valid credentials."""
        from backend.api.auth import UserLogin

        login_data = UserLogin(userid="test@example.com", password="TestPassword123!")

        with patch("backend.api.auth.login_security") as mock_login_security, patch(
            "backend.api.auth.db"
        ) as mock_db, patch("backend.api.auth.config") as mock_config_module, patch(
            "backend.api.auth.mfa_service"
        ) as mock_mfa_service:
            mock_login_security.validate_login_attempt.return_value = (True, "Allowed")
            mock_login_security.is_user_account_locked.return_value = False

            _stub_auth_config_getters(mock_config_module)

            # Phase 10.3 MFA flow: ``login`` returns ``{mfa_required,
            # pending_token}`` instead of a real session token when the
            # user has an MFA enrollment.  This test exercises the
            # legacy no-MFA path, so make ``get_enrollment`` return None
            # and ``get_settings().admin_required`` return False so the
            # function falls through to issuing a regular Authorization.
            mock_mfa_service.get_enrollment.return_value = None
            mock_mfa_service.get_settings.return_value = MagicMock(admin_required=False)

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            mock_db.get_db.return_value = None
            mock_db.get_engine.return_value = MagicMock()

            # Create a properly configured sessionmaker mock
            with patch("backend.api.auth.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                result = await login(login_data, mock_request, mock_response)

                assert "Authorization" in result
                mock_login_security.record_successful_login.assert_called()

    @pytest.mark.asyncio
    async def test_login_with_admin_credentials(
        self, mock_config, mock_request, mock_response
    ):
        """Test successful login with admin credentials from config."""
        from backend.api.auth import UserLogin

        login_data = UserLogin(
            userid=TEST_CONFIG["security"]["admin_userid"],
            password=TEST_CONFIG["security"]["admin_password"],
        )

        with patch("backend.api.auth.login_security") as mock_login_security, patch(
            "backend.api.auth.db"
        ) as mock_db, patch("backend.api.auth.config") as mock_config_module:
            mock_login_security.validate_login_attempt.return_value = (True, "Allowed")

            _stub_auth_config_getters(mock_config_module)
            mock_db.get_db.return_value = None
            mock_db.get_engine.return_value = MagicMock()

            with patch("backend.api.auth.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=MagicMock()
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                result = await login(login_data, mock_request, mock_response)

                assert "Authorization" in result

    @pytest.mark.asyncio
    async def test_login_with_invalid_password(
        self, mock_config, mock_user, mock_request, mock_response
    ):
        """Test login failure with invalid password."""
        from backend.api.auth import UserLogin

        login_data = UserLogin(userid="test@example.com", password="WrongPassword!")

        with patch("backend.api.auth.login_security") as mock_login_security, patch(
            "backend.api.auth.db"
        ) as mock_db, patch("backend.api.auth.config") as mock_config_module:
            mock_login_security.validate_login_attempt.return_value = (True, "Allowed")
            mock_login_security.is_user_account_locked.return_value = False
            mock_login_security.record_failed_login_for_user.return_value = False

            _stub_auth_config_getters(mock_config_module)
            mock_db.get_db.return_value = None
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.auth.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await login(login_data, mock_request, mock_response)

                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_with_nonexistent_user(
        self, mock_config, mock_request, mock_response
    ):
        """Test login failure with nonexistent user."""
        from backend.api.auth import UserLogin

        login_data = UserLogin(
            userid="nonexistent@example.com", password="SomePassword!"
        )

        with patch("backend.api.auth.login_security") as mock_login_security, patch(
            "backend.api.auth.db"
        ) as mock_db, patch("backend.api.auth.config") as mock_config_module:
            mock_login_security.validate_login_attempt.return_value = (True, "Allowed")

            _stub_auth_config_getters(mock_config_module)
            mock_db.get_db.return_value = None
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch("backend.api.auth.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await login(login_data, mock_request, mock_response)

                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_with_locked_account(
        self, mock_config, mock_user, mock_request, mock_response
    ):
        """Test login failure with locked account."""
        from backend.api.auth import UserLogin

        mock_user.is_locked = True
        mock_user.locked_at = datetime.now(timezone.utc)

        login_data = UserLogin(userid="test@example.com", password="TestPassword123!")

        with patch("backend.api.auth.login_security") as mock_login_security, patch(
            "backend.api.auth.db"
        ) as mock_db, patch("backend.api.auth.config") as mock_config_module:
            mock_login_security.validate_login_attempt.return_value = (True, "Allowed")
            mock_login_security.is_user_account_locked.return_value = True

            _stub_auth_config_getters(mock_config_module)
            mock_db.get_db.return_value = None
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.auth.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await login(login_data, mock_request, mock_response)

                assert exc_info.value.status_code == 423  # Account locked

    @pytest.mark.asyncio
    async def test_login_rate_limited(self, mock_config, mock_request, mock_response):
        """Test login failure when rate limited."""
        from backend.api.auth import UserLogin

        login_data = UserLogin(userid="test@example.com", password="TestPassword123!")

        with patch("backend.api.auth.login_security") as mock_login_security, patch(
            "backend.api.auth.config"
        ) as mock_config_module:
            mock_login_security.validate_login_attempt.return_value = (
                False,
                "Too many login attempts",
            )

            _stub_auth_config_getters(mock_config_module)

            with pytest.raises(HTTPException) as exc_info:
                await login(login_data, mock_request, mock_response)

            assert exc_info.value.status_code == 429


# =============================================================================
# USER LOGOUT TESTS
# =============================================================================


class TestUserLogout:
    """Test cases for user logout functionality."""

    @pytest.mark.asyncio
    async def test_logout_logs_audit_event(self, mock_config, mock_user, mock_request):
        """Test that logout logs an audit event."""
        with patch("backend.api.auth.db") as mock_db, patch(
            "backend.api.auth.AuditService"
        ) as mock_audit:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.auth.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                result = await logout(mock_request, "test@example.com")

                assert "message" in result
                mock_audit.log.assert_called_once()


# =============================================================================
# TOKEN REFRESH TESTS
# =============================================================================


class TestTokenRefresh:
    """Test cases for token refresh functionality."""

    @pytest.mark.asyncio
    async def test_refresh_with_valid_token(self, mock_config, mock_request):
        """Test token refresh with valid refresh token."""
        # Create a valid refresh token
        refresh_token = sign_refresh_token("test@example.com")
        mock_request.cookies = {"refresh_token": refresh_token}

        result = await refresh(mock_request)

        assert "Authorization" in result

    @pytest.mark.asyncio
    async def test_refresh_with_missing_token(self, mock_config, mock_request):
        """Test token refresh failure with missing refresh token."""
        mock_request.cookies = {}

        with pytest.raises(HTTPException) as exc_info:
            await refresh(mock_request)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_refresh_with_invalid_token(self, mock_config, mock_request):
        """Test token refresh failure with invalid refresh token."""
        mock_request.cookies = {"refresh_token": "invalid.token.here"}

        with pytest.raises(HTTPException) as exc_info:
            await refresh(mock_request)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_refresh_with_expired_token(self, mock_config, mock_request):
        """Test token refresh failure with expired refresh token."""
        # Create an expired token
        payload = {
            "user_id": "test@example.com",
            "expires": time.time() - 3600,
        }
        expired_token = jwt.encode(
            payload,
            TEST_CONFIG["security"]["jwt_secret"],
            algorithm=TEST_CONFIG["security"]["jwt_algorithm"],
        )
        mock_request.cookies = {"refresh_token": expired_token}

        with pytest.raises(HTTPException) as exc_info:
            await refresh(mock_request)

        assert exc_info.value.status_code == 403
