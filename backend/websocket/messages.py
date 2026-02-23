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
    COMMAND_ACKNOWLEDGMENT = (
        "command_acknowledgment"  # Agent confirms receipt of command
    )
    ERROR = "error"
    OS_VERSION_UPDATE = "os_version_update"
    HARDWARE_UPDATE = "hardware_update"
    USER_ACCESS_UPDATE = "user_access_update"
    SOFTWARE_INVENTORY_UPDATE = "software_inventory_update"
    PACKAGE_UPDATES_UPDATE = "package_updates_update"
    AVAILABLE_PACKAGES_UPDATE = "available_packages_update"
    AVAILABLE_PACKAGES_BATCH_START = "available_packages_batch_start"
    AVAILABLE_PACKAGES_BATCH = "available_packages_batch"
    AVAILABLE_PACKAGES_BATCH_END = "available_packages_batch_end"
    UPDATE_APPLY_RESULT = "update_apply_result"
    SCRIPT_EXECUTION_RESULT = "script_execution_result"
    REBOOT_STATUS_UPDATE = "reboot_status_update"
    DIAGNOSTIC_COLLECTION_RESULT = "diagnostic_collection_result"
    HOST_CERTIFICATES_UPDATE = "host_certificates_update"
    ROLE_DATA = "role_data"
    THIRD_PARTY_REPOSITORY_UPDATE = "third_party_repository_update"
    ANTIVIRUS_STATUS_UPDATE = "antivirus_status_update"
    COMMERCIAL_ANTIVIRUS_STATUS_UPDATE = "commercial_antivirus_status_update"
    FIREWALL_STATUS_UPDATE = "firewall_status_update"
    GRAYLOG_STATUS_UPDATE = "graylog_status_update"
    HOSTNAME_CHANGED = "hostname_changed"

    # Generic deployment responses
    FILE_DEPLOYMENT_RESULT = "file_deployment_result"
    COMMAND_SEQUENCE_PROGRESS = "command_sequence_progress"
    COMMAND_SEQUENCE_RESULT = "command_sequence_result"

    # Child Host / Virtualization responses
    VIRTUALIZATION_SUPPORT_UPDATE = "virtualization_support_update"
    CHILD_HOST_LIST_UPDATE = "child_host_list_update"
    CHILD_HOST_CREATED = "child_host_created"
    CHILD_HOST_CREATION_PROGRESS = "child_host_creation_progress"
    CHILD_HOST_CREATION_FAILED = "child_host_creation_failed"
    CHILD_HOST_DELETED = "child_host_deleted"
    CHILD_HOST_STARTED = "child_host_started"
    CHILD_HOST_STOPPED = "child_host_stopped"
    CHILD_HOST_RESTARTED = "child_host_restarted"
    CHILD_HOST_STATUS_UPDATE = "child_host_status_update"
    LXD_INITIALIZED = "lxd_initialized"
    LXD_INITIALIZATION_FAILED = "lxd_initialization_failed"
    VMM_INITIALIZED = "vmm_initialized"
    VMM_INITIALIZATION_FAILED = "vmm_initialization_failed"
    KVM_INITIALIZED = "kvm_initialized"
    KVM_INITIALIZATION_FAILED = "kvm_initialization_failed"
    KVM_MODULES_ENABLED = "kvm_modules_enabled"
    KVM_MODULES_ENABLE_FAILED = "kvm_modules_enable_failed"
    KVM_MODULES_DISABLED = "kvm_modules_disabled"
    KVM_MODULES_DISABLE_FAILED = "kvm_modules_disable_failed"
    BHYVE_INITIALIZED = "bhyve_initialized"
    BHYVE_INITIALIZATION_FAILED = "bhyve_initialization_failed"

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
    COLLECT_CERTIFICATES = "collect_certificates"
    DEPLOY_ANTIVIRUS = "deploy_antivirus"
    ENABLE_ANTIVIRUS = "enable_antivirus"
    DISABLE_ANTIVIRUS = "disable_antivirus"
    REMOVE_ANTIVIRUS = "remove_antivirus"
    DEPLOY_FIREWALL = "deploy_firewall"
    ENABLE_FIREWALL = "enable_firewall"
    DISABLE_FIREWALL = "disable_firewall"
    RESTART_FIREWALL = "restart_firewall"
    APPLY_FIREWALL_ROLES = "apply_firewall_roles"
    REMOVE_FIREWALL_PORTS = "remove_firewall_ports"
    ATTACH_TO_GRAYLOG = "attach_to_graylog"
    ENABLE_PACKAGE_MANAGER = "enable_package_manager"
    CREATE_HOST_USER = "create_host_user"
    CREATE_HOST_GROUP = "create_host_group"
    DELETE_HOST_USER = "delete_host_user"
    DELETE_HOST_GROUP = "delete_host_group"
    REFRESH_USER_ACCESS = "refresh_user_access"
    CHANGE_HOSTNAME = "change_hostname"

    # Generic deployment commands
    DEPLOY_FILES = "deploy_files"
    EXECUTE_COMMAND_SEQUENCE = "execute_command_sequence"

    # Child Host / Virtualization Commands
    CHECK_VIRTUALIZATION_SUPPORT = "check_virtualization_support"
    CREATE_CHILD_HOST = "create_child_host"
    DELETE_CHILD_HOST = "delete_child_host"
    START_CHILD_HOST = "start_child_host"
    STOP_CHILD_HOST = "stop_child_host"
    RESTART_CHILD_HOST = "restart_child_host"
    LIST_CHILD_HOSTS = "list_child_hosts"
    CHILD_HOST_STATUS = "child_host_status"
    INITIALIZE_LXD = "initialize_lxd"
    INITIALIZE_VMM = "initialize_vmm"
    INITIALIZE_KVM = "initialize_kvm"
    INITIALIZE_BHYVE = "initialize_bhyve"
    ENABLE_KVM_MODULES = "enable_kvm_modules"
    DISABLE_KVM_MODULES = "disable_kvm_modules"


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
        is_privileged: bool = None,
        **kwargs
    ):
        data = {
            "agent_status": agent_status,
            "system_load": system_load,
            "memory_usage": memory_usage,
            "is_privileged": is_privileged,
            **kwargs,
        }
        super().__init__(MessageType.HEARTBEAT, data)


class ErrorMessage(Message):
    """Error message for communication issues."""

    def __init__(
        self, error_code: str, error_message: str, details: Dict[str, Any] = None
    ):
        # Store error info for custom to_dict method
        self._error_code = error_code
        self._error_message = error_message
        self._details = details or {}
        super().__init__(MessageType.ERROR, {})

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert error message to dictionary for JSON serialization.

        Uses the standard error format expected by agents:
        - error_type: The error code/type
        - message: The human-readable error message
        - data: Additional details (empty dict if none)
        """
        return {
            "message_type": self.message_type,
            "error_type": self._error_code,
            "message": self._error_message,
            "data": self._details,
        }


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
        host_id: str,
        host_token: str = None,
        approval_status: str = "approved",
        certificate: str = None,
        **kwargs
    ):
        data = {
            "host_id": host_id,  # Keep for backward compatibility
            "host_token": host_token,  # New secure token
            "approval_status": approval_status,
            "certificate": certificate,
            **kwargs,
        }
        super().__init__(MessageType.HOST_APPROVED, data)


class ScriptExecutionResultMessage(Message):
    """Message sent from agent to server with script execution results."""

    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        script_id: str = None,
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

    def __init__(
        self,
        collection_id: str = None,
        success: bool = True,
        collection_size_bytes: int = None,
        files_collected: int = None,
        error: str = None,
        collection_time: float = None,
        hostname: str = None,
        **kwargs
    ):
        _diagnostic_fields = [
            "system_logs",
            "configuration_files",
            "network_info",
            "process_info",
            "disk_usage",
            "environment_variables",
            "agent_logs",
            "error_logs",
        ]
        data = {
            "collection_id": collection_id,
            "success": success,
            "collection_size_bytes": collection_size_bytes,
            "files_collected": files_collected,
            "error": error,
            "collection_time": collection_time,
            "hostname": hostname,
        }
        for field in _diagnostic_fields:
            data[field] = kwargs.pop(field, None)
        data.update(kwargs)
        super().__init__(MessageType.DIAGNOSTIC_COLLECTION_RESULT, data)


# Message factory for creating messages from raw data
def create_message(  # NOSONAR
    raw_data: Dict[str, Any],
) -> Message:
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
            is_privileged=data.get("is_privileged"),
            **{
                k: v
                for k, v in data.items()
                if k
                not in ["agent_status", "system_load", "memory_usage", "is_privileged"]
            }
        )
    if message_type == MessageType.ERROR:
        # Handle both old format (data.error_code) and new format (error_type at top level)
        data = raw_data.get("data", {})
        error_code = raw_data.get("error_type") or data.get("error_code", "")
        error_message = raw_data.get("message") or data.get("error_message", "")
        details = data.get("details") if data else raw_data.get("data", {})
        return ErrorMessage(
            error_code=error_code,
            error_message=error_message,
            details=details if isinstance(details, dict) else {},
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
    host_id: str,
    host_token: str = None,
    approval_status: str = "approved",
    certificate: str = None,
) -> Dict[str, Any]:
    """Create a host approved message dictionary for sending to agents."""
    message = HostApprovedMessage(
        host_id=host_id,
        host_token=host_token,
        approval_status=approval_status,
        certificate=certificate,
    )
    return message.to_dict()
