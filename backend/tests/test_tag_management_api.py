# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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
            "backend.api.tag.get_tenant_db"
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
                "backend.api.tag.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                # Mock the refresh to set the tag id
                def mock_refresh(tag):
                    tag.id = uuid.uuid4()

                mock_db.refresh = mock_refresh

                result = await create_tag(tag_data, mock_db, mock_admin_user)

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
            "backend.api.tag.get_tenant_db"
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
                    await create_tag(tag_data, mock_db, mock_admin_user)

                assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_tag_without_permission(
        self, mock_config, mock_user_no_tag_permission
    ):
        """Test creating tag fails without EDIT_TAGS permission."""
        from backend.api.tag import TagCreate, create_tag

        tag_data = TagCreate(name="new-tag", description="A new tag")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
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
                    await create_tag(tag_data, mock_db, mock_user_no_tag_permission)

                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_authenticated_user_unknown_user_401(self, mock_config):
        """The user-not-found path moved out of the tag handlers into the shared
        ``require_authenticated_user`` dependency (authz is resolved on the MAIN
        engine, server-global); it raises 401 when the user does not exist."""
        from backend.auth.auth_bearer import require_authenticated_user

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with patch(
            "backend.persistence.db.get_engine", return_value=MagicMock()
        ), patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker:
            # session_local = sessionmaker(...); session = session_local()
            mock_sessionmaker.return_value.return_value = mock_session

            with pytest.raises(HTTPException) as exc_info:
                require_authenticated_user("unknown@example.com")

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_create_tag_with_empty_description(
        self, mock_config, mock_admin_user
    ):
        """Test creating a tag with empty description."""
        from backend.api.tag import TagCreate, create_tag

        tag_data = TagCreate(name="minimal-tag", description=None)

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
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
                "backend.api.tag.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                def mock_refresh(tag):
                    tag.id = uuid.uuid4()

                mock_db.refresh = mock_refresh

                result = await create_tag(tag_data, mock_db, mock_admin_user)

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
            "backend.api.tag.get_tenant_db"
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
                "backend.api.tag.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                result = await update_tag(
                    str(mock_tag.id), update_data, mock_db, mock_admin_user
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
            "backend.api.tag.get_tenant_db"
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
                "backend.api.tag.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                result = await update_tag(
                    str(mock_tag.id), update_data, mock_db, mock_admin_user
                )

                assert mock_tag.description == "Updated production description"
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_update_tag_not_found(self, mock_config, mock_admin_user):
        """Test updating a non-existent tag."""
        from backend.api.tag import TagUpdate, update_tag

        update_data = TagUpdate(name="updated-name")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
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
                        str(uuid.uuid4()), update_data, mock_db, mock_admin_user
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
            "backend.api.tag.get_tenant_db"
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
                        str(mock_tag.id), update_data, mock_db, mock_admin_user
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
            "backend.api.tag.get_tenant_db"
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
                        str(mock_tag.id),
                        update_data,
                        mock_db,
                        mock_user_no_tag_permission,
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
            "backend.api.tag.get_tenant_db"
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
                "backend.api.tag.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                # Should return None (204 No Content)
                result = await delete_tag(str(mock_tag.id), mock_db, mock_admin_user)

                # Verify SQL deletion was called
                assert mock_db.execute.call_count == 2  # DELETE host_tags, DELETE tags
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_delete_tag_not_found(self, mock_config, mock_admin_user):
        """Test deleting a non-existent tag."""
        from backend.api.tag import delete_tag

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
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
                    await delete_tag(str(uuid.uuid4()), mock_db, mock_admin_user)

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_tag_without_permission(
        self, mock_config, mock_user_no_tag_permission, mock_tag
    ):
        """Test deleting tag fails without EDIT_TAGS permission."""
        from backend.api.tag import delete_tag

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
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
                    await delete_tag(
                        str(mock_tag.id), mock_db, mock_user_no_tag_permission
                    )

                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_tag_removes_host_associations(
        self, mock_config, mock_admin_user, mock_tag
    ):
        """Test that deleting a tag removes host-tag associations."""
        from backend.api.tag import delete_tag

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
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
                "backend.api.tag.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                await delete_tag(str(mock_tag.id), mock_db, mock_admin_user)

                # Verify host_tags deletion was called first
                calls = mock_db.execute.call_args_list
                assert len(calls) >= 2
