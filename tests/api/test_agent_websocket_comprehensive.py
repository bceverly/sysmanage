"""
Simplified comprehensive tests for agent WebSocket functionality.
Tests core WebSocket message processing with correct mocking.
"""

import json
from unittest.mock import AsyncMock, Mock, patch
import pytest

from backend.api.agent import (
    _process_websocket_message,
    _handle_message_by_type,
    _handle_script_execution_result,
)
from backend.websocket.messages import MessageType


class TestWebSocketMessageProcessing:
    """Test WebSocket message processing."""

    @pytest.fixture
    def mock_connection(self):
        connection = Mock()
        connection.agent_id = "test-agent-123"
        connection.send_message = AsyncMock()
        return connection

    @pytest.fixture
    def mock_db(self):
        return Mock()

    @pytest.mark.asyncio
    async def test_process_websocket_message_valid_json(self, mock_connection, mock_db):
        """Test processing valid JSON message."""
        valid_message = {
            "message_type": "heartbeat",
            "message_id": "msg-123",
            "data": {"status": "online"},
        }

        with patch("backend.api.agent.websocket_security") as mock_security, patch(
            "backend.api.agent._handle_message_by_type"
        ) as mock_handle:

            mock_security.validate_message_integrity.return_value = True
            mock_handle.return_value = None

            await _process_websocket_message(
                json.dumps(valid_message), mock_connection, mock_db, "connection-123"
            )

            mock_handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_websocket_message_invalid_json(
        self, mock_connection, mock_db
    ):
        """Test processing invalid JSON."""
        invalid_json = "{ invalid json"

        await _process_websocket_message(
            invalid_json, mock_connection, mock_db, "connection-123"
        )

        # Should send error message
        mock_connection.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_websocket_message_security_validation_fails(
        self, mock_connection, mock_db
    ):
        """Test processing when security validation fails."""
        valid_message = {"message_type": "heartbeat", "data": {"status": "online"}}

        with patch("backend.api.agent.websocket_security") as mock_security:
            mock_security.validate_message_integrity.return_value = False

            await _process_websocket_message(
                json.dumps(valid_message), mock_connection, mock_db, "connection-123"
            )

            # Should send error message
            mock_connection.send_message.assert_called_once()


class TestMessageTypeHandling:
    """Test message type handling."""

    @pytest.fixture
    def mock_connection(self):
        connection = Mock()
        connection.agent_id = "test-agent-123"
        connection.send_message = AsyncMock()
        return connection

    @pytest.fixture
    def mock_db(self):
        return Mock()

    @pytest.mark.asyncio
    async def test_handle_heartbeat_message(self, mock_connection, mock_db):
        """Test handling heartbeat message."""
        message = Mock()
        message.message_type = MessageType.HEARTBEAT
        message.data = {"status": "online"}

        await _handle_message_by_type(message, mock_connection, mock_db)

        # Heartbeat should be handled without error
        # No specific assertions needed for heartbeat

    @pytest.mark.asyncio
    async def test_handle_system_info_message(self, mock_connection, mock_db):
        """Test handling system info message."""
        message = Mock()
        message.message_type = MessageType.SYSTEM_INFO
        message.data = {
            "hostname": "test-host.example.com",
            "os_name": "Ubuntu",
            "os_version": "22.04",
        }

        # System info messages should be handled without error
        await _handle_message_by_type(message, mock_connection, mock_db)

    @pytest.mark.asyncio
    async def test_handle_command_result_message(self, mock_connection, mock_db):
        """Test that command result messages are NOT handled by _handle_message_by_type.

        COMMAND_RESULT messages should be queued, not handled directly.
        This test verifies that passing one to _handle_message_by_type logs a warning.
        """
        message = Mock()
        message.message_type = MessageType.COMMAND_RESULT
        message.data = {
            "command_id": "cmd-123",
            "exit_code": 0,
            "output": "Command executed successfully",
        }

        with patch("backend.api.agent.logger") as mock_logger:
            await _handle_message_by_type(message, mock_connection, mock_db)

            # Should log a warning about unexpected message type
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args[0][0]
            assert "Unexpected message type" in warning_call

    @pytest.mark.asyncio
    async def test_handle_script_execution_result_message(
        self, mock_connection, mock_db
    ):
        """Test handling script execution result message."""
        message = Mock()
        message.message_type = MessageType.SCRIPT_EXECUTION_RESULT
        message.data = {
            "execution_id": "exec-123",
            "exit_code": 0,
            "output": "Script executed successfully",
        }

        with patch("backend.api.agent._validate_and_get_host") as mock_validate:
            mock_validate.return_value = (Mock(), None)

            await _handle_message_by_type(message, mock_connection, mock_db)

            # Should handle without error

    @pytest.mark.asyncio
    async def test_handle_unknown_message_type(self, mock_connection, mock_db):
        """Test handling unknown message type."""
        message = Mock()
        message.message_type = "unknown_type"
        message.data = {}

        # Should handle gracefully without error
        await _handle_message_by_type(message, mock_connection, mock_db)


class TestScriptExecutionResultHandling:
    """Test script execution result handling."""

    @pytest.fixture
    def mock_connection(self):
        connection = Mock()
        connection.agent_id = "test-agent-123"
        connection.send_message = AsyncMock()
        return connection

    @pytest.fixture
    def mock_db(self):
        return Mock()

    @pytest.mark.asyncio
    async def test_handle_script_execution_result_success(
        self, mock_connection, mock_db
    ):
        """Test successful script execution result handling."""
        message = Mock()
        message.data = {
            "execution_id": "exec-123",
            "exit_code": 0,
            "output": "Script completed successfully",
        }

        with patch("backend.api.agent._validate_and_get_host") as mock_validate:
            mock_validate.return_value = (Mock(), None)

            await _handle_script_execution_result(message, mock_connection, mock_db)

            # Should handle without error

    @pytest.mark.asyncio
    async def test_handle_script_execution_result_queue_error(
        self, mock_connection, mock_db
    ):
        """Test script execution result handling with queue error."""
        message = Mock()
        message.data = {
            "execution_id": "exec-123",
            "exit_code": 1,
            "output": "Script failed",
        }

        with patch("backend.api.agent._validate_and_get_host") as mock_validate:
            mock_validate.return_value = (Mock(), None)

            await _handle_script_execution_result(message, mock_connection, mock_db)

            # Should handle without error even with queue issues


class TestBasicFunctionality:
    """Test basic functionality exists."""

    def test_functions_exist(self):
        """Test that all main functions exist and are callable."""
        assert callable(_process_websocket_message)
        assert callable(_handle_message_by_type)
        assert callable(_handle_script_execution_result)

    @pytest.mark.asyncio
    async def test_message_processing_basic(self):
        """Test basic message processing functionality."""
        mock_connection = Mock()
        mock_connection.send_message = AsyncMock()
        mock_db = Mock()

        # Test with minimal valid message
        simple_message = {"message_type": "heartbeat", "data": {}}

        with patch("backend.api.agent.websocket_security") as mock_security:
            mock_security.validate_message_integrity.return_value = True

            # Should not raise exceptions
            await _process_websocket_message(
                json.dumps(simple_message), mock_connection, mock_db, "test-connection"
            )
