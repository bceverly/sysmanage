"""
Message protocol definitions for SysManage WebSocket communication.
Defines the structure and types of messages exchanged between server and agents.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict


class MessageType(str, Enum):
    """Types of messages in the SysManage protocol."""

    # Agent -> Server messages
    SYSTEM_INFO = "system_info"
    HEARTBEAT = "heartbeat"
    COMMAND_RESULT = "command_result"
    ERROR = "error"
    OS_VERSION_UPDATE = "os_version_update"
    HARDWARE_UPDATE = "hardware_update"
    USER_ACCESS_UPDATE = "user_access_update"
    SOFTWARE_INVENTORY_UPDATE = "software_inventory_update"
    PACKAGE_UPDATES_UPDATE = "package_updates_update"
    UPDATE_APPLY_RESULT = "update_apply_result"
    SCRIPT_EXECUTION_RESULT = "script_execution_result"
    REBOOT_STATUS_UPDATE = "reboot_status_update"
    DIAGNOSTIC_COLLECTION_RESULT = "diagnostic_collection_result"

    # Server -> Agent messages
    COMMAND = "command"
    UPDATE_REQUEST = "update_request"
    PING = "ping"
    SHUTDOWN = "shutdown"
    HOST_APPROVED = "host_approved"


class CommandType(str, Enum):
    """Types of commands that can be sent to agents."""

    EXECUTE_SHELL = "execute_shell"
    INSTALL_PACKAGE = "install_package"
    UPDATE_SYSTEM = "update_system"
    APPLY_UPDATES = "apply_updates"
    RESTART_SERVICE = "restart_service"
    GET_SYSTEM_INFO = "get_system_info"
    GET_INSTALLED_PACKAGES = "get_installed_packages"
    GET_AVAILABLE_UPDATES = "get_available_updates"
    REBOOT_SYSTEM = "reboot_system"
    EXECUTE_SCRIPT = "execute_script"
    CHECK_REBOOT_STATUS = "check_reboot_status"
    COLLECT_DIAGNOSTICS = "collect_diagnostics"


class Message:
    """Base message class for all SysManage WebSocket messages."""

    def __init__(
        self,
        message_type: MessageType,
        data: Dict[str, Any] = None,
        message_id: str = None,
    ):
        self.message_type = message_type
        self.message_id = message_id or str(uuid.uuid4())
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.data = data or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary for JSON serialization."""
        return {
            "message_type": self.message_type,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Create message from dictionary."""
        message = cls(
            message_type=data.get("message_type"),
            data=data.get("data", {}),
            message_id=data.get("message_id"),
        )
        if "timestamp" in data:
            message.timestamp = data["timestamp"]
        return message


class SystemInfoMessage(Message):
    """Message containing agent system information."""

    def __init__(
        self,
        hostname: str,
        ipv4: str = None,
        ipv6: str = None,
        platform: str = None,
        **kwargs
    ):
        data = {
            "hostname": hostname,
            "ipv4": ipv4,
            "ipv6": ipv6,
            "platform": platform,
            **kwargs,
        }
        super().__init__(MessageType.SYSTEM_INFO, data)


class CommandMessage(Message):
    """Message containing a command to execute on an agent."""

    def __init__(
        self,
        command_type: CommandType,
        parameters: Dict[str, Any] = None,
        timeout: int = 300,
    ):
        data = {
            "command_type": command_type,
            "parameters": parameters or {},
            "timeout": timeout,
        }
        super().__init__(MessageType.COMMAND, data)


class CommandResultMessage(Message):
    """Message containing the result of a command execution."""

    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        command_id: str,
        success: bool,
        result: Any = None,
        error: str = None,
        exit_code: int = None,
    ):
        data = {
            "command_id": command_id,
            "success": success,
            "result": result,
            "error": error,
            "exit_code": exit_code,
        }
        super().__init__(MessageType.COMMAND_RESULT, data)


class HeartbeatMessage(Message):
    """Periodic heartbeat message from agent to server."""

    def __init__(
        self,
        agent_status: str = "healthy",
        system_load: float = None,
        memory_usage: float = None,
    ):
        data = {
            "agent_status": agent_status,
            "system_load": system_load,
            "memory_usage": memory_usage,
        }
        super().__init__(MessageType.HEARTBEAT, data)


class ErrorMessage(Message):
    """Error message for communication issues."""

    def __init__(
        self, error_code: str, error_message: str, details: Dict[str, Any] = None
    ):
        data = {
            "error_code": error_code,
            "error_message": error_message,
            "details": details or {},
        }
        super().__init__(MessageType.ERROR, data)


class OSVersionUpdateMessage(Message):
    """Message containing OS version information from agent."""

    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        platform: str = None,
        platform_release: str = None,
        platform_version: str = None,
        architecture: str = None,
        processor: str = None,
        machine_architecture: str = None,
        python_version: str = None,
        os_info: Dict[str, Any] = None,
        **kwargs
    ):
        data = {
            "platform": platform,
            "platform_release": platform_release,
            "platform_version": platform_version,
            "architecture": architecture,
            "processor": processor,
            "machine_architecture": machine_architecture,
            "python_version": python_version,
            "os_info": os_info or {},
            **kwargs,
        }
        super().__init__(MessageType.OS_VERSION_UPDATE, data)


class HardwareUpdateMessage(Message):
    """Message containing hardware information from agent."""

    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        cpu_vendor: str = None,
        cpu_model: str = None,
        cpu_cores: int = None,
        cpu_threads: int = None,
        cpu_frequency_mhz: int = None,
        memory_total_mb: int = None,
        storage_details: str = None,
        network_details: str = None,
        hardware_details: str = None,
        **kwargs
    ):
        data = {
            "cpu_vendor": cpu_vendor,
            "cpu_model": cpu_model,
            "cpu_cores": cpu_cores,
            "cpu_threads": cpu_threads,
            "cpu_frequency_mhz": cpu_frequency_mhz,
            "memory_total_mb": memory_total_mb,
            "storage_details": storage_details,
            "network_details": network_details,
            "hardware_details": hardware_details,
            **kwargs,
        }
        super().__init__(MessageType.HARDWARE_UPDATE, data)


class UserAccessUpdateMessage(Message):
    """Message containing user access information from agent."""

    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        users: list = None,
        groups: list = None,
        platform: str = None,
        total_users: int = None,
        total_groups: int = None,
        system_users: int = None,
        regular_users: int = None,
        system_groups: int = None,
        regular_groups: int = None,
        **kwargs
    ):
        data = {
            "users": users or [],
            "groups": groups or [],
            "platform": platform,
            "total_users": total_users,
            "total_groups": total_groups,
            "system_users": system_users,
            "regular_users": regular_users,
            "system_groups": system_groups,
            "regular_groups": regular_groups,
            **kwargs,
        }
        super().__init__(MessageType.USER_ACCESS_UPDATE, data)


class SoftwareInventoryUpdateMessage(Message):
    """Message containing software inventory information from agent."""

    def __init__(
        self,
        software_packages: list = None,
        platform: str = None,
        total_packages: int = None,
        collection_timestamp: str = None,
        **kwargs
    ):
        data = {
            "software_packages": software_packages or [],
            "platform": platform,
            "total_packages": total_packages,
            "collection_timestamp": collection_timestamp,
            **kwargs,
        }
        super().__init__(MessageType.SOFTWARE_INVENTORY_UPDATE, data)


class HostApprovedMessage(Message):
    """Message sent from server to agent when host is approved."""

    def __init__(
        self,
        host_id: int,
        approval_status: str = "approved",
        certificate: str = None,
        **kwargs
    ):
        data = {
            "host_id": host_id,
            "approval_status": approval_status,
            "certificate": certificate,
            **kwargs,
        }
        super().__init__(MessageType.HOST_APPROVED, data)


class ScriptExecutionResultMessage(Message):
    """Message sent from agent to server with script execution results."""

    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        script_id: int = None,
        execution_id: str = None,
        success: bool = True,
        exit_code: int = None,
        stdout: str = None,
        stderr: str = None,
        execution_time: float = None,
        shell_used: str = None,
        error: str = None,
        timeout: bool = False,
        hostname: str = None,
        **kwargs
    ):
        data = {
            "script_id": script_id,
            "execution_id": execution_id,
            "success": success,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "execution_time": execution_time,
            "shell_used": shell_used,
            "error": error,
            "timeout": timeout,
            "hostname": hostname,
            **kwargs,
        }
        super().__init__(MessageType.SCRIPT_EXECUTION_RESULT, data)


class DiagnosticCollectionResultMessage(Message):
    """Message sent from agent to server with diagnostic collection results."""

    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        collection_id: str = None,
        success: bool = True,
        system_logs: dict = None,
        configuration_files: dict = None,
        network_info: dict = None,
        process_info: dict = None,
        disk_usage: dict = None,
        environment_variables: dict = None,
        agent_logs: dict = None,
        error_logs: dict = None,
        collection_size_bytes: int = None,
        files_collected: int = None,
        error: str = None,
        collection_time: float = None,
        hostname: str = None,
        **kwargs
    ):
        data = {
            "collection_id": collection_id,
            "success": success,
            "system_logs": system_logs,
            "configuration_files": configuration_files,
            "network_info": network_info,
            "process_info": process_info,
            "disk_usage": disk_usage,
            "environment_variables": environment_variables,
            "agent_logs": agent_logs,
            "error_logs": error_logs,
            "collection_size_bytes": collection_size_bytes,
            "files_collected": files_collected,
            "error": error,
            "collection_time": collection_time,
            "hostname": hostname,
            **kwargs,
        }
        super().__init__(MessageType.DIAGNOSTIC_COLLECTION_RESULT, data)


# Message factory for creating messages from raw data
def create_message(raw_data: Dict[str, Any]) -> Message:
    """Create appropriate message object from raw dictionary data."""
    message_type = raw_data.get("message_type")

    if message_type == MessageType.SYSTEM_INFO:
        data = raw_data.get("data", {})
        hostname = data.get("hostname", "")
        return SystemInfoMessage(
            hostname=hostname,
            ipv4=data.get("ipv4"),
            ipv6=data.get("ipv6"),
            platform=data.get("platform"),
            **{
                k: v
                for k, v in data.items()
                if k not in ["hostname", "ipv4", "ipv6", "platform"]
            }
        )
    if message_type == MessageType.COMMAND:
        data = raw_data.get("data", {})
        command_type = data.get("command_type", "")
        return CommandMessage(
            command_type=command_type,
            parameters=data.get("parameters", {}),
            timeout=data.get("timeout", 300),
        )
    if message_type == MessageType.COMMAND_RESULT:
        data = raw_data.get("data", {})
        return CommandResultMessage(
            command_id=data.get("command_id", ""),
            success=data.get("success", False),
            result=data.get("result"),
            error=data.get("error"),
            exit_code=data.get("exit_code"),
        )
    if message_type == MessageType.HEARTBEAT:
        data = raw_data.get("data", {})
        return HeartbeatMessage(
            agent_status=data.get("agent_status", "healthy"),
            system_load=data.get("system_load"),
            memory_usage=data.get("memory_usage"),
        )
    if message_type == MessageType.ERROR:
        data = raw_data.get("data", {})
        return ErrorMessage(
            error_code=data.get("error_code", ""),
            error_message=data.get("error_message", ""),
            details=data.get("details"),
        )
    if message_type == MessageType.OS_VERSION_UPDATE:
        data = raw_data.get("data", {})
        return OSVersionUpdateMessage(
            platform=data.get("platform"),
            platform_release=data.get("platform_release"),
            platform_version=data.get("platform_version"),
            architecture=data.get("architecture"),
            processor=data.get("processor"),
            machine_architecture=data.get("machine_architecture"),
            python_version=data.get("python_version"),
            os_info=data.get("os_info"),
            **{
                k: v
                for k, v in data.items()
                if k
                not in [
                    "platform",
                    "platform_release",
                    "platform_version",
                    "architecture",
                    "processor",
                    "machine_architecture",
                    "python_version",
                    "os_info",
                ]
            }
        )
    if message_type == MessageType.HARDWARE_UPDATE:
        data = raw_data.get("data", {})
        return HardwareUpdateMessage(
            cpu_vendor=data.get("cpu_vendor"),
            cpu_model=data.get("cpu_model"),
            cpu_cores=data.get("cpu_cores"),
            cpu_threads=data.get("cpu_threads"),
            cpu_frequency_mhz=data.get("cpu_frequency_mhz"),
            memory_total_mb=data.get("memory_total_mb"),
            storage_details=data.get("storage_details"),
            network_details=data.get("network_details"),
            hardware_details=data.get("hardware_details"),
            **{
                k: v
                for k, v in data.items()
                if k
                not in [
                    "cpu_vendor",
                    "cpu_model",
                    "cpu_cores",
                    "cpu_threads",
                    "cpu_frequency_mhz",
                    "memory_total_mb",
                    "storage_details",
                    "network_details",
                    "hardware_details",
                ]
            }
        )
    if message_type == MessageType.USER_ACCESS_UPDATE:
        data = raw_data.get("data", {})
        return UserAccessUpdateMessage(
            users=data.get("users"),
            groups=data.get("groups"),
            platform=data.get("platform"),
            total_users=data.get("total_users"),
            total_groups=data.get("total_groups"),
            system_users=data.get("system_users"),
            regular_users=data.get("regular_users"),
            system_groups=data.get("system_groups"),
            regular_groups=data.get("regular_groups"),
            **{
                k: v
                for k, v in data.items()
                if k
                not in [
                    "users",
                    "groups",
                    "platform",
                    "total_users",
                    "total_groups",
                    "system_users",
                    "regular_users",
                    "system_groups",
                    "regular_groups",
                ]
            }
        )
    if message_type == MessageType.SOFTWARE_INVENTORY_UPDATE:
        data = raw_data.get("data", {})
        return SoftwareInventoryUpdateMessage(
            software_packages=data.get("software_packages"),
            platform=data.get("platform"),
            total_packages=data.get("total_packages"),
            collection_timestamp=data.get("collection_timestamp"),
            **{
                k: v
                for k, v in data.items()
                if k
                not in [
                    "software_packages",
                    "platform",
                    "total_packages",
                    "collection_timestamp",
                ]
            }
        )
    if message_type == MessageType.HOST_APPROVED:
        data = raw_data.get("data", {})
        return HostApprovedMessage(
            host_id=data.get("host_id"),
            approval_status=data.get("approval_status", "approved"),
            certificate=data.get("certificate"),
            **{
                k: v
                for k, v in data.items()
                if k not in ["host_id", "approval_status", "certificate"]
            }
        )
    if message_type == MessageType.SCRIPT_EXECUTION_RESULT:
        # Script execution results come with data at the top level, not under a 'data' field
        # Extract all fields except message_type, message_id, and timestamp
        script_data = {
            k: v
            for k, v in raw_data.items()
            if k not in ["message_type", "message_id", "timestamp"]
        }
        return ScriptExecutionResultMessage(
            script_id=script_data.get("script_id"),
            execution_id=script_data.get("execution_id"),
            success=script_data.get("success", True),
            exit_code=script_data.get("exit_code"),
            stdout=script_data.get("stdout"),
            stderr=script_data.get("stderr"),
            execution_time=script_data.get("execution_time"),
            shell_used=script_data.get("shell_used"),
            error=script_data.get("error"),
            timeout=script_data.get("timeout", False),
            hostname=script_data.get("hostname"),
            **{
                k: v
                for k, v in script_data.items()
                if k
                not in [
                    "script_id",
                    "execution_id",
                    "success",
                    "exit_code",
                    "stdout",
                    "stderr",
                    "execution_time",
                    "shell_used",
                    "error",
                    "timeout",
                    "hostname",
                ]
            }
        )
    if message_type == MessageType.DIAGNOSTIC_COLLECTION_RESULT:
        data = raw_data.get("data", {})
        return DiagnosticCollectionResultMessage(
            collection_id=data.get("collection_id"),
            success=data.get("success", True),
            system_logs=data.get("system_logs"),
            configuration_files=data.get("configuration_files"),
            network_info=data.get("network_info"),
            process_info=data.get("process_info"),
            disk_usage=data.get("disk_usage"),
            environment_variables=data.get("environment_variables"),
            agent_logs=data.get("agent_logs"),
            error_logs=data.get("error_logs"),
            collection_size_bytes=data.get("collection_size_bytes"),
            files_collected=data.get("files_collected"),
            error=data.get("error"),
            collection_time=data.get("collection_time"),
            hostname=data.get("hostname"),
            **{
                k: v
                for k, v in data.items()
                if k
                not in [
                    "collection_id",
                    "success",
                    "system_logs",
                    "configuration_files",
                    "network_info",
                    "process_info",
                    "disk_usage",
                    "environment_variables",
                    "agent_logs",
                    "error_logs",
                    "collection_size_bytes",
                    "files_collected",
                    "error",
                    "collection_time",
                    "hostname",
                ]
            }
        )
    # Default fallback
    return Message.from_dict(raw_data)


def create_command_message(
    command_type: str, parameters: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Create a command message dictionary for sending to agents."""
    message = CommandMessage(command_type=command_type, parameters=parameters or {})
    return message.to_dict()


def create_host_approved_message(
    host_id: int, approval_status: str = "approved", certificate: str = None
) -> Dict[str, Any]:
    """Create a host approved message dictionary for sending to agents."""
    message = HostApprovedMessage(
        host_id=host_id, approval_status=approval_status, certificate=certificate
    )
    return message.to_dict()
