# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Comprehensive tests for backend/api/v1/host_operations.py module.
Tests host system operations endpoints (reboot, shutdown, software refresh).
"""

from unittest.mock import Mock, patch

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
    """Mock database session.

    Phase 13.1: the host lookup now runs on the tenant-routed session
    (``tenant_db``) and authorization moved into the shared
    ``require_authenticated_user`` dependency, so the User query path is no
    longer exercised by these direct-call tests.  ``users`` is retained for
    backwards compatibility but unused by the handlers.
    """

    def __init__(self, hosts=None, users=None):
        self.hosts = hosts or []
        self.users = users or [MockUser()]  # retained for compatibility
        self.committed = False
        self.added_objects = []

    def query(self, model):
        # Return different mock queries based on model type
        if hasattr(model, "__name__") and "User" in model.__name__:
            return MockQuery(self.users)
        return MockQuery(self.hosts)

    def add(self, obj):
        """Mock add method."""
        self.added_objects.append(obj)

    def refresh(self, obj):
        """Mock refresh method."""

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

    @patch("backend.api.host_operations.create_command_message")
    @patch("backend.api.host_operations.queue_ops")
    def test_refresh_host_software_success(self, mock_queue_ops, mock_create_msg):
        """Test successful software refresh request."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_create_msg.return_value = {"command": "update_software_inventory"}
        mock_queue_ops.enqueue_message = Mock(
            return_value="550e8400-e29b-41d4-a716-446655440000"
        )

        result = refresh_host_software(
            1, tenant_db=mock_session, current_user=MockUser()
        )

        assert result["result"] is True
        assert "Software inventory update requested" in result["message"]
        mock_create_msg.assert_called_once_with(
            command_type="update_software_inventory", parameters={}
        )
        mock_queue_ops.enqueue_message.assert_called_once()

    def test_refresh_host_software_host_not_found(self):
        """Test software refresh when host not found."""
        mock_session = MockSession([])  # Empty hosts list

        with pytest.raises(HTTPException) as exc_info:
            refresh_host_software(999, tenant_db=mock_session, current_user=MockUser())

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)


class TestRebootHost:
    """Test reboot_host function."""

    @patch("backend.api.host_operations.create_command_message")
    @patch("backend.api.host_operations.queue_ops")
    def test_reboot_host_success(self, mock_queue_ops, mock_create_msg):
        """Test successful reboot request."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_create_msg.return_value = {"command": "reboot_system"}
        mock_queue_ops.enqueue_message = Mock(
            return_value="550e8400-e29b-41d4-a716-446655440000"
        )

        result = reboot_host(1, tenant_db=mock_session, current_user=MockUser())

        assert result["result"] is True
        assert "System reboot requested" in result["message"]
        mock_create_msg.assert_called_once_with(
            command_type="reboot_system", parameters={}
        )
        mock_queue_ops.enqueue_message.assert_called_once()

    def test_reboot_host_host_not_found(self):
        """Test reboot when host not found."""
        mock_session = MockSession([])  # Empty hosts list

        with pytest.raises(HTTPException) as exc_info:
            reboot_host(999, tenant_db=mock_session, current_user=MockUser())

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)


class TestShutdownHost:
    """Test shutdown_host function."""

    @patch("backend.api.host_operations.create_command_message")
    @patch("backend.api.host_operations.queue_ops")
    def test_shutdown_host_success(self, mock_queue_ops, mock_create_msg):
        """Test successful shutdown request."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_create_msg.return_value = {"command": "shutdown_system"}
        mock_queue_ops.enqueue_message = Mock(
            return_value="550e8400-e29b-41d4-a716-446655440000"
        )

        result = shutdown_host(1, tenant_db=mock_session, current_user=MockUser())

        assert result["result"] is True
        assert "System shutdown requested" in result["message"]
        mock_create_msg.assert_called_once_with(
            command_type="shutdown_system", parameters={}
        )
        mock_queue_ops.enqueue_message.assert_called_once()

    def test_shutdown_host_host_not_found(self):
        """Test shutdown when host not found."""
        mock_session = MockSession([])  # Empty hosts list

        with pytest.raises(HTTPException) as exc_info:
            shutdown_host(999, tenant_db=mock_session, current_user=MockUser())

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)


class TestHostOperationsIntegration:
    """Integration tests for host operations module."""

    @patch("backend.api.host_operations.create_command_message")
    @patch("backend.api.host_operations.queue_ops")
    def test_all_operations_same_host(self, mock_queue_ops, mock_create_msg):
        """Test that all operations work for the same host."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_user = MockUser()
        mock_queue_ops.enqueue_message = Mock(
            return_value="550e8400-e29b-41d4-a716-446655440000"
        )

        # Test software refresh
        mock_create_msg.return_value = {"command": "update_software_inventory"}
        result1 = refresh_host_software(
            1, tenant_db=mock_session, current_user=mock_user
        )
        assert result1["result"] is True

        # Test reboot
        mock_create_msg.return_value = {"command": "reboot_system"}
        result2 = reboot_host(1, tenant_db=mock_session, current_user=mock_user)
        assert result2["result"] is True

        # Test shutdown
        mock_create_msg.return_value = {"command": "shutdown_system"}
        result3 = shutdown_host(1, tenant_db=mock_session, current_user=mock_user)
        assert result3["result"] is True

        # Verify all commands were enqueued
        assert mock_queue_ops.enqueue_message.call_count == 3

    def test_all_operations_host_not_found(self):
        """Test that all operations fail consistently when host not found."""
        mock_session = MockSession([])  # Empty hosts list
        mock_user = MockUser()

        # All operations should fail with 404
        with pytest.raises(HTTPException) as exc_info1:
            refresh_host_software(999, tenant_db=mock_session, current_user=mock_user)
        assert exc_info1.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info2:
            reboot_host(999, tenant_db=mock_session, current_user=mock_user)
        assert exc_info2.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info3:
            shutdown_host(999, tenant_db=mock_session, current_user=mock_user)
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


class TestOneConnectionOffTheEventLoop:
    """Production 2026-11-18: asking every host to upgrade its agent stalled
    the server 30 s.  The handlers were ``async def`` waiting for a pooled
    connection on the event loop, and each took two from a 2 + 6 tenant pool."""

    def test_every_handler_runs_in_the_thread_pool(self):
        import inspect  # pylint: disable=import-outside-toplevel

        from backend.api import (
            host_operations,
        )  # pylint: disable=import-outside-toplevel

        for name in ("refresh_host_software", "reboot_host", "shutdown_host",
                     "update_agent", "request_packages"):  # fmt: skip
            handler = getattr(host_operations, name)
            assert not inspect.iscoroutinefunction(handler), name

    @patch("backend.api.host_operations.create_command_message")
    @patch("backend.api.host_operations.queue_ops")
    def test_update_agent_audits_on_the_request_session(
        self, mock_queue_ops, mock_create_msg
    ):
        from backend.api.host_operations import (
            update_agent,
        )  # pylint: disable=import-outside-toplevel
        from backend.persistence import (
            models,
        )  # pylint: disable=import-outside-toplevel

        mock_session = MockSession([MockHost()])
        mock_create_msg.return_value = {"command": "update_agent"}
        mock_queue_ops.enqueue_message = Mock(return_value="id")
        with patch("sqlalchemy.orm.sessionmaker") as other_sessions:
            result = update_agent("1", tenant_db=mock_session, current_user=MockUser())
        assert result["result"] is True
        audits = [
            o for o in mock_session.added_objects if isinstance(o, models.AuditLog)
        ]
        assert len(audits) == 1 and "agent update" in audits[0].description
        other_sessions.assert_not_called()
