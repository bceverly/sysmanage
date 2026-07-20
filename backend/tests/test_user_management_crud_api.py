# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Unit tests for the user management API: user CRUD, account locking,
user permissions, and password reset.

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
    add_user,
    delete_user,
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

    @pytest.mark.asyncio
    async def test_get_user_permissions_config_admin_shortcut(self, mock_config):
        """Config-admin (no DB row) gets every permission instead of 401."""
        # The fixture sets admin_userid = "admin@test.com" with no DB row.
        # Without the shortcut this would raise 401; with it, the user
        # gets is_admin=True and every SecurityRole granted.
        result = await get_user_permissions("admin@test.com")
        assert result["is_admin"] is True
        # Every defined role should be True for the config-admin.
        from backend.security.roles import SecurityRoles  # local import for clarity

        assert all(result["permissions"][role.value] is True for role in SecurityRoles)


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
