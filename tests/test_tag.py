"""
Comprehensive tests for backend/api/tag.py module.
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
    TagWithHostsResponse,
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

    def __init__(self, userid="test@example.com"):
        self.userid = userid
        self.active = True
        self._role_cache = None

    def load_role_cache(self, session):
        """Mock method to load role cache."""
        self._role_cache = MockRoleCache()

    def has_role(self, role):
        """Mock method that returns True for all roles (testing purposes)."""
        if self._role_cache is None:
            return False
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


class TestGetTags:
    """Test get_tags function."""

    @pytest.mark.asyncio
    @patch("backend.api.tag.get_current_user")
    async def test_get_tags_success(self, mock_get_user):
        """Test successful tags retrieval."""
        mock_get_user.return_value = "test@example.com"
        mock_tags = [
            MockTag(1, "production", "Production environment", 5),
            MockTag(2, "development", "Development environment", 2),
        ]

        execute_result = MockExecuteResult(scalars=mock_tags)
        mock_db = MockDB(execute_results=[execute_result])

        result = await get_tags(mock_db, "test@example.com")

        assert len(result) == 2
        assert result[0].name == "production"
        assert result[0].host_count == 5
        assert result[1].name == "development"
        assert result[1].host_count == 2

    @pytest.mark.asyncio
    @patch("backend.api.tag.get_current_user")
    async def test_get_tags_empty(self, mock_get_user):
        """Test getting tags when none exist."""
        mock_get_user.return_value = "test@example.com"
        execute_result = MockExecuteResult(scalars=[])
        mock_db = MockDB(execute_results=[execute_result])

        result = await get_tags(mock_db, "test@example.com")

        assert len(result) == 0

    @pytest.mark.asyncio
    @patch("backend.api.tag.get_current_user")
    async def test_get_tags_host_count_failure(self, mock_get_user):
        """Test getting tags when host count fails."""
        mock_get_user.return_value = "test@example.com"

        # Create a tag where hosts.count() raises an exception
        mock_tag = MockTag(1, "test-tag", "Test tag")
        mock_tag.hosts = Mock()
        mock_tag.hosts.count.side_effect = Exception("Database error")

        execute_result = MockExecuteResult(scalars=[mock_tag])
        mock_db = MockDB(execute_results=[execute_result])

        result = await get_tags(mock_db, "test@example.com")

        assert len(result) == 1
        assert result[0].host_count == 0  # Should fallback to 0

    @pytest.mark.asyncio
    @patch("backend.api.tag.get_current_user")
    async def test_get_tags_database_error(self, mock_get_user):
        """Test getting tags when database error occurs."""
        mock_get_user.return_value = "test@example.com"
        mock_db = MockDB()
        mock_db.execute = Mock(side_effect=Exception("Database connection failed"))

        with pytest.raises(HTTPException) as exc_info:
            await get_tags(mock_db, "test@example.com")

        assert exc_info.value.status_code == 500


class TestCreateTag:
    """Test create_tag function."""

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_create_tag_success(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test successful tag creation."""
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

        mock_db = MockDB([])  # No existing tags

        # Mock the added tag to have an ID after commit
        def mock_refresh(obj):
            obj.id = "550e8400-e29b-41d4-a716-446655440001"

        mock_db.refresh = mock_refresh

        tag_data = TagCreate(name="new-tag", description="New test tag")
        result = await create_tag(tag_data, mock_db, "test@example.com")

        assert result.name == "new-tag"
        assert result.description == "New test tag"
        assert result.host_count == 0
        assert mock_db.committed is True
        assert len(mock_db.added_objects) == 1

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_create_tag_duplicate_name(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test creating tag with duplicate name."""
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

        existing_tag = MockTag(1, "existing-tag")
        mock_db = MockDB([existing_tag])

        tag_data = TagCreate(name="existing-tag", description="Duplicate tag")

        with pytest.raises(HTTPException) as exc_info:
            await create_tag(tag_data, mock_db, "test@example.com")

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_create_tag_integrity_error(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test creating tag with integrity error."""
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

        mock_db = MockDB([])
        mock_db.commit = Mock(side_effect=IntegrityError("", "", ""))

        tag_data = TagCreate(name="new-tag", description="New test tag")

        with pytest.raises(HTTPException) as exc_info:
            await create_tag(tag_data, mock_db, "test@example.com")

        assert exc_info.value.status_code == 400
        assert mock_db.rolled_back is True

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_create_tag_general_error(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test creating tag with general error."""
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

        mock_db = MockDB([])
        mock_db.commit = Mock(side_effect=Exception("Database error"))

        tag_data = TagCreate(name="new-tag", description="New test tag")

        with pytest.raises(HTTPException) as exc_info:
            await create_tag(tag_data, mock_db, "test@example.com")

        assert exc_info.value.status_code == 500
        assert mock_db.rolled_back is True


class TestUpdateTag:
    """Test update_tag function."""

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_update_tag_success(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test successful tag update."""
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

        existing_tag = MockTag(1, "old-name", "Old description")

        # Mock to return the tag on first query, and no duplicates on name check
        mock_db = MockDB([existing_tag])
        original_query = mock_db.query
        call_count = 0

        def mock_query_calls(model):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First call - find the tag to update
                return MockQuery([existing_tag])
            else:  # Second call - check for duplicates
                return MockQuery([])  # No duplicates

        mock_db.query = mock_query_calls

        tag_data = TagUpdate(name="new-name", description="New description")
        result = await update_tag(1, tag_data, mock_db, "test@example.com")

        assert result.name == "new-name"
        assert result.description == "New description"
        assert mock_db.committed is True

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_update_tag_not_found(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test updating non-existent tag."""
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

        mock_db = MockDB([])  # No tags

        tag_data = TagUpdate(name="new-name")

        with pytest.raises(HTTPException) as exc_info:
            await update_tag(999, tag_data, mock_db, "test@example.com")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_update_tag_duplicate_name(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test updating tag to duplicate name."""
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

        tag1 = MockTag(1, "tag1")
        tag2 = MockTag(2, "tag2")

        mock_db = MockDB([tag1])
        call_count = 0

        def mock_query_calls(model):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First call - find the tag to update
                return MockQuery([tag1])
            else:  # Second call - check for duplicates with new name
                return MockQuery([tag2])  # Return existing tag with that name

        mock_db.query = mock_query_calls

        tag_data = TagUpdate(name="tag2")  # Try to rename to existing name

        with pytest.raises(HTTPException) as exc_info:
            await update_tag(1, tag_data, mock_db, "test@example.com")

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_update_tag_partial_update(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test partial tag update."""
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

        existing_tag = MockTag(1, "existing-tag", "Old description")
        mock_db = MockDB([existing_tag])

        # Since we're not updating the name, there should be no duplicate check
        def mock_query_calls(model):
            return MockQuery([existing_tag])

        mock_db.query = mock_query_calls

        tag_data = TagUpdate(description="New description only")
        result = await update_tag(1, tag_data, mock_db, "test@example.com")

        assert result.name == "existing-tag"  # Name unchanged
        assert result.description == "New description only"

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_update_tag_host_count_error(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test updating tag when host count fails."""
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

        existing_tag = MockTag(1, "existing-tag")
        existing_tag.hosts = Mock()
        existing_tag.hosts.count.side_effect = Exception("Database error")

        mock_db = MockDB([existing_tag])
        call_count = 0

        def mock_query_calls(model):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First call - find the tag to update
                return MockQuery([existing_tag])
            else:  # Second call - check for duplicates
                return MockQuery([])  # No duplicates

        mock_db.query = mock_query_calls

        tag_data = TagUpdate(name="new-name")
        result = await update_tag(1, tag_data, mock_db, "test@example.com")

        assert result.host_count == 0  # Should fallback to 0


class TestDeleteTag:
    """Test delete_tag function."""

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_delete_tag_success(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test successful tag deletion."""
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

        existing_tag = MockTag(1, "test-tag")
        mock_db = MockDB([existing_tag])

        await delete_tag(1, mock_db, "test@example.com")

        assert mock_db.committed is True
        assert mock_db.execute_call_count == 2  # Two SQL deletes

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_delete_tag_not_found(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test deleting non-existent tag."""
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

        mock_db = MockDB([])

        with pytest.raises(HTTPException) as exc_info:
            await delete_tag(999, mock_db, "test@example.com")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.tag.db_module.get_engine")
    @patch("backend.api.tag.sessionmaker")
    @patch("backend.api.tag.get_current_user")
    async def test_delete_tag_database_error(
        self, mock_get_user, mock_sessionmaker, mock_get_engine
    ):
        """Test deleting tag with database error."""
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

        existing_tag = MockTag(1, "test-tag")
        mock_db = MockDB([existing_tag])
        mock_db.execute = Mock(side_effect=Exception("Database error"))

        with pytest.raises(HTTPException) as exc_info:
            await delete_tag(1, mock_db, "test@example.com")

        assert exc_info.value.status_code == 500
        assert mock_db.rolled_back is True


class TestGetTagHosts:
    """Test get_tag_hosts function."""

    @pytest.mark.asyncio
    @patch("backend.api.tag.get_current_user")
    async def test_get_tag_hosts_success(self, mock_get_user):
        """Test successful tag hosts retrieval."""
        mock_get_user.return_value = "test@example.com"

        tag_result = MockResultRow(
            id="550e8400-e29b-41d4-a716-446655440001",
            name="test-tag",
            description="Test tag",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        host_results = [
            MockResultRow(
                id="550e8400-e29b-41d4-a716-446655440011",
                fqdn="host1.example.com",
                ipv4="192.168.1.1",
                ipv6=None,
                active=True,
                status="up",
            ),
            MockResultRow(
                id="550e8400-e29b-41d4-a716-446655440012",
                fqdn="host2.example.com",
                ipv4="192.168.1.2",
                ipv6=None,
                active=True,
                status="up",
            ),
        ]

        mock_db = MockDB(
            execute_results=[
                MockExecuteResult(first_result=tag_result),
                MockExecuteResult(fetchall_results=host_results),
            ]
        )

        result = await get_tag_hosts(
            "550e8400-e29b-41d4-a716-446655440001", mock_db, "test@example.com"
        )

        assert result.id == "550e8400-e29b-41d4-a716-446655440001"
        assert result.name == "test-tag"
        assert len(result.hosts) == 2
        assert result.hosts[0]["fqdn"] == "host1.example.com"

    @pytest.mark.asyncio
    @patch("backend.api.tag.get_current_user")
    async def test_get_tag_hosts_tag_not_found(self, mock_get_user):
        """Test getting hosts for non-existent tag."""
        mock_get_user.return_value = "test@example.com"

        mock_db = MockDB(execute_results=[MockExecuteResult(first_result=None)])

        with pytest.raises(HTTPException) as exc_info:
            await get_tag_hosts(
                "550e8400-e29b-41d4-a716-446655440999", mock_db, "test@example.com"
            )

        assert exc_info.value.status_code == 404


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
            "test@example.com",
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
                "test@example.com",
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
                "test@example.com",
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
                "test@example.com",
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
            "test@example.com",
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
                "test@example.com",
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

        result = await get_host_tags(1, mock_db, "test@example.com")

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
            await get_host_tags(999, mock_db, "test@example.com")

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

        result = await get_host_tags(1, mock_db, "test@example.com")

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
