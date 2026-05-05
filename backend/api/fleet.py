"""
Fleet management REST API endpoints for sending commands to agents
and managing the fleet of connected systems.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.error_constants import error_host_not_found
from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import CommandMessage, CommandType, MessageType
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)
router = APIRouter()
queue_ops = QueueOperations()


# Pydantic models for API requests
class CommandRequest(BaseModel):
    """Request model for fleet commands."""

    command_type: CommandType
    parameters: dict = {}
    timeout: int = 300


class ShellCommandRequest(BaseModel):
    """Request model for shell commands."""

    command: str
    timeout: int = 300
    working_directory: Optional[str] = None


class PackageRequest(BaseModel):
    """Request model for package operations."""

    package_name: str
    version: Optional[str] = None
    timeout: int = 300


class ServiceRequest(BaseModel):
    """Request model for service operations."""

    service_name: str
    timeout: int = 300


class BroadcastRequest(BaseModel):
    """Request model for broadcast messages."""

    message: str
    message_type: MessageType = MessageType.COMMAND


# Fleet status and information endpoints


@router.get("/fleet/status")
async def get_fleet_status(_dependencies=Depends(JWTBearer())):
    """Get status of all connected agents."""
    agents = connection_manager.get_active_agents()
    return {"total_agents": len(agents), "agents": agents}


@router.get("/fleet/agents")
async def list_agents(_dependencies=Depends(JWTBearer())):
    """List all connected agents with their details."""
    return connection_manager.get_active_agents()


@router.get("/fleet/agent/{hostname}")
async def get_agent(hostname: str, _dependencies=Depends(JWTBearer())):
    """Get details of a specific agent by hostname."""
    agent = connection_manager.get_agent_by_hostname(hostname)
    if not agent:
        raise HTTPException(
            status_code=404, detail=_("Agent with hostname %s not found") % hostname
        )
    return agent


# Command sending endpoints


@router.post("/fleet/agent/{hostname}/command")
async def send_command_to_agent(
    hostname: str,
    command: CommandRequest,
    db: Session = Depends(get_db),
    _dependencies=Depends(JWTBearer()),
):
    """Send a command to a specific agent by hostname."""
    # Look up host by hostname
    host = db.query(models.Host).filter(models.Host.fqdn == hostname).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    # Create and send command
    cmd_message = CommandMessage(
        command.command_type, command.parameters, command.timeout
    )

    queue_ops.enqueue_message(
        message_type="command",
        message_data=cmd_message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )
    # Commit the session to persist the queued message
    db.commit()

    return {
        "status": "sent",
        "command_id": cmd_message.message_id,
        "message": _("Command {command_type} sent to {hostname}").format(
            command_type=command.command_type.value, hostname=hostname
        ),
    }


@router.post("/fleet/agent/{hostname}/shell")
async def execute_shell_command(
    hostname: str,
    shell_request: ShellCommandRequest,
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
):
    """Execute a shell command on a specific agent."""
    # Look up host by hostname
    host = db.query(models.Host).filter(models.Host.fqdn == hostname).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    parameters = {
        "command": shell_request.command,
        "working_directory": shell_request.working_directory,
    }

    cmd_message = CommandMessage(
        CommandType.EXECUTE_SHELL, parameters, shell_request.timeout
    )

    queue_ops.enqueue_message(
        message_type="command",
        message_data=cmd_message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )
    # Commit the session to persist the queued message
    db.commit()

    return {
        "status": "sent",
        "command_id": cmd_message.message_id,
        "command": shell_request.command,
        "message": _("Shell command sent to {hostname}").format(hostname=hostname),
    }


@router.post("/fleet/agent/{hostname}/install-package")
async def install_package(
    hostname: str,
    package_request: PackageRequest,
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
):
    """Install a package on a specific agent."""
    # Look up host by hostname
    host = db.query(models.Host).filter(models.Host.fqdn == hostname).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    parameters = {
        "package_name": package_request.package_name,
        "version": package_request.version,
    }

    cmd_message = CommandMessage(
        CommandType.INSTALL_PACKAGE, parameters, package_request.timeout
    )

    queue_ops.enqueue_message(
        message_type="command",
        message_data=cmd_message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )
    # Commit the session to persist the queued message
    db.commit()

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
    hostname: str,
    service_request: ServiceRequest,
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
):
    """Restart a service on a specific agent."""
    # Look up host by hostname
    host = db.query(models.Host).filter(models.Host.fqdn == hostname).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    parameters = {"service_name": service_request.service_name}

    cmd_message = CommandMessage(
        CommandType.RESTART_SERVICE, parameters, service_request.timeout
    )

    queue_ops.enqueue_message(
        message_type="command",
        message_data=cmd_message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )
    # Commit the session to persist the queued message
    db.commit()

    return {
        "status": "sent",
        "command_id": cmd_message.message_id,
        "service": service_request.service_name,
        "message": _("Service restart command sent to {hostname}").format(
            hostname=hostname
        ),
    }


@router.post("/fleet/agent/{hostname}/update-system")
async def update_system(
    hostname: str, db: Session = Depends(get_db), dependencies=Depends(JWTBearer())
):
    """Trigger system updates on a specific agent."""
    # Look up host by hostname
    host = db.query(models.Host).filter(models.Host.fqdn == hostname).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    cmd_message = CommandMessage(
        CommandType.UPDATE_SYSTEM, {}, 1800
    )  # 30 minute timeout

    queue_ops.enqueue_message(
        message_type="command",
        message_data=cmd_message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )
    # Commit the session to persist the queued message
    db.commit()

    return {
        "status": "sent",
        "command_id": cmd_message.message_id,
        "message": _("System update command sent to {hostname}").format(
            hostname=hostname
        ),
    }


@router.post("/fleet/agent/{hostname}/reboot")
async def reboot_system(
    hostname: str, db: Session = Depends(get_db), dependencies=Depends(JWTBearer())
):
    """Reboot a specific agent system."""
    # Look up host by hostname
    host = db.query(models.Host).filter(models.Host.fqdn == hostname).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    cmd_message = CommandMessage(
        CommandType.REBOOT_SYSTEM, {}, 60
    )  # Short timeout before reboot

    queue_ops.enqueue_message(
        message_type="command",
        message_data=cmd_message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )
    # Commit the session to persist the queued message
    db.commit()

    return {
        "status": "sent",
        "command_id": cmd_message.message_id,
        "message": _("Reboot command sent to {hostname}").format(hostname=hostname),
    }


# Broadcast endpoints


def _enqueue_command_for_hosts(db: Session, host_ids: list, message_dict: dict) -> int:
    """Enqueue one OUTBOUND row of ``message_dict`` per host_id.  Direct
    ``connection_manager.broadcast_to_*`` calls bypass the queue, lose
    messages on transient disconnects, and never reach offline agents —
    fan-out must always go through the queue."""
    enqueued = 0
    for host_id in host_ids:
        try:
            queue_ops.enqueue_message(
                message_type="command",
                message_data=message_dict,
                direction=QueueDirection.OUTBOUND,
                host_id=str(host_id),
                db=db,
            )
            enqueued += 1
        except Exception:  # pylint: disable=broad-exception-caught
            # Per-host failure must not abort the rest of the fan-out:
            # one failed enqueue (e.g. row-level constraint violation,
            # transient DB error) shouldn't drop messages for the other
            # hosts in the same broadcast.  Caller commits if any rows
            # succeeded.
            logger.exception(
                "Failed to enqueue broadcast command for host_id=%s; "
                "skipping this host",
                host_id,
            )
            continue
    if enqueued:
        db.commit()
    return enqueued


@router.post("/fleet/broadcast/command")
async def broadcast_command(
    command: CommandRequest,
    db: Session = Depends(get_db),
    _dependencies=Depends(JWTBearer()),
):
    """Broadcast a command to every active host (queued; offline hosts
    receive it on reconnect)."""
    cmd_message = CommandMessage(
        command.command_type, command.parameters, command.timeout
    )
    host_ids = [
        row[0]
        for row in db.query(models.Host.id).filter(models.Host.active.is_(True)).all()
    ]
    sent_count = _enqueue_command_for_hosts(db, host_ids, cmd_message.to_dict())

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
    shell_request: ShellCommandRequest,
    db: Session = Depends(get_db),
    _dependencies=Depends(JWTBearer()),
):
    """Broadcast a shell command to every active host (queued)."""
    parameters = {
        "command": shell_request.command,
        "working_directory": shell_request.working_directory,
    }

    cmd_message = CommandMessage(
        CommandType.EXECUTE_SHELL, parameters, shell_request.timeout
    )
    host_ids = [
        row[0]
        for row in db.query(models.Host.id).filter(models.Host.active.is_(True)).all()
    ]
    sent_count = _enqueue_command_for_hosts(db, host_ids, cmd_message.to_dict())

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
    platform: str,
    command: CommandRequest,
    db: Session = Depends(get_db),
    _dependencies=Depends(JWTBearer()),
):
    """Queue a command for every active host on a specific platform
    (e.g., 'Linux', 'Darwin', 'Windows')."""
    cmd_message = CommandMessage(
        command.command_type, command.parameters, command.timeout
    )
    host_ids = [
        row[0]
        for row in db.query(models.Host.id)
        .filter(models.Host.active.is_(True), models.Host.platform == platform)
        .all()
    ]
    if not host_ids:
        raise HTTPException(
            status_code=404, detail=_("No agents found for platform %s") % platform
        )
    sent_count = _enqueue_command_for_hosts(db, host_ids, cmd_message.to_dict())

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
