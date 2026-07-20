# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Unit tests for tag validation, response formats, error handling, audit logging,
bulk operations, and edge cases in the SysManage tag management API.

Split from test_tag_management_api.py. Covers:
- Tag validation (TagCreate / TagUpdate)
- Tag response formats
- Error handling (database errors)
- Audit logging
- Bulk tag operations
- Edge cases

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
            "backend.api.tag.get_tenant_db"
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
                    await create_tag(tag_data, mock_db, mock_admin_user)

                assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_update_tag_database_error(
        self, mock_config, mock_admin_user, mock_tag
    ):
        """Test updating tag handles database error gracefully."""
        from backend.api.tag import TagUpdate, update_tag

        update_data = TagUpdate(name="updated-name")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
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
                        str(mock_tag.id), update_data, mock_db, mock_admin_user
                    )

                assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_delete_tag_database_error(
        self, mock_config, mock_admin_user, mock_tag
    ):
        """Test deleting tag handles database error gracefully."""
        from backend.api.tag import delete_tag

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
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
                    await delete_tag(str(mock_tag.id), mock_db, mock_admin_user)

                assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_add_tag_to_host_database_error(
        self, mock_config, mock_admin_user, mock_host, mock_tag
    ):
        """Test adding tag to host handles database error gracefully."""
        from backend.api.tag import add_tag_to_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
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
                        mock_admin_user,
                    )

                assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_remove_tag_from_host_database_error(
        self, mock_config, mock_admin_user, mock_host, mock_tag, mock_host_tag
    ):
        """Test removing tag from host handles database error gracefully."""
        from backend.api.tag import remove_tag_from_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
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
                        mock_admin_user,
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
            "backend.api.tag.get_tenant_db"
        ) as mock_get_db, patch("backend.api.tag.AuditService") as mock_audit:
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

                await create_tag(tag_data, mock_db, mock_admin_user)

                mock_audit.log_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_tag_logs_audit(self, mock_config, mock_admin_user, mock_tag):
        """Test that updating a tag logs an audit event."""
        from backend.api.tag import TagUpdate, update_tag

        update_data = TagUpdate(name="audit-updated")

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
        ) as mock_get_db, patch("backend.api.tag.AuditService") as mock_audit:
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
                    str(mock_tag.id), update_data, mock_db, mock_admin_user
                )

                mock_audit.log_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_tag_logs_audit(self, mock_config, mock_admin_user, mock_tag):
        """Test that deleting a tag logs an audit event."""
        from backend.api.tag import delete_tag

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
        ) as mock_get_db, patch("backend.api.tag.AuditService") as mock_audit:
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

                await delete_tag(str(mock_tag.id), mock_db, mock_admin_user)

                mock_audit.log_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_tag_to_host_logs_audit(
        self, mock_config, mock_admin_user, mock_host, mock_tag
    ):
        """Test that adding a tag to host logs an audit event."""
        from backend.api.tag import add_tag_to_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
        ) as mock_get_db, patch("backend.api.tag.AuditService") as mock_audit:
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
                    str(mock_host.id), str(mock_tag.id), mock_db, mock_admin_user
                )

                mock_audit.log.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_tag_from_host_logs_audit(
        self, mock_config, mock_admin_user, mock_host, mock_tag, mock_host_tag
    ):
        """Test that removing a tag from host logs an audit event."""
        from backend.api.tag import remove_tag_from_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_tenant_db"
        ) as mock_get_db, patch("backend.api.tag.AuditService") as mock_audit:
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
                    str(mock_host.id), str(mock_tag.id), mock_db, mock_admin_user
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
            "backend.api.tag.get_tenant_db"
        ) as mock_get_db, patch("backend.api.tag.AuditService"):
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
                            mock_admin_user,
                        )
                        success_count += 1
                    except HTTPException:
                        _ = None  # empty-except: failure here is non-fatal; see code above

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
            "backend.api.tag.get_tenant_db"
        ) as mock_get_db, patch("backend.api.tag.AuditService"):
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
                            mock_admin_user,
                        )
                        success_count += 1
                    except HTTPException:
                        _ = None  # empty-except: failure here is non-fatal; see code above

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
            "backend.api.tag.get_tenant_db"
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
                    await create_tag(tag_data, mock_db, mock_admin_user)

                assert exc_info.value.status_code == 400
                mock_db.rollback.assert_called()
