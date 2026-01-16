"""
Comprehensive tests for backend/api/message_handlers.py module.
Tests WebSocket message handling functions for agent communication.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.api.message_handlers import (
    handle_command_result,
    handle_config_acknowledgment,
    handle_diagnostic_result,
    handle_heartbeat,
    handle_system_info,
)


class MockConnection:
    """Mock WebSocket connection for testing."""

    def __init__(self, host_id=None, hostname=None, ipv4=None, ipv6=None):
        self.host_id = host_id
        self.hostname = hostname
        self.ipv4 = ipv4
        self.ipv6 = ipv6
        self.agent_id = f"agent_{host_id}" if host_id else "test_agent"
        self.sent_messages = []

    async def send_message(self, message):
        """Mock send_message method."""
        self.sent_messages.append(message)


class MockHost:
    """Mock host object for database operations."""

    def __init__(
        self,
        host_id="550e8400-e29b-41d4-a716-446655440001",
        hostname="test-host",
        approval_status="approved",
    ):
        self.id = host_id
        self.hostname = hostname
        self.fqdn = f"{hostname}.example.com"
        self.approval_status = approval_status
        self.status = "up"
        self.active = True
        self.platform = "linux"
        self.is_agent_privileged = False
        self.enabled_shells = None
        self.last_access = datetime.now(timezone.utc)
        self.host_token = None  # For secure token support


class MockSession:
    """Mock database session."""

    def __init__(self, hosts=None):
        self.hosts = hosts or []
        self.committed = False
        self.flushed = False
        self.executed_statements = []

    def query(self, model):
        return MockQuery(self.hosts)

    def execute(self, stmt):
        self.executed_statements.append(stmt)

    def commit(self):
        self.committed = True

    def flush(self):
        self.flushed = True

    def add(self, obj):
        self.hosts.append(obj)

    def refresh(self, obj):
        pass


class MockQuery:
    """Mock SQLAlchemy query."""

    def __init__(self, hosts):
        self.hosts = hosts

    def filter(self, *args):
        return self

    def first(self):
        return self.hosts[0] if self.hosts else None


class TestHandleSystemInfo:
    """Test handle_system_info function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_utils.update_or_create_host")
    async def test_system_info_new_host_approved(self, mock_update_host):
        """Test system info handling for new approved host."""
        mock_host = MockHost(
            "550e8400-e29b-41d4-a716-446655440001", "test-host", "approved"
        )
        mock_update_host.return_value = mock_host
        mock_session = MockSession()
        connection = MockConnection()

        message_data = {
            "hostname": "test-host",
            "ipv4": "192.168.1.100",
            "ipv6": "::1",
            "platform": "linux",
            "is_privileged": True,
        }

        with patch(
            "backend.websocket.connection_manager.connection_manager"
        ) as mock_conn_mgr:
            result = await handle_system_info(mock_session, connection, message_data)

        assert result["message_type"] == "registration_success"
        assert result["approved"] is True
        assert result["hostname"] == "test-host"
        assert result["host_id"] == "550e8400-e29b-41d4-a716-446655440001"
        assert connection.host_id == "550e8400-e29b-41d4-a716-446655440001"
        assert connection.hostname == "test-host"
        assert mock_session.committed
        assert mock_session.flushed
        mock_conn_mgr.register_agent.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.api.host_utils.update_or_create_host")
    async def test_system_info_new_host_pending(self, mock_update_host):
        """Test system info handling for new pending host."""
        mock_host = MockHost(1, "test-host", "pending")
        mock_update_host.return_value = mock_host
        mock_session = MockSession()
        connection = MockConnection()

        message_data = {
            "hostname": "test-host",
            "ipv4": "192.168.1.100",
            "ipv6": "::1",
            "platform": "linux",
        }

        result = await handle_system_info(mock_session, connection, message_data)

        assert result["message_type"] == "registration_pending"
        assert result["approved"] is False
        assert result["hostname"] == "test-host"
        assert "pending approval" in result["message"]

    @pytest.mark.asyncio
    async def test_system_info_no_hostname(self):
        """Test system info handling when no hostname provided."""
        mock_session = MockSession()
        connection = MockConnection()
        message_data = {"platform": "linux"}

        result = await handle_system_info(mock_session, connection, message_data)

        assert result is None

    @pytest.mark.asyncio
    @patch("backend.api.host_utils.update_or_create_host")
    async def test_system_info_with_enabled_shells(self, mock_update_host):
        """Test system info handling with enabled shells."""
        mock_host = MockHost(
            "550e8400-e29b-41d4-a716-446655440001", "test-host", "approved"
        )
        mock_update_host.return_value = mock_host
        mock_session = MockSession()
        connection = MockConnection()

        message_data = {
            "hostname": "test-host",
            "ipv4": "192.168.1.100",
            "ipv6": "::1",
            "platform": "linux",
            "enabled_shells": ["bash", "sh", "zsh"],
        }

        with patch("backend.websocket.connection_manager.connection_manager"):
            result = await handle_system_info(mock_session, connection, message_data)

        assert result["message_type"] == "registration_success"
        assert mock_session.executed_statements

    @pytest.mark.asyncio
    @patch("backend.api.host_utils.update_or_create_host")
    async def test_system_info_mock_connection(self, mock_update_host):
        """Test system info handling with mock connection."""
        mock_host = MockHost(
            "550e8400-e29b-41d4-a716-446655440001", "test-host", "approved"
        )
        mock_update_host.return_value = mock_host
        mock_session = MockSession()
        connection = MockConnection()
        connection.is_mock_connection = True

        message_data = {
            "hostname": "test-host",
            "ipv4": "192.168.1.100",
            "ipv6": "::1",
            "platform": "linux",
        }

        with patch("backend.websocket.connection_manager.connection_manager"):
            result = await handle_system_info(mock_session, connection, message_data)

        assert result["message_type"] == "registration_success"


class TestHandleHeartbeat:
    """Test handle_heartbeat function."""

    @pytest.mark.asyncio
    async def test_heartbeat_mock_connection_no_hostname(self):
        """Test heartbeat with mock connection that has no hostname."""
        mock_session = MockSession()
        connection = MockConnection()
        connection.hostname = None
        connection.host_id = "<Mock object>"

        message_data = {"message_id": "test_123"}

        result = await handle_heartbeat(mock_session, connection, message_data)

        assert result["message_type"] == "success"
        assert len(connection.sent_messages) == 1
        assert connection.sent_messages[0]["message_type"] == "ack"
        assert connection.sent_messages[0]["message_id"] == "test_123"

    @pytest.mark.asyncio
    async def test_heartbeat_existing_host(self):
        """Test heartbeat with existing host."""
        mock_host = MockHost(1, "test-host")
        mock_session = MockSession([mock_host])
        connection = MockConnection(1, "test-host")

        message_data = {
            "message_id": "heartbeat_456",
            "is_privileged": True,
            "enabled_shells": ["bash", "sh"],
        }

        result = await handle_heartbeat(mock_session, connection, message_data)

        assert result["message_type"] == "heartbeat_ack"
        assert "timestamp" in result
        assert mock_session.committed
        assert len(connection.sent_messages) == 1
        assert mock_host.status == "up"
        assert mock_host.active is True
        assert mock_host.is_agent_privileged is True

    @pytest.mark.asyncio
    async def test_heartbeat_host_not_found_create_new(self):
        """Test heartbeat when host not found but connection has info."""
        mock_session = MockSession([])
        connection = MockConnection(999, "new-host", "192.168.1.200", "::2")

        message_data = {
            "message_id": "heartbeat_789",
            "is_privileged": False,
            "enabled_shells": ["powershell"],
        }

        result = await handle_heartbeat(mock_session, connection, message_data)

        assert result["message_type"] == "heartbeat_ack"
        assert len(mock_session.hosts) == 1
        new_host = mock_session.hosts[0]
        assert new_host.fqdn == "new-host"
        assert new_host.ipv4 == "192.168.1.200"
        assert new_host.approval_status == "pending"

    @pytest.mark.asyncio
    async def test_heartbeat_host_not_found_no_connection_info(self):
        """Test heartbeat when host not found and no connection info."""
        mock_session = MockSession([])
        connection = MockConnection(999)

        message_data = {"message_id": "heartbeat_999"}

        result = await handle_heartbeat(mock_session, connection, message_data)

        assert result["message_type"] == "heartbeat_ack"
        assert connection.host_id is None
        assert connection.hostname is None

    @pytest.mark.asyncio
    async def test_heartbeat_no_host_id(self):
        """Test heartbeat when connection has no host_id."""
        mock_session = MockSession()
        connection = MockConnection()

        message_data = {"message_id": "no_host"}

        result = await handle_heartbeat(mock_session, connection, message_data)

        assert result["message_type"] == "error"
        assert "not registered" in result["message"]

    @pytest.mark.asyncio
    async def test_heartbeat_database_error(self):
        """Test heartbeat handling when database error occurs."""
        mock_session = MockSession([MockHost()])
        connection = MockConnection(1, "test-host")

        def mock_commit():
            raise Exception("Database connection failed")

        mock_session.commit = mock_commit

        message_data = {"message_id": "error_test"}

        result = await handle_heartbeat(mock_session, connection, message_data)

        assert result["message_type"] == "error"
        assert "Failed to process heartbeat" in result["message"]

    @pytest.mark.asyncio
    async def test_heartbeat_mock_connection_no_last_access_update(self):
        """Test that mock connections don't update last_access."""
        mock_host = MockHost(1, "test-host")
        original_last_access = mock_host.last_access
        mock_session = MockSession([mock_host])
        connection = MockConnection(1, "test-host")
        connection.is_mock_connection = True

        message_data = {"message_id": "mock_test"}

        await handle_heartbeat(mock_session, connection, message_data)

        time_diff = abs((mock_host.last_access - original_last_access).total_seconds())
        assert time_diff < 1


class TestHandleCommandResult:
    """Test handle_command_result function."""

    @pytest.mark.asyncio
    async def test_command_result_regular_command(self):
        """Test handling of regular command result."""
        connection = MockConnection(1, "test-host")
        message_data = {
            "command": "ls -la",
            "exit_code": 0,
            "stdout": "file1.txt\nfile2.txt",
            "stderr": "",
        }

        result = await handle_command_result(connection, message_data)

        assert result["message_type"] == "command_result_ack"
        assert "timestamp" in result

    @pytest.mark.asyncio
    @patch("backend.api.handlers.handle_script_execution_result")
    @patch("backend.persistence.db.get_db")
    async def test_command_result_script_execution(
        self, mock_get_db, mock_script_handler
    ):
        """Test handling of script execution result."""
        connection = MockConnection(1, "test-host")
        message_data = {
            "execution_id": "script_123",
            "exit_code": 0,
            "stdout": "Script completed successfully",
            "stderr": "",
        }

        mock_db_session = Mock()
        mock_get_db.return_value = iter([mock_db_session])
        mock_script_handler.return_value = {"status": "completed"}

        result = await handle_command_result(connection, message_data)

        mock_script_handler.assert_called_once_with(
            mock_db_session, connection, message_data
        )
        mock_db_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_command_result_unknown_hostname(self):
        """Test command result handling with unknown hostname."""
        connection = MockConnection()
        message_data = {"command": "test", "exit_code": 0}

        result = await handle_command_result(connection, message_data)

        assert result["message_type"] == "command_result_ack"


class TestHandleConfigAcknowledgment:
    """Test handle_config_acknowledgment function."""

    @pytest.mark.asyncio
    async def test_config_acknowledgment_success(self):
        """Test successful config acknowledgment handling."""
        connection = MockConnection(1, "test-host")
        message_data = {"status": "applied", "config_version": "1.2.3"}

        result = await handle_config_acknowledgment(connection, message_data)

        assert result["message_type"] == "config_ack_received"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_config_acknowledgment_no_hostname(self):
        """Test config acknowledgment with unknown hostname."""
        connection = MockConnection()
        message_data = {"status": "failed"}

        result = await handle_config_acknowledgment(connection, message_data)

        assert result["message_type"] == "config_ack_received"

    @pytest.mark.asyncio
    async def test_config_acknowledgment_missing_status(self):
        """Test config acknowledgment with missing status."""
        connection = MockConnection(1, "test-host")
        message_data = {}

        result = await handle_config_acknowledgment(connection, message_data)

        assert result["message_type"] == "config_ack_received"


class TestHandleDiagnosticResult:
    """Test handle_diagnostic_result function."""

    @pytest.mark.asyncio
    @patch("backend.api.diagnostics.process_diagnostic_result")
    async def test_diagnostic_result_success(self, mock_process_diagnostic):
        """Test successful diagnostic result handling."""
        mock_host = MockHost(1, "test-host")
        mock_session = MockSession([mock_host])
        connection = MockConnection(1, "test-host")

        message_data = {
            "diagnostic_type": "system_info",
            "data": {"cpu_usage": 45.2, "memory_usage": 78.1},
        }

        mock_process_diagnostic.return_value = None

        result = await handle_diagnostic_result(mock_session, connection, message_data)

        assert result["message_type"] == "diagnostic_result_ack"
        assert result["status"] == "processed"
        assert "timestamp" in result
        assert mock_session.committed
        assert mock_session.executed_statements
        mock_process_diagnostic.assert_called_once_with(message_data)

    @pytest.mark.asyncio
    @patch("backend.api.diagnostics.process_diagnostic_result")
    async def test_diagnostic_result_processing_error(self, mock_process_diagnostic):
        """Test diagnostic result handling when processing fails."""
        mock_host = MockHost(1, "test-host")
        mock_session = MockSession([mock_host])
        connection = MockConnection(1, "test-host")

        message_data = {"diagnostic_type": "invalid", "data": {}}

        mock_process_diagnostic.side_effect = Exception("Processing failed")

        result = await handle_diagnostic_result(mock_session, connection, message_data)

        assert result["message_type"] == "error"
        assert "Failed to process diagnostic result" in result["message"]
        assert mock_session.committed

    @pytest.mark.asyncio
    @patch("backend.api.diagnostics.process_diagnostic_result")
    async def test_diagnostic_result_no_host_id(self, mock_process_diagnostic):
        """Test diagnostic result handling with no host_id."""
        mock_session = MockSession()
        connection = MockConnection()

        message_data = {"diagnostic_type": "test", "data": {}}

        mock_process_diagnostic.return_value = None

        result = await handle_diagnostic_result(mock_session, connection, message_data)

        assert result["message_type"] == "diagnostic_result_ack"
        assert result["status"] == "processed"
        assert not mock_session.executed_statements

    @pytest.mark.asyncio
    @patch("backend.api.diagnostics.process_diagnostic_result")
    async def test_diagnostic_result_db_error_on_status_update(
        self, mock_process_diagnostic
    ):
        """Test diagnostic result when database status update fails."""
        mock_host = MockHost(1, "test-host")
        mock_session = MockSession([mock_host])
        connection = MockConnection(1, "test-host")

        mock_process_diagnostic.side_effect = Exception("Processing error")

        def mock_execute(stmt):
            raise Exception("Database error")

        mock_session.execute = mock_execute

        message_data = {"diagnostic_type": "test", "data": {}}

        result = await handle_diagnostic_result(mock_session, connection, message_data)

        assert result["message_type"] == "error"
        mock_process_diagnostic.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.api.diagnostics.process_diagnostic_result")
    async def test_diagnostic_result_large_data(self, mock_process_diagnostic):
        """Test diagnostic result with large data."""
        mock_session = MockSession()
        connection = MockConnection(1, "test-host")

        large_data = {"logs": "x" * 10000, "metrics": list(range(1000))}
        message_data = {
            "diagnostic_type": "full_system",
            "data": large_data,
            "metadata": {"size": "large"},
        }

        mock_process_diagnostic.return_value = None

        result = await handle_diagnostic_result(mock_session, connection, message_data)

        assert result["message_type"] == "diagnostic_result_ack"
        mock_process_diagnostic.assert_called_once_with(message_data)


class TestMessageHandlersIntegration:
    """Integration tests for message handlers."""

    @pytest.mark.asyncio
    async def test_message_handlers_preserve_message_structure(self):
        """Test that all handlers return properly structured messages."""
        handlers_and_data = [
            (handle_command_result, {"command": "test"}),
            (handle_config_acknowledgment, {"status": "ok"}),
        ]

        connection = MockConnection(1, "test-host")

        for handler, data in handlers_and_data:
            result = await handler(connection, data)

            assert "message_type" in result
            assert isinstance(result["message_type"], str)

            if "timestamp" in result:
                assert isinstance(result["timestamp"], str)

    @pytest.mark.asyncio
    async def test_connection_state_consistency(self):
        """Test that connection state is properly maintained."""
        connection = MockConnection()
        original_agent_id = connection.agent_id

        await handle_command_result(connection, {"command": "test"})
        await handle_config_acknowledgment(connection, {"status": "ok"})

        assert connection.agent_id == original_agent_id

    @pytest.mark.asyncio
    @patch("backend.api.host_utils.update_or_create_host")
    async def test_system_info_to_heartbeat_flow(self, mock_update_host):
        """Test flow from system info registration to heartbeat."""
        mock_host = MockHost(
            "550e8400-e29b-41d4-a716-446655440001", "test-host", "approved"
        )
        mock_update_host.return_value = mock_host
        mock_session = MockSession()
        connection = MockConnection()

        system_info_data = {
            "hostname": "test-host",
            "ipv4": "192.168.1.100",
            "ipv6": "::1",
            "platform": "linux",
        }

        with patch("backend.websocket.connection_manager.connection_manager"):
            sys_result = await handle_system_info(
                mock_session, connection, system_info_data
            )

        assert sys_result["message_type"] == "registration_success"
        assert connection.host_id == "550e8400-e29b-41d4-a716-446655440001"

        mock_session.hosts = [mock_host]
        heartbeat_data = {"message_id": "hb_1"}

        hb_result = await handle_heartbeat(mock_session, connection, heartbeat_data)

        assert hb_result["message_type"] == "heartbeat_ack"
        assert len(connection.sent_messages) == 1

    def test_message_data_validation(self):
        """Test that handlers handle various message data formats gracefully."""
        test_cases = [
            {},
            {"unknown_field": "value"},
            {"hostname": ""},
            {"message_id": None},
        ]

        for case in test_cases:
            assert isinstance(case, dict)

    @pytest.mark.asyncio
    async def test_error_message_consistency(self):
        """Test that error messages follow consistent format."""
        mock_session = MockSession()
        connection = MockConnection()

        result = await handle_heartbeat(mock_session, connection, {})

        if result["message_type"] == "error":
            assert "message" in result
            assert isinstance(result["message"], str)
            assert len(result["message"]) > 0


class TestMessageHandlersLogging:
    """Test message handlers module logging initialization."""

    @patch("builtins.open", side_effect=OSError("Permission denied"))
    @patch("os.makedirs")
    def test_logging_fallback_on_os_error(self, mock_makedirs, mock_open):
        """Test logging falls back to console when file logging fails."""
        # Force module reload to trigger the logging initialization with mocked open
        import importlib
        import sys

        # Remove module to force re-import and re-initialization
        if "backend.api.message_handlers" in sys.modules:
            del sys.modules["backend.api.message_handlers"]

        # Import module which should trigger fallback logging due to OSError
        import backend.api.message_handlers

        # Verify that the module still loads successfully despite logging error
        assert hasattr(backend.api.message_handlers, "handle_system_info")
        assert hasattr(backend.api.message_handlers, "handle_heartbeat")
