# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Comprehensive tests for backend/api/v1/tag.py module (part 2).
Tests tag management API endpoints.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from backend.api.tag import (
    HostTagRequest,
    TagCreate,
    TagResponse,
    TagUpdate,
    add_tag_to_host,
    create_tag,
    delete_tag,
    get_host_tags,
    get_tag_hosts,
    get_tags,
    remove_tag_from_host,
    update_tag,
)


class MockTag:
    """Mock tag object."""

    def __init__(self, tag_id=1, name="test-tag", description="Test tag", host_count=0):
        self.id = tag_id
        self.name = name
        self.description = description
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.hosts = MockHostsRelation(host_count)


class MockHostsRelation:
    """Mock hosts relationship."""

    def __init__(self, count=0):
        self._count = count

    def count(self):
        return self._count


class MockHostTag:
    """Mock host tag association."""

    def __init__(self, host_id=1, tag_id=1):
        self.host_id = host_id
        self.tag_id = tag_id
        self.created_at = datetime.now(timezone.utc)


class MockRoleCache:
    """Mock role cache that allows all roles."""

    def has_role(self, role):
        return True

    def has_any_role(self, roles):
        return True

    def has_all_roles(self, roles):
        return True


class MockUser:
    """Mock user object for RBAC checks."""

    def __init__(
        self, userid="test@example.com", user_id="550e8400-e29b-41d4-a716-446655440100"
    ):
        self.id = user_id
        self.userid = userid
        self.active = True
        self._role_cache = None

    def load_role_cache(self, session):
        """Mock method to load role cache."""
        self._role_cache = MockRoleCache()

    def has_role(self, role):
        """Mock method that returns True for all roles (testing purposes)."""
        if self._role_cache is None:
            return True
        return self._role_cache.has_role(role)


class MockDB:
    """Mock database session."""

    def __init__(self, tags=None, host_tags=None, execute_results=None):
        self.tags = tags or []
        self.host_tags = host_tags or []
        # Always include a default current user for RBAC checks
        self.current_user = MockUser()
        self.execute_results = execute_results or []
        self.committed = False
        self.rolled_back = False
        self.added_objects = []
        self.deleted_objects = []
        self.execute_call_count = 0
        self.query_count = 0

    def query(self, model):
        self.query_count += 1
        # First query is typically for User (RBAC check)
        if hasattr(model, "__name__") and model.__name__ == "User":
            return MockQuery([self.current_user])
        elif hasattr(model, "__name__") and model.__name__ == "Tag":
            return MockQuery(self.tags)
        elif hasattr(model, "__name__") and model.__name__ == "HostTag":
            return MockQuery(self.host_tags)
        return MockQuery([])

    def add(self, obj):
        self.added_objects.append(obj)

    def delete(self, obj):
        self.deleted_objects.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def refresh(self, obj):
        pass

    def execute(self, stmt, params=None):
        self.execute_call_count += 1
        if self.execute_results:
            result = self.execute_results.pop(0)
            return result
        return MockExecuteResult()


class MockQuery:
    """Mock SQLAlchemy query."""

    def __init__(self, objects):
        self.objects = objects

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return self.objects[0] if self.objects else None

    def all(self):
        return self.objects


class MockExecuteResult:
    """Mock SQL execute result."""

    def __init__(
        self, scalars=None, first_result=None, fetchall_results=None, scalar_result=None
    ):
        self.scalars_result = scalars or []
        self.first_result = first_result
        self.fetchall_results = fetchall_results or []
        self.scalar_result = scalar_result

    def scalars(self):
        return MockScalars(self.scalars_result)

    def first(self):
        return self.first_result

    def fetchall(self):
        return self.fetchall_results

    def scalar(self):
        return self.scalar_result


class MockScalars:
    """Mock scalars result."""

    def __init__(self, objects):
        self.objects = objects

    def all(self):
        return self.objects


class MockResultRow:
    """Mock database result row."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class TestAddTagToHost:
    """Test add_tag_to_host function."""

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_add_tag_to_host_success(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test successfully adding tag to host."""
        mock_get_user.return_value = "test@example.com"

        # Create a mock RBAC session
        mock_user = MockUser()
        mock_rbac_session = MockDB()
        mock_rbac_session.current_user = mock_user

        # Create a context manager that returns the RBAC session
        def create_rbac_context():
            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=mock_rbac_session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_rbac_context
        mock_get_engine.return_value = Mock()

        host_result = MockResultRow(id="550e8400-e29b-41d4-a716-446655440011")
        tag_result = MockResultRow(id="550e8400-e29b-41d4-a716-446655440001")

        mock_db = MockDB(
            execute_results=[
                MockExecuteResult(first_result=host_result),  # Host exists
                MockExecuteResult(first_result=tag_result),  # Tag exists
                MockExecuteResult(first_result=None),  # Association doesn't exist
            ]
        )

        result = await add_tag_to_host(
            "550e8400-e29b-41d4-a716-446655440011",
            "550e8400-e29b-41d4-a716-446655440001",
            mock_db,
            MockUser(),
        )

        assert "Tag added to host successfully" in result["message"]
        assert mock_db.committed is True
        assert len(mock_db.added_objects) == 1

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_add_tag_to_host_host_not_found(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test adding tag to non-existent host."""
        mock_get_user.return_value = "test@example.com"

        # Create a mock RBAC session
        mock_user = MockUser()
        mock_rbac_session = MockDB()
        mock_rbac_session.current_user = mock_user

        # Create a context manager that returns the RBAC session
        def create_rbac_context():
            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=mock_rbac_session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_rbac_context
        mock_get_engine.return_value = Mock()

        mock_db = MockDB(
            execute_results=[MockExecuteResult(first_result=None)]  # Host doesn't exist
        )

        with pytest.raises(HTTPException) as exc_info:
            await add_tag_to_host(
                "550e8400-e29b-41d4-a716-446655440999",
                "550e8400-e29b-41d4-a716-446655440001",
                mock_db,
                MockUser(),
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_add_tag_to_host_tag_not_found(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test adding non-existent tag to host."""
        mock_get_user.return_value = "test@example.com"

        # Create a mock RBAC session
        mock_user = MockUser()
        mock_rbac_session = MockDB()
        mock_rbac_session.current_user = mock_user

        # Create a context manager that returns the RBAC session
        def create_rbac_context():
            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=mock_rbac_session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_rbac_context
        mock_get_engine.return_value = Mock()

        host_result = MockResultRow(id="550e8400-e29b-41d4-a716-446655440011")

        mock_db = MockDB(
            execute_results=[
                MockExecuteResult(first_result=host_result),  # Host exists
                MockExecuteResult(first_result=None),  # Tag doesn't exist
            ]
        )

        with pytest.raises(HTTPException) as exc_info:
            await add_tag_to_host(
                "550e8400-e29b-41d4-a716-446655440011",
                "550e8400-e29b-41d4-a716-446655440999",
                mock_db,
                MockUser(),
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_add_tag_to_host_already_associated(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test adding tag to host when already associated."""
        mock_get_user.return_value = "test@example.com"

        # Create a mock RBAC session
        mock_user = MockUser()
        mock_rbac_session = MockDB()
        mock_rbac_session.current_user = mock_user

        # Create a context manager that returns the RBAC session
        def create_rbac_context():
            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=mock_rbac_session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_rbac_context
        mock_get_engine.return_value = Mock()

        host_result = MockResultRow(id="550e8400-e29b-41d4-a716-446655440011")
        tag_result = MockResultRow(id="550e8400-e29b-41d4-a716-446655440001")
        existing_association = MockResultRow(id="550e8400-e29b-41d4-a716-446655440021")

        mock_db = MockDB(
            execute_results=[
                MockExecuteResult(first_result=host_result),  # Host exists
                MockExecuteResult(first_result=tag_result),  # Tag exists
                MockExecuteResult(
                    first_result=existing_association
                ),  # Association exists
            ]
        )

        with pytest.raises(HTTPException) as exc_info:
            await add_tag_to_host(
                "550e8400-e29b-41d4-a716-446655440011",
                "550e8400-e29b-41d4-a716-446655440001",
                mock_db,
                MockUser(),
            )

        assert exc_info.value.status_code == 400


class TestRemoveTagFromHost:
    """Test remove_tag_from_host function."""

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_remove_tag_from_host_success(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test successfully removing tag from host."""
        mock_get_user.return_value = "test@example.com"

        # Create a mock RBAC session
        mock_user = MockUser()
        mock_rbac_session = MockDB()
        mock_rbac_session.current_user = mock_user

        # Create a context manager that returns the RBAC session
        def create_rbac_context():
            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=mock_rbac_session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_rbac_context
        mock_get_engine.return_value = Mock()

        existing_association = MockHostTag(1, 1)
        mock_db = MockDB(host_tags=[existing_association])

        await remove_tag_from_host(
            "550e8400-e29b-41d4-a716-446655440011",
            "550e8400-e29b-41d4-a716-446655440001",
            mock_db,
            MockUser(),
        )

        assert mock_db.committed is True
        assert len(mock_db.deleted_objects) == 1

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_remove_tag_from_host_not_associated(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test removing tag from host when not associated."""
        mock_get_user.return_value = "test@example.com"

        # Create a mock RBAC session
        mock_user = MockUser()
        mock_rbac_session = MockDB()
        mock_rbac_session.current_user = mock_user

        # Create a context manager that returns the RBAC session
        def create_rbac_context():
            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=mock_rbac_session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_rbac_context
        mock_get_engine.return_value = Mock()

        mock_db = MockDB(host_tags=[])  # No associations

        with pytest.raises(HTTPException) as exc_info:
            await remove_tag_from_host(
                "550e8400-e29b-41d4-a716-446655440011",
                "550e8400-e29b-41d4-a716-446655440001",
                mock_db,
                MockUser(),
            )

        assert exc_info.value.status_code == 404


class TestGetHostTags:
    """Test get_host_tags function."""

    @pytest.mark.asyncio
    @patch("backend.api.tag.get_current_user")
    async def test_get_host_tags_success(self, mock_get_user):
        """Test successfully getting host tags."""
        mock_get_user.return_value = "test@example.com"

        host_result = MockResultRow(id="550e8400-e29b-41d4-a716-446655440011")
        tag_results = [
            MockResultRow(
                id="550e8400-e29b-41d4-a716-446655440001",
                name="tag1",
                description="Tag 1",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
            MockResultRow(
                id="550e8400-e29b-41d4-a716-446655440002",
                name="tag2",
                description="Tag 2",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ]

        mock_db = MockDB(
            execute_results=[
                MockExecuteResult(first_result=host_result),  # Host exists
                MockExecuteResult(fetchall_results=tag_results),  # Tags for host
                MockExecuteResult(scalar_result=3),  # Host count for tag1
                MockExecuteResult(scalar_result=1),  # Host count for tag2
            ]
        )

        result = await get_host_tags(1, mock_db, MockUser())

        assert len(result) == 2
        assert result[0].name == "tag1"
        assert result[0].host_count == 3
        assert result[1].name == "tag2"
        assert result[1].host_count == 1

    @pytest.mark.asyncio
    @patch("backend.api.tag.get_current_user")
    async def test_get_host_tags_host_not_found(self, mock_get_user):
        """Test getting tags for non-existent host."""
        mock_get_user.return_value = "test@example.com"

        mock_db = MockDB(
            execute_results=[MockExecuteResult(first_result=None)]  # Host doesn't exist
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_host_tags(999, mock_db, MockUser())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.tag.get_current_user")
    async def test_get_host_tags_count_error(self, mock_get_user):
        """Test getting host tags when count query fails."""
        mock_get_user.return_value = "test@example.com"

        host_result = MockResultRow(id="550e8400-e29b-41d4-a716-446655440011")
        tag_results = [
            MockResultRow(
                id="550e8400-e29b-41d4-a716-446655440001",
                name="tag1",
                description="Tag 1",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ]

        # First execute returns host, second returns tags, third raises exception for count
        mock_db = MockDB(
            execute_results=[
                MockExecuteResult(first_result=host_result),
                MockExecuteResult(fetchall_results=tag_results),
            ]
        )

        # Make the third execute call fail
        original_execute = mock_db.execute
        call_count = 0

        def execute_with_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 3:  # Third call fails
                raise Exception("Count query failed")
            return original_execute(*args, **kwargs)

        mock_db.execute = execute_with_error

        result = await get_host_tags(1, mock_db, MockUser())

        assert len(result) == 1
        assert result[0].host_count == 0  # Should fallback to 0


class TestModels:
    """Test Pydantic models."""

    def test_tag_create_valid(self):
        """Test valid TagCreate model."""
        tag = TagCreate(name="test-tag", description="Test description")
        assert tag.name == "test-tag"
        assert tag.description == "Test description"

    def test_tag_create_minimal(self):
        """Test minimal TagCreate model."""
        tag = TagCreate(name="test-tag")
        assert tag.name == "test-tag"
        assert tag.description is None

    def test_tag_update_partial(self):
        """Test partial TagUpdate model."""
        tag = TagUpdate(name="new-name")
        assert tag.name == "new-name"
        assert tag.description is None

    def test_host_tag_request(self):
        """Test HostTagRequest model."""
        request = HostTagRequest(
            host_id="550e8400-e29b-41d4-a716-446655440001",
            tag_id="550e8400-e29b-41d4-a716-446655440002",
        )
        assert request.host_id == "550e8400-e29b-41d4-a716-446655440001"
        assert request.tag_id == "550e8400-e29b-41d4-a716-446655440002"


class TestIntegration:
    """Integration tests for tag module."""

    def test_datetime_handling(self):
        """Test datetime handling in tag responses."""
        now = datetime.now(timezone.utc)
        iso_string = now.isoformat()

        # Should be valid ISO format
        parsed = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None

    def test_tag_response_structure(self):
        """Test TagResponse structure."""
        tag_data = {
            "id": "550e8400-e29b-41d4-a716-446655440003",
            "name": "test-tag",
            "description": "Test tag",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "host_count": 5,
        }

        response = TagResponse(**tag_data)
        assert response.id == "550e8400-e29b-41d4-a716-446655440003"
        assert response.name == "test-tag"
        assert response.host_count == 5
