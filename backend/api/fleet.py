"""
Fleet management REST API endpoints for sending commands to agents
and managing the fleet of connected systems.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import CommandMessage, CommandType, MessageType

router = APIRouter()


# Pydantic models for API requests
class CommandRequest(BaseModel):
    command_type: CommandType
    parameters: dict = {}
    timeout: int = 300


class ShellCommandRequest(BaseModel):
    command: str
    timeout: int = 300
    working_directory: Optional[str] = None


class PackageRequest(BaseModel):
    package_name: str
    version: Optional[str] = None
    timeout: int = 300


class ServiceRequest(BaseModel):
    service_name: str
    timeout: int = 300


class BroadcastRequest(BaseModel):
    message: str
    message_type: MessageType = MessageType.COMMAND


# Fleet status and information endpoints


@router.get("/fleet/status")
async def get_fleet_status(dependencies=Depends(JWTBearer())):
    """Get status of all connected agents."""
    agents = connection_manager.get_active_agents()
    return {"total_agents": len(agents), "agents": agents}


@router.get("/fleet/agents")
async def list_agents(dependencies=Depends(JWTBearer())):
    """List all connected agents with their details."""
    return connection_manager.get_active_agents()


@router.get("/fleet/agent/{hostname}")
async def get_agent(hostname: str, dependencies=Depends(JWTBearer())):
    """Get details of a specific agent by hostname."""
    agent = connection_manager.get_agent_by_hostname(hostname)
    if not agent:
        raise HTTPException(
            status_code=404, detail=f"Agent with hostname {hostname} not found"
        )
    return agent


# Command sending endpoints


@router.post("/fleet/agent/{hostname}/command")
async def send_command_to_agent(
    hostname: str, command: CommandRequest, dependencies=Depends(JWTBearer())
):
    """Send a command to a specific agent by hostname."""
    # Check if agent is connected
    if not connection_manager.get_agent_by_hostname(hostname):
        raise HTTPException(
            status_code=404, detail=f"Agent {hostname} is not connected"
        )

    # Create and send command
    cmd_message = CommandMessage(
        command.command_type, command.parameters, command.timeout
    )
    success = await connection_manager.send_to_hostname(hostname, cmd_message.to_dict())

    if not success:
        raise HTTPException(
            status_code=500, detail=f"Failed to send command to {hostname}"
        )

    return {
        "status": "sent",
        "command_id": cmd_message.message_id,
        "message": _("Command {command_type} sent to {hostname}").format(
            command_type=command.command_type, hostname=hostname
        ),
    }


@router.post("/fleet/agent/{hostname}/shell")
async def execute_shell_command(
    hostname: str, shell_request: ShellCommandRequest, dependencies=Depends(JWTBearer())
):
    """Execute a shell command on a specific agent."""
    if not connection_manager.get_agent_by_hostname(hostname):
        raise HTTPException(
            status_code=404, detail=f"Agent {hostname} is not connected"
        )

    parameters = {
        "command": shell_request.command,
        "working_directory": shell_request.working_directory,
    }

    cmd_message = CommandMessage(
        CommandType.EXECUTE_SHELL, parameters, shell_request.timeout
    )
    success = await connection_manager.send_to_hostname(hostname, cmd_message.to_dict())

    if not success:
        raise HTTPException(
            status_code=500, detail=f"Failed to send shell command to {hostname}"
        )

    return {
        "status": "sent",
        "command_id": cmd_message.message_id,
        "command": shell_request.command,
        "message": _("Shell command sent to {hostname}").format(hostname=hostname),
    }


@router.post("/fleet/agent/{hostname}/install-package")
async def install_package(
    hostname: str, package_request: PackageRequest, dependencies=Depends(JWTBearer())
):
    """Install a package on a specific agent."""
    if not connection_manager.get_agent_by_hostname(hostname):
        raise HTTPException(
            status_code=404, detail=f"Agent {hostname} is not connected"
        )

    parameters = {
        "package_name": package_request.package_name,
        "version": package_request.version,
    }

    cmd_message = CommandMessage(
        CommandType.INSTALL_PACKAGE, parameters, package_request.timeout
    )
    success = await connection_manager.send_to_hostname(hostname, cmd_message.to_dict())

    if not success:
        raise HTTPException(
            status_code=500, detail=f"Failed to send install command to {hostname}"
        )

    return {
        "status": "sent",
        "command_id": cmd_message.message_id,
        "package": package_request.package_name,
        "message": _("Package installation command sent to {hostname}").format(
            hostname=hostname
        ),
    }


@router.post("/fleet/agent/{hostname}/restart-service")
async def restart_service(
    hostname: str, service_request: ServiceRequest, dependencies=Depends(JWTBearer())
):
    """Restart a service on a specific agent."""
    if not connection_manager.get_agent_by_hostname(hostname):
        raise HTTPException(
            status_code=404, detail=f"Agent {hostname} is not connected"
        )

    parameters = {"service_name": service_request.service_name}

    cmd_message = CommandMessage(
        CommandType.RESTART_SERVICE, parameters, service_request.timeout
    )
    success = await connection_manager.send_to_hostname(hostname, cmd_message.to_dict())

    if not success:
        raise HTTPException(
            status_code=500, detail=f"Failed to send restart command to {hostname}"
        )

    return {
        "status": "sent",
        "command_id": cmd_message.message_id,
        "service": service_request.service_name,
        "message": _("Service restart command sent to {hostname}").format(
            hostname=hostname
        ),
    }


@router.post("/fleet/agent/{hostname}/update-system")
async def update_system(hostname: str, dependencies=Depends(JWTBearer())):
    """Trigger system updates on a specific agent."""
    if not connection_manager.get_agent_by_hostname(hostname):
        raise HTTPException(
            status_code=404, detail=f"Agent {hostname} is not connected"
        )

    cmd_message = CommandMessage(
        CommandType.UPDATE_SYSTEM, {}, 1800
    )  # 30 minute timeout
    success = await connection_manager.send_to_hostname(hostname, cmd_message.to_dict())

    if not success:
        raise HTTPException(
            status_code=500, detail=f"Failed to send update command to {hostname}"
        )

    return {
        "status": "sent",
        "command_id": cmd_message.message_id,
        "message": _("System update command sent to {hostname}").format(
            hostname=hostname
        ),
    }


@router.post("/fleet/agent/{hostname}/reboot")
async def reboot_system(hostname: str, dependencies=Depends(JWTBearer())):
    """Reboot a specific agent system."""
    if not connection_manager.get_agent_by_hostname(hostname):
        raise HTTPException(
            status_code=404, detail=f"Agent {hostname} is not connected"
        )

    cmd_message = CommandMessage(
        CommandType.REBOOT_SYSTEM, {}, 60
    )  # Short timeout before reboot
    success = await connection_manager.send_to_hostname(hostname, cmd_message.to_dict())

    if not success:
        raise HTTPException(
            status_code=500, detail=f"Failed to send reboot command to {hostname}"
        )

    return {
        "status": "sent",
        "command_id": cmd_message.message_id,
        "message": _("Reboot command sent to {hostname}").format(hostname=hostname),
    }


# Broadcast endpoints


@router.post("/fleet/broadcast/command")
async def broadcast_command(command: CommandRequest, dependencies=Depends(JWTBearer())):
    """Broadcast a command to all connected agents."""
    cmd_message = CommandMessage(
        command.command_type, command.parameters, command.timeout
    )
    sent_count = await connection_manager.broadcast_to_all(cmd_message.to_dict())

    return {
        "status": "broadcast",
        "command_id": cmd_message.message_id,
        "sent_to": sent_count,
        "message": _("Command {command_type} broadcast to {sent_count} agents").format(
            command_type=command.command_type, sent_count=sent_count
        ),
    }


@router.post("/fleet/broadcast/shell")
async def broadcast_shell_command(
    shell_request: ShellCommandRequest, dependencies=Depends(JWTBearer())
):
    """Broadcast a shell command to all connected agents."""
    parameters = {
        "command": shell_request.command,
        "working_directory": shell_request.working_directory,
    }

    cmd_message = CommandMessage(
        CommandType.EXECUTE_SHELL, parameters, shell_request.timeout
    )
    sent_count = await connection_manager.broadcast_to_all(cmd_message.to_dict())

    return {
        "status": "broadcast",
        "command_id": cmd_message.message_id,
        "command": shell_request.command,
        "sent_to": sent_count,
        "message": _("Shell command broadcast to {sent_count} agents").format(
            sent_count=sent_count
        ),
    }


@router.post("/fleet/platform/{platform}/command")
async def send_command_to_platform(
    platform: str, command: CommandRequest, dependencies=Depends(JWTBearer())
):
    """Send a command to all agents of a specific platform (e.g., 'Linux', 'Darwin', 'Windows')."""
    cmd_message = CommandMessage(
        command.command_type, command.parameters, command.timeout
    )
    sent_count = await connection_manager.broadcast_to_platform(
        platform, cmd_message.to_dict()
    )

    if sent_count == 0:
        raise HTTPException(
            status_code=404, detail=f"No agents found for platform {platform}"
        )

    return {
        "status": "sent",
        "command_id": cmd_message.message_id,
        "platform": platform,
        "sent_to": sent_count,
        "message": _(
            "Command {command_type} sent to {sent_count} {platform} agents"
        ).format(
            command_type=command.command_type, sent_count=sent_count, platform=platform
        ),
    }
