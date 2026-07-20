# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Unit tests for tag assignment and tag queries in the SysManage tag management
API.

Split from test_tag_management_api.py. Covers:
- Adding tags to hosts
- Removing tags from hosts
- Getting tags for a host
- Getting hosts for a tag

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
            "backend.api.tag.get_tenant_db"
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
                "backend.api.tag.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                result = await add_tag_to_host(
                    str(mock_host.id), str(mock_tag.id), mock_db, mock_admin_user
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
            "backend.api.tag.get_tenant_db"
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
                        mock_admin_user,
                    )

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_add_tag_to_host_tag_not_found(
        self, mock_config, mock_admin_user, mock_host
    ):
        """Test adding non-existent tag to host fails."""
        from backend.api.tag import add_tag_to_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
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
                        mock_admin_user,
                    )

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_add_tag_to_host_already_exists(
        self, mock_config, mock_admin_user, mock_host, mock_tag
    ):
        """Test adding a tag that is already associated with host fails."""
        from backend.api.tag import add_tag_to_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
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
                        mock_admin_user,
                    )

                assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_add_tag_to_host_without_permission(
        self, mock_config, mock_user_no_tag_permission, mock_host, mock_tag
    ):
        """Test adding tag to host fails without EDIT_TAGS permission."""
        from backend.api.tag import add_tag_to_host

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
                    await add_tag_to_host(
                        str(mock_host.id),
                        str(mock_tag.id),
                        mock_db,
                        mock_user_no_tag_permission,
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
            "backend.api.tag.get_tenant_db"
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
                "backend.api.tag.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                # Should return None (204 No Content)
                result = await remove_tag_from_host(
                    str(mock_host.id), str(mock_tag.id), mock_db, mock_admin_user
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
                    await remove_tag_from_host(
                        str(mock_host.id),
                        str(uuid.uuid4()),
                        mock_db,
                        mock_admin_user,
                    )

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_tag_from_host_without_permission(
        self, mock_config, mock_user_no_tag_permission, mock_host, mock_tag
    ):
        """Test removing tag from host fails without EDIT_TAGS permission."""
        from backend.api.tag import remove_tag_from_host

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
                    await remove_tag_from_host(
                        str(mock_host.id),
                        str(mock_tag.id),
                        mock_db,
                        mock_user_no_tag_permission,
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
            "backend.api.tag.get_tenant_db"
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
            "backend.api.tag.get_tenant_db"
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
            "backend.api.tag.get_tenant_db"
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
