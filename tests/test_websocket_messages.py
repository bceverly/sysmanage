"""
Tests for WebSocket message protocol and classes.
"""

from datetime import datetime

import pytest

from backend.websocket.messages import (
    CommandMessage,
    CommandResultMessage,
    CommandType,
    ErrorMessage,
    HeartbeatMessage,
    Message,
    MessageType,
    SystemInfoMessage,
    create_message,
)


class TestMessageTypes:
    """Test message type enums."""

    def test_message_type_values(self):
        """Test that message types have expected values."""
        assert MessageType.SYSTEM_INFO == "system_info"
        assert MessageType.HEARTBEAT == "heartbeat"
        assert MessageType.COMMAND == "command"
        assert MessageType.COMMAND_RESULT == "command_result"
        assert MessageType.ERROR == "error"
        assert MessageType.PING == "ping"
        assert MessageType.SHUTDOWN == "shutdown"

    def test_command_type_values(self):
        """Test that command types have expected values."""
        assert CommandType.EXECUTE_SHELL == "execute_shell"
        assert CommandType.INSTALL_PACKAGE == "install_package"
        assert CommandType.UPDATE_SYSTEM == "update_system"
        assert CommandType.RESTART_SERVICE == "restart_service"
        assert CommandType.GET_SYSTEM_INFO == "get_system_info"
        assert CommandType.REBOOT_SYSTEM == "reboot_system"


class TestBaseMessage:
    """Test the base Message class."""

    def test_message_creation(self):
        """Test basic message creation."""
        msg = Message(MessageType.PING, {"test": "data"})

        assert msg.message_type == MessageType.PING
        assert msg.data == {"test": "data"}
        assert msg.message_id is not None
        assert msg.timestamp is not None

    def test_message_to_dict(self):
        """Test message serialization to dictionary."""
        msg = Message(MessageType.PING, {"test": "data"}, "test-id-123")
        result = msg.to_dict()

        assert result["message_type"] == MessageType.PING
        assert result["message_id"] == "test-id-123"
        assert result["data"] == {"test": "data"}
        assert "timestamp" in result

    def test_message_from_dict(self):
        """Test message deserialization from dictionary."""
        data = {
            "message_type": "ping",
            "message_id": "test-123",
            "timestamp": "2024-01-01T00:00:00.000000",
            "data": {"test": "value"},
        }

        msg = Message.from_dict(data)
        assert msg.message_type == "ping"
        assert msg.message_id == "test-123"
        assert msg.data == {"test": "value"}
        assert msg.timestamp == "2024-01-01T00:00:00.000000"


class TestSystemInfoMessage:
    """Test SystemInfoMessage class."""

    def test_system_info_creation(self):
        """Test system info message creation."""
        msg = SystemInfoMessage(
            hostname="test.example.com",
            ipv4="192.168.1.1",
            ipv6="2001:db8::1",
            platform="Linux",
        )

        assert msg.message_type == MessageType.SYSTEM_INFO
        assert msg.data["hostname"] == "test.example.com"
        assert msg.data["ipv4"] == "192.168.1.1"
        assert msg.data["ipv6"] == "2001:db8::1"
        assert msg.data["platform"] == "Linux"

    def test_system_info_with_extra_data(self):
        """Test system info with additional data."""
        msg = SystemInfoMessage(
            hostname="test.example.com", architecture="x86_64", memory="8GB"
        )

        assert msg.data["hostname"] == "test.example.com"
        assert msg.data["architecture"] == "x86_64"
        assert msg.data["memory"] == "8GB"


class TestCommandMessage:
    """Test CommandMessage class."""

    def test_command_creation(self):
        """Test command message creation."""
        msg = CommandMessage(
            CommandType.EXECUTE_SHELL, {"command": "ls -la"}, timeout=60
        )

        assert msg.message_type == MessageType.COMMAND
        assert msg.data["command_type"] == CommandType.EXECUTE_SHELL
        assert msg.data["parameters"]["command"] == "ls -la"
        assert msg.data["timeout"] == 60

    def test_command_default_timeout(self):
        """Test command with default timeout."""
        msg = CommandMessage(CommandType.GET_SYSTEM_INFO)

        assert msg.data["command_type"] == CommandType.GET_SYSTEM_INFO
        assert msg.data["parameters"] == {}
        assert msg.data["timeout"] == 300


class TestCommandResultMessage:
    """Test CommandResultMessage class."""

    def test_successful_result(self):
        """Test successful command result."""
        msg = CommandResultMessage(
            command_id="cmd-123",
            success=True,
            result={"output": "Hello World"},
            exit_code=0,
        )

        assert msg.message_type == MessageType.COMMAND_RESULT
        assert msg.data["command_id"] == "cmd-123"
        assert msg.data["success"] is True
        assert msg.data["result"]["output"] == "Hello World"
        assert msg.data["exit_code"] == 0
        assert msg.data["error"] is None

    def test_failed_result(self):
        """Test failed command result."""
        msg = CommandResultMessage(
            command_id="cmd-456",
            success=False,
            error="Command not found",
            exit_code=127,
        )

        assert msg.data["command_id"] == "cmd-456"
        assert msg.data["success"] is False
        assert msg.data["error"] == "Command not found"
        assert msg.data["exit_code"] == 127
        assert msg.data["result"] is None


class TestHeartbeatMessage:
    """Test HeartbeatMessage class."""

    def test_heartbeat_creation(self):
        """Test heartbeat message creation."""
        msg = HeartbeatMessage(
            agent_status="healthy", system_load=0.5, memory_usage=75.2
        )

        assert msg.message_type == MessageType.HEARTBEAT
        assert msg.data["agent_status"] == "healthy"
        assert msg.data["system_load"] == 0.5
        assert msg.data["memory_usage"] == 75.2

    def test_heartbeat_defaults(self):
        """Test heartbeat with default values."""
        msg = HeartbeatMessage()

        assert msg.data["agent_status"] == "healthy"
        assert msg.data["system_load"] is None
        assert msg.data["memory_usage"] is None


class TestErrorMessage:
    """Test ErrorMessage class."""

    def test_error_creation(self):
        """Test error message creation."""
        msg = ErrorMessage(
            error_code="invalid_command",
            error_message="Command type not recognized",
            details={"received_type": "unknown_command"},
        )

        assert msg.message_type == MessageType.ERROR
        assert msg.data["error_code"] == "invalid_command"
        assert msg.data["error_message"] == "Command type not recognized"
        assert msg.data["details"]["received_type"] == "unknown_command"

    def test_error_minimal(self):
        """Test error message with minimal data."""
        msg = ErrorMessage("general_error", "Something went wrong")

        assert msg.data["error_code"] == "general_error"
        assert msg.data["error_message"] == "Something went wrong"
        assert msg.data["details"] == {}


class TestMessageFactory:
    """Test the message factory function."""

    def test_create_system_info(self):
        """Test creating system info message via factory."""
        data = {
            "message_type": "system_info",
            "message_id": "test-123",
            "data": {"hostname": "test.com"},
        }

        msg = create_message(data)
        assert isinstance(msg, SystemInfoMessage)
        assert msg.message_type == MessageType.SYSTEM_INFO
        assert msg.data["hostname"] == "test.com"

    def test_create_command(self):
        """Test creating command message via factory."""
        data = {
            "message_type": "command",
            "message_id": "test-456",
            "data": {"command_type": "execute_shell"},
        }

        msg = create_message(data)
        assert isinstance(msg, CommandMessage)
        assert msg.message_type == MessageType.COMMAND

    def test_create_unknown_message(self):
        """Test creating unknown message type."""
        data = {
            "message_type": "unknown_type",
            "message_id": "test-789",
            "data": {"test": "data"},
        }

        msg = create_message(data)
        assert isinstance(msg, Message)
        assert msg.message_type == "unknown_type"
        assert msg.data["test"] == "data"
