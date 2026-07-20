# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Unit tests for the user management API: login security, password
security, session security, user role cache, and error handling.

Split from test_user_management_api.py.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from argon2 import PasswordHasher
from fastapi import HTTPException

from backend.api.user import (
    User,
    delete_user,
    get_logged_in_user,
    lock_user,
    unlock_user,
    update_user,
)
from backend.auth.auth_handler import sign_jwt
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
            _stub_auth_config_getters(mock_config_module)
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
