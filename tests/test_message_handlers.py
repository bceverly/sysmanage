"""
Comprehensive tests for backend/api/message_handlers.py module.
Tests message handling functionality for SysManage server.
"""

import json
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
    """Mock WebSocket connection."""

    def __init__(self, agent_id="test-agent", hostname=None, host_id=None):
        self.agent_id = agent_id
        self.hostname = hostname
        self.host_id = host_id
        self.ipv4 = "192.168.1.100"
        self.ipv6 = "2001:db8::1"
        self.is_mock_connection = True
        self.messages_sent = []

    async def send_message(self, message):
        self.messages_sent.append(message)


class MockHost:
    """Mock host object."""

    def __init__(self, host_id=1, hostname="test-host", approval_status="approved"):
        self.id = host_id
        self.fqdn = hostname
        self.hostname = hostname
        self.approval_status = approval_status
        self.status = "down"
        self.active = False
        self.last_access = None
        self.platform = None
        self.is_agent_privileged = False
        self.script_execution_enabled = False
        self.enabled_shells = None
        self.diagnostics_request_status = None


class MockDB:
    """Mock database session."""

    def __init__(self):
        self.objects = {}
        self.committed = False
        self.flushed = False
        self.query_results = []

    def add(self, obj):
        self.objects[id(obj)] = obj

    def commit(self):
        self.committed = True

    def flush(self):
        self.flushed = True

    def refresh(self, obj):
        pass

    def execute(self, stmt):
        pass

    def query(self, model):
        return MockQuery(self.query_results)


class MockQuery:
    """Mock SQLAlchemy query."""

    def __init__(self, results):
        self.results = results

    def filter(self, *args):
        return self

    def first(self):
        return self.results[0] if self.results else None


class TestHandleSystemInfo:
    """Test handle_system_info function."""

    @pytest.mark.asyncio
    async def test_handle_system_info_no_hostname(self):
        """Test handling system info without hostname."""
        mock_db = MockDB()
        mock_connection = MockConnection()

        message_data = {"ipv4": "192.168.1.100", "platform": "Linux"}

        result = await handle_system_info(mock_db, mock_connection, message_data)

        # Should return None when no hostname provided
        assert result is None


class TestHandleHeartbeat:
    """Test handle_heartbeat function."""

    @pytest.mark.asyncio
    async def test_handle_heartbeat_mock_connection_no_hostname(self):
        """Test heartbeat with mock connection that has no hostname."""
        mock_db = MockDB()
        mock_connection = MockConnection(host_id="<Mock id='123'>")
        mock_connection.hostname = None

        message_data = {"message_id": "heartbeat-123"}

        result = await handle_heartbeat(mock_db, mock_connection, message_data)

        # Should handle mock connection specially
        assert result["message_type"] == "success"
        assert len(mock_connection.messages_sent) == 1
        assert mock_connection.messages_sent[0]["message_type"] == "ack"

    @pytest.mark.asyncio
    async def test_handle_heartbeat_existing_host(self):
        """Test heartbeat for existing host."""
        mock_db = MockDB()
        mock_connection = MockConnection(host_id=1, hostname="test-host")

        # Setup existing host
        mock_host = MockHost(host_id=1)
        mock_db.query_results = [mock_host]

        message_data = {
            "message_id": "heartbeat-456",
            "is_privileged": True,
            "enabled_shells": ["/bin/bash"],
        }

        result = await handle_heartbeat(mock_db, mock_connection, message_data)

        # Verify result
        assert result["message_type"] == "heartbeat_ack"
        assert "timestamp" in result

        # Verify host was updated
        assert mock_host.status == "up"
        assert mock_host.active is True
        assert mock_host.is_agent_privileged is True
        assert mock_db.committed is True

        # Verify ack was sent
        assert len(mock_connection.messages_sent) == 1
        assert mock_connection.messages_sent[0]["message_type"] == "ack"

    @pytest.mark.asyncio
    async def test_handle_heartbeat_host_not_found_create_new(self):
        """Test heartbeat when host not found, creates new host."""
        mock_db = MockDB()
        mock_connection = MockConnection(host_id=999, hostname="new-host")

        # No existing host found
        mock_db.query_results = []

        message_data = {
            "message_id": "heartbeat-789",
            "is_privileged": False,
            "enabled_shells": ["/bin/sh"],
        }

        result = await handle_heartbeat(mock_db, mock_connection, message_data)

        # Verify result
        assert result["message_type"] == "heartbeat_ack"

        # Verify new host was created and added to DB
        assert len(mock_db.objects) == 1
        assert mock_db.committed is True

    @pytest.mark.asyncio
    async def test_handle_heartbeat_no_host_id(self):
        """Test heartbeat without host_id."""
        mock_db = MockDB()
        mock_connection = MockConnection()
        mock_connection.host_id = None

        message_data = {"message_id": "heartbeat-error"}

        result = await handle_heartbeat(mock_db, mock_connection, message_data)

        # Should return error
        assert result["message_type"] == "error"
        assert "not registered" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_heartbeat_database_error(self):
        """Test heartbeat with database error."""
        mock_db = MockDB()
        mock_connection = MockConnection(host_id=1, hostname="test-host")

        # Make query raise an exception
        def failing_query(*args):
            raise Exception("Database error")

        mock_db.query = failing_query

        message_data = {"message_id": "heartbeat-fail"}

        result = await handle_heartbeat(mock_db, mock_connection, message_data)

        # Should return error
        assert result["message_type"] == "error"
        assert "Failed to process heartbeat" in result["error"]


class TestHandleCommandResult:
    """Test handle_command_result function."""

    @pytest.mark.asyncio
    async def test_handle_command_result_regular_command(self):
        """Test command result for regular command."""
        mock_connection = MockConnection(hostname="test-host")

        message_data = {"command": "system_info", "status": "success"}

        result = await handle_command_result(mock_connection, message_data)

        # Should return regular command ack
        assert result["message_type"] == "command_result_ack"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_handle_command_result_no_hostname(self):
        """Test command result without hostname."""
        mock_connection = MockConnection()
        mock_connection.hostname = None

        message_data = {"command": "test", "status": "success"}

        result = await handle_command_result(mock_connection, message_data)

        assert result["message_type"] == "command_result_ack"


class TestHandleConfigAcknowledgment:
    """Test handle_config_acknowledgment function."""

    @pytest.mark.asyncio
    async def test_handle_config_acknowledgment_success(self):
        """Test successful config acknowledgment."""
        mock_connection = MockConnection(hostname="test-host")

        message_data = {"status": "applied", "config_version": 1}

        result = await handle_config_acknowledgment(mock_connection, message_data)

        assert result["message_type"] == "config_ack_received"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_handle_config_acknowledgment_failure(self):
        """Test failed config acknowledgment."""
        mock_connection = MockConnection(hostname="test-host")

        message_data = {"status": "failed", "error": "Invalid configuration"}

        result = await handle_config_acknowledgment(mock_connection, message_data)

        assert result["message_type"] == "config_ack_received"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_handle_config_acknowledgment_no_status(self):
        """Test config acknowledgment without status."""
        mock_connection = MockConnection(hostname="test-host")

        message_data = {"config_version": 2}

        result = await handle_config_acknowledgment(mock_connection, message_data)

        assert result["message_type"] == "config_ack_received"


class TestHandleDiagnosticResult:
    """Test handle_diagnostic_result function."""


class TestMessageHandlersIntegration:
    """Integration tests for message handlers."""

    def test_json_serialization_in_handlers(self):
        """Test JSON serialization used in handlers."""
        # Test enabled shells serialization
        enabled_shells = ["/bin/bash", "/bin/sh", "/usr/bin/zsh"]
        json_str = json.dumps(enabled_shells)
        parsed = json.loads(json_str)

        assert parsed == enabled_shells

        # Test empty shells
        empty_shells = []
        json_str = json.dumps(empty_shells)
        parsed = json.loads(json_str)

        assert parsed == []

    def test_datetime_handling(self):
        """Test datetime handling in handlers."""
        now = datetime.now(timezone.utc)
        iso_string = now.isoformat()

        # Should be valid ISO format
        parsed = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None

    @pytest.mark.asyncio
    async def test_message_data_validation(self):
        """Test message data validation patterns."""
        mock_connection = MockConnection(hostname="test-host")

        # Test various message data formats
        test_cases = [
            {"status": "success"},
            {"status": "failed", "error": "Test error"},
            {"execution_id": "exec-123", "exit_code": 0},
            {},  # Empty message data
        ]

        for message_data in test_cases:
            # Should not raise exceptions
            result = await handle_config_acknowledgment(mock_connection, message_data)
            assert result["message_type"] == "config_ack_received"
