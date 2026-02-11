"""
Tests for backend/websocket/messages.py module.
Tests message protocol definitions for WebSocket communication.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from backend.websocket.messages import (
    CommandMessage,
    CommandResultMessage,
    CommandType,
    DiagnosticCollectionResultMessage,
    ErrorMessage,
    HardwareUpdateMessage,
    HeartbeatMessage,
    HostApprovedMessage,
    Message,
    MessageType,
    OSVersionUpdateMessage,
    ScriptExecutionResultMessage,
    SoftwareInventoryUpdateMessage,
    SystemInfoMessage,
    UserAccessUpdateMessage,
    create_command_message,
    create_host_approved_message,
    create_message,
)


class TestMessageType:
    """Tests for MessageType enum."""

    def test_message_type_values(self):
        """Test that key message types have expected values."""
        assert MessageType.SYSTEM_INFO == "system_info"
        assert MessageType.HEARTBEAT == "heartbeat"
        assert MessageType.COMMAND == "command"
        assert MessageType.ERROR == "error"

    def test_message_type_enum_count(self):
        """Test that there are expected number of message types."""
        assert len(MessageType) > 30  # Many message types defined


class TestCommandType:
    """Tests for CommandType enum."""

    def test_command_type_values(self):
        """Test that key command types have expected values."""
        assert CommandType.EXECUTE_SHELL == "execute_shell"
        assert CommandType.REBOOT_SYSTEM == "reboot_system"
        assert CommandType.GET_SYSTEM_INFO == "get_system_info"


class TestMessage:
    """Tests for base Message class."""

    def test_message_init_defaults(self):
        """Test message initialization with defaults."""
        msg = Message(MessageType.HEARTBEAT)

        assert msg.message_type == MessageType.HEARTBEAT
        assert msg.message_id is not None
        assert msg.timestamp is not None
        assert msg.data == {}

    def test_message_init_with_data(self):
        """Test message initialization with data."""
        data = {"key": "value"}
        msg = Message(MessageType.HEARTBEAT, data=data)

        assert msg.data == {"key": "value"}

    def test_message_init_with_message_id(self):
        """Test message initialization with custom message_id."""
        msg = Message(MessageType.HEARTBEAT, message_id="custom-id")

        assert msg.message_id == "custom-id"

    def test_message_to_dict(self):
        """Test message serialization to dictionary."""
        msg = Message(MessageType.HEARTBEAT, data={"test": "data"})
        result = msg.to_dict()

        assert result["message_type"] == MessageType.HEARTBEAT
        assert result["data"] == {"test": "data"}
        assert "message_id" in result
        assert "timestamp" in result

    def test_message_from_dict(self):
        """Test message creation from dictionary."""
        data = {
            "message_type": "heartbeat",
            "message_id": "test-id",
            "timestamp": "2024-01-01T00:00:00Z",
            "data": {"key": "value"},
        }
        msg = Message.from_dict(data)

        assert msg.message_type == "heartbeat"
        assert msg.message_id == "test-id"
        assert msg.timestamp == "2024-01-01T00:00:00Z"
        assert msg.data == {"key": "value"}

    def test_message_from_dict_no_timestamp(self):
        """Test message creation from dictionary without timestamp."""
        data = {
            "message_type": "heartbeat",
            "data": {},
        }
        msg = Message.from_dict(data)

        # Should have a timestamp generated
        assert msg.timestamp is not None


class TestSystemInfoMessage:
    """Tests for SystemInfoMessage class."""

    def test_system_info_message_init(self):
        """Test SystemInfoMessage initialization."""
        msg = SystemInfoMessage(
            hostname="testhost",
            ipv4="192.168.1.1",
            ipv6="::1",
            platform="Linux",
        )

        assert msg.message_type == MessageType.SYSTEM_INFO
        assert msg.data["hostname"] == "testhost"
        assert msg.data["ipv4"] == "192.168.1.1"
        assert msg.data["ipv6"] == "::1"
        assert msg.data["platform"] == "Linux"

    def test_system_info_message_extra_kwargs(self):
        """Test SystemInfoMessage with extra kwargs."""
        msg = SystemInfoMessage(
            hostname="testhost",
            custom_field="custom_value",
        )

        assert msg.data["custom_field"] == "custom_value"


class TestCommandMessage:
    """Tests for CommandMessage class."""

    def test_command_message_init(self):
        """Test CommandMessage initialization."""
        msg = CommandMessage(
            command_type=CommandType.GET_SYSTEM_INFO,
            parameters={"param1": "value1"},
            timeout=60,
        )

        assert msg.message_type == MessageType.COMMAND
        assert msg.data["command_type"] == CommandType.GET_SYSTEM_INFO
        assert msg.data["parameters"] == {"param1": "value1"}
        assert msg.data["timeout"] == 60

    def test_command_message_defaults(self):
        """Test CommandMessage with default values."""
        msg = CommandMessage(command_type=CommandType.GET_SYSTEM_INFO)

        assert msg.data["parameters"] == {}
        assert msg.data["timeout"] == 300


class TestCommandResultMessage:
    """Tests for CommandResultMessage class."""

    def test_command_result_success(self):
        """Test CommandResultMessage for successful command."""
        msg = CommandResultMessage(
            command_id="cmd-123",
            success=True,
            result={"output": "success"},
            exit_code=0,
        )

        assert msg.message_type == MessageType.COMMAND_RESULT
        assert msg.data["command_id"] == "cmd-123"
        assert msg.data["success"] is True
        assert msg.data["exit_code"] == 0

    def test_command_result_failure(self):
        """Test CommandResultMessage for failed command."""
        msg = CommandResultMessage(
            command_id="cmd-456",
            success=False,
            error="Command failed",
            exit_code=1,
        )

        assert msg.data["success"] is False
        assert msg.data["error"] == "Command failed"


class TestHeartbeatMessage:
    """Tests for HeartbeatMessage class."""

    def test_heartbeat_message_init(self):
        """Test HeartbeatMessage initialization."""
        msg = HeartbeatMessage(
            agent_status="healthy",
            system_load=1.5,
            memory_usage=45.2,
            is_privileged=True,
        )

        assert msg.message_type == MessageType.HEARTBEAT
        assert msg.data["agent_status"] == "healthy"
        assert msg.data["system_load"] == 1.5
        assert msg.data["memory_usage"] == 45.2
        assert msg.data["is_privileged"] is True

    def test_heartbeat_message_defaults(self):
        """Test HeartbeatMessage with defaults."""
        msg = HeartbeatMessage()

        assert msg.data["agent_status"] == "healthy"


class TestErrorMessage:
    """Tests for ErrorMessage class."""

    def test_error_message_init(self):
        """Test ErrorMessage initialization."""
        msg = ErrorMessage(
            error_code="ERR001",
            error_message="Something went wrong",
            details={"field": "value"},
        )

        assert msg.message_type == MessageType.ERROR

    def test_error_message_to_dict(self):
        """Test ErrorMessage serialization."""
        msg = ErrorMessage(
            error_code="ERR001",
            error_message="Something went wrong",
            details={"field": "value"},
        )
        result = msg.to_dict()

        assert result["error_type"] == "ERR001"
        assert result["message"] == "Something went wrong"
        assert result["data"] == {"field": "value"}

    def test_error_message_no_details(self):
        """Test ErrorMessage without details."""
        msg = ErrorMessage(
            error_code="ERR002",
            error_message="Error",
        )
        result = msg.to_dict()

        assert result["data"] == {}


class TestOSVersionUpdateMessage:
    """Tests for OSVersionUpdateMessage class."""

    def test_os_version_update_message(self):
        """Test OSVersionUpdateMessage initialization."""
        msg = OSVersionUpdateMessage(
            platform="Linux",
            platform_release="6.1.0",
            platform_version="#1 SMP",
            architecture="x86_64",
            processor="Intel",
        )

        assert msg.message_type == MessageType.OS_VERSION_UPDATE
        assert msg.data["platform"] == "Linux"
        assert msg.data["platform_release"] == "6.1.0"


class TestHardwareUpdateMessage:
    """Tests for HardwareUpdateMessage class."""

    def test_hardware_update_message(self):
        """Test HardwareUpdateMessage initialization."""
        msg = HardwareUpdateMessage(
            cpu_vendor="Intel",
            cpu_model="Core i7",
            cpu_cores=8,
            cpu_threads=16,
            memory_total_mb=16384,
        )

        assert msg.message_type == MessageType.HARDWARE_UPDATE
        assert msg.data["cpu_vendor"] == "Intel"
        assert msg.data["cpu_cores"] == 8


class TestUserAccessUpdateMessage:
    """Tests for UserAccessUpdateMessage class."""

    def test_user_access_update_message(self):
        """Test UserAccessUpdateMessage initialization."""
        msg = UserAccessUpdateMessage(
            users=[{"username": "user1"}],
            groups=[{"group_name": "group1"}],
            platform="Linux",
            total_users=10,
            total_groups=5,
        )

        assert msg.message_type == MessageType.USER_ACCESS_UPDATE
        assert len(msg.data["users"]) == 1
        assert msg.data["total_users"] == 10

    def test_user_access_update_defaults(self):
        """Test UserAccessUpdateMessage with defaults."""
        msg = UserAccessUpdateMessage()

        assert msg.data["users"] == []
        assert msg.data["groups"] == []


class TestSoftwareInventoryUpdateMessage:
    """Tests for SoftwareInventoryUpdateMessage class."""

    def test_software_inventory_update_message(self):
        """Test SoftwareInventoryUpdateMessage initialization."""
        msg = SoftwareInventoryUpdateMessage(
            software_packages=[{"name": "vim"}],
            platform="Linux",
            total_packages=100,
        )

        assert msg.message_type == MessageType.SOFTWARE_INVENTORY_UPDATE
        assert len(msg.data["software_packages"]) == 1


class TestHostApprovedMessage:
    """Tests for HostApprovedMessage class."""

    def test_host_approved_message(self):
        """Test HostApprovedMessage initialization."""
        msg = HostApprovedMessage(
            host_id="host-123",
            host_token="token-abc",
            approval_status="approved",
            certificate="cert-data",
        )

        assert msg.message_type == MessageType.HOST_APPROVED
        assert msg.data["host_id"] == "host-123"
        assert msg.data["host_token"] == "token-abc"

    def test_host_approved_message_defaults(self):
        """Test HostApprovedMessage with defaults."""
        msg = HostApprovedMessage(host_id="host-123")

        assert msg.data["approval_status"] == "approved"


class TestScriptExecutionResultMessage:
    """Tests for ScriptExecutionResultMessage class."""

    def test_script_execution_result_success(self):
        """Test ScriptExecutionResultMessage for success."""
        msg = ScriptExecutionResultMessage(
            script_id="script-123",
            execution_id="exec-456",
            success=True,
            exit_code=0,
            stdout="output",
            stderr="",
            execution_time=1.5,
        )

        assert msg.message_type == MessageType.SCRIPT_EXECUTION_RESULT
        assert msg.data["script_id"] == "script-123"
        assert msg.data["success"] is True

    def test_script_execution_result_timeout(self):
        """Test ScriptExecutionResultMessage for timeout."""
        msg = ScriptExecutionResultMessage(
            script_id="script-123",
            success=False,
            timeout=True,
            error="Script timed out",
        )

        assert msg.data["timeout"] is True


class TestDiagnosticCollectionResultMessage:
    """Tests for DiagnosticCollectionResultMessage class."""

    def test_diagnostic_collection_result(self):
        """Test DiagnosticCollectionResultMessage initialization."""
        msg = DiagnosticCollectionResultMessage(
            collection_id="diag-123",
            success=True,
            collection_size_bytes=12345,
            files_collected=10,
            system_logs="log data",
        )

        assert msg.message_type == MessageType.DIAGNOSTIC_COLLECTION_RESULT
        assert msg.data["collection_id"] == "diag-123"
        assert msg.data["system_logs"] == "log data"


class TestCreateMessage:
    """Tests for create_message factory function."""

    def test_create_system_info_message(self):
        """Test creating SystemInfoMessage from raw data."""
        raw_data = {
            "message_type": MessageType.SYSTEM_INFO,
            "data": {
                "hostname": "testhost",
                "ipv4": "192.168.1.1",
            },
        }
        msg = create_message(raw_data)

        assert isinstance(msg, SystemInfoMessage)
        assert msg.data["hostname"] == "testhost"

    def test_create_command_message(self):
        """Test creating CommandMessage from raw data."""
        raw_data = {
            "message_type": MessageType.COMMAND,
            "data": {
                "command_type": CommandType.GET_SYSTEM_INFO,
                "parameters": {},
                "timeout": 60,
            },
        }
        msg = create_message(raw_data)

        assert isinstance(msg, CommandMessage)

    def test_create_command_result_message(self):
        """Test creating CommandResultMessage from raw data."""
        raw_data = {
            "message_type": MessageType.COMMAND_RESULT,
            "data": {
                "command_id": "cmd-123",
                "success": True,
            },
        }
        msg = create_message(raw_data)

        assert isinstance(msg, CommandResultMessage)

    def test_create_heartbeat_message(self):
        """Test creating HeartbeatMessage from raw data."""
        raw_data = {
            "message_type": MessageType.HEARTBEAT,
            "data": {
                "agent_status": "healthy",
            },
        }
        msg = create_message(raw_data)

        assert isinstance(msg, HeartbeatMessage)

    def test_create_error_message(self):
        """Test creating ErrorMessage from raw data."""
        raw_data = {
            "message_type": MessageType.ERROR,
            "error_type": "ERR001",
            "message": "Error occurred",
            "data": {},
        }
        msg = create_message(raw_data)

        assert isinstance(msg, ErrorMessage)

    def test_create_error_message_old_format(self):
        """Test creating ErrorMessage from old format."""
        raw_data = {
            "message_type": MessageType.ERROR,
            "data": {
                "error_code": "ERR002",
                "error_message": "Old format error",
            },
        }
        msg = create_message(raw_data)

        assert isinstance(msg, ErrorMessage)

    def test_create_os_version_update_message(self):
        """Test creating OSVersionUpdateMessage from raw data."""
        raw_data = {
            "message_type": MessageType.OS_VERSION_UPDATE,
            "data": {
                "platform": "Linux",
            },
        }
        msg = create_message(raw_data)

        assert isinstance(msg, OSVersionUpdateMessage)

    def test_create_hardware_update_message(self):
        """Test creating HardwareUpdateMessage from raw data."""
        raw_data = {
            "message_type": MessageType.HARDWARE_UPDATE,
            "data": {
                "cpu_vendor": "Intel",
            },
        }
        msg = create_message(raw_data)

        assert isinstance(msg, HardwareUpdateMessage)

    def test_create_user_access_update_message(self):
        """Test creating UserAccessUpdateMessage from raw data."""
        raw_data = {
            "message_type": MessageType.USER_ACCESS_UPDATE,
            "data": {
                "users": [],
                "groups": [],
            },
        }
        msg = create_message(raw_data)

        assert isinstance(msg, UserAccessUpdateMessage)

    def test_create_software_inventory_update_message(self):
        """Test creating SoftwareInventoryUpdateMessage from raw data."""
        raw_data = {
            "message_type": MessageType.SOFTWARE_INVENTORY_UPDATE,
            "data": {
                "software_packages": [],
            },
        }
        msg = create_message(raw_data)

        assert isinstance(msg, SoftwareInventoryUpdateMessage)

    def test_create_host_approved_message(self):
        """Test creating HostApprovedMessage from raw data."""
        raw_data = {
            "message_type": MessageType.HOST_APPROVED,
            "data": {
                "host_id": "host-123",
            },
        }
        msg = create_message(raw_data)

        assert isinstance(msg, HostApprovedMessage)

    def test_create_script_execution_result_message(self):
        """Test creating ScriptExecutionResultMessage from raw data."""
        raw_data = {
            "message_type": MessageType.SCRIPT_EXECUTION_RESULT,
            "script_id": "script-123",
            "success": True,
        }
        msg = create_message(raw_data)

        assert isinstance(msg, ScriptExecutionResultMessage)

    def test_create_diagnostic_collection_result_message(self):
        """Test creating DiagnosticCollectionResultMessage from raw data."""
        raw_data = {
            "message_type": MessageType.DIAGNOSTIC_COLLECTION_RESULT,
            "data": {
                "collection_id": "diag-123",
            },
        }
        msg = create_message(raw_data)

        assert isinstance(msg, DiagnosticCollectionResultMessage)

    def test_create_unknown_message_fallback(self):
        """Test fallback for unknown message types."""
        raw_data = {
            "message_type": "unknown_type",
            "data": {"key": "value"},
        }
        msg = create_message(raw_data)

        # Should fall back to base Message class
        assert isinstance(msg, Message)


class TestCreateCommandMessageHelper:
    """Tests for create_command_message helper function."""

    def test_create_command_message_helper(self):
        """Test create_command_message helper."""
        result = create_command_message(CommandType.GET_SYSTEM_INFO, {"param": "value"})

        assert result["message_type"] == MessageType.COMMAND
        assert result["data"]["command_type"] == CommandType.GET_SYSTEM_INFO
        assert result["data"]["parameters"] == {"param": "value"}

    def test_create_command_message_no_params(self):
        """Test create_command_message without parameters."""
        result = create_command_message(CommandType.GET_SYSTEM_INFO)

        assert result["data"]["parameters"] == {}


class TestCreateHostApprovedMessageHelper:
    """Tests for create_host_approved_message helper function."""

    def test_create_host_approved_message_helper(self):
        """Test create_host_approved_message helper."""
        result = create_host_approved_message(
            host_id="host-123",
            host_token="token-abc",
            approval_status="approved",
            certificate="cert-data",
        )

        assert result["message_type"] == MessageType.HOST_APPROVED
        assert result["data"]["host_id"] == "host-123"
        assert result["data"]["host_token"] == "token-abc"

    def test_create_host_approved_message_minimal(self):
        """Test create_host_approved_message with minimal args."""
        result = create_host_approved_message(host_id="host-123")

        assert result["data"]["host_id"] == "host-123"
        assert result["data"]["approval_status"] == "approved"
