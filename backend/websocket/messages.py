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

    # Server -> Agent messages
    COMMAND = "command"
    UPDATE_REQUEST = "update_request"
    PING = "ping"
    SHUTDOWN = "shutdown"


class CommandType(str, Enum):
    """Types of commands that can be sent to agents."""

    EXECUTE_SHELL = "execute_shell"
    INSTALL_PACKAGE = "install_package"
    UPDATE_SYSTEM = "update_system"
    RESTART_SERVICE = "restart_service"
    GET_SYSTEM_INFO = "get_system_info"
    GET_INSTALLED_PACKAGES = "get_installed_packages"
    GET_AVAILABLE_UPDATES = "get_available_updates"
    REBOOT_SYSTEM = "reboot_system"


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

    def __init__(
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
    # Default fallback
    return Message.from_dict(raw_data)
