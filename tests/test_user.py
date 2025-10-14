"""
Comprehensive tests for backend/api/user.py module.
Tests user management functionality for SysManage server.
"""

import json
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from backend.api.user import (
    User,
    add_user,
    delete_user,
    delete_user_profile_image,
    get_all_users,
    get_logged_in_user,
    get_user,
    get_user_by_userid,
    get_user_profile_image,
    unlock_user,
    update_user,
    upload_user_profile_image,
)


class MockUser:
    """Mock user object."""

    def __init__(
        self, user_id=1, userid="test@example.com", active=True, is_locked=False
    ):
        self.id = user_id
        self.userid = userid
        self.active = active
        self.first_name = "John"
        self.last_name = "Doe"
        self.hashed_password = "hashed_password_123"
        self.last_access = datetime.now(timezone.utc)
        self.is_locked = is_locked
        self.failed_login_attempts = 0
        self.locked_at = None
        self.profile_image = None
        self.profile_image_type = None
        self.profile_image_uploaded_at = None
        self._role_cache = None

    def load_role_cache(self, session):
        """Mock method to load role cache."""
        self._role_cache = set()

    def has_role(self, role):
        """Mock method that returns True for all roles (testing purposes)."""
        return True


class MockSession:
    """Mock database session."""

    def __init__(self, users=None, skip_rbac_user=False):
        # Store the provided users list for other operations
        self.users = users or []
        self.committed = False
        self.added_objects = []
        self.query_count = 0
        self.skip_rbac_user = skip_rbac_user
        # Always create a default current user for RBAC checks unless skipped
        if not skip_rbac_user:
            self.current_user = MockUser(userid="test@example.com")
        else:
            self.current_user = None

    def query(self, model):
        # Increment query counter to track which query this is
        self.query_count += 1
        # First query is typically for current_user (RBAC check)
        # Subsequent queries are for the actual operation
        if self.query_count == 1 and not self.skip_rbac_user:
            return MockQuery([self.current_user])
        else:
            return MockQuery(self.users)

    def add(self, obj):
        self.added_objects.append(obj)

    def refresh(self, obj):
        """Mock refresh method."""
        pass

    def commit(self):
        self.committed = True

    def __enter__(self):
        self.query_count = 0  # Reset counter when entering context
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockQuery:
    """Mock SQLAlchemy query."""

    def __init__(self, users):
        self.users = users

    def filter(self, *args):
        return self

    def all(self):
        return self.users

    def first(self):
        return self.users[0] if self.users else None

    def delete(self):
        pass

    def update(self, values):
        pass


class MockRequest:
    """Mock FastAPI request."""

    def __init__(self, headers=None):
        self.headers = headers or {}


class MockSessionLocal:
    """Mock session factory."""

    def __init__(self, mock_session):
        self.mock_session = mock_session

    def __call__(self):
        return self.mock_session


class TestDeleteUser:
    """Test delete_user function."""

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_delete_user_success(self, mock_db, mock_sessionmaker):
        """Test successful user deletion."""
        mock_user = MockUser()
        mock_session = MockSession([mock_user])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        result = await delete_user(1)

        assert result == {"result": True}
        assert mock_session.committed

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_delete_user_not_found(self, mock_db, mock_sessionmaker):
        """Test deletion of non-existent user."""
        mock_session = MockSession([])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await delete_user(999)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_delete_user_multiple_found(self, mock_db, mock_sessionmaker):
        """Test deletion when multiple users found."""
        mock_users = [MockUser(1), MockUser(1)]
        mock_session = MockSession(mock_users)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await delete_user(1)

        assert exc_info.value.status_code == 404


class TestGetLoggedInUser:
    """Test get_logged_in_user function."""

    @pytest.mark.asyncio
    @patch("backend.api.user.decode_jwt")
    @patch("backend.api.user.config")
    async def test_get_logged_in_user_admin(self, mock_config, mock_decode_jwt):
        """Test getting admin user."""
        mock_config.get_config.return_value = {
            "security": {"admin_userid": "admin@example.com"}
        }
        mock_decode_jwt.return_value = {"user_id": "admin@example.com"}

        request = MockRequest({"Authorization": "Bearer token123"})
        result = await get_logged_in_user(request)

        assert result.userid == "admin@example.com"
        assert result.id == 0
        assert result.active is True

    @pytest.mark.asyncio
    @patch("backend.api.user.decode_jwt")
    @patch("backend.api.user.config")
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_logged_in_user_regular(
        self, mock_db, mock_sessionmaker, mock_config, mock_decode_jwt
    ):
        """Test getting regular user."""
        mock_config.get_config.return_value = {
            "security": {"admin_userid": "admin@example.com"}
        }
        mock_decode_jwt.return_value = {"user_id": "test@example.com"}
        mock_user = MockUser(userid="test@example.com")
        mock_session = MockSession([mock_user])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        request = MockRequest({"Authorization": "Bearer token123"})
        result = await get_logged_in_user(request)

        assert result.userid == "test@example.com"
        assert result.id == 1

    @pytest.mark.asyncio
    @patch("backend.api.user.decode_jwt")
    @patch("backend.api.user.config")
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_logged_in_user_not_found(
        self, mock_db, mock_sessionmaker, mock_config, mock_decode_jwt
    ):
        """Test getting user that doesn't exist."""
        mock_config.get_config.return_value = {
            "security": {"admin_userid": "admin@example.com"}
        }
        mock_decode_jwt.return_value = {"user_id": "nonexistent@example.com"}
        mock_session = MockSession([], skip_rbac_user=True)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        request = MockRequest({"Authorization": "Bearer token123"})

        with pytest.raises(HTTPException) as exc_info:
            await get_logged_in_user(request)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.user.decode_jwt")
    @patch("backend.api.user.config")
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_logged_in_user_no_auth_header(
        self, mock_db, mock_sessionmaker, mock_config, mock_decode_jwt
    ):
        """Test getting user without auth header."""
        mock_config.get_config.return_value = {
            "security": {"admin_userid": "admin@example.com"}
        }
        mock_session = MockSession([], skip_rbac_user=True)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        request = MockRequest({})

        with pytest.raises(HTTPException) as exc_info:
            await get_logged_in_user(request)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.user.decode_jwt")
    @patch("backend.api.user.config")
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_logged_in_user_invalid_token_format(
        self, mock_db, mock_sessionmaker, mock_config, mock_decode_jwt
    ):
        """Test getting user with invalid token format."""
        mock_config.get_config.return_value = {
            "security": {"admin_userid": "admin@example.com"}
        }
        mock_session = MockSession([], skip_rbac_user=True)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        request = MockRequest({"Authorization": "InvalidToken"})

        with pytest.raises(HTTPException) as exc_info:
            await get_logged_in_user(request)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.user.decode_jwt")
    @patch("backend.api.user.config")
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_logged_in_user_decode_fails(
        self, mock_db, mock_sessionmaker, mock_config, mock_decode_jwt
    ):
        """Test getting user when JWT decode fails."""
        mock_config.get_config.return_value = {
            "security": {"admin_userid": "admin@example.com"}
        }
        mock_decode_jwt.return_value = None
        mock_session = MockSession([], skip_rbac_user=True)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        request = MockRequest({"Authorization": "Bearer invalidtoken"})

        with pytest.raises(HTTPException) as exc_info:
            await get_logged_in_user(request)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.user.decode_jwt")
    @patch("backend.api.user.config")
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_logged_in_user_no_user_id_in_token(
        self, mock_db, mock_sessionmaker, mock_config, mock_decode_jwt
    ):
        """Test getting user when token has no user_id."""
        mock_config.get_config.return_value = {
            "security": {"admin_userid": "admin@example.com"}
        }
        mock_decode_jwt.return_value = {"other_field": "value"}
        mock_session = MockSession([], skip_rbac_user=True)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        request = MockRequest({"Authorization": "Bearer token123"})

        with pytest.raises(HTTPException) as exc_info:
            await get_logged_in_user(request)

        assert exc_info.value.status_code == 404


class TestGetUser:
    """Test get_user function."""

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_user_success(self, mock_db, mock_sessionmaker):
        """Test successful user retrieval."""
        mock_user = MockUser()
        mock_session = MockSession([mock_user])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        result = await get_user(1)

        assert result.id == 1
        assert result.userid == "test@example.com"

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_user_not_found(self, mock_db, mock_sessionmaker):
        """Test retrieval of non-existent user."""
        mock_session = MockSession([], skip_rbac_user=True)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await get_user(999)

        assert exc_info.value.status_code == 404


class TestGetUserByUserid:
    """Test get_user_by_userid function."""

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_user_by_userid_success(self, mock_db, mock_sessionmaker):
        """Test successful user retrieval by userid."""
        mock_user = MockUser(userid="test@example.com")
        mock_session = MockSession([mock_user])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        result = await get_user_by_userid("test@example.com")

        assert result.userid == "test@example.com"

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_user_by_userid_not_found(self, mock_db, mock_sessionmaker):
        """Test retrieval of non-existent user by userid."""
        mock_session = MockSession([], skip_rbac_user=True)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await get_user_by_userid("nonexistent@example.com")

        assert exc_info.value.status_code == 404


class TestGetAllUsers:
    """Test get_all_users function."""

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_all_users_success(self, mock_db, mock_sessionmaker):
        """Test successful retrieval of all users."""
        mock_users = [
            MockUser(1, "user1@example.com"),
            MockUser(2, "user2@example.com"),
        ]
        mock_session = MockSession(mock_users, skip_rbac_user=True)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        result = await get_all_users()

        assert len(result) == 2
        assert result[0].userid == "user1@example.com"
        assert result[1].userid == "user2@example.com"

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_all_users_empty(self, mock_db, mock_sessionmaker):
        """Test retrieval when no users exist."""
        mock_session = MockSession([], skip_rbac_user=True)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        result = await get_all_users()

        assert len(result) == 0


class TestAddUser:
    """Test add_user function."""

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    @patch("backend.api.user.argon2_hasher")
    async def test_add_user_with_password(
        self, mock_hasher, mock_db, mock_sessionmaker
    ):
        """Test adding user with password."""
        mock_hasher.hash.return_value = "hashed_password"
        mock_session = MockSession([])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        user_data = User(
            userid="new@example.com",
            active=True,
            password="password123",
            first_name="New",
            last_name="User",
        )
        request = MockRequest()

        result = await add_user(user_data, request)

        assert result.userid == "new@example.com"
        assert mock_session.committed
        # With audit logging, 2 objects are added: User + AuditLog
        assert len(mock_session.added_objects) == 2

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    @patch("backend.api.user.argon2_hasher")
    @patch("backend.api.password_reset.create_password_reset_token")
    @patch("backend.api.password_reset.send_initial_setup_email")
    async def test_add_user_without_password(
        self,
        mock_send_email,
        mock_create_token,
        mock_hasher,
        mock_db,
        mock_sessionmaker,
    ):
        """Test adding user without password."""
        mock_hasher.hash.return_value = "hashed_placeholder"
        mock_create_token.return_value = "reset_token_123"
        mock_session = MockSession([])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        user_data = User(
            userid="new@example.com", active=True, first_name="New", last_name="User"
        )
        request = MockRequest()

        result = await add_user(user_data, request)

        assert result.userid == "new@example.com"
        assert mock_session.committed
        mock_create_token.assert_called_once()
        mock_send_email.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_add_user_duplicate(self, mock_db, mock_sessionmaker):
        """Test adding user that already exists."""
        existing_user = MockUser(userid="existing@example.com")
        mock_session = MockSession([existing_user])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        user_data = User(
            userid="existing@example.com", active=True, password="password123"
        )
        request = MockRequest()

        with pytest.raises(HTTPException) as exc_info:
            await add_user(user_data, request)

        assert exc_info.value.status_code == 409


class TestUpdateUser:
    """Test update_user function."""

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    @patch("backend.api.user.argon2_hasher")
    async def test_update_user_success(self, mock_hasher, mock_db, mock_sessionmaker):
        """Test successful user update."""
        mock_hasher.hash.return_value = "new_hashed_password"
        mock_user = MockUser()
        mock_session = MockSession([mock_user])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        user_data = User(
            userid="updated@example.com",
            active=False,
            password="newpassword",
            first_name="Updated",
            last_name="User",
        )

        result = await update_user(1, user_data)

        assert result.userid == "updated@example.com"
        assert result.active is False
        assert mock_session.committed

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_update_user_not_found(self, mock_db, mock_sessionmaker):
        """Test updating non-existent user."""
        mock_session = MockSession([])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        user_data = User(
            userid="updated@example.com", active=True, password="password123"
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_user(999, user_data)

        assert exc_info.value.status_code == 404


class TestUnlockUser:
    """Test unlock_user function."""

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    @patch("backend.api.user.login_security")
    async def test_unlock_user_success(
        self, mock_login_security, mock_db, mock_sessionmaker
    ):
        """Test successful user unlock."""
        mock_user = MockUser(is_locked=True)
        mock_session = MockSession([mock_user])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        result = await unlock_user(1)

        assert result.id == 1
        mock_login_security.unlock_user_account.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_unlock_user_not_found(self, mock_db, mock_sessionmaker):
        """Test unlocking non-existent user."""
        mock_session = MockSession([])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await unlock_user(999)

        assert exc_info.value.status_code == 404


class TestUploadUserProfileImage:
    """Test upload_user_profile_image function."""

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    @patch("backend.api.user.validate_and_process_image")
    async def test_upload_user_profile_image_success(
        self, mock_validate, mock_db, mock_sessionmaker
    ):
        """Test successful profile image upload."""
        mock_validate.return_value = (b"processed_image", "jpeg")
        mock_user = MockUser()
        mock_session = MockSession([mock_user])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        file_content = b"fake_image_data"
        mock_file = Mock()
        mock_file.read = AsyncMock(return_value=file_content)
        mock_file.filename = "profile.jpg"

        result = await upload_user_profile_image(1, mock_file)

        assert "Profile image uploaded successfully" in result["message"]
        assert result["image_format"] == "jpeg"
        assert mock_session.committed

    @pytest.mark.asyncio
    async def test_upload_user_profile_image_no_file(self):
        """Test upload without file."""
        with pytest.raises(HTTPException) as exc_info:
            await upload_user_profile_image(1, None)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_user_profile_image_read_error(self):
        """Test upload with file read error."""
        mock_file = Mock()
        mock_file.read = AsyncMock(side_effect=Exception("Read error"))

        with pytest.raises(HTTPException) as exc_info:
            await upload_user_profile_image(1, mock_file)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    @patch("backend.api.user.validate_and_process_image")
    async def test_upload_user_profile_image_user_not_found(
        self, mock_validate, mock_db, mock_sessionmaker
    ):
        """Test upload for non-existent user."""
        mock_validate.return_value = (b"processed_image", "jpeg")
        mock_session = MockSession([], skip_rbac_user=True)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        mock_file = Mock()
        mock_file.read = AsyncMock(return_value=b"fake_image_data")
        mock_file.filename = "profile.jpg"

        with pytest.raises(HTTPException) as exc_info:
            await upload_user_profile_image(999, mock_file)

        assert exc_info.value.status_code == 404


class TestGetUserProfileImage:
    """Test get_user_profile_image function."""

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_user_profile_image_success_jpeg(
        self, mock_db, mock_sessionmaker
    ):
        """Test successful profile image retrieval for JPEG."""
        mock_user = MockUser()
        mock_user.profile_image = b"image_data"
        mock_user.profile_image_type = "jpg"
        mock_user.profile_image_uploaded_at = datetime.now(timezone.utc)
        mock_session = MockSession([mock_user], skip_rbac_user=True)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        result = await get_user_profile_image(1)

        assert result.body == b"image_data"
        assert result.media_type == "image/jpeg"

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_user_profile_image_success_png(self, mock_db, mock_sessionmaker):
        """Test successful profile image retrieval for PNG."""
        mock_user = MockUser()
        mock_user.profile_image = b"image_data"
        mock_user.profile_image_type = "png"
        mock_user.profile_image_uploaded_at = None
        mock_session = MockSession([mock_user], skip_rbac_user=True)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        result = await get_user_profile_image(1)

        assert result.body == b"image_data"
        assert result.media_type == "image/png"

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_user_profile_image_user_not_found(
        self, mock_db, mock_sessionmaker
    ):
        """Test retrieval for non-existent user."""
        mock_session = MockSession([])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await get_user_profile_image(999)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_get_user_profile_image_no_image(self, mock_db, mock_sessionmaker):
        """Test retrieval when user has no profile image."""
        mock_user = MockUser()
        mock_user.profile_image = None
        mock_session = MockSession([mock_user])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await get_user_profile_image(1)

        assert exc_info.value.status_code == 404


class TestDeleteUserProfileImage:
    """Test delete_user_profile_image function."""

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_delete_user_profile_image_success(self, mock_db, mock_sessionmaker):
        """Test successful profile image deletion."""
        mock_user = MockUser()
        mock_user.profile_image = b"image_data"
        mock_user.profile_image_type = "jpeg"
        mock_user.profile_image_uploaded_at = datetime.now(timezone.utc)
        mock_session = MockSession([mock_user], skip_rbac_user=True)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        result = await delete_user_profile_image(1)

        assert "Profile image deleted successfully" in result["message"]
        assert mock_session.committed

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_delete_user_profile_image_user_not_found(
        self, mock_db, mock_sessionmaker
    ):
        """Test deletion for non-existent user."""
        mock_session = MockSession([])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await delete_user_profile_image(999)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.user.sessionmaker")
    @patch("backend.api.user.db")
    async def test_delete_user_profile_image_no_image(self, mock_db, mock_sessionmaker):
        """Test deletion when user has no profile image."""
        mock_user = MockUser()
        mock_user.profile_image = None
        mock_session = MockSession([mock_user])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await delete_user_profile_image(1)

        assert exc_info.value.status_code == 404


class TestUserModel:
    """Test User model validation."""

    def test_user_model_valid(self):
        """Test valid user model creation."""
        user = User(
            active=True,
            userid="test@example.com",
            password="password123",
            first_name="John",
            last_name="Doe",
        )

        assert user.active is True
        assert user.userid == "test@example.com"
        assert user.password == "password123"

    def test_user_model_optional_fields(self):
        """Test user model with optional fields."""
        user = User(active=False, userid="test@example.com")

        assert user.active is False
        assert user.userid == "test@example.com"
        assert user.password is None
        assert user.first_name is None
        assert user.last_name is None


class TestIntegration:
    """Integration tests for user module."""

    def test_datetime_handling(self):
        """Test datetime handling in user functions."""
        now = datetime.now(timezone.utc)
        iso_string = now.isoformat()

        # Should be valid ISO format
        parsed = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None

    def test_email_validation(self):
        """Test email validation in User model."""
        # Valid email should work
        user = User(active=True, userid="valid@example.com")
        assert user.userid == "valid@example.com"
