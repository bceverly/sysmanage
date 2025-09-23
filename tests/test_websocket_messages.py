"""
Comprehensive tests for backend/websocket/messages.py module.
Tests message protocol definitions and utility classes for WebSocket communication.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.websocket.messages import (
    CommandMessage,
    CommandResultMessage,
    CommandType,
    DiagnosticCollectionResultMessage,
    HardwareUpdateMessage,
    HostApprovedMessage,
    Message,
    MessageType,
    SoftwareInventoryUpdateMessage,
    SystemInfoMessage,
    UserAccessUpdateMessage,
    create_message,
)


class TestMessageType:
    """Test MessageType enum."""

    def test_agent_to_server_message_types(self):
        """Test that all agent-to-server message types are defined."""
        # Verify they are all strings and have expected values
        assert MessageType.SYSTEM_INFO == "system_info"
        assert MessageType.HEARTBEAT == "heartbeat"
        assert MessageType.COMMAND_RESULT == "command_result"
        assert MessageType.ERROR == "error"
        assert MessageType.OS_VERSION_UPDATE == "os_version_update"

    def test_server_to_agent_message_types(self):
        """Test that all server-to-agent message types are defined."""
        # Verify they are all strings and have expected values
        assert MessageType.COMMAND == "command"
        assert MessageType.UPDATE_REQUEST == "update_request"
        assert MessageType.PING == "ping"
        assert MessageType.SHUTDOWN == "shutdown"
        assert MessageType.HOST_APPROVED == "host_approved"

    def test_message_type_enum_behavior(self):
        """Test that MessageType behaves as expected enum."""
        assert MessageType.SYSTEM_INFO == "system_info"
        assert MessageType.COMMAND == "command"
        assert MessageType.SYSTEM_INFO != MessageType.COMMAND


class TestCommandType:
    """Test CommandType enum."""

    def test_command_types_defined(self):
        """Test that all command types are properly defined."""
        assert CommandType.EXECUTE_SHELL == "execute_shell"
        assert CommandType.INSTALL_PACKAGE == "install_package"
        assert CommandType.UPDATE_SYSTEM == "update_system"
        assert CommandType.REBOOT_SYSTEM == "reboot_system"
        assert CommandType.EXECUTE_SCRIPT == "execute_script"

    def test_command_type_enum_behavior(self):
        """Test that CommandType behaves as expected enum."""
        assert CommandType.EXECUTE_SHELL == "execute_shell"
        assert CommandType.REBOOT_SYSTEM == "reboot_system"
        assert CommandType.EXECUTE_SHELL != CommandType.REBOOT_SYSTEM


class TestMessage:
    """Test base Message class."""

    def test_message_initialization_minimal(self):
        """Test message initialization with minimal parameters."""
        msg = Message(MessageType.HEARTBEAT)

        assert msg.message_type == MessageType.HEARTBEAT
        assert isinstance(msg.message_id, str)
        assert len(msg.message_id) > 0
        assert isinstance(msg.timestamp, str)
        assert msg.data == {}

    def test_message_initialization_complete(self):
        """Test message initialization with all parameters."""
        test_data = {"key": "value", "number": 42}
        test_id = "test-message-id"

        msg = Message(
            message_type=MessageType.COMMAND, data=test_data, message_id=test_id
        )

        assert msg.message_type == MessageType.COMMAND
        assert msg.message_id == test_id
        assert msg.data == test_data
        assert isinstance(msg.timestamp, str)

    def test_message_id_generation(self):
        """Test that message ID is generated when not provided."""
        msg1 = Message(MessageType.PING)
        msg2 = Message(MessageType.PING)

        assert msg1.message_id != msg2.message_id
        assert len(msg1.message_id) == 36  # Standard UUID length
        uuid.UUID(msg1.message_id)  # Should not raise exception

    @patch("backend.websocket.messages.datetime")
    def test_message_timestamp_generation(self, mock_datetime):
        """Test that timestamp is generated correctly."""
        test_time = datetime(2024, 1, 15, 12, 30, 45, 123456, timezone.utc)
        mock_datetime.now.return_value = test_time

        msg = Message(MessageType.SYSTEM_INFO)

        mock_datetime.now.assert_called_once_with(timezone.utc)
        assert msg.timestamp == test_time.isoformat()

    def test_to_dict_conversion(self):
        """Test conversion of message to dictionary."""
        test_data = {"hostname": "test-host", "status": "online"}
        test_id = "msg-123"

        msg = Message(
            message_type=MessageType.SYSTEM_INFO, data=test_data, message_id=test_id
        )

        result = msg.to_dict()

        expected_keys = {"message_type", "message_id", "timestamp", "data"}
        assert set(result.keys()) == expected_keys
        assert result["message_type"] == MessageType.SYSTEM_INFO
        assert result["message_id"] == test_id
        assert result["data"] == test_data

    def test_from_dict_creation_complete(self):
        """Test creation of message from complete dictionary."""
        input_dict = {
            "message_type": MessageType.HEARTBEAT,
            "message_id": "test-id-456",
            "timestamp": "2024-01-15T12:30:45.123456+00:00",
            "data": {"status": "alive", "uptime": 3600},
        }

        msg = Message.from_dict(input_dict)

        assert msg.message_type == MessageType.HEARTBEAT
        assert msg.message_id == "test-id-456"
        assert msg.timestamp == "2024-01-15T12:30:45.123456+00:00"
        assert msg.data == {"status": "alive", "uptime": 3600}

    def test_from_dict_creation_minimal(self):
        """Test creation of message from minimal dictionary."""
        input_dict = {"message_type": MessageType.ERROR}

        msg = Message.from_dict(input_dict)

        assert msg.message_type == MessageType.ERROR
        assert msg.data == {}
        assert isinstance(msg.message_id, str)  # Generated when not in dict

    def test_from_dict_with_missing_data(self):
        """Test creation of message when data key is missing."""
        input_dict = {"message_type": MessageType.PING, "message_id": "ping-123"}

        msg = Message.from_dict(input_dict)

        assert msg.message_type == MessageType.PING
        assert msg.message_id == "ping-123"
        assert msg.data == {}


class TestSystemInfoMessage:
    """Test SystemInfoMessage class."""

    def test_system_info_message_minimal(self):
        """Test SystemInfoMessage with minimal parameters."""
        msg = SystemInfoMessage("test-hostname")

        assert msg.message_type == MessageType.SYSTEM_INFO
        assert msg.data["hostname"] == "test-hostname"
        assert msg.data["ipv4"] is None
        assert msg.data["ipv6"] is None
        assert msg.data["platform"] is None

    def test_system_info_message_complete(self):
        """Test SystemInfoMessage with all parameters."""
        msg = SystemInfoMessage(
            hostname="production-server",
            ipv4="192.168.1.100",
            ipv6="2001:db8::1",
            platform="linux",
        )

        assert msg.message_type == MessageType.SYSTEM_INFO
        assert msg.data["hostname"] == "production-server"
        assert msg.data["ipv4"] == "192.168.1.100"
        assert msg.data["ipv6"] == "2001:db8::1"
        assert msg.data["platform"] == "linux"

    def test_system_info_message_with_kwargs(self):
        """Test SystemInfoMessage with additional keyword arguments."""
        msg = SystemInfoMessage(
            hostname="test-host", ipv4="10.0.0.1", cpu_count=4, memory_gb=16
        )

        assert msg.data["hostname"] == "test-host"
        assert msg.data["ipv4"] == "10.0.0.1"
        assert msg.data["cpu_count"] == 4
        assert msg.data["memory_gb"] == 16

    def test_system_info_message_inheritance(self):
        """Test that SystemInfoMessage inherits from Message correctly."""
        msg = SystemInfoMessage("test-host")

        assert isinstance(msg.message_id, str)
        assert isinstance(msg.timestamp, str)

        result = msg.to_dict()
        assert result["message_type"] == MessageType.SYSTEM_INFO
        assert "hostname" in result["data"]


class TestCommandMessage:
    """Test CommandMessage class."""

    def test_command_message_minimal(self):
        """Test CommandMessage with minimal parameters."""
        msg = CommandMessage(CommandType.GET_SYSTEM_INFO)

        assert msg.message_type == MessageType.COMMAND
        assert msg.data["command_type"] == CommandType.GET_SYSTEM_INFO
        assert msg.data["parameters"] == {}
        assert msg.data["timeout"] == 300

    def test_command_message_with_parameters(self):
        """Test CommandMessage with parameters."""
        params = {"shell": "bash", "script": "echo 'hello'"}
        msg = CommandMessage(
            command_type=CommandType.EXECUTE_SHELL, parameters=params, timeout=60
        )

        assert msg.message_type == MessageType.COMMAND
        assert msg.data["command_type"] == CommandType.EXECUTE_SHELL
        assert msg.data["parameters"] == params
        assert msg.data["timeout"] == 60

    def test_command_message_none_parameters(self):
        """Test CommandMessage when parameters is None."""
        msg = CommandMessage(
            command_type=CommandType.REBOOT_SYSTEM, parameters=None, timeout=30
        )

        assert msg.data["command_type"] == CommandType.REBOOT_SYSTEM
        assert msg.data["parameters"] == {}
        assert msg.data["timeout"] == 30

    def test_command_message_inheritance(self):
        """Test that CommandMessage inherits from Message correctly."""
        msg = CommandMessage(CommandType.UPDATE_SYSTEM)

        assert isinstance(msg.message_id, str)
        assert isinstance(msg.timestamp, str)

        result = msg.to_dict()
        assert result["message_type"] == MessageType.COMMAND
        assert "command_type" in result["data"]


class TestCommandResultMessage:
    """Test CommandResultMessage class."""

    def test_command_result_message_minimal(self):
        """Test CommandResultMessage with minimal parameters."""
        msg = CommandResultMessage("cmd-123", True)

        assert msg.message_type == MessageType.COMMAND_RESULT
        assert msg.data["command_id"] == "cmd-123"
        assert msg.data["success"] is True
        assert msg.data["result"] is None
        assert msg.data["error"] is None
        assert msg.data["exit_code"] is None

    def test_command_result_message_success(self):
        """Test CommandResultMessage for successful command."""
        result_data = {"stdout": "Command completed", "stderr": ""}
        msg = CommandResultMessage(
            command_id="cmd-456", success=True, result=result_data, exit_code=0
        )

        assert msg.data["command_id"] == "cmd-456"
        assert msg.data["success"] is True
        assert msg.data["result"] == result_data
        assert msg.data["error"] is None
        assert msg.data["exit_code"] == 0

    def test_command_result_message_failure(self):
        """Test CommandResultMessage for failed command."""
        msg = CommandResultMessage(
            command_id="cmd-789",
            success=False,
            error="Command not found",
            exit_code=127,
        )

        assert msg.data["command_id"] == "cmd-789"
        assert msg.data["success"] is False
        assert msg.data["result"] is None
        assert msg.data["error"] == "Command not found"
        assert msg.data["exit_code"] == 127

    def test_command_result_message_complete(self):
        """Test CommandResultMessage with all parameters."""
        result_data = {"output": "test output"}
        msg = CommandResultMessage(
            command_id="cmd-complete",
            success=True,
            result=result_data,
            error="warning message",
            exit_code=0,
        )

        assert msg.data["command_id"] == "cmd-complete"
        assert msg.data["success"] is True
        assert msg.data["result"] == result_data
        assert msg.data["error"] == "warning message"
        assert msg.data["exit_code"] == 0


class TestMessageClassesIntegration:
    """Integration tests for message classes."""

    def test_all_message_types_work_with_base_class(self):
        """Test that all message types work with base Message functionality."""
        messages = [
            Message(MessageType.PING),
            SystemInfoMessage("test-host"),
            CommandMessage(CommandType.GET_SYSTEM_INFO),
            CommandResultMessage("cmd-1", True),
        ]

        for msg in messages:
            msg_dict = msg.to_dict()
            assert "message_type" in msg_dict
            assert "message_id" in msg_dict
            assert "timestamp" in msg_dict
            assert "data" in msg_dict

            recreated = Message.from_dict(msg_dict)
            assert recreated.message_type == msg.message_type

    def test_message_serialization_json_compatibility(self):
        """Test that messages can be serialized to JSON-compatible dicts."""
        import json

        messages = [
            SystemInfoMessage("host1", ipv4="192.168.1.1"),
            CommandMessage(CommandType.EXECUTE_SHELL, {"cmd": "ls -la"}),
            CommandResultMessage("cmd-1", True, {"output": "file1.txt"}),
        ]

        for msg in messages:
            msg_dict = msg.to_dict()
            json_str = json.dumps(msg_dict)
            assert isinstance(json_str, str)

            restored_dict = json.loads(json_str)
            assert restored_dict == msg_dict

    def test_unique_message_ids(self):
        """Test that message IDs are unique across instances."""
        messages = [Message(MessageType.HEARTBEAT) for _ in range(50)]
        message_ids = [msg.message_id for msg in messages]

        assert len(set(message_ids)) == len(message_ids)

    def test_timestamp_format_consistency(self):
        """Test that timestamps follow consistent format."""
        messages = [
            Message(MessageType.PING),
            SystemInfoMessage("host"),
            CommandMessage(CommandType.GET_SYSTEM_INFO),
            CommandResultMessage("cmd", True),
        ]

        for msg in messages:
            assert isinstance(msg.timestamp, str)
            datetime.fromisoformat(msg.timestamp.replace("Z", "+00:00"))


class TestCreateMessageMissingTypes:
    """Test create_message function for missing coverage message types."""

    def test_create_hardware_update_message(self):
        """Test creating HARDWARE_UPDATE message to hit line 479-480."""
        raw_data = {
            "message_type": MessageType.HARDWARE_UPDATE,
            "data": {
                "cpu_vendor": "Intel",
                "cpu_model": "Core i7",
                "cpu_cores": 4,
                "cpu_threads": 8,
                "memory_total": 16777216,
                "hostname": "test-host",
            },
        }

        message = create_message(raw_data)
        assert isinstance(message, HardwareUpdateMessage)

    def test_create_user_access_update_message(self):
        """Test creating USER_ACCESS_UPDATE message to hit line 508-509."""
        raw_data = {
            "message_type": MessageType.USER_ACCESS_UPDATE,
            "data": {
                "users": ["user1", "user2"],
                "groups": ["group1", "group2"],
                "platform": "Linux",
                "total_users": 2,
                "total_groups": 2,
                "hostname": "test-host",
            },
        }

        message = create_message(raw_data)
        assert isinstance(message, UserAccessUpdateMessage)

    def test_create_software_inventory_update_message(self):
        """Test creating SOFTWARE_INVENTORY_UPDATE message to hit line 537-538."""
        raw_data = {
            "message_type": MessageType.SOFTWARE_INVENTORY_UPDATE,
            "data": {
                "software_packages": [{"name": "package1", "version": "1.0"}],
                "platform": "Ubuntu",
                "total_packages": 100,
                "collection_timestamp": "2023-01-01T00:00:00Z",
                "hostname": "test-host",
            },
        }

        message = create_message(raw_data)
        assert isinstance(message, SoftwareInventoryUpdateMessage)

    def test_create_host_approved_message(self):
        """Test creating HOST_APPROVED message to hit line 556-557."""
        raw_data = {
            "message_type": MessageType.HOST_APPROVED,
            "data": {
                "host_id": 123,
                "approval_status": "approved",
                "certificate": "cert-data",
                "hostname": "test-host",
            },
        }

        message = create_message(raw_data)
        assert isinstance(message, HostApprovedMessage)

    def test_create_diagnostic_collection_result_message(self):
        """Test creating DIAGNOSTIC_COLLECTION_RESULT message to hit line 607-608."""
        raw_data = {
            "message_type": MessageType.DIAGNOSTIC_COLLECTION_RESULT,
            "data": {
                "collection_id": "diag-123",
                "success": True,
                "system_logs": {"syslog": "log data"},
                "configuration_files": {"config": "config data"},
                "network_info": {"interfaces": []},
                "process_info": {"processes": []},
                "hostname": "test-host",
            },
        }

        message = create_message(raw_data)
        assert isinstance(message, DiagnosticCollectionResultMessage)
