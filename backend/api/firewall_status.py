"""
This module houses the API routes for firewall status management in SysManage.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session

from backend.api.error_constants import (
    error_host_not_found,
    error_invalid_host_id,
    error_permission_denied,
    error_user_not_found,
)
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import CommandType, Message, MessageType
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)

router = APIRouter()
queue_ops = QueueOperations()


class FirewallStatusResponse(BaseModel):
    """Response model for firewall status."""

    id: str
    host_id: str
    firewall_name: Optional[str] = None
    enabled: bool
    tcp_open_ports: Optional[str] = None
    udp_open_ports: Optional[str] = None
    ipv4_ports: Optional[str] = None
    ipv6_ports: Optional[str] = None
    last_updated: datetime

    @validator("id", "host_id", pre=True)
    def convert_uuid_to_string(cls, value):  # pylint: disable=no-self-argument
        """Convert UUID objects to strings."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    @validator("last_updated", pre=True)
    def add_utc_timezone(cls, value):  # pylint: disable=no-self-argument
        """Add UTC timezone to naive datetime."""
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


@router.get(
    "/hosts/{host_id}/firewall-status",
    response_model=Optional[FirewallStatusResponse],
)
async def get_firewall_status(
    host_id: str,
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
):
    """Get firewall status for a specific host."""
    try:
        # Convert host_id to UUID
        try:
            host_uuid = uuid.UUID(host_id)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=error_invalid_host_id(),
            ) from e

        # Check if host exists
        host = db.query(models.Host).filter(models.Host.id == host_uuid).first()
        if not host:
            raise HTTPException(
                status_code=404,
                detail=error_host_not_found(),
            )

        # Get firewall status
        status = (
            db.query(models.FirewallStatus)
            .filter(models.FirewallStatus.host_id == host_uuid)
            .first()
        )

        if not status:
            return None

        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting firewall status for host %s: %s", host_id, e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve firewall status: %s") % str(e),
        ) from e


@router.post(
    "/hosts/{host_id}/firewall/enable",
    dependencies=[Depends(JWTBearer())],
)
async def enable_firewall(
    host_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Enable firewall on a specific host."""
    # Check permission
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=error_user_not_found())

    if user._role_cache is None:
        user.load_role_cache(db)

    if not user.has_role(SecurityRoles.ENABLE_FIREWALL):
        raise HTTPException(status_code=403, detail=error_permission_denied())

    # Get host
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    # Queue enable command for agent (will be delivered when agent is available)
    message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.ENABLE_FIREWALL,
            "parameters": {},
            "timeout": 300,
        },
    )

    queue_ops.enqueue_message(
        message_type="command",
        message_data=message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )

    # Audit log the firewall enable command
    AuditService.log(
        db=db,
        user_id=user.id,
        username=current_user,
        action_type=ActionType.EXECUTE,
        entity_type=EntityType.HOST,
        entity_id=str(host.id),
        entity_name=host.fqdn,
        description=f"Requested firewall enable for host {host.fqdn}",
        result=Result.SUCCESS,
    )

    # Commit the session to persist the queued message and audit log
    db.commit()

    logger.info("Firewall enable command sent to host %s", host.fqdn)
    return {"message": _("Firewall enable command sent successfully")}


@router.post(
    "/hosts/{host_id}/firewall/disable",
    dependencies=[Depends(JWTBearer())],
)
async def disable_firewall(
    host_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Disable firewall on a specific host."""
    # Check permission
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=error_user_not_found())

    if user._role_cache is None:
        user.load_role_cache(db)

    if not user.has_role(SecurityRoles.DISABLE_FIREWALL):
        raise HTTPException(status_code=403, detail=error_permission_denied())

    # Get host
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    # Queue disable command for agent (will be delivered when agent is available)
    message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.DISABLE_FIREWALL,
            "parameters": {},
            "timeout": 300,
        },
    )

    queue_ops.enqueue_message(
        message_type="command",
        message_data=message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )

    # Audit log the firewall disable command
    AuditService.log(
        db=db,
        user_id=user.id,
        username=current_user,
        action_type=ActionType.EXECUTE,
        entity_type=EntityType.HOST,
        entity_id=str(host.id),
        entity_name=host.fqdn,
        description=f"Requested firewall disable for host {host.fqdn}",
        result=Result.SUCCESS,
    )

    db.commit()

    logger.info("Firewall disable command sent to host %s", host.fqdn)
    return {"message": _("Firewall disable command sent successfully")}


@router.post(
    "/hosts/{host_id}/firewall/restart",
    dependencies=[Depends(JWTBearer())],
)
async def restart_firewall(
    host_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Restart firewall on a specific host."""
    # Check permission
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=error_user_not_found())

    if user._role_cache is None:
        user.load_role_cache(db)

    if not user.has_role(SecurityRoles.RESTART_FIREWALL):
        raise HTTPException(status_code=403, detail=error_permission_denied())

    # Get host
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    # Queue restart command for agent (will be delivered when agent is available)
    message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.RESTART_FIREWALL,
            "parameters": {},
            "timeout": 300,
        },
    )

    queue_ops.enqueue_message(
        message_type="command",
        message_data=message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )

    # Audit log the firewall restart command
    AuditService.log(
        db=db,
        user_id=user.id,
        username=current_user,
        action_type=ActionType.EXECUTE,
        entity_type=EntityType.HOST,
        entity_id=str(host.id),
        entity_name=host.fqdn,
        description=f"Requested firewall restart for host {host.fqdn}",
        result=Result.SUCCESS,
    )

    db.commit()

    logger.info("Firewall restart command sent to host %s", host.fqdn)
    return {"message": _("Firewall restart command sent successfully")}


@router.post(
    "/hosts/{host_id}/firewall/deploy",
    dependencies=[Depends(JWTBearer())],
)
async def deploy_firewall(
    host_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Deploy firewall on a specific host."""
    # Check permission
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_(("User not found")))

    if user._role_cache is None:
        user.load_role_cache(db)

    if not user.has_role(SecurityRoles.DEPLOY_FIREWALL):
        raise HTTPException(status_code=403, detail=error_permission_denied())

    # Get host
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    # Queue deploy command for agent (will be delivered when agent is available)
    message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.DEPLOY_FIREWALL,
            "parameters": {},
            "timeout": 300,
        },
    )

    queue_ops.enqueue_message(
        message_type="command",
        message_data=message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )

    # Audit log the firewall deployment command
    AuditService.log(
        db=db,
        user_id=user.id,
        username=current_user,
        action_type=ActionType.EXECUTE,
        entity_type=EntityType.HOST,
        entity_id=str(host.id),
        entity_name=host.fqdn,
        description=f"Requested firewall deployment for host {host.fqdn}",
        result=Result.SUCCESS,
    )

    db.commit()

    logger.info("Firewall deploy command sent to host %s", host.fqdn)
    return {"message": _("Firewall deploy command sent successfully")}
