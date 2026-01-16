"""
Comprehensive unit tests for backend.websocket.messages module.
Tests the message classes and factory functions for WebSocket communication.
"""

from datetime import datetime, timezone
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


class TestMessageTypes:
    """Test message type enumerations."""

    def test_message_type_values(self):
        """Test that message types have expected string values."""
        # Agent -> Server messages
        assert MessageType.SYSTEM_INFO == "system_info"
        assert MessageType.HEARTBEAT == "heartbeat"
        assert MessageType.COMMAND_RESULT == "command_result"
        assert MessageType.ERROR == "error"
        assert MessageType.OS_VERSION_UPDATE == "os_version_update"
        assert MessageType.HARDWARE_UPDATE == "hardware_update"
        assert MessageType.USER_ACCESS_UPDATE == "user_access_update"
        assert MessageType.SOFTWARE_INVENTORY_UPDATE == "software_inventory_update"
        assert MessageType.PACKAGE_UPDATES_UPDATE == "package_updates_update"
        assert MessageType.UPDATE_APPLY_RESULT == "update_apply_result"
        assert MessageType.SCRIPT_EXECUTION_RESULT == "script_execution_result"
        assert MessageType.REBOOT_STATUS_UPDATE == "reboot_status_update"
        assert (
            MessageType.DIAGNOSTIC_COLLECTION_RESULT == "diagnostic_collection_result"
        )

        # Server -> Agent messages
        assert MessageType.COMMAND == "command"
        assert MessageType.UPDATE_REQUEST == "update_request"
        assert MessageType.PING == "ping"
        assert MessageType.SHUTDOWN == "shutdown"
        assert MessageType.HOST_APPROVED == "host_approved"

    def test_command_type_values(self):
        """Test that command types have expected string values."""
        assert CommandType.EXECUTE_SHELL == "execute_shell"
        assert CommandType.INSTALL_PACKAGE == "install_package"
        assert CommandType.UPDATE_SYSTEM == "update_system"
        assert CommandType.APPLY_UPDATES == "apply_updates"
        assert CommandType.RESTART_SERVICE == "restart_service"
        assert CommandType.GET_SYSTEM_INFO == "get_system_info"
        assert CommandType.GET_INSTALLED_PACKAGES == "get_installed_packages"
        assert CommandType.GET_AVAILABLE_UPDATES == "get_available_updates"
        assert CommandType.REBOOT_SYSTEM == "reboot_system"
        assert CommandType.EXECUTE_SCRIPT == "execute_script"
        assert CommandType.CHECK_REBOOT_STATUS == "check_reboot_status"
        assert CommandType.COLLECT_DIAGNOSTICS == "collect_diagnostics"


class TestBaseMessage:
    """Test base Message class."""

    def test_message_initialization_minimal(self):
        """Test basic message initialization with minimal parameters."""
        message = Message(MessageType.HEARTBEAT)

        assert message.message_type == MessageType.HEARTBEAT
        assert message.message_id is not None
        assert message.timestamp is not None
        assert message.data == {}

    def test_message_initialization_with_data(self):
        """Test message initialization with data."""
        data = {"key": "value", "number": 42}
        message = Message(MessageType.SYSTEM_INFO, data=data)

        assert message.message_type == MessageType.SYSTEM_INFO
        assert message.data == data

    def test_message_initialization_with_custom_id(self):
        """Test message initialization with custom message ID."""
        custom_id = "custom-message-id-123"
        message = Message(MessageType.ERROR, message_id=custom_id)

        assert message.message_id == custom_id

    def test_message_to_dict(self):
        """Test converting message to dictionary."""
        data = {"test": "data"}
        message = Message(MessageType.COMMAND, data=data, message_id="test-id")

        result = message.to_dict()

        assert result["message_type"] == MessageType.COMMAND
        assert result["message_id"] == "test-id"
        assert result["data"] == data
        assert "timestamp" in result

    def test_message_from_dict_complete(self):
        """Test creating message from complete dictionary."""
        test_dict = {
            "message_type": MessageType.HEARTBEAT,
            "message_id": "test-message-123",
            "timestamp": "2025-09-16T12:34:56Z",
            "data": {"status": "healthy"},
        }

        message = Message.from_dict(test_dict)

        assert message.message_type == MessageType.HEARTBEAT
        assert message.message_id == "test-message-123"
        assert message.timestamp == "2025-09-16T12:34:56Z"
        assert message.data == {"status": "healthy"}

    def test_message_from_dict_minimal(self):
        """Test creating message from minimal dictionary."""
        test_dict = {"message_type": MessageType.ERROR}

        message = Message.from_dict(test_dict)

        assert message.message_type == MessageType.ERROR
        assert message.data == {}
        assert message.message_id is not None

    def test_message_timestamp_format(self):
        """Test that message timestamp is in ISO format."""
        with patch("backend.websocket.messages.datetime") as mock_datetime:
            mock_now = datetime(2025, 9, 16, 12, 34, 56, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            mock_datetime.timezone = timezone

            message = Message(MessageType.PING)

            mock_datetime.now.assert_called_once_with(timezone.utc)
            assert message.timestamp == "2025-09-16T12:34:56+00:00"


class TestSystemInfoMessage:
    """Test SystemInfoMessage class."""

    def test_system_info_message_basic(self):
        """Test basic system info message creation."""
        hostname = "test-host.example.com"
        message = SystemInfoMessage(hostname=hostname)

        assert message.message_type == MessageType.SYSTEM_INFO
        assert message.data["hostname"] == hostname
        assert message.data["ipv4"] is None

    def test_system_info_message_complete(self):
        """Test system info message with all parameters."""
        message = SystemInfoMessage(
            hostname="test-host",
            ipv4="192.168.1.100",
            ipv6="2001:db8::1",
            platform="Linux",
            custom_field="custom_value",
        )

        assert message.data["hostname"] == "test-host"
        assert message.data["ipv4"] == "192.168.1.100"
        assert message.data["ipv6"] == "2001:db8::1"
        assert message.data["platform"] == "Linux"
        assert message.data["custom_field"] == "custom_value"


class TestCommandMessage:
    """Test CommandMessage class."""

    def test_command_message_basic(self):
        """Test basic command message creation."""
        message = CommandMessage(CommandType.GET_SYSTEM_INFO)

        assert message.message_type == MessageType.COMMAND
        assert message.data["command_type"] == CommandType.GET_SYSTEM_INFO
        assert message.data["parameters"] == {}
        assert message.data["timeout"] == 300

    def test_command_message_with_parameters(self):
        """Test command message with parameters and custom timeout."""
        params = {"package_name": "nginx", "version": "latest"}
        message = CommandMessage(
            CommandType.INSTALL_PACKAGE, parameters=params, timeout=600
        )

        assert message.data["command_type"] == CommandType.INSTALL_PACKAGE
        assert message.data["parameters"] == params
        assert message.data["timeout"] == 600


class TestCommandResultMessage:
    """Test CommandResultMessage class."""

    def test_command_result_message_success(self):
        """Test successful command result message."""
        message = CommandResultMessage(
            command_id="cmd-123",
            success=True,
            result="Command completed successfully",
            exit_code=0,
        )

        assert message.message_type == MessageType.COMMAND_RESULT
        assert message.data["command_id"] == "cmd-123"
        assert message.data["success"] is True
        assert message.data["result"] == "Command completed successfully"
        assert message.data["error"] is None
        assert message.data["exit_code"] == 0

    def test_command_result_message_failure(self):
        """Test failed command result message."""
        message = CommandResultMessage(
            command_id="cmd-456", success=False, error="Command failed", exit_code=1
        )

        assert message.data["success"] is False
        assert message.data["error"] == "Command failed"
        assert message.data["exit_code"] == 1


class TestHeartbeatMessage:
    """Test HeartbeatMessage class."""

    def test_heartbeat_message_basic(self):
        """Test basic heartbeat message."""
        message = HeartbeatMessage()

        assert message.message_type == MessageType.HEARTBEAT
        assert message.data["agent_status"] == "healthy"
        assert message.data["system_load"] is None

    def test_heartbeat_message_complete(self):
        """Test heartbeat message with all parameters."""
        message = HeartbeatMessage(
            agent_status="degraded",
            system_load=0.75,
            memory_usage=0.65,
            is_privileged=True,
            custom_metric=42,
        )

        assert message.data["agent_status"] == "degraded"
        assert message.data["system_load"] == 0.75
        assert message.data["memory_usage"] == 0.65
        assert message.data["is_privileged"] is True
        assert message.data["custom_metric"] == 42


class TestErrorMessage:
    """Test ErrorMessage class."""

    def test_error_message_basic(self):
        """Test basic error message."""
        message = ErrorMessage("AUTH_FAILED", "Authentication failed")

        assert message.message_type == MessageType.ERROR
        msg_dict = message.to_dict()
        assert msg_dict["error_type"] == "AUTH_FAILED"
        assert msg_dict["message"] == "Authentication failed"
        assert msg_dict["data"] == {}

    def test_error_message_with_details(self):
        """Test error message with details."""
        details = {"attempt_count": 3, "ip": "192.168.1.100"}
        message = ErrorMessage("RATE_LIMITED", "Too many attempts", details)

        msg_dict = message.to_dict()
        assert msg_dict["error_type"] == "RATE_LIMITED"
        assert msg_dict["message"] == "Too many attempts"
        assert msg_dict["data"] == details


class TestOSVersionUpdateMessage:
    """Test OSVersionUpdateMessage class."""

    def test_os_version_update_message_basic(self):
        """Test basic OS version update message."""
        message = OSVersionUpdateMessage()

        assert message.message_type == MessageType.OS_VERSION_UPDATE
        assert message.data["platform"] is None
        assert message.data["os_info"] == {}

    def test_os_version_update_message_complete(self):
        """Test OS version update message with all parameters."""
        os_info = {"name": "Ubuntu", "version": "22.04"}
        message = OSVersionUpdateMessage(
            platform="Linux",
            platform_release="5.15.0",
            platform_version="#72-Ubuntu",
            architecture="x86_64",
            processor="Intel Core i7",
            machine_architecture="x86_64",
            python_version="3.10.6",
            os_info=os_info,
            custom_field="custom_value",
        )

        assert message.data["platform"] == "Linux"
        assert message.data["platform_release"] == "5.15.0"
        assert message.data["platform_version"] == "#72-Ubuntu"
        assert message.data["architecture"] == "x86_64"
        assert message.data["processor"] == "Intel Core i7"
        assert message.data["machine_architecture"] == "x86_64"
        assert message.data["python_version"] == "3.10.6"
        assert message.data["os_info"] == os_info
        assert message.data["custom_field"] == "custom_value"


class TestHardwareUpdateMessage:
    """Test HardwareUpdateMessage class."""

    def test_hardware_update_message_basic(self):
        """Test basic hardware update message."""
        message = HardwareUpdateMessage()

        assert message.message_type == MessageType.HARDWARE_UPDATE
        assert message.data["cpu_vendor"] is None
        assert message.data["memory_total_mb"] is None

    def test_hardware_update_message_complete(self):
        """Test hardware update message with all parameters."""
        message = HardwareUpdateMessage(
            cpu_vendor="Intel",
            cpu_model="Core i7-10700K",
            cpu_cores=8,
            cpu_threads=16,
            cpu_frequency_mhz=3800,
            memory_total_mb=16384,
            storage_details="SSD 1TB",
            network_details="Ethernet 1Gbps",
            hardware_details="Workstation",
            gpu_info="NVIDIA RTX 3080",
        )

        assert message.data["cpu_vendor"] == "Intel"
        assert message.data["cpu_model"] == "Core i7-10700K"
        assert message.data["cpu_cores"] == 8
        assert message.data["cpu_threads"] == 16
        assert message.data["cpu_frequency_mhz"] == 3800
        assert message.data["memory_total_mb"] == 16384
        assert message.data["storage_details"] == "SSD 1TB"
        assert message.data["network_details"] == "Ethernet 1Gbps"
        assert message.data["hardware_details"] == "Workstation"
        assert message.data["gpu_info"] == "NVIDIA RTX 3080"


class TestUserAccessUpdateMessage:
    """Test UserAccessUpdateMessage class."""

    def test_user_access_update_message_basic(self):
        """Test basic user access update message."""
        message = UserAccessUpdateMessage()

        assert message.message_type == MessageType.USER_ACCESS_UPDATE
        assert message.data["users"] == []
        assert message.data["groups"] == []

    def test_user_access_update_message_complete(self):
        """Test user access update message with all parameters."""
        users = [{"name": "alice", "uid": 1000}, {"name": "bob", "uid": 1001}]
        groups = [{"name": "admin", "gid": 100}, {"name": "users", "gid": 1000}]

        message = UserAccessUpdateMessage(
            users=users,
            groups=groups,
            platform="Linux",
            total_users=2,
            total_groups=2,
            system_users=0,
            regular_users=2,
            system_groups=0,
            regular_groups=2,
            last_login_data="recent",
        )

        assert message.data["users"] == users
        assert message.data["groups"] == groups
        assert message.data["platform"] == "Linux"
        assert message.data["total_users"] == 2
        assert message.data["total_groups"] == 2
        assert message.data["system_users"] == 0
        assert message.data["regular_users"] == 2
        assert message.data["system_groups"] == 0
        assert message.data["regular_groups"] == 2
        assert message.data["last_login_data"] == "recent"


class TestSoftwareInventoryUpdateMessage:
    """Test SoftwareInventoryUpdateMessage class."""

    def test_software_inventory_update_message_basic(self):
        """Test basic software inventory update message."""
        message = SoftwareInventoryUpdateMessage()

        assert message.message_type == MessageType.SOFTWARE_INVENTORY_UPDATE
        assert message.data["software_packages"] == []

    def test_software_inventory_update_message_complete(self):
        """Test software inventory update message with all parameters."""
        packages = [
            {"name": "nginx", "version": "1.20.1"},
            {"name": "python3", "version": "3.10.6"},
        ]

        message = SoftwareInventoryUpdateMessage(
            software_packages=packages,
            platform="Linux",
            total_packages=2,
            collection_timestamp="2025-09-16T12:34:56Z",
            package_manager="apt",
        )

        assert message.data["software_packages"] == packages
        assert message.data["platform"] == "Linux"
        assert message.data["total_packages"] == 2
        assert message.data["collection_timestamp"] == "2025-09-16T12:34:56Z"
        assert message.data["package_manager"] == "apt"


class TestHostApprovedMessage:
    """Test HostApprovedMessage class."""

    def test_host_approved_message_basic(self):
        """Test basic host approved message."""
        message = HostApprovedMessage(host_id=123)

        assert message.message_type == MessageType.HOST_APPROVED
        assert message.data["host_id"] == 123
        assert message.data["approval_status"] == "approved"
        assert message.data["certificate"] is None

    def test_host_approved_message_complete(self):
        """Test host approved message with all parameters."""
        cert = "-----BEGIN CERTIFICATE-----\nMIIC..."
        message = HostApprovedMessage(
            host_id=456,
            approval_status="pending",
            certificate=cert,
            expiry_date="2026-09-16",
        )

        assert message.data["host_id"] == 456
        assert message.data["approval_status"] == "pending"
        assert message.data["certificate"] == cert
        assert message.data["expiry_date"] == "2026-09-16"


class TestScriptExecutionResultMessage:
    """Test ScriptExecutionResultMessage class."""

    def test_script_execution_result_message_basic(self):
        """Test basic script execution result message."""
        message = ScriptExecutionResultMessage()

        assert message.message_type == MessageType.SCRIPT_EXECUTION_RESULT
        assert message.data["success"] is True
        assert message.data["timeout"] is False

    def test_script_execution_result_message_complete(self):
        """Test script execution result message with all parameters."""
        message = ScriptExecutionResultMessage(
            script_id=789,
            execution_id="exec-abc-123",
            success=True,
            exit_code=0,
            stdout="Script output here",
            stderr="",
            execution_time=2.5,
            shell_used="/bin/bash",
            error=None,
            timeout=False,
            hostname="test-host",
            working_dir="/tmp",
        )

        assert message.data["script_id"] == 789
        assert message.data["execution_id"] == "exec-abc-123"
        assert message.data["success"] is True
        assert message.data["exit_code"] == 0
        assert message.data["stdout"] == "Script output here"
        assert message.data["stderr"] == ""
        assert message.data["execution_time"] == 2.5
        assert message.data["shell_used"] == "/bin/bash"
        assert message.data["error"] is None
        assert message.data["timeout"] is False
        assert message.data["hostname"] == "test-host"
        assert message.data["working_dir"] == "/tmp"


class TestDiagnosticCollectionResultMessage:
    """Test DiagnosticCollectionResultMessage class."""

    def test_diagnostic_collection_result_message_basic(self):
        """Test basic diagnostic collection result message."""
        message = DiagnosticCollectionResultMessage()

        assert message.message_type == MessageType.DIAGNOSTIC_COLLECTION_RESULT
        assert message.data["success"] is True

    def test_diagnostic_collection_result_message_complete(self):
        """Test diagnostic collection result message with all parameters."""
        system_logs = {"syslog": "log content"}
        config_files = {"nginx.conf": "config content"}

        message = DiagnosticCollectionResultMessage(
            collection_id="diag-001",
            success=True,
            system_logs=system_logs,
            configuration_files=config_files,
            network_info={"interfaces": ["eth0"]},
            process_info={"count": 150},
            disk_usage={"root": "75%"},
            environment_variables={"PATH": "/usr/bin"},
            agent_logs={"agent.log": "agent content"},
            error_logs={"error.log": "error content"},
            collection_size_bytes=1048576,
            files_collected=25,
            error=None,
            collection_time=30.5,
            hostname="diagnostic-host",
            compression="gzip",
        )

        assert message.data["collection_id"] == "diag-001"
        assert message.data["success"] is True
        assert message.data["system_logs"] == system_logs
        assert message.data["configuration_files"] == config_files
        assert message.data["network_info"] == {"interfaces": ["eth0"]}
        assert message.data["process_info"] == {"count": 150}
        assert message.data["disk_usage"] == {"root": "75%"}
        assert message.data["environment_variables"] == {"PATH": "/usr/bin"}
        assert message.data["agent_logs"] == {"agent.log": "agent content"}
        assert message.data["error_logs"] == {"error.log": "error content"}
        assert message.data["collection_size_bytes"] == 1048576
        assert message.data["files_collected"] == 25
        assert message.data["error"] is None
        assert message.data["collection_time"] == 30.5
        assert message.data["hostname"] == "diagnostic-host"
        assert message.data["compression"] == "gzip"


class TestMessageFactory:
    """Test message factory functions."""

    def test_create_message_system_info(self):
        """Test creating system info message from raw data."""
        raw_data = {
            "message_type": MessageType.SYSTEM_INFO,
            "data": {
                "hostname": "test-host",
                "ipv4": "192.168.1.100",
                "custom_field": "custom_value",
            },
        }

        message = create_message(raw_data)

        assert isinstance(message, SystemInfoMessage)
        assert message.data["hostname"] == "test-host"
        assert message.data["ipv4"] == "192.168.1.100"
        assert message.data["custom_field"] == "custom_value"

    def test_create_message_command(self):
        """Test creating command message from raw data."""
        raw_data = {
            "message_type": MessageType.COMMAND,
            "data": {
                "command_type": CommandType.INSTALL_PACKAGE,
                "parameters": {"package": "nginx"},
                "timeout": 600,
            },
        }

        message = create_message(raw_data)

        assert isinstance(message, CommandMessage)
        assert message.data["command_type"] == CommandType.INSTALL_PACKAGE
        assert message.data["parameters"] == {"package": "nginx"}
        assert message.data["timeout"] == 600

    def test_create_message_command_result(self):
        """Test creating command result message from raw data."""
        raw_data = {
            "message_type": MessageType.COMMAND_RESULT,
            "data": {
                "command_id": "cmd-123",
                "success": False,
                "error": "Command failed",
                "exit_code": 1,
            },
        }

        message = create_message(raw_data)

        assert isinstance(message, CommandResultMessage)
        assert message.data["command_id"] == "cmd-123"
        assert message.data["success"] is False
        assert message.data["error"] == "Command failed"
        assert message.data["exit_code"] == 1

    def test_create_message_heartbeat(self):
        """Test creating heartbeat message from raw data."""
        raw_data = {
            "message_type": MessageType.HEARTBEAT,
            "data": {
                "agent_status": "degraded",
                "system_load": 0.8,
                "custom_metric": 42,
            },
        }

        message = create_message(raw_data)

        assert isinstance(message, HeartbeatMessage)
        assert message.data["agent_status"] == "degraded"
        assert message.data["system_load"] == 0.8
        assert message.data["custom_metric"] == 42

    def test_create_message_error(self):
        """Test creating error message from raw data."""
        raw_data = {
            "message_type": MessageType.ERROR,
            "data": {
                "error_code": "TIMEOUT",
                "error_message": "Operation timed out",
                "details": {"timeout_seconds": 30},
            },
        }

        message = create_message(raw_data)

        assert isinstance(message, ErrorMessage)
        msg_dict = message.to_dict()
        assert msg_dict["error_type"] == "TIMEOUT"
        assert msg_dict["message"] == "Operation timed out"
        assert msg_dict["data"] == {"timeout_seconds": 30}

    def test_create_message_script_execution_result_special_format(self):
        """Test creating script execution result with special top-level format."""
        raw_data = {
            "message_type": MessageType.SCRIPT_EXECUTION_RESULT,
            "script_id": 123,
            "execution_id": "exec-456",
            "success": True,
            "exit_code": 0,
            "stdout": "Script output",
            "message_id": "msg-789",
            "timestamp": "2025-09-16T12:34:56Z",
        }

        message = create_message(raw_data)

        assert isinstance(message, ScriptExecutionResultMessage)
        assert message.data["script_id"] == 123
        assert message.data["execution_id"] == "exec-456"
        assert message.data["success"] is True
        assert message.data["exit_code"] == 0
        assert message.data["stdout"] == "Script output"

    def test_create_message_unknown_type_fallback(self):
        """Test creating message with unknown type falls back to base Message."""
        raw_data = {
            "message_type": "unknown_type",
            "message_id": "test-123",
            "data": {"custom": "data"},
        }

        message = create_message(raw_data)

        assert isinstance(message, Message)
        assert message.message_type == "unknown_type"
        assert message.message_id == "test-123"
        assert message.data == {"custom": "data"}

    def test_create_command_message_function(self):
        """Test create_command_message utility function."""
        result = create_command_message("install_package", {"package": "vim"})

        assert result["message_type"] == MessageType.COMMAND
        assert result["data"]["command_type"] == "install_package"
        assert result["data"]["parameters"] == {"package": "vim"}
        assert "message_id" in result
        assert "timestamp" in result

    def test_create_command_message_function_no_params(self):
        """Test create_command_message with no parameters."""
        result = create_command_message("get_system_info")

        assert result["data"]["command_type"] == "get_system_info"
        assert result["data"]["parameters"] == {}

    def test_create_host_approved_message_function(self):
        """Test create_host_approved_message utility function."""
        result = create_host_approved_message(
            123, approval_status="approved", certificate="certificate-data"
        )

        assert result["message_type"] == MessageType.HOST_APPROVED
        assert result["data"]["host_id"] == 123
        assert result["data"]["approval_status"] == "approved"
        assert result["data"]["certificate"] == "certificate-data"

    def test_create_host_approved_message_function_defaults(self):
        """Test create_host_approved_message with defaults."""
        result = create_host_approved_message(456)

        assert result["data"]["host_id"] == 456
        assert result["data"]["approval_status"] == "approved"
        assert result["data"]["certificate"] is None
