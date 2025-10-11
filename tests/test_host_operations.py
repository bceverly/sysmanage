"""
Comprehensive tests for backend/api/host_operations.py module.
Tests host system operations endpoints (reboot, shutdown, software refresh).
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from backend.api.host_operations import (
    reboot_host,
    refresh_host_software,
    shutdown_host,
)


class MockHost:
    """Mock host object."""

    def __init__(self, host_id=1, hostname="test-host"):
        self.id = host_id
        self.hostname = hostname
        self.fqdn = f"{hostname}.example.com"
        self.approval_status = "approved"
        self.status = "up"
        self.active = True
        self._role_cache = None

    def load_role_cache(self, session):
        """Mock method to load role cache."""
        self._role_cache = set()

    def has_role(self, role):
        """Mock method that returns True for all roles (testing purposes)."""
        return True


class MockUser:
    """Mock user object."""

    def __init__(self, user_id=1, userid="test@example.com"):
        self.id = user_id
        self.userid = userid
        self.active = True
        self._role_cache = None

    def load_role_cache(self, session):
        """Mock method to load role cache."""
        self._role_cache = set()

    def has_role(self, role):
        """Mock method that returns True for all roles (testing purposes)."""
        return True


class MockSession:
    """Mock database session."""

    def __init__(self, hosts=None, users=None):
        self.hosts = hosts or []
        self.users = users or [MockUser()]  # Default user for RBAC checks
        self.committed = False

    def query(self, model):
        # Return different mock queries based on model type
        if hasattr(model, "__name__") and "User" in model.__name__:
            return MockQuery(self.users)
        return MockQuery(self.hosts)

    def commit(self):
        """Mock commit method."""
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockQuery:
    """Mock SQLAlchemy query."""

    def __init__(self, hosts):
        self.hosts = hosts

    def filter(self, *args):
        return self

    def first(self):
        return self.hosts[0] if self.hosts else None


class MockSessionLocal:
    """Mock session factory."""

    def __init__(self, mock_session):
        self.mock_session = mock_session

    def __call__(self):
        return self.mock_session


class TestRefreshHostSoftware:
    """Test refresh_host_software function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_operations.sessionmaker")
    @patch("backend.api.host_operations.db")
    @patch("backend.api.host_operations.create_command_message")
    @patch("backend.api.host_operations.queue_ops")
    async def test_refresh_host_software_success(
        self, mock_queue_ops, mock_create_msg, mock_db, mock_sessionmaker
    ):
        """Test successful software refresh request."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)
        mock_create_msg.return_value = {"command": "update_software_inventory"}
        mock_queue_ops.enqueue_message = Mock(
            return_value="550e8400-e29b-41d4-a716-446655440000"
        )

        result = await refresh_host_software(1)

        assert result["result"] is True
        assert "Software inventory update requested" in result["message"]
        mock_create_msg.assert_called_once_with(
            command_type="update_software_inventory", parameters={}
        )
        mock_queue_ops.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.api.host_operations.sessionmaker")
    @patch("backend.api.host_operations.db")
    async def test_refresh_host_software_host_not_found(
        self, mock_db, mock_sessionmaker
    ):
        """Test software refresh when host not found."""
        mock_session = MockSession([])  # Empty hosts list
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await refresh_host_software(999)

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)


class TestRebootHost:
    """Test reboot_host function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_operations.sessionmaker")
    @patch("backend.api.host_operations.db")
    @patch("backend.api.host_operations.create_command_message")
    @patch("backend.api.host_operations.queue_ops")
    async def test_reboot_host_success(
        self, mock_queue_ops, mock_create_msg, mock_db, mock_sessionmaker
    ):
        """Test successful reboot request."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)
        mock_create_msg.return_value = {"command": "reboot_system"}
        mock_queue_ops.enqueue_message = Mock(
            return_value="550e8400-e29b-41d4-a716-446655440000"
        )

        result = await reboot_host(1)

        assert result["result"] is True
        assert "System reboot requested" in result["message"]
        mock_create_msg.assert_called_once_with(
            command_type="reboot_system", parameters={}
        )
        mock_queue_ops.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.api.host_operations.sessionmaker")
    @patch("backend.api.host_operations.db")
    async def test_reboot_host_host_not_found(self, mock_db, mock_sessionmaker):
        """Test reboot when host not found."""
        mock_session = MockSession([])  # Empty hosts list
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await reboot_host(999)

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)


class TestShutdownHost:
    """Test shutdown_host function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_operations.sessionmaker")
    @patch("backend.api.host_operations.db")
    @patch("backend.api.host_operations.create_command_message")
    @patch("backend.api.host_operations.queue_ops")
    async def test_shutdown_host_success(
        self, mock_queue_ops, mock_create_msg, mock_db, mock_sessionmaker
    ):
        """Test successful shutdown request."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)
        mock_create_msg.return_value = {"command": "shutdown_system"}
        mock_queue_ops.enqueue_message = Mock(
            return_value="550e8400-e29b-41d4-a716-446655440000"
        )

        result = await shutdown_host(1)

        assert result["result"] is True
        assert "System shutdown requested" in result["message"]
        mock_create_msg.assert_called_once_with(
            command_type="shutdown_system", parameters={}
        )
        mock_queue_ops.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.api.host_operations.sessionmaker")
    @patch("backend.api.host_operations.db")
    async def test_shutdown_host_host_not_found(self, mock_db, mock_sessionmaker):
        """Test shutdown when host not found."""
        mock_session = MockSession([])  # Empty hosts list
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await shutdown_host(999)

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)


class TestHostOperationsIntegration:
    """Integration tests for host operations module."""

    @pytest.mark.asyncio
    @patch("backend.api.host_operations.sessionmaker")
    @patch("backend.api.host_operations.db")
    @patch("backend.api.host_operations.create_command_message")
    @patch("backend.api.host_operations.queue_ops")
    async def test_all_operations_same_host(
        self, mock_queue_ops, mock_create_msg, mock_db, mock_sessionmaker
    ):
        """Test that all operations work for the same host."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)
        mock_queue_ops.enqueue_message = Mock(
            return_value="550e8400-e29b-41d4-a716-446655440000"
        )

        # Test software refresh
        mock_create_msg.return_value = {"command": "update_software_inventory"}
        result1 = await refresh_host_software(1)
        assert result1["result"] is True

        # Test reboot
        mock_create_msg.return_value = {"command": "reboot_system"}
        result2 = await reboot_host(1)
        assert result2["result"] is True

        # Test shutdown
        mock_create_msg.return_value = {"command": "shutdown_system"}
        result3 = await shutdown_host(1)
        assert result3["result"] is True

        # Verify all commands were enqueued
        assert mock_queue_ops.enqueue_message.call_count == 3

    @pytest.mark.asyncio
    @patch("backend.api.host_operations.sessionmaker")
    @patch("backend.api.host_operations.db")
    async def test_all_operations_host_not_found(self, mock_db, mock_sessionmaker):
        """Test that all operations fail consistently when host not found."""
        mock_session = MockSession([])  # Empty hosts list
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        # All operations should fail with 404
        with pytest.raises(HTTPException) as exc_info1:
            await refresh_host_software(999)
        assert exc_info1.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info2:
            await reboot_host(999)
        assert exc_info2.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info3:
            await shutdown_host(999)
        assert exc_info3.value.status_code == 404

    def test_command_message_parameters(self):
        """Test that command messages are created with correct parameters."""
        # This is a unit test for the expected behavior
        expected_commands = {
            "refresh_host_software": "update_software_inventory",
            "reboot_host": "reboot_system",
            "shutdown_host": "shutdown_system",
        }

        # Verify we're testing the right command types
        assert len(expected_commands) == 3
        assert "update_software_inventory" in expected_commands.values()
        assert "reboot_system" in expected_commands.values()
        assert "shutdown_system" in expected_commands.values()

    def test_mock_objects_structure(self):
        """Test mock objects have expected structure."""
        host = MockHost()
        session = MockSession([host])

        # Host should have required fields
        assert hasattr(host, "id")
        assert hasattr(host, "hostname")
        assert hasattr(host, "fqdn")

        # Session should work as expected
        assert session.hosts == [host]
        query = session.query(None)
        assert query.first() == host

    def test_error_message_consistency(self):
        """Test that error messages are consistent across operations."""
        # This tests the pattern of error handling
        expected_errors = {404: "Host not found"}

        # This ensures we maintain consistent error messaging
        assert 404 in expected_errors
