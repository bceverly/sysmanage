"""
Comprehensive tests for backend/api/host_ubuntu_pro.py module.
Tests Ubuntu Pro management endpoints for SysManage server.
"""

import importlib
import sys
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from backend.api.host_ubuntu_pro import (
    UbuntuProAttachRequest,
    UbuntuProServiceRequest,
    attach_ubuntu_pro,
    detach_ubuntu_pro,
    disable_ubuntu_pro_service,
    enable_ubuntu_pro_service,
)


class MockHost:
    """Mock host object."""

    def __init__(self, host_id=1):
        self.id = host_id
        self.fqdn = "test.example.com"
        self.hostname = "test-host"
        self._role_cache = None

    def load_role_cache(self, session):
        """Mock method to load role cache."""
        self._role_cache = set()

    def has_role(self, role):
        """Mock method that returns True for all roles (testing purposes)."""
        return True


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


class MockQuery:
    """Mock SQLAlchemy query."""

    def __init__(self, objects):
        self.objects = objects

    def filter(self, *args):
        return self

    def first(self):
        return self.objects[0] if self.objects else None


class MockDBSession:
    """Mock database session."""

    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.current_user = MockUser()

    def query(self, model):
        # Return MockUser for User queries (RBAC checks)
        if hasattr(model, "__name__") and model.__name__ == "User":
            return MockQuery([self.current_user])
        return MockQuery([])

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class TestUbuntuProAttachRequest:
    """Test UbuntuProAttachRequest model."""

    def test_valid_request(self):
        """Test valid attach request."""
        request = UbuntuProAttachRequest(token="C123456789abcdef")
        assert request.token == "C123456789abcdef"

    def test_empty_token(self):
        """Test request with empty token."""
        request = UbuntuProAttachRequest(token="")
        assert request.token == ""

    def test_extra_field_forbidden(self):
        """Test that extra fields are forbidden."""
        with pytest.raises(ValueError):
            UbuntuProAttachRequest(token="test", extra_field="value")


class TestUbuntuProServiceRequest:
    """Test UbuntuProServiceRequest model."""

    def test_valid_request(self):
        """Test valid service request."""
        request = UbuntuProServiceRequest(service="esm-infra")
        assert request.service == "esm-infra"

    def test_empty_service(self):
        """Test request with empty service."""
        request = UbuntuProServiceRequest(service="")
        assert request.service == ""

    def test_extra_field_forbidden(self):
        """Test that extra fields are forbidden."""
        with pytest.raises(ValueError):
            UbuntuProServiceRequest(service="esm-infra", extra_field="value")


class TestAttachUbuntuPro:
    """Test attach_ubuntu_pro endpoint."""

    @pytest.mark.asyncio
    @patch("backend.api.host_ubuntu_pro.sessionmaker")
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    @patch("backend.api.host_ubuntu_pro.server_queue_manager")
    async def test_attach_success(
        self, mock_queue_manager, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test successful Ubuntu Pro attach."""
        # Setup TWO sessions: one for RBAC check, one for actual work
        rbac_session = MockDBSession()  # First session for RBAC check
        work_session = MockDBSession()  # Second session for actual work

        session_instances = [rbac_session, work_session]
        session_index = [0]  # Use list to allow mutation in nested function

        def create_context_manager():
            # Each call to session_local() returns a new context manager
            session = session_instances[session_index[0]]
            session_index[0] += 1

            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_context_manager

        mock_get_engine.return_value = Mock()

        mock_host = MockHost(host_id=1)
        mock_get_host.return_value = mock_host
        mock_queue_manager.enqueue_message.return_value = "queue-123"

        request = UbuntuProAttachRequest(token="C123456789abcdef")
        result = await attach_ubuntu_pro(1, request, current_user="test@example.com")

        # Verify result
        assert result["result"] is True
        assert "Ubuntu Pro attach requested" in result["message"]
        assert result["queue_id"] == "queue-123"

        # Verify interactions
        mock_get_host.assert_called_once_with(1)
        mock_queue_manager.enqueue_message.assert_called_once()
        # Verify that the WORK session (second one) was committed
        assert work_session.committed is True

    @pytest.mark.asyncio
    @patch("backend.api.host_ubuntu_pro.sessionmaker")
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    async def test_attach_empty_token(self, mock_get_engine, mock_sessionmaker):
        """Test attach with empty token."""
        # Setup session for RBAC check
        rbac_session = MockDBSession()
        mock_session_factory = Mock()
        mock_session_factory.return_value.__enter__ = Mock(return_value=rbac_session)
        mock_session_factory.return_value.__exit__ = Mock(return_value=None)
        mock_sessionmaker.return_value = mock_session_factory
        mock_get_engine.return_value = Mock()

        request = UbuntuProAttachRequest(token="   ")

        with pytest.raises(HTTPException) as exc_info:
            await attach_ubuntu_pro(1, request, current_user="test@example.com")

        assert exc_info.value.status_code == 400
        assert "Ubuntu Pro token is required" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("backend.api.host_ubuntu_pro.sessionmaker")
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    async def test_attach_host_not_found(
        self, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test attach with non-existent host."""
        # Setup TWO sessions: one for RBAC check, one for actual work
        rbac_session = MockDBSession()
        work_session = MockDBSession()

        session_instances = [rbac_session, work_session]
        session_index = 0

        def get_next_session():
            nonlocal session_index
            session = session_instances[session_index]
            session_index += 1
            return session

        mock_session_factory = Mock()
        mock_session_factory.return_value.__enter__ = Mock(side_effect=get_next_session)
        mock_session_factory.return_value.__exit__ = Mock(return_value=None)
        mock_sessionmaker.return_value = mock_session_factory
        mock_get_engine.return_value = Mock()

        mock_get_host.side_effect = HTTPException(
            status_code=404, detail="Host not found"
        )

        request = UbuntuProAttachRequest(token="C123456789abcdef")

        with pytest.raises(HTTPException) as exc_info:
            await attach_ubuntu_pro(999, request, current_user="test@example.com")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.host_ubuntu_pro.sessionmaker")
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    @patch("backend.api.host_ubuntu_pro.server_queue_manager")
    async def test_attach_queue_error(
        self, mock_queue_manager, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test attach with queue manager error."""
        # Setup TWO sessions: one for RBAC check, one for actual work
        rbac_session = MockDBSession()
        work_session = MockDBSession()

        session_instances = [rbac_session, work_session]
        session_index = [0]  # Use list to allow mutation in nested function

        def create_context_manager():
            # Each call to session_local() returns a new context manager
            session = session_instances[session_index[0]]
            session_index[0] += 1

            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_context_manager
        mock_get_engine.return_value = Mock()

        mock_host = MockHost(host_id=1)
        mock_get_host.return_value = mock_host
        mock_queue_manager.enqueue_message.side_effect = Exception("Queue error")

        request = UbuntuProAttachRequest(token="C123456789abcdef")

        with pytest.raises(HTTPException) as exc_info:
            await attach_ubuntu_pro(1, request, current_user="test@example.com")

        assert exc_info.value.status_code == 500
        assert "Failed to request Ubuntu Pro attach" in str(exc_info.value.detail)
        # Verify that the WORK session (second one) was rolled back
        assert work_session.rolled_back is True


class TestDetachUbuntuPro:
    """Test detach_ubuntu_pro endpoint."""

    @pytest.mark.asyncio
    @patch("backend.api.host_ubuntu_pro.sessionmaker")
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    @patch("backend.api.host_ubuntu_pro.server_queue_manager")
    async def test_detach_success(
        self, mock_queue_manager, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test successful Ubuntu Pro detach."""
        # Setup TWO sessions: one for RBAC check, one for actual work
        rbac_session = MockDBSession()
        work_session = MockDBSession()

        session_instances = [rbac_session, work_session]
        session_index = [0]  # Use list to allow mutation in nested function

        def create_context_manager():
            # Each call to session_local() returns a new context manager
            session = session_instances[session_index[0]]
            session_index[0] += 1

            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_context_manager

        # Setup mocks
        mock_get_engine.return_value = Mock()
        mock_host = MockHost(host_id=1)
        mock_get_host.return_value = mock_host
        mock_queue_manager.enqueue_message.return_value = "queue-456"

        result = await detach_ubuntu_pro(1, current_user="test@example.com")

        # Verify result
        assert result["result"] is True
        assert "Ubuntu Pro detach requested" in result["message"]
        assert result["queue_id"] == "queue-456"

        # Verify interactions
        mock_get_host.assert_called_once_with(1)
        mock_queue_manager.enqueue_message.assert_called_once()
        # Verify that the WORK session (second one) was committed
        assert work_session.committed is True

    @pytest.mark.asyncio
    @patch("backend.api.host_ubuntu_pro.sessionmaker")
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    async def test_detach_host_not_found(
        self, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test detach with non-existent host."""
        # Setup TWO sessions: one for RBAC check, one for actual work
        rbac_session = MockDBSession()
        work_session = MockDBSession()

        session_instances = [rbac_session, work_session]
        session_index = 0

        def get_next_session():
            nonlocal session_index
            session = session_instances[session_index]
            session_index += 1
            return session

        mock_session_factory = Mock()
        mock_session_factory.return_value.__enter__ = Mock(side_effect=get_next_session)
        mock_session_factory.return_value.__exit__ = Mock(return_value=None)
        mock_sessionmaker.return_value = mock_session_factory
        mock_get_engine.return_value = Mock()

        mock_get_host.side_effect = HTTPException(
            status_code=404, detail="Host not found"
        )

        with pytest.raises(HTTPException) as exc_info:
            await detach_ubuntu_pro(999, current_user="test@example.com")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.host_ubuntu_pro.sessionmaker")
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    @patch("backend.api.host_ubuntu_pro.server_queue_manager")
    async def test_detach_queue_error(
        self, mock_queue_manager, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test detach with queue manager error."""
        # Setup TWO sessions: one for RBAC check, one for actual work
        rbac_session = MockDBSession()
        work_session = MockDBSession()

        session_instances = [rbac_session, work_session]
        session_index = [0]  # Use list to allow mutation in nested function

        def create_context_manager():
            # Each call to session_local() returns a new context manager
            session = session_instances[session_index[0]]
            session_index[0] += 1

            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_context_manager
        mock_get_engine.return_value = Mock()

        mock_host = MockHost(host_id=1)
        mock_get_host.return_value = mock_host
        mock_queue_manager.enqueue_message.side_effect = Exception("Queue error")

        with pytest.raises(HTTPException) as exc_info:
            await detach_ubuntu_pro(1, current_user="test@example.com")

        assert exc_info.value.status_code == 500
        assert "Failed to request Ubuntu Pro detach" in str(exc_info.value.detail)
        # Verify that the WORK session (second one) was rolled back
        assert work_session.rolled_back is True


class TestEnableUbuntuProService:
    """Test enable_ubuntu_pro_service endpoint."""

    @pytest.mark.asyncio
    @patch("sqlalchemy.orm.sessionmaker")  # Local import inside the function
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    @patch("backend.api.host_ubuntu_pro.server_queue_manager")
    async def test_enable_service_success(
        self, mock_queue_manager, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test successful Ubuntu Pro service enable."""
        # Note: enable_ubuntu_pro_service does NOT have RBAC checks, so only ONE session
        work_session = MockDBSession()

        def create_context_manager():
            # Each call to session_local() returns a new context manager
            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=work_session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_context_manager

        # Setup mocks
        mock_get_engine.return_value = Mock()
        mock_host = MockHost(host_id=1)
        mock_get_host.return_value = mock_host
        mock_queue_manager.enqueue_message.return_value = "queue-789"

        request = UbuntuProServiceRequest(service="esm-infra")
        result = await enable_ubuntu_pro_service(1, request)

        # Verify result
        assert result["result"] is True
        assert "Ubuntu Pro service enable requested" in result["message"]
        assert result["queue_id"] == "queue-789"

        # Verify interactions
        mock_get_host.assert_called_once_with(1)
        mock_queue_manager.enqueue_message.assert_called_once()
        assert work_session.committed is True

    @pytest.mark.asyncio
    async def test_enable_service_empty_service(self):
        """Test enable service with empty service name."""
        request = UbuntuProServiceRequest(service="   ")

        with pytest.raises(HTTPException) as exc_info:
            await enable_ubuntu_pro_service(1, request)

        assert exc_info.value.status_code == 400
        assert "Service name is required" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("backend.api.host_ubuntu_pro.sessionmaker")
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    async def test_enable_service_host_not_found(
        self, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test enable service with non-existent host."""
        # Note: enable_ubuntu_pro_service does NOT have RBAC checks, so only ONE session
        mock_db_session = MockDBSession()
        mock_session_factory = Mock()
        mock_session_factory.return_value.__enter__ = Mock(return_value=mock_db_session)
        mock_session_factory.return_value.__exit__ = Mock(return_value=None)
        mock_sessionmaker.return_value = mock_session_factory
        mock_get_engine.return_value = Mock()

        mock_get_host.side_effect = HTTPException(
            status_code=404, detail="Host not found"
        )

        request = UbuntuProServiceRequest(service="esm-infra")

        with pytest.raises(HTTPException) as exc_info:
            await enable_ubuntu_pro_service(999, request)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("sqlalchemy.orm.sessionmaker")  # Local import inside the function
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    @patch("backend.api.host_ubuntu_pro.server_queue_manager")
    async def test_enable_service_queue_error(
        self, mock_queue_manager, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test enable service with queue manager error."""
        # Note: enable_ubuntu_pro_service does NOT have RBAC checks, so only ONE session
        work_session = MockDBSession()

        def create_context_manager():
            # Each call to session_local() returns a new context manager
            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=work_session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_context_manager
        mock_get_engine.return_value = Mock()

        mock_host = MockHost(host_id=1)
        mock_get_host.return_value = mock_host
        mock_queue_manager.enqueue_message.side_effect = Exception("Queue error")

        request = UbuntuProServiceRequest(service="esm-infra")

        with pytest.raises(HTTPException) as exc_info:
            await enable_ubuntu_pro_service(1, request)

        assert exc_info.value.status_code == 500
        assert "Failed to request Ubuntu Pro service enable" in str(
            exc_info.value.detail
        )
        assert work_session.rolled_back is True


class TestDisableUbuntuProService:
    """Test disable_ubuntu_pro_service endpoint."""

    @pytest.mark.asyncio
    @patch("sqlalchemy.orm.sessionmaker")  # Local import inside the function
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    @patch("backend.api.host_ubuntu_pro.server_queue_manager")
    async def test_disable_service_success(
        self, mock_queue_manager, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test successful Ubuntu Pro service disable."""
        # Note: disable_ubuntu_pro_service does NOT have RBAC checks, so only ONE session
        work_session = MockDBSession()

        def create_context_manager():
            # Each call to session_local() returns a new context manager
            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=work_session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_context_manager

        # Setup mocks
        mock_get_engine.return_value = Mock()
        mock_host = MockHost(host_id=1)
        mock_get_host.return_value = mock_host
        mock_queue_manager.enqueue_message.return_value = "queue-012"

        request = UbuntuProServiceRequest(service="esm-apps")
        result = await disable_ubuntu_pro_service(1, request)

        # Verify result
        assert result["result"] is True
        assert "Ubuntu Pro service disable requested" in result["message"]
        assert result["queue_id"] == "queue-012"

        # Verify interactions
        mock_get_host.assert_called_once_with(1)
        mock_queue_manager.enqueue_message.assert_called_once()
        assert work_session.committed is True

    @pytest.mark.asyncio
    async def test_disable_service_empty_service(self):
        """Test disable service with empty service name."""
        request = UbuntuProServiceRequest(service="   ")

        with pytest.raises(HTTPException) as exc_info:
            await disable_ubuntu_pro_service(1, request)

        assert exc_info.value.status_code == 400
        assert "Service name is required" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("backend.api.host_ubuntu_pro.sessionmaker")
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    async def test_disable_service_host_not_found(
        self, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test disable service with non-existent host."""
        # Note: disable_ubuntu_pro_service does NOT have RBAC checks, so only ONE session
        mock_db_session = MockDBSession()
        mock_session_factory = Mock()
        mock_session_factory.return_value.__enter__ = Mock(return_value=mock_db_session)
        mock_session_factory.return_value.__exit__ = Mock(return_value=None)
        mock_sessionmaker.return_value = mock_session_factory
        mock_get_engine.return_value = Mock()

        mock_get_host.side_effect = HTTPException(
            status_code=404, detail="Host not found"
        )

        request = UbuntuProServiceRequest(service="esm-apps")

        with pytest.raises(HTTPException) as exc_info:
            await disable_ubuntu_pro_service(999, request)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("sqlalchemy.orm.sessionmaker")  # Local import inside the function
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    @patch("backend.api.host_ubuntu_pro.server_queue_manager")
    async def test_disable_service_queue_error(
        self, mock_queue_manager, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test disable service with queue manager error."""
        # Note: disable_ubuntu_pro_service does NOT have RBAC checks, so only ONE session
        work_session = MockDBSession()

        def create_context_manager():
            # Each call to session_local() returns a new context manager
            context_mgr = Mock()
            context_mgr.__enter__ = Mock(return_value=work_session)
            context_mgr.__exit__ = Mock(return_value=None)
            return context_mgr

        mock_sessionmaker.return_value = create_context_manager
        mock_get_engine.return_value = Mock()

        mock_host = MockHost(host_id=1)
        mock_get_host.return_value = mock_host
        mock_queue_manager.enqueue_message.side_effect = Exception("Queue error")

        request = UbuntuProServiceRequest(service="esm-apps")

        with pytest.raises(HTTPException) as exc_info:
            await disable_ubuntu_pro_service(1, request)

        assert exc_info.value.status_code == 500
        assert "Failed to request Ubuntu Pro service disable" in str(
            exc_info.value.detail
        )
        assert work_session.rolled_back is True


class TestUbuntuProIntegration:
    """Integration tests for Ubuntu Pro endpoints."""

    @pytest.mark.asyncio
    @patch("backend.api.host_ubuntu_pro.sessionmaker")
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    @patch("backend.api.host_ubuntu_pro.server_queue_manager")
    async def test_full_ubuntu_pro_workflow(
        self, mock_queue_manager, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test complete Ubuntu Pro workflow."""
        # Setup multiple sessions for the workflow:
        # - attach: 2 sessions (RBAC + work)
        # - enable: 1 session (no RBAC)
        # - disable: 1 session (no RBAC)
        # - detach: 2 sessions (RBAC + work)
        # Total: 6 sessions
        sessions = [MockDBSession() for _ in range(6)]
        session_index = 0

        def get_next_session():
            nonlocal session_index
            session = sessions[session_index]
            session_index += 1
            return session

        mock_session_factory = Mock()
        mock_session_factory.return_value.__enter__ = Mock(side_effect=get_next_session)
        mock_session_factory.return_value.__exit__ = Mock(return_value=None)
        mock_sessionmaker.return_value = mock_session_factory

        # Setup mocks
        mock_get_engine.return_value = Mock()
        mock_host = MockHost(host_id=1)
        mock_get_host.return_value = mock_host
        mock_queue_manager.enqueue_message.side_effect = [
            "attach-123",
            "enable-456",
            "disable-789",
            "detach-012",
        ]

        # Test attach
        attach_request = UbuntuProAttachRequest(token="C123456789abcdef")
        attach_result = await attach_ubuntu_pro(
            1, attach_request, current_user="test@example.com"
        )
        assert attach_result["result"] is True
        assert attach_result["queue_id"] == "attach-123"

        # Test enable service
        enable_request = UbuntuProServiceRequest(service="esm-infra")
        enable_result = await enable_ubuntu_pro_service(1, enable_request)
        assert enable_result["result"] is True
        assert enable_result["queue_id"] == "enable-456"

        # Test disable service
        disable_request = UbuntuProServiceRequest(service="esm-apps")
        disable_result = await disable_ubuntu_pro_service(1, disable_request)
        assert disable_result["result"] is True
        assert disable_result["queue_id"] == "disable-789"

        # Test detach
        detach_result = await detach_ubuntu_pro(1, current_user="test@example.com")
        assert detach_result["result"] is True
        assert detach_result["queue_id"] == "detach-012"

        # Verify all operations used the same host
        assert mock_get_host.call_count == 4
        for call in mock_get_host.call_args_list:
            assert call[0][0] == 1

    def test_request_model_validation(self):
        """Test request model validation edge cases."""
        # Test UbuntuProAttachRequest with various tokens
        valid_tokens = [
            "C123456789abcdef",
            "C" + "x" * 23,  # 24 chars total
            "token-with-dashes",
        ]

        for token in valid_tokens:
            request = UbuntuProAttachRequest(token=token)
            assert request.token == token

        # Test UbuntuProServiceRequest with various services
        valid_services = [
            "esm-infra",
            "esm-apps",
            "cc-eal",
            "fips",
            "fips-updates",
        ]

        for service in valid_services:
            request = UbuntuProServiceRequest(service=service)
            assert request.service == service

    @pytest.mark.asyncio
    @patch("backend.api.host_ubuntu_pro.sessionmaker")
    @patch("backend.api.host_ubuntu_pro.db.get_engine")
    @patch("backend.api.host_ubuntu_pro.get_host_by_id")
    @patch("backend.api.host_ubuntu_pro.server_queue_manager")
    async def test_command_data_structure(
        self, mock_queue_manager, mock_get_host, mock_get_engine, mock_sessionmaker
    ):
        """Test that command data is structured correctly."""
        # Setup sessions: attach needs 2 (RBAC + work), enable needs 1 (no RBAC)
        # Total: 3 sessions
        sessions = [MockDBSession() for _ in range(3)]
        session_index = 0

        def get_next_session():
            nonlocal session_index
            session = sessions[session_index]
            session_index += 1
            return session

        mock_session_factory = Mock()
        mock_session_factory.return_value.__enter__ = Mock(side_effect=get_next_session)
        mock_session_factory.return_value.__exit__ = Mock(return_value=None)
        mock_sessionmaker.return_value = mock_session_factory

        # Setup mocks
        mock_get_engine.return_value = Mock()
        mock_host = MockHost(host_id=1)
        mock_get_host.return_value = mock_host
        mock_queue_manager.enqueue_message.return_value = "queue-123"

        # Test attach command structure
        attach_request = UbuntuProAttachRequest(token="test-token")
        await attach_ubuntu_pro(1, attach_request, current_user="test@example.com")

        # Verify attach command data
        attach_call = mock_queue_manager.enqueue_message.call_args
        attach_data = attach_call[1]["message_data"]
        assert attach_data["command_type"] == "ubuntu_pro_attach"
        assert attach_data["parameters"]["token"] == "test-token"

        # Reset mock
        mock_queue_manager.reset_mock()

        # Test service enable command structure
        enable_request = UbuntuProServiceRequest(service="esm-infra")
        await enable_ubuntu_pro_service(1, enable_request)

        # Verify enable command data
        enable_call = mock_queue_manager.enqueue_message.call_args
        enable_data = enable_call[1]["message_data"]
        assert enable_data["command_type"] == "ubuntu_pro_enable_service"
        assert enable_data["parameters"]["service"] == "esm-infra"
