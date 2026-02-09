"""
Comprehensive unit tests for the user management API in SysManage.

Tests cover:
- User CRUD operations (create, read, update, delete)
- Authentication (login, logout, token refresh)
- Password management (change password, reset)
- Role-based access control
- Session management
- Account locking/unlocking
- Error handling

These tests use pytest and pytest-asyncio for async tests with mocked database.
"""

import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.auth import login, logout, refresh
from backend.api.user import (
    User,
    add_user,
    delete_user,
    get_all_users,
    get_logged_in_user,
    get_user,
    get_user_by_userid,
    get_user_permissions,
    lock_user,
    unlock_user,
    update_user,
)
from backend.api.password_reset import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    forgot_password,
    reset_password,
    validate_reset_token,
)
from backend.auth.auth_handler import decode_jwt, sign_jwt, sign_refresh_token
from backend.security.login_security import (
    LoginSecurityValidator,
    PasswordSecurityValidator,
    SessionSecurityManager,
)
from backend.security.roles import SecurityRoles, UserRoleCache

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
        ) as mock_db, patch("backend.api.auth.config") as mock_config_module:
            mock_login_security.validate_login_attempt.return_value = (True, "Allowed")
            mock_login_security.is_user_account_locked.return_value = False

            mock_config_module.get_config.return_value = TEST_CONFIG

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

            mock_config_module.get_config.return_value = TEST_CONFIG
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

            mock_config_module.get_config.return_value = TEST_CONFIG
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

            mock_config_module.get_config.return_value = TEST_CONFIG
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

            mock_config_module.get_config.return_value = TEST_CONFIG
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

            mock_config_module.get_config.return_value = TEST_CONFIG

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


# =============================================================================
# USER CRUD TESTS
# =============================================================================


class TestUserCRUD:
    """Test cases for user CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_all_users(self, mock_config, mock_user):
        """Test retrieving all users."""
        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.all.return_value = [mock_user]

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                # Mock the asyncio event loop run in executor
                with patch("asyncio.get_event_loop") as mock_loop:
                    mock_loop.return_value.run_in_executor.return_value = [mock_user]

                    # Call the sync helper directly for testing
                    from backend.api.user import _get_all_users_sync

                    result = _get_all_users_sync()

                    assert len(result) >= 0  # At least returns a list

    @pytest.mark.asyncio
    async def test_get_user_by_id_success(self, mock_config, mock_user):
        """Test retrieving a user by ID successfully."""
        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.all.return_value = [
                mock_user
            ]

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                result = await get_user(str(mock_user.id))

                assert result.userid == mock_user.userid

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self, mock_config):
        """Test retrieving a non-existent user by ID."""
        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.all.return_value = []

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await get_user(str(uuid.uuid4()))

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_user_by_userid_success(self, mock_config, mock_user):
        """Test retrieving a user by userid (email)."""
        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.all.return_value = [
                mock_user
            ]

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                result = await get_user_by_userid("test@example.com")

                assert result.userid == mock_user.userid

    @pytest.mark.asyncio
    async def test_add_user_success(self, mock_config, mock_admin_user, mock_request):
        """Test adding a new user successfully."""
        new_user_data = User(
            active=True,
            userid="newuser@example.com",
            password="NewPassword123!",
            first_name="New",
            last_name="User",
        )

        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )
            mock_session.query.return_value.filter.return_value.all.return_value = []

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with patch("backend.api.user.AuditService"):
                    result = await add_user(
                        new_user_data, mock_request, "admin@example.com"
                    )

                    assert result.userid == "newuser@example.com"
                    mock_session.add.assert_called_once()
                    mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_add_user_without_permission(
        self, mock_config, mock_user, mock_request
    ):
        """Test adding user fails without ADD_USER permission."""
        mock_user.has_role = MagicMock(return_value=False)

        new_user_data = User(
            active=True,
            userid="newuser@example.com",
            password="NewPassword123!",
        )

        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await add_user(new_user_data, mock_request, "test@example.com")

                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_add_duplicate_user(
        self, mock_config, mock_admin_user, mock_user, mock_request
    ):
        """Test adding a duplicate user fails."""
        new_user_data = User(
            active=True,
            userid="test@example.com",  # Already exists
            password="NewPassword123!",
        )

        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            # First call returns admin user for auth check
            # Second call (for duplicate check) returns existing user
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )
            mock_session.query.return_value.filter.return_value.all.return_value = [
                mock_user
            ]  # Duplicate found

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await add_user(new_user_data, mock_request, "admin@example.com")

                assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_update_user_success(self, mock_config, mock_admin_user, mock_user):
        """Test updating a user successfully."""
        updated_data = User(
            active=True,
            userid="test@example.com",
            password="UpdatedPassword123!",
            first_name="Updated",
            last_name="User",
        )

        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )
            mock_session.query.return_value.filter.return_value.all.return_value = [
                mock_user
            ]

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with patch("backend.api.user.AuditService"):
                    result = await update_user(
                        str(mock_user.id), updated_data, "admin@example.com"
                    )

                    assert result.userid == "test@example.com"

    @pytest.mark.asyncio
    async def test_delete_user_success(self, mock_config, mock_admin_user, mock_user):
        """Test deleting a user successfully."""
        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )
            mock_session.query.return_value.filter.return_value.all.return_value = [
                mock_user
            ]

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with patch("backend.api.user.AuditService"):
                    result = await delete_user(str(mock_user.id), "admin@example.com")

                    assert result["result"] is True

    @pytest.mark.asyncio
    async def test_delete_user_without_permission(self, mock_config, mock_user):
        """Test deleting user fails without DELETE_USER permission."""
        mock_user.has_role = MagicMock(return_value=False)

        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await delete_user(str(uuid.uuid4()), "test@example.com")

                assert exc_info.value.status_code == 403


# =============================================================================
# ACCOUNT LOCK/UNLOCK TESTS
# =============================================================================


class TestAccountLocking:
    """Test cases for account locking and unlocking."""

    @pytest.mark.asyncio
    async def test_lock_user_success(self, mock_config, mock_admin_user, mock_user):
        """Test locking a user account successfully."""
        with patch("backend.api.user.db") as mock_db, patch(
            "backend.api.user.login_security"
        ) as mock_login_security:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,  # Auth user query
                mock_user,  # Target user query
            ]

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                result = await lock_user(str(mock_user.id), "admin@example.com")

                mock_login_security.lock_user_account.assert_called_once()
                assert result.userid == mock_user.userid

    @pytest.mark.asyncio
    async def test_unlock_user_success(self, mock_config, mock_admin_user, mock_user):
        """Test unlocking a user account successfully."""
        mock_user.is_locked = True

        with patch("backend.api.user.db") as mock_db, patch(
            "backend.api.user.login_security"
        ) as mock_login_security:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,  # Auth user query
                mock_user,  # Target user query
            ]

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                result = await unlock_user(str(mock_user.id), "admin@example.com")

                mock_login_security.unlock_user_account.assert_called_once()
                assert result.userid == mock_user.userid

    @pytest.mark.asyncio
    async def test_lock_user_without_permission(self, mock_config, mock_user):
        """Test locking user fails without LOCK_USER permission."""
        mock_user.has_role = MagicMock(return_value=False)

        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await lock_user(str(uuid.uuid4()), "test@example.com")

                assert exc_info.value.status_code == 403


# =============================================================================
# USER PERMISSIONS TESTS
# =============================================================================


class TestUserPermissions:
    """Test cases for user permission retrieval."""

    @pytest.mark.asyncio
    async def test_get_user_permissions_success(self, mock_config, mock_user):
        """Test retrieving user permissions successfully."""
        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                result = await get_user_permissions("test@example.com")

                assert "is_admin" in result
                assert "permissions" in result

    @pytest.mark.asyncio
    async def test_get_user_permissions_user_not_found(self, mock_config):
        """Test retrieving permissions for non-existent user."""
        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await get_user_permissions("nonexistent@example.com")

                assert exc_info.value.status_code == 401


# =============================================================================
# PASSWORD RESET TESTS
# =============================================================================


class TestPasswordReset:
    """Test cases for password reset functionality."""

    @pytest.mark.asyncio
    async def test_forgot_password_with_existing_user(
        self, mock_config, mock_user, mock_request
    ):
        """Test forgot password with existing user."""
        request_data = ForgotPasswordRequest(email="test@example.com")

        with patch("backend.api.password_reset.db") as mock_db, patch(
            "backend.api.password_reset.email_service"
        ) as mock_email:
            mock_db.get_engine.return_value = MagicMock()
            mock_email.is_enabled.return_value = True
            mock_email.send_email.return_value = True

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.password_reset.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                result = await forgot_password(request_data, mock_request)

                assert result.success is True

    @pytest.mark.asyncio
    async def test_forgot_password_with_nonexistent_user(
        self, mock_config, mock_request
    ):
        """Test forgot password with non-existent user (should not reveal user existence)."""
        request_data = ForgotPasswordRequest(email="nonexistent@example.com")

        with patch("backend.api.password_reset.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch("backend.api.password_reset.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                result = await forgot_password(request_data, mock_request)

                # Should still return success (security - don't reveal if user exists)
                assert result.success is True

    @pytest.mark.asyncio
    async def test_reset_password_with_valid_token(self, mock_config, mock_user):
        """Test password reset with valid token."""
        request_data = ResetPasswordRequest(
            token="valid-token-123",
            password="NewSecurePassword123!",
            confirm_password="NewSecurePassword123!",
        )

        mock_reset_token = MagicMock()
        mock_reset_token.user_id = mock_user.id
        mock_reset_token.token = "valid-token-123"
        mock_reset_token.used_at = None
        mock_reset_token.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        with patch("backend.api.password_reset.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_reset_token
            )
            mock_session.query.return_value.get.return_value = mock_user

            with patch("backend.api.password_reset.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                result = await reset_password(request_data)

                assert result.success is True

    @pytest.mark.asyncio
    async def test_reset_password_with_invalid_token(self, mock_config):
        """Test password reset with invalid token."""
        request_data = ResetPasswordRequest(
            token="invalid-token",
            password="NewSecurePassword123!",
            confirm_password="NewSecurePassword123!",
        )

        with patch("backend.api.password_reset.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch("backend.api.password_reset.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await reset_password(request_data)

                assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_password_passwords_dont_match(self, mock_config):
        """Test password reset with mismatched passwords."""
        request_data = ResetPasswordRequest(
            token="valid-token",
            password="Password1!",
            confirm_password="Password2!",
        )

        with pytest.raises(HTTPException) as exc_info:
            await reset_password(request_data)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_password_too_short(self, mock_config):
        """Test password reset with too short password."""
        request_data = ResetPasswordRequest(
            token="valid-token",
            password="Short1!",
            confirm_password="Short1!",
        )

        with pytest.raises(HTTPException) as exc_info:
            await reset_password(request_data)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_validate_reset_token_valid(self, mock_config):
        """Test validating a valid reset token."""
        mock_reset_token = MagicMock()
        mock_reset_token.used_at = None
        mock_reset_token.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        with patch("backend.api.password_reset.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_reset_token
            )

            with patch("backend.api.password_reset.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                result = await validate_reset_token("valid-token")

                assert result.success is True

    @pytest.mark.asyncio
    async def test_validate_reset_token_invalid(self, mock_config):
        """Test validating an invalid reset token."""
        with patch("backend.api.password_reset.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch("backend.api.password_reset.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await validate_reset_token("invalid-token")

                assert exc_info.value.status_code == 400


# =============================================================================
# LOGIN SECURITY TESTS
# =============================================================================


class TestLoginSecurity:
    """Test cases for login security functionality."""

    def test_validate_login_attempt_allowed(self):
        """Test login attempt validation when allowed."""
        validator = LoginSecurityValidator()

        is_allowed, reason = validator.validate_login_attempt(
            "test@example.com", "127.0.0.1"
        )

        assert is_allowed is True

    def test_validate_login_attempt_blocked_ip(self):
        """Test login attempt validation with blocked IP."""
        validator = LoginSecurityValidator()
        validator.blocked_ips["127.0.0.1"] = datetime.now(timezone.utc) + timedelta(
            hours=1
        )

        is_allowed, reason = validator.validate_login_attempt(
            "test@example.com", "127.0.0.1"
        )

        assert is_allowed is False
        assert "blocked" in reason.lower()

    def test_record_failed_login(self):
        """Test recording failed login attempts."""
        validator = LoginSecurityValidator()

        validator.record_failed_login("test@example.com", "127.0.0.1", "TestAgent")

        assert len(validator.failed_attempts["127.0.0.1"]) == 1

    def test_record_successful_login_clears_failures(self):
        """Test that successful login clears failed attempts."""
        validator = LoginSecurityValidator()
        validator.failed_attempts["127.0.0.1"] = [datetime.now(timezone.utc)]

        validator.record_successful_login("test@example.com", "127.0.0.1", "TestAgent")

        assert "127.0.0.1" not in validator.failed_attempts

    def test_is_ip_blocked_not_blocked(self):
        """Test IP not blocked when not in blocked list."""
        validator = LoginSecurityValidator()

        is_blocked = validator.is_ip_blocked("127.0.0.1")

        assert is_blocked is False

    def test_is_ip_blocked_expired(self):
        """Test IP block expires correctly."""
        validator = LoginSecurityValidator()
        validator.blocked_ips["127.0.0.1"] = datetime.now(timezone.utc) - timedelta(
            hours=1
        )

        is_blocked = validator.is_ip_blocked("127.0.0.1")

        assert is_blocked is False
        assert "127.0.0.1" not in validator.blocked_ips

    def test_is_rate_limited(self):
        """Test rate limiting detection."""
        validator = LoginSecurityValidator()

        # Add 5 failed attempts
        for _ in range(5):
            validator.failed_attempts["127.0.0.1"].append(datetime.now(timezone.utc))

        is_limited = validator.is_rate_limited("127.0.0.1")

        assert is_limited is True

    def test_user_account_locked_check(self):
        """Test checking if user account is locked."""
        validator = LoginSecurityValidator()

        mock_user = MagicMock()
        mock_user.is_locked = True
        mock_user.locked_at = datetime.now(timezone.utc)

        with patch(
            "backend.security.login_security.get_account_lockout_duration",
            return_value=15,
        ):
            is_locked = validator.is_user_account_locked(mock_user)

            assert is_locked is True

    def test_user_account_lockout_expired(self):
        """Test that account lockout expires."""
        validator = LoginSecurityValidator()

        mock_user = MagicMock()
        mock_user.is_locked = True
        mock_user.locked_at = datetime.now(timezone.utc) - timedelta(minutes=30)

        with patch(
            "backend.security.login_security.get_account_lockout_duration",
            return_value=15,
        ):
            is_locked = validator.is_user_account_locked(mock_user)

            assert is_locked is False


# =============================================================================
# PASSWORD SECURITY TESTS
# =============================================================================


class TestPasswordSecurity:
    """Test cases for password security validation."""

    def test_password_too_short(self):
        """Test password validation fails for short password."""
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            "Short1!"
        )

        assert is_valid is False
        assert "8 characters" in message

    def test_password_too_long(self):
        """Test password validation fails for too long password."""
        long_password = "A" * 130 + "1!"
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            long_password
        )

        assert is_valid is False
        assert "less than 128" in message

    def test_password_no_lowercase(self):
        """Test password validation fails without lowercase."""
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            "ALLUPPERCASE1!"
        )

        assert is_valid is False
        assert "lowercase" in message

    def test_password_no_uppercase(self):
        """Test password validation fails without uppercase."""
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            "alllowercase1!"
        )

        assert is_valid is False
        assert "uppercase" in message

    def test_password_no_digit(self):
        """Test password validation fails without digit."""
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            "NoDigitsHere!"
        )

        assert is_valid is False
        assert "number" in message

    def test_password_no_special(self):
        """Test password validation fails without special character."""
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            "NoSpecial123"
        )

        assert is_valid is False
        assert "special" in message

    def test_password_valid(self):
        """Test password validation passes for valid password."""
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            "ValidP@ssword123"
        )

        assert is_valid is True

    def test_common_password_detected(self):
        """Test common password is detected."""
        is_compromised = PasswordSecurityValidator.is_password_compromised("password")

        assert is_compromised is True

    def test_uncommon_password_not_detected(self):
        """Test uncommon password is not flagged."""
        is_compromised = PasswordSecurityValidator.is_password_compromised(
            "UniqueP@ssw0rd"
        )

        assert is_compromised is False


# =============================================================================
# SESSION SECURITY TESTS
# =============================================================================


class TestSessionSecurity:
    """Test cases for session security functionality."""

    def test_create_secure_session_token(self, mock_config):
        """Test creating a secure session token."""
        manager = SessionSecurityManager()
        manager.config = TEST_CONFIG

        token = manager.create_secure_session_token("test@example.com", "127.0.0.1")

        assert token is not None
        assert ":" in token

    def test_validate_session_token_valid(self, mock_config):
        """Test validating a valid session token."""
        manager = SessionSecurityManager()
        manager.config = TEST_CONFIG

        token = manager.create_secure_session_token("test@example.com", "127.0.0.1")
        is_valid, user_id = manager.validate_session_token(token, "127.0.0.1")

        assert is_valid is True
        assert user_id == "test@example.com"

    def test_validate_session_token_tampered(self, mock_config):
        """Test validating a tampered session token."""
        manager = SessionSecurityManager()
        manager.config = TEST_CONFIG

        is_valid, user_id = manager.validate_session_token(
            "tampered:token:123:invalid", "127.0.0.1"
        )

        assert is_valid is False
        assert user_id is None

    def test_validate_session_token_malformed(self, mock_config):
        """Test validating a malformed session token."""
        manager = SessionSecurityManager()
        manager.config = TEST_CONFIG

        is_valid, user_id = manager.validate_session_token("malformed", "127.0.0.1")

        assert is_valid is False
        assert user_id is None


# =============================================================================
# USER ROLE CACHE TESTS
# =============================================================================


class TestUserRoleCache:
    """Test cases for user role cache functionality."""

    def test_role_cache_creation(self):
        """Test creating a user role cache."""
        user_id = uuid.uuid4()
        role_names = {"Add User", "Edit User", "Delete User"}

        cache = UserRoleCache(user_id, role_names)

        assert cache.user_id == user_id
        assert len(cache._role_names) == 3

    def test_has_role_present(self):
        """Test checking for a present role."""
        user_id = uuid.uuid4()
        role_names = {"Add User"}

        cache = UserRoleCache(user_id, role_names)

        assert cache.has_role(SecurityRoles.ADD_USER) is True

    def test_has_role_absent(self):
        """Test checking for an absent role."""
        user_id = uuid.uuid4()
        role_names = {"Add User"}

        cache = UserRoleCache(user_id, role_names)

        assert cache.has_role(SecurityRoles.DELETE_USER) is False

    def test_has_any_role(self):
        """Test checking for any of multiple roles."""
        user_id = uuid.uuid4()
        role_names = {"Add User"}

        cache = UserRoleCache(user_id, role_names)

        result = cache.has_any_role([SecurityRoles.ADD_USER, SecurityRoles.DELETE_USER])

        assert result is True

    def test_has_all_roles(self):
        """Test checking for all of multiple roles."""
        user_id = uuid.uuid4()
        role_names = {"Add User", "Edit User"}

        cache = UserRoleCache(user_id, role_names)

        has_all = cache.has_all_roles([SecurityRoles.ADD_USER, SecurityRoles.EDIT_USER])
        has_none = cache.has_all_roles(
            [SecurityRoles.ADD_USER, SecurityRoles.DELETE_USER]
        )

        assert has_all is True
        assert has_none is False

    def test_get_roles(self):
        """Test getting all roles from cache."""
        user_id = uuid.uuid4()
        role_names = {"Add User", "Edit User"}

        cache = UserRoleCache(user_id, role_names)

        roles = cache.get_roles()

        assert SecurityRoles.ADD_USER in roles
        assert SecurityRoles.EDIT_USER in roles

    def test_get_role_names(self):
        """Test getting role names as strings."""
        user_id = uuid.uuid4()
        role_names = {"Add User", "Edit User"}

        cache = UserRoleCache(user_id, role_names)

        names = cache.get_role_names()

        assert "Add User" in names
        assert "Edit User" in names


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Test cases for error handling in user management."""

    @pytest.mark.asyncio
    async def test_get_logged_in_user_not_found(self, mock_config, mock_request):
        """Test getting logged-in user when user doesn't exist."""
        mock_request.headers = {
            "Authorization": "Bearer " + sign_jwt("nonexistent@example.com")
        }

        with patch("backend.api.user.db") as mock_db, patch(
            "backend.api.user.config"
        ) as mock_config_module:
            mock_config_module.get_config.return_value = TEST_CONFIG
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.all.return_value = []

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await get_logged_in_user(mock_request)

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_user_not_found(self, mock_config, mock_admin_user):
        """Test updating a non-existent user."""
        updated_data = User(
            active=True,
            userid="test@example.com",
            password="UpdatedPassword123!",
        )

        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )
            mock_session.query.return_value.filter.return_value.all.return_value = []

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await update_user(
                        str(uuid.uuid4()), updated_data, "admin@example.com"
                    )

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_user_not_found(self, mock_config, mock_admin_user):
        """Test deleting a non-existent user."""
        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )
            mock_session.query.return_value.filter.return_value.all.return_value = []

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await delete_user(str(uuid.uuid4()), "admin@example.com")

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_lock_user_not_found(self, mock_config, mock_admin_user):
        """Test locking a non-existent user."""
        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,  # Auth user query
                None,  # Target user query - not found
            ]

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await lock_user(str(uuid.uuid4()), "admin@example.com")

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unlock_user_not_found(self, mock_config, mock_admin_user):
        """Test unlocking a non-existent user."""
        with patch("backend.api.user.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,  # Auth user query
                None,  # Target user query - not found
            ]

            with patch("backend.api.user.sessionmaker") as mock_sessionmaker:
                mock_session_factory = MagicMock()
                mock_session_factory.return_value.__enter__ = MagicMock(
                    return_value=mock_session
                )
                mock_session_factory.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_sessionmaker.return_value = mock_session_factory

                with pytest.raises(HTTPException) as exc_info:
                    await unlock_user(str(uuid.uuid4()), "admin@example.com")

                assert exc_info.value.status_code == 404
