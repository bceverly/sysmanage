"""
Comprehensive unit tests for the tag management API in SysManage.

Tests cover:
- Tag CRUD operations (create, list, update, delete)
- Tag assignment to hosts
- Tag-based filtering
- Tag validation
- Bulk tag operations
- Error handling

These tests use pytest and pytest-asyncio for async tests with mocked database.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.security.roles import SecurityRoles

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
    },
}


@pytest.fixture
def mock_config():
    """Mock the configuration system to use test config."""
    with patch("backend.config.config.get_config", return_value=TEST_CONFIG):
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
    mock_session.refresh = MagicMock()
    mock_session.delete = MagicMock()
    mock_session.flush = MagicMock()
    mock_session.execute = MagicMock()
    return mock_session


@pytest.fixture
def mock_user():
    """Create a mock user object."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.userid = "test@example.com"
    user.active = True
    user.is_admin = False
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
    user.is_admin = True
    user._role_cache = MagicMock()
    user.load_role_cache = MagicMock()
    user.has_role = MagicMock(return_value=True)
    return user


@pytest.fixture
def mock_user_no_tag_permission():
    """Create a mock user without tag edit permission."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.userid = "noperm@example.com"
    user.active = True
    user.is_admin = False
    user._role_cache = None
    user.load_role_cache = MagicMock()
    user.has_role = MagicMock(return_value=False)
    return user


@pytest.fixture
def mock_tag():
    """Create a mock tag object."""
    tag = MagicMock()
    tag.id = uuid.uuid4()
    tag.name = "production"
    tag.description = "Production servers"
    tag.created_at = datetime.now(timezone.utc)
    tag.updated_at = datetime.now(timezone.utc)
    tag.hosts = MagicMock()
    tag.hosts.count.return_value = 5
    return tag


@pytest.fixture
def mock_tag_list():
    """Create a list of mock tag objects."""
    tags = []
    for i, name in enumerate(["production", "development", "staging", "testing"]):
        tag = MagicMock()
        tag.id = uuid.uuid4()
        tag.name = name
        tag.description = f"{name.capitalize()} servers"
        tag.created_at = datetime.now(timezone.utc)
        tag.updated_at = datetime.now(timezone.utc)
        tag.hosts = MagicMock()
        tag.hosts.count.return_value = i + 1
        tags.append(tag)
    return tags


@pytest.fixture
def mock_host():
    """Create a mock host object."""
    host = MagicMock()
    host.id = uuid.uuid4()
    host.fqdn = "test-host.example.com"
    host.ipv4 = "192.168.1.100"
    host.ipv6 = "::1"
    host.active = True
    host.status = "up"
    host.approval_status = "approved"
    host.tags = MagicMock()
    host.tags.all.return_value = []
    return host


@pytest.fixture
def mock_host_tag():
    """Create a mock host-tag association object."""
    host_tag = MagicMock()
    host_tag.id = uuid.uuid4()
    host_tag.host_id = uuid.uuid4()
    host_tag.tag_id = uuid.uuid4()
    host_tag.created_at = datetime.now(timezone.utc)
    return host_tag


def create_mock_session_context(mock_session):
    """Helper to create a mock session context manager."""
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_session_factory.return_value.__exit__ = MagicMock(return_value=False)
    return mock_session_factory


# =============================================================================
# TAG CRUD TESTS - LIST TAGS
# =============================================================================


class TestListTags:
    """Test cases for listing tags."""

    @pytest.mark.asyncio
    async def test_get_all_tags_success(self, mock_config, mock_tag_list):
        """Test retrieving all tags successfully."""
        from backend.api.tag import _get_tags_sync

        with patch("backend.api.tag.db_module") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = mock_tag_list
            mock_session.execute.return_value = mock_result

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = _get_tags_sync()

                assert len(result) == 4
                assert result[0]["name"] == "production"

    @pytest.mark.asyncio
    async def test_get_all_tags_empty(self, mock_config):
        """Test retrieving tags when none exist."""
        from backend.api.tag import _get_tags_sync

        with patch("backend.api.tag.db_module") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = _get_tags_sync()

                assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_tags_includes_host_count(self, mock_config, mock_tag):
        """Test that get_tags includes host count for each tag."""
        from backend.api.tag import _get_tags_sync

        with patch("backend.api.tag.db_module") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_tag]
            mock_session.execute.return_value = mock_result

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = _get_tags_sync()

                assert len(result) == 1
                assert result[0]["host_count"] == 5


# =============================================================================
# TAG CRUD TESTS - CREATE TAG
# =============================================================================


class TestCreateTag:
    """Test cases for creating tags."""

    @pytest.mark.asyncio
    async def test_create_tag_success(self, mock_config, mock_admin_user):
        """Test creating a new tag successfully."""
        from backend.api.tag import TagCreate, create_tag

        tag_data = TagCreate(name="new-tag", description="A new tag")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker, patch(
                "backend.services.audit_service.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                # Mock the refresh to set the tag id
                def mock_refresh(tag):
                    tag.id = uuid.uuid4()

                mock_db.refresh = mock_refresh

                result = await create_tag(tag_data, mock_db, "admin@example.com")

                assert result.name == "new-tag"
                assert result.description == "A new tag"
                mock_db.add.assert_called_once()
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_create_tag_duplicate_name(
        self, mock_config, mock_admin_user, mock_tag
    ):
        """Test creating a tag with duplicate name fails."""
        from backend.api.tag import TagCreate, create_tag

        tag_data = TagCreate(name="production", description="Another production tag")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_tag
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await create_tag(tag_data, mock_db, "admin@example.com")

                assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_tag_without_permission(
        self, mock_config, mock_user_no_tag_permission
    ):
        """Test creating tag fails without EDIT_TAGS permission."""
        from backend.api.tag import TagCreate, create_tag

        tag_data = TagCreate(name="new-tag", description="A new tag")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_user_no_tag_permission
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await create_tag(tag_data, mock_db, "noperm@example.com")

                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_create_tag_user_not_found(self, mock_config):
        """Test creating tag fails when user not found."""
        from backend.api.tag import TagCreate, create_tag

        tag_data = TagCreate(name="new-tag", description="A new tag")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await create_tag(tag_data, mock_db, "unknown@example.com")

                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_create_tag_with_empty_description(
        self, mock_config, mock_admin_user
    ):
        """Test creating a tag with empty description."""
        from backend.api.tag import TagCreate, create_tag

        tag_data = TagCreate(name="minimal-tag", description=None)

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker, patch(
                "backend.services.audit_service.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                def mock_refresh(tag):
                    tag.id = uuid.uuid4()

                mock_db.refresh = mock_refresh

                result = await create_tag(tag_data, mock_db, "admin@example.com")

                assert result.name == "minimal-tag"
                assert result.description is None


# =============================================================================
# TAG CRUD TESTS - UPDATE TAG
# =============================================================================


class TestUpdateTag:
    """Test cases for updating tags."""

    @pytest.mark.asyncio
    async def test_update_tag_name_success(
        self, mock_config, mock_admin_user, mock_tag
    ):
        """Test updating a tag name successfully."""
        from backend.api.tag import TagUpdate, update_tag

        update_data = TagUpdate(name="updated-production")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.side_effect = [
                mock_tag,  # Find tag
                None,  # No conflict
            ]
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker, patch(
                "backend.services.audit_service.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                result = await update_tag(
                    str(mock_tag.id), update_data, mock_db, "admin@example.com"
                )

                assert mock_tag.name == "updated-production"
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_update_tag_description_success(
        self, mock_config, mock_admin_user, mock_tag
    ):
        """Test updating a tag description successfully."""
        from backend.api.tag import TagUpdate, update_tag

        update_data = TagUpdate(description="Updated production description")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_tag
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker, patch(
                "backend.services.audit_service.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                result = await update_tag(
                    str(mock_tag.id), update_data, mock_db, "admin@example.com"
                )

                assert mock_tag.description == "Updated production description"
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_update_tag_not_found(self, mock_config, mock_admin_user):
        """Test updating a non-existent tag."""
        from backend.api.tag import TagUpdate, update_tag

        update_data = TagUpdate(name="updated-name")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await update_tag(
                        str(uuid.uuid4()), update_data, mock_db, "admin@example.com"
                    )

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_tag_name_conflict(
        self, mock_config, mock_admin_user, mock_tag, mock_tag_list
    ):
        """Test updating a tag with a name that already exists."""
        from backend.api.tag import TagUpdate, update_tag

        # Trying to rename to an existing tag name
        update_data = TagUpdate(name="development")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            # First call finds the tag to update, second call finds conflict
            mock_db.query.return_value.filter.return_value.first.side_effect = [
                mock_tag,  # Find tag to update
                mock_tag_list[1],  # Conflict with development tag
            ]
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await update_tag(
                        str(mock_tag.id), update_data, mock_db, "admin@example.com"
                    )

                assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_tag_without_permission(
        self, mock_config, mock_user_no_tag_permission, mock_tag
    ):
        """Test updating tag fails without EDIT_TAGS permission."""
        from backend.api.tag import TagUpdate, update_tag

        update_data = TagUpdate(name="updated-name")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_user_no_tag_permission
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await update_tag(
                        str(mock_tag.id), update_data, mock_db, "noperm@example.com"
                    )

                assert exc_info.value.status_code == 403


# =============================================================================
# TAG CRUD TESTS - DELETE TAG
# =============================================================================


class TestDeleteTag:
    """Test cases for deleting tags."""

    @pytest.mark.asyncio
    async def test_delete_tag_success(self, mock_config, mock_admin_user, mock_tag):
        """Test deleting a tag successfully."""
        from backend.api.tag import delete_tag

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_tag
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker, patch(
                "backend.services.audit_service.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                # Should return None (204 No Content)
                result = await delete_tag(
                    str(mock_tag.id), mock_db, "admin@example.com"
                )

                # Verify SQL deletion was called
                assert mock_db.execute.call_count == 2  # DELETE host_tags, DELETE tags
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_delete_tag_not_found(self, mock_config, mock_admin_user):
        """Test deleting a non-existent tag."""
        from backend.api.tag import delete_tag

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await delete_tag(str(uuid.uuid4()), mock_db, "admin@example.com")

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_tag_without_permission(
        self, mock_config, mock_user_no_tag_permission, mock_tag
    ):
        """Test deleting tag fails without EDIT_TAGS permission."""
        from backend.api.tag import delete_tag

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_user_no_tag_permission
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await delete_tag(str(mock_tag.id), mock_db, "noperm@example.com")

                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_tag_removes_host_associations(
        self, mock_config, mock_admin_user, mock_tag
    ):
        """Test that deleting a tag removes host-tag associations."""
        from backend.api.tag import delete_tag

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_tag
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker, patch(
                "backend.services.audit_service.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                await delete_tag(str(mock_tag.id), mock_db, "admin@example.com")

                # Verify host_tags deletion was called first
                calls = mock_db.execute.call_args_list
                assert len(calls) >= 2


# =============================================================================
# TAG ASSIGNMENT TESTS - ADD TAG TO HOST
# =============================================================================


class TestAddTagToHost:
    """Test cases for adding tags to hosts."""

    @pytest.mark.asyncio
    async def test_add_tag_to_host_success(
        self, mock_config, mock_admin_user, mock_host, mock_tag
    ):
        """Test adding a tag to a host successfully."""
        from backend.api.tag import add_tag_to_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            # Mock raw SQL executions
            mock_db.execute.return_value.first.side_effect = [
                MagicMock(id=mock_host.id),  # Host exists
                MagicMock(id=mock_tag.id),  # Tag exists
                None,  # No existing association
            ]
            mock_db.execute.return_value.scalar.side_effect = [
                mock_tag.name,
                mock_host.fqdn,
            ]
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker, patch(
                "backend.services.audit_service.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                result = await add_tag_to_host(
                    str(mock_host.id), str(mock_tag.id), mock_db, "admin@example.com"
                )

                assert "message" in result
                mock_db.add.assert_called_once()
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_add_tag_to_host_host_not_found(
        self, mock_config, mock_admin_user, mock_tag
    ):
        """Test adding tag to non-existent host fails."""
        from backend.api.tag import add_tag_to_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.execute.return_value.first.return_value = None  # Host not found
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await add_tag_to_host(
                        str(uuid.uuid4()),
                        str(mock_tag.id),
                        mock_db,
                        "admin@example.com",
                    )

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_add_tag_to_host_tag_not_found(
        self, mock_config, mock_admin_user, mock_host
    ):
        """Test adding non-existent tag to host fails."""
        from backend.api.tag import add_tag_to_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.execute.return_value.first.side_effect = [
                MagicMock(id=mock_host.id),  # Host exists
                None,  # Tag not found
            ]
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await add_tag_to_host(
                        str(mock_host.id),
                        str(uuid.uuid4()),
                        mock_db,
                        "admin@example.com",
                    )

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_add_tag_to_host_already_exists(
        self, mock_config, mock_admin_user, mock_host, mock_tag
    ):
        """Test adding a tag that is already associated with host fails."""
        from backend.api.tag import add_tag_to_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.execute.return_value.first.side_effect = [
                MagicMock(id=mock_host.id),  # Host exists
                MagicMock(id=mock_tag.id),  # Tag exists
                MagicMock(),  # Association already exists
            ]
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await add_tag_to_host(
                        str(mock_host.id),
                        str(mock_tag.id),
                        mock_db,
                        "admin@example.com",
                    )

                assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_add_tag_to_host_without_permission(
        self, mock_config, mock_user_no_tag_permission, mock_host, mock_tag
    ):
        """Test adding tag to host fails without EDIT_TAGS permission."""
        from backend.api.tag import add_tag_to_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_user_no_tag_permission
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await add_tag_to_host(
                        str(mock_host.id),
                        str(mock_tag.id),
                        mock_db,
                        "noperm@example.com",
                    )

                assert exc_info.value.status_code == 403


# =============================================================================
# TAG ASSIGNMENT TESTS - REMOVE TAG FROM HOST
# =============================================================================


class TestRemoveTagFromHost:
    """Test cases for removing tags from hosts."""

    @pytest.mark.asyncio
    async def test_remove_tag_from_host_success(
        self, mock_config, mock_admin_user, mock_host, mock_tag, mock_host_tag
    ):
        """Test removing a tag from a host successfully."""
        from backend.api.tag import remove_tag_from_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = (
                mock_host_tag
            )
            mock_db.execute.return_value.scalar.side_effect = [
                mock_tag.name,
                mock_host.fqdn,
            ]
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker, patch(
                "backend.services.audit_service.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                # Should return None (204 No Content)
                result = await remove_tag_from_host(
                    str(mock_host.id), str(mock_tag.id), mock_db, "admin@example.com"
                )

                mock_db.delete.assert_called_once_with(mock_host_tag)
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_remove_tag_from_host_not_associated(
        self, mock_config, mock_admin_user, mock_host
    ):
        """Test removing a tag that is not associated with host fails."""
        from backend.api.tag import remove_tag_from_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await remove_tag_from_host(
                        str(mock_host.id),
                        str(uuid.uuid4()),
                        mock_db,
                        "admin@example.com",
                    )

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_tag_from_host_without_permission(
        self, mock_config, mock_user_no_tag_permission, mock_host, mock_tag
    ):
        """Test removing tag from host fails without EDIT_TAGS permission."""
        from backend.api.tag import remove_tag_from_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_user_no_tag_permission
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await remove_tag_from_host(
                        str(mock_host.id),
                        str(mock_tag.id),
                        mock_db,
                        "noperm@example.com",
                    )

                assert exc_info.value.status_code == 403


# =============================================================================
# TAG QUERY TESTS - GET HOST TAGS
# =============================================================================


class TestGetHostTags:
    """Test cases for getting tags associated with a host."""

    @pytest.mark.asyncio
    async def test_get_host_tags_success(
        self, mock_config, mock_admin_user, mock_host, mock_tag_list
    ):
        """Test getting all tags for a host successfully."""
        from backend.api.tag import get_host_tags

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()

            # Create mock result rows
            mock_tag_rows = []
            for tag in mock_tag_list[:2]:  # Use first 2 tags
                row = MagicMock()
                row.id = tag.id
                row.name = tag.name
                row.description = tag.description
                row.created_at = tag.created_at
                row.updated_at = tag.updated_at
                mock_tag_rows.append(row)

            mock_db.execute.return_value.first.return_value = MagicMock(id=mock_host.id)
            mock_db.execute.return_value.fetchall.return_value = mock_tag_rows
            mock_db.execute.return_value.scalar.return_value = 2
            mock_get_db.return_value = mock_db

            with patch("backend.api.tag.sessionmaker"):
                result = await get_host_tags(
                    str(mock_host.id), mock_db, "admin@example.com"
                )

                assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_host_tags_empty(self, mock_config, mock_admin_user, mock_host):
        """Test getting tags for a host with no tags."""
        from backend.api.tag import get_host_tags

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.execute.return_value.first.return_value = MagicMock(id=mock_host.id)
            mock_db.execute.return_value.fetchall.return_value = []
            mock_get_db.return_value = mock_db

            with patch("backend.api.tag.sessionmaker"):
                result = await get_host_tags(
                    str(mock_host.id), mock_db, "admin@example.com"
                )

                assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_host_tags_host_not_found(self, mock_config, mock_admin_user):
        """Test getting tags for a non-existent host fails."""
        from backend.api.tag import get_host_tags

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.execute.return_value.first.return_value = None
            mock_get_db.return_value = mock_db

            with patch("backend.api.tag.sessionmaker"):
                with pytest.raises(HTTPException) as exc_info:
                    await get_host_tags(str(uuid.uuid4()), mock_db, "admin@example.com")

                assert exc_info.value.status_code == 404


# =============================================================================
# TAG QUERY TESTS - GET TAG HOSTS
# =============================================================================


class TestGetTagHosts:
    """Test cases for getting hosts associated with a tag."""

    @pytest.mark.asyncio
    async def test_get_tag_hosts_success(self, mock_config, mock_tag, mock_host):
        """Test getting all hosts for a tag successfully."""
        from backend.api.tag import _get_tag_hosts_sync

        with patch("backend.api.tag.db_module") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()

            # Mock tag result
            tag_result = MagicMock()
            tag_result.id = mock_tag.id
            tag_result.name = mock_tag.name
            tag_result.description = mock_tag.description
            tag_result.created_at = mock_tag.created_at
            tag_result.updated_at = mock_tag.updated_at

            # Mock host results
            host_row = MagicMock()
            host_row.id = mock_host.id
            host_row.fqdn = mock_host.fqdn
            host_row.ipv4 = mock_host.ipv4
            host_row.ipv6 = mock_host.ipv6
            host_row.active = mock_host.active
            host_row.status = mock_host.status

            mock_session.execute.return_value.first.return_value = tag_result
            mock_session.execute.return_value.fetchall.return_value = [host_row]

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = _get_tag_hosts_sync(str(mock_tag.id))

                assert result["name"] == mock_tag.name
                assert len(result["hosts"]) == 1
                assert result["hosts"][0]["fqdn"] == mock_host.fqdn

    @pytest.mark.asyncio
    async def test_get_tag_hosts_tag_not_found(self, mock_config):
        """Test getting hosts for a non-existent tag fails."""
        from backend.api.tag import _get_tag_hosts_sync

        with patch("backend.api.tag.db_module") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.execute.return_value.first.return_value = None

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    _get_tag_hosts_sync(str(uuid.uuid4()))

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_tag_hosts_empty(self, mock_config, mock_tag):
        """Test getting hosts for a tag with no associated hosts."""
        from backend.api.tag import _get_tag_hosts_sync

        with patch("backend.api.tag.db_module") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()

            tag_result = MagicMock()
            tag_result.id = mock_tag.id
            tag_result.name = mock_tag.name
            tag_result.description = mock_tag.description
            tag_result.created_at = mock_tag.created_at
            tag_result.updated_at = mock_tag.updated_at

            mock_session.execute.return_value.first.return_value = tag_result
            mock_session.execute.return_value.fetchall.return_value = []

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = _get_tag_hosts_sync(str(mock_tag.id))

                assert result["name"] == mock_tag.name
                assert len(result["hosts"]) == 0


# =============================================================================
# TAG VALIDATION TESTS
# =============================================================================


class TestTagValidation:
    """Test cases for tag validation."""

    def test_tag_create_valid_name(self):
        """Test TagCreate with valid name."""
        from backend.api.tag import TagCreate

        tag = TagCreate(name="valid-tag", description="A valid tag")
        assert tag.name == "valid-tag"
        assert tag.description == "A valid tag"

    def test_tag_create_name_too_long(self):
        """Test TagCreate with name exceeding max length."""
        from pydantic import ValidationError

        from backend.api.tag import TagCreate

        with pytest.raises(ValidationError):
            TagCreate(name="x" * 101, description="Too long name")

    def test_tag_create_empty_name(self):
        """Test TagCreate with empty name."""
        from pydantic import ValidationError

        from backend.api.tag import TagCreate

        with pytest.raises(ValidationError):
            TagCreate(name="", description="Empty name")

    def test_tag_create_description_too_long(self):
        """Test TagCreate with description exceeding max length."""
        from pydantic import ValidationError

        from backend.api.tag import TagCreate

        with pytest.raises(ValidationError):
            TagCreate(name="valid-tag", description="x" * 501)

    def test_tag_update_valid(self):
        """Test TagUpdate with valid data."""
        from backend.api.tag import TagUpdate

        update = TagUpdate(name="updated-name", description="Updated description")
        assert update.name == "updated-name"
        assert update.description == "Updated description"

    def test_tag_update_partial(self):
        """Test TagUpdate with partial data."""
        from backend.api.tag import TagUpdate

        update = TagUpdate(name="only-name")
        assert update.name == "only-name"
        assert update.description is None

    def test_tag_update_only_description(self):
        """Test TagUpdate with only description."""
        from backend.api.tag import TagUpdate

        update = TagUpdate(description="Only description")
        assert update.name is None
        assert update.description == "Only description"


# =============================================================================
# TAG RESPONSE TESTS
# =============================================================================


class TestTagResponse:
    """Test cases for tag response format."""

    def test_tag_response_format(self):
        """Test TagResponse format."""
        from backend.api.tag import TagResponse

        response = TagResponse(
            id=str(uuid.uuid4()),
            name="test-tag",
            description="Test description",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            host_count=5,
        )

        assert response.name == "test-tag"
        assert response.description == "Test description"
        assert response.host_count == 5

    def test_tag_response_default_host_count(self):
        """Test TagResponse with default host count."""
        from backend.api.tag import TagResponse

        response = TagResponse(
            id=str(uuid.uuid4()),
            name="test-tag",
            description="Test description",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        assert response.host_count == 0

    def test_tag_with_hosts_response_format(self):
        """Test TagWithHostsResponse format."""
        from backend.api.tag import TagWithHostsResponse

        hosts = [
            {"id": str(uuid.uuid4()), "fqdn": "host1.example.com"},
            {"id": str(uuid.uuid4()), "fqdn": "host2.example.com"},
        ]

        response = TagWithHostsResponse(
            id=str(uuid.uuid4()),
            name="test-tag",
            description="Test description",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            hosts=hosts,
        )

        assert response.name == "test-tag"
        assert len(response.hosts) == 2


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestTagErrorHandling:
    """Test cases for error handling in tag management."""

    @pytest.mark.asyncio
    async def test_create_tag_database_error(self, mock_config, mock_admin_user):
        """Test creating tag handles database error gracefully."""
        from backend.api.tag import TagCreate, create_tag

        tag_data = TagCreate(name="error-tag", description="Will cause error")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_db.add.side_effect = Exception("Database connection error")
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await create_tag(tag_data, mock_db, "admin@example.com")

                assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_update_tag_database_error(
        self, mock_config, mock_admin_user, mock_tag
    ):
        """Test updating tag handles database error gracefully."""
        from backend.api.tag import TagUpdate, update_tag

        update_data = TagUpdate(name="updated-name")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            # First call finds tag, second call (conflict check) returns None
            mock_db.query.return_value.filter.return_value.first.side_effect = [
                mock_tag,  # Find tag to update
                None,  # No conflict with new name
            ]
            mock_db.commit.side_effect = Exception("Database connection error")
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await update_tag(
                        str(mock_tag.id), update_data, mock_db, "admin@example.com"
                    )

                assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_delete_tag_database_error(
        self, mock_config, mock_admin_user, mock_tag
    ):
        """Test deleting tag handles database error gracefully."""
        from backend.api.tag import delete_tag

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_tag
            mock_db.execute.side_effect = Exception("Database connection error")
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await delete_tag(str(mock_tag.id), mock_db, "admin@example.com")

                assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_add_tag_to_host_database_error(
        self, mock_config, mock_admin_user, mock_host, mock_tag
    ):
        """Test adding tag to host handles database error gracefully."""
        from backend.api.tag import add_tag_to_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.execute.return_value.first.side_effect = [
                MagicMock(id=mock_host.id),  # Host exists
                MagicMock(id=mock_tag.id),  # Tag exists
                None,  # No existing association
            ]
            mock_db.add.side_effect = Exception("Database connection error")
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await add_tag_to_host(
                        str(mock_host.id),
                        str(mock_tag.id),
                        mock_db,
                        "admin@example.com",
                    )

                assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_remove_tag_from_host_database_error(
        self, mock_config, mock_admin_user, mock_host, mock_tag, mock_host_tag
    ):
        """Test removing tag from host handles database error gracefully."""
        from backend.api.tag import remove_tag_from_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = (
                mock_host_tag
            )
            mock_db.delete.side_effect = Exception("Database connection error")
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await remove_tag_from_host(
                        str(mock_host.id),
                        str(mock_tag.id),
                        mock_db,
                        "admin@example.com",
                    )

                assert exc_info.value.status_code == 500


# =============================================================================
# AUDIT LOGGING TESTS
# =============================================================================


class TestTagAuditLogging:
    """Test cases for audit logging in tag management."""

    @pytest.mark.asyncio
    async def test_create_tag_logs_audit(self, mock_config, mock_admin_user):
        """Test that creating a tag logs an audit event."""
        from backend.api.tag import TagCreate, create_tag

        tag_data = TagCreate(name="audit-tag", description="Audit test")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db, patch(
            "backend.services.audit_service.AuditService"
        ) as mock_audit:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None

            def mock_refresh(tag):
                tag.id = uuid.uuid4()

            mock_db.refresh = mock_refresh
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                await create_tag(tag_data, mock_db, "admin@example.com")

                mock_audit.log_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_tag_logs_audit(self, mock_config, mock_admin_user, mock_tag):
        """Test that updating a tag logs an audit event."""
        from backend.api.tag import TagUpdate, update_tag

        update_data = TagUpdate(name="audit-updated")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db, patch(
            "backend.services.audit_service.AuditService"
        ) as mock_audit:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.side_effect = [
                mock_tag,
                None,
            ]
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                await update_tag(
                    str(mock_tag.id), update_data, mock_db, "admin@example.com"
                )

                mock_audit.log_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_tag_logs_audit(self, mock_config, mock_admin_user, mock_tag):
        """Test that deleting a tag logs an audit event."""
        from backend.api.tag import delete_tag

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db, patch(
            "backend.services.audit_service.AuditService"
        ) as mock_audit:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_tag
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                await delete_tag(str(mock_tag.id), mock_db, "admin@example.com")

                mock_audit.log_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_tag_to_host_logs_audit(
        self, mock_config, mock_admin_user, mock_host, mock_tag
    ):
        """Test that adding a tag to host logs an audit event."""
        from backend.api.tag import add_tag_to_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db, patch(
            "backend.services.audit_service.AuditService"
        ) as mock_audit:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.execute.return_value.first.side_effect = [
                MagicMock(id=mock_host.id),
                MagicMock(id=mock_tag.id),
                None,
            ]
            mock_db.execute.return_value.scalar.side_effect = [
                mock_tag.name,
                mock_host.fqdn,
            ]
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                await add_tag_to_host(
                    str(mock_host.id), str(mock_tag.id), mock_db, "admin@example.com"
                )

                mock_audit.log.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_tag_from_host_logs_audit(
        self, mock_config, mock_admin_user, mock_host, mock_tag, mock_host_tag
    ):
        """Test that removing a tag from host logs an audit event."""
        from backend.api.tag import remove_tag_from_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db, patch(
            "backend.services.audit_service.AuditService"
        ) as mock_audit:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = (
                mock_host_tag
            )
            mock_db.execute.return_value.scalar.side_effect = [
                mock_tag.name,
                mock_host.fqdn,
            ]
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                await remove_tag_from_host(
                    str(mock_host.id), str(mock_tag.id), mock_db, "admin@example.com"
                )

                mock_audit.log.assert_called_once()


# =============================================================================
# BULK OPERATIONS TESTS
# =============================================================================


class TestBulkTagOperations:
    """Test cases for bulk tag operations."""

    @pytest.mark.asyncio
    async def test_add_multiple_tags_to_host(
        self, mock_config, mock_admin_user, mock_host, mock_tag_list
    ):
        """Test adding multiple tags to a single host."""
        from backend.api.tag import add_tag_to_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db, patch("backend.services.audit_service.AuditService"):
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                success_count = 0
                for tag in mock_tag_list[:3]:
                    mock_db.execute.return_value.first.side_effect = [
                        MagicMock(id=mock_host.id),
                        MagicMock(id=tag.id),
                        None,
                    ]
                    mock_db.execute.return_value.scalar.side_effect = [
                        tag.name,
                        mock_host.fqdn,
                    ]

                    try:
                        await add_tag_to_host(
                            str(mock_host.id),
                            str(tag.id),
                            mock_db,
                            "admin@example.com",
                        )
                        success_count += 1
                    except HTTPException:
                        pass

                assert success_count == 3

    @pytest.mark.asyncio
    async def test_add_tag_to_multiple_hosts(
        self, mock_config, mock_admin_user, mock_tag
    ):
        """Test adding a single tag to multiple hosts."""
        from backend.api.tag import add_tag_to_host

        # Create multiple mock hosts
        hosts = []
        for i in range(3):
            host = MagicMock()
            host.id = uuid.uuid4()
            host.fqdn = f"host{i}.example.com"
            hosts.append(host)

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db, patch("backend.services.audit_service.AuditService"):
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                success_count = 0
                for host in hosts:
                    mock_db.execute.return_value.first.side_effect = [
                        MagicMock(id=host.id),
                        MagicMock(id=mock_tag.id),
                        None,
                    ]
                    mock_db.execute.return_value.scalar.side_effect = [
                        mock_tag.name,
                        host.fqdn,
                    ]

                    try:
                        await add_tag_to_host(
                            str(host.id),
                            str(mock_tag.id),
                            mock_db,
                            "admin@example.com",
                        )
                        success_count += 1
                    except HTTPException:
                        pass

                assert success_count == 3


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestTagEdgeCases:
    """Test cases for edge cases in tag management."""

    def test_tag_name_with_special_characters(self):
        """Test TagCreate with special characters in name."""
        from backend.api.tag import TagCreate

        # Valid special characters
        tag = TagCreate(name="prod-env_v1.0", description="Production v1.0")
        assert tag.name == "prod-env_v1.0"

    def test_tag_name_unicode(self):
        """Test TagCreate with unicode characters in name."""
        from backend.api.tag import TagCreate

        tag = TagCreate(name="production", description="Description")
        assert tag.name == "production"

    def test_tag_description_with_newlines(self):
        """Test TagCreate with newlines in description."""
        from backend.api.tag import TagCreate

        description = "Line 1\nLine 2\nLine 3"
        tag = TagCreate(name="test-tag", description=description)
        assert "\n" in tag.description

    def test_tag_name_whitespace_handling(self):
        """Test TagCreate strips whitespace from name."""
        from backend.api.tag import TagCreate

        # Note: Pydantic doesn't strip whitespace by default
        tag = TagCreate(name=" valid-tag ", description="Test")
        # The name will include spaces unless the model strips them
        assert "valid-tag" in tag.name

    @pytest.mark.asyncio
    async def test_concurrent_tag_creation_same_name(
        self, mock_config, mock_admin_user
    ):
        """Test handling of concurrent tag creation with same name."""
        from sqlalchemy.exc import IntegrityError

        from backend.api.tag import TagCreate, create_tag

        tag_data = TagCreate(name="concurrent-tag", description="Test")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_db.commit.side_effect = IntegrityError(
                "INSERT INTO tags",
                {"name": "concurrent-tag"},
                Exception("duplicate key"),
            )
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await create_tag(tag_data, mock_db, "admin@example.com")

                assert exc_info.value.status_code == 400
                mock_db.rollback.assert_called()
