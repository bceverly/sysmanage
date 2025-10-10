"""
This module houses the API routes for antivirus status management in SysManage.
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db as persistence_db, models
from backend.persistence.db import get_db
from backend.security.roles import SecurityRoles
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import CommandType, Message, MessageType

logger = logging.getLogger(__name__)

router = APIRouter()


class AntivirusStatusResponse(BaseModel):
    """Response model for antivirus status."""

    id: str
    host_id: str
    software_name: Optional[str] = None
    install_path: Optional[str] = None
    version: Optional[str] = None
    enabled: Optional[bool] = None
    last_updated: datetime

    @validator("id", "host_id", pre=True)
    def convert_uuid_to_string(cls, value):  # pylint: disable=no-self-argument
        """Convert UUID objects to strings."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    class Config:
        from_attributes = True


@router.get(
    "/hosts/{host_id}/antivirus-status",
    response_model=Optional[AntivirusStatusResponse],
)
async def get_antivirus_status(
    host_id: str,
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
):
    """Get antivirus status for a specific host."""
    try:
        # Convert host_id to UUID
        try:
            host_uuid = uuid.UUID(host_id)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=_("Invalid host ID format"),
            ) from e

        # Check if host exists
        host = db.query(models.Host).filter(models.Host.id == host_uuid).first()
        if not host:
            raise HTTPException(
                status_code=404,
                detail=_("Host not found"),
            )

        # Get antivirus status
        status = (
            db.query(models.AntivirusStatus)
            .filter(models.AntivirusStatus.host_id == host_uuid)
            .first()
        )

        if not status:
            return None

        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting antivirus status for host %s: %s", host_id, e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve antivirus status: %s") % str(e),
        ) from e


class AntivirusDeployRequest(BaseModel):
    """Request model for deploying antivirus to hosts."""

    host_ids: List[str]


class AntivirusDeployResponse(BaseModel):
    """Response model for antivirus deployment."""

    success_count: int
    failed_hosts: List[dict]
    message: str


@router.post("/deploy", response_model=AntivirusDeployResponse)
async def deploy_antivirus(
    deploy_request: AntivirusDeployRequest,
    db_session: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Deploy antivirus to one or more hosts."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=persistence_db.get_engine()
    )

    with session_local() as session:
        # Check if user has permission to deploy antivirus
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=_("User not found"))

        if user._role_cache is None:
            user.load_role_cache(session)

        if not user.has_role(SecurityRoles.DEPLOY_ANTIVIRUS):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: DEPLOY_ANTIVIRUS role required"),
            )

    # Process each host
    success_count = 0
    failed_hosts = []

    for host_id_str in deploy_request.host_ids:
        try:
            # Convert host_id to UUID
            try:
                host_id = uuid.UUID(host_id_str)
            except ValueError:
                failed_hosts.append(
                    {
                        "host_id": host_id_str,
                        "hostname": "Unknown",
                        "reason": _("Invalid host ID format"),
                    }
                )
                continue

            # Get host details
            with session_local() as session:
                host = (
                    session.query(models.Host).filter(models.Host.id == host_id).first()
                )
                if not host:
                    failed_hosts.append(
                        {
                            "host_id": host_id_str,
                            "hostname": "Unknown",
                            "reason": _("Host not found"),
                        }
                    )
                    continue

                # Get OS name (platform_release or platform)
                # For macOS, use platform directly since platform_release contains version codenames
                # For BSD systems, platform_release might be just "7.7", so fall back to platform
                if host.platform == "macOS":
                    os_name_raw = "macOS"
                else:
                    os_name_raw = host.platform_release or host.platform

                    # If platform_release doesn't start with a letter (e.g., "7.7" for OpenBSD), use platform instead
                    if os_name_raw and not re.match(r"^[A-Za-z]", os_name_raw):
                        os_name_raw = host.platform or os_name_raw

                if not os_name_raw:
                    failed_hosts.append(
                        {
                            "host_id": host_id_str,
                            "hostname": host.fqdn,
                            "reason": _("Unable to determine host operating system"),
                        }
                    )
                    continue

                # Extract base OS name without version (e.g., "Ubuntu 25.04" -> "Ubuntu")
                # For macOS, we already have the base name
                if host.platform == "macOS":
                    os_name = "macOS"
                else:
                    match = re.match(r"^([A-Za-z]+)", os_name_raw)
                    os_name = match.group(1) if match else os_name_raw

                # Get antivirus default for this OS
                antivirus_default = (
                    session.query(models.AntivirusDefault)
                    .filter(models.AntivirusDefault.os_name == os_name)
                    .first()
                )

                if not antivirus_default or not antivirus_default.antivirus_package:
                    failed_hosts.append(
                        {
                            "host_id": host_id_str,
                            "hostname": host.fqdn,
                            "reason": _("No antivirus default configured for OS: %s")
                            % os_name,
                        }
                    )
                    continue

                # Create command message for antivirus deployment
                command_message = Message(
                    message_type=MessageType.COMMAND,
                    data={
                        "command_type": CommandType.DEPLOY_ANTIVIRUS,
                        "parameters": {
                            "antivirus_package": antivirus_default.antivirus_package
                        },
                    },
                )

                # Send command to agent via WebSocket/queue
                success = await connection_manager.send_to_host(
                    str(host_id), command_message.to_dict()
                )

                if not success:
                    failed_hosts.append(
                        {
                            "host_id": host_id_str,
                            "hostname": host.fqdn,
                            "reason": _("Agent is not connected"),
                        }
                    )
                    continue

                success_count += 1
                logger.info(
                    "Antivirus deployment initiated for host %s (%s) with package %s",
                    host.fqdn,
                    host_id_str,
                    antivirus_default.antivirus_package,
                )

        except Exception as e:
            logger.error("Error deploying antivirus to host %s: %s", host_id_str, e)
            failed_hosts.append(
                {"host_id": host_id_str, "hostname": "Unknown", "reason": str(e)}
            )

    # Generate response message
    if success_count == len(deploy_request.host_ids):
        message = _("Antivirus deployment initiated for all %d hosts") % success_count
    elif success_count > 0:
        message = _("Antivirus deployment initiated for %d of %d hosts") % (
            success_count,
            len(deploy_request.host_ids),
        )
    else:
        message = _("Antivirus deployment failed for all hosts")

    return AntivirusDeployResponse(
        success_count=success_count, failed_hosts=failed_hosts, message=message
    )


@router.post(
    "/hosts/{host_id}/antivirus/enable",
    dependencies=[Depends(JWTBearer())],
)
async def enable_antivirus(
    host_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Enable antivirus on a specific host."""
    # Check permission
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_("User not found"))

    if user._role_cache is None:
        user.load_role_cache(db)

    if not user.has_role(SecurityRoles.ENABLE_ANTIVIRUS):
        raise HTTPException(status_code=403, detail=_("Permission denied"))

    # Get host
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))

    # Check if agent is connected
    if host.fqdn not in connection_manager.hostname_to_agent:
        raise HTTPException(status_code=400, detail=_("Host agent is not connected"))

    # Send enable command to agent
    message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.ENABLE_ANTIVIRUS,
            "parameters": {},
            "timeout": 300,
        },
    )

    success = await connection_manager.send_to_host(host.id, message.to_dict())
    if not success:
        raise HTTPException(status_code=503, detail=_("Agent is not connected"))

    logger.info("Antivirus enable command sent to host %s", host.fqdn)
    return {"message": _("Antivirus enable command sent successfully")}


@router.post(
    "/hosts/{host_id}/antivirus/disable",
    dependencies=[Depends(JWTBearer())],
)
async def disable_antivirus(
    host_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Disable antivirus on a specific host."""
    # Check permission
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_("User not found"))

    if user._role_cache is None:
        user.load_role_cache(db)

    if not user.has_role(SecurityRoles.DISABLE_ANTIVIRUS):
        raise HTTPException(status_code=403, detail=_("Permission denied"))

    # Get host
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))

    # Check if agent is connected
    if host.fqdn not in connection_manager.hostname_to_agent:
        raise HTTPException(status_code=400, detail=_("Host agent is not connected"))

    # Send disable command to agent
    message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.DISABLE_ANTIVIRUS,
            "parameters": {},
            "timeout": 300,
        },
    )

    success = await connection_manager.send_to_host(host.id, message.to_dict())
    if not success:
        raise HTTPException(status_code=503, detail=_("Agent is not connected"))

    logger.info("Antivirus disable command sent to host %s", host.fqdn)
    return {"message": _("Antivirus disable command sent successfully")}


@router.post(
    "/hosts/{host_id}/antivirus/remove",
    dependencies=[Depends(JWTBearer())],
)
async def remove_antivirus(
    host_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Remove antivirus from a specific host."""
    try:
        # Check permission
        logger.info(
            "remove_antivirus called for host_id=%s by user=%s", host_id, current_user
        )
        user = db.query(models.User).filter(models.User.userid == current_user).first()
        if not user:
            logger.error("User not found: %s", current_user)
            raise HTTPException(status_code=401, detail=_("User not found"))

        if user._role_cache is None:
            user.load_role_cache(db)

        if not user.has_role(SecurityRoles.REMOVE_ANTIVIRUS):
            logger.error("User %s lacks REMOVE_ANTIVIRUS role", current_user)
            raise HTTPException(status_code=403, detail=_("Permission denied"))

        # Get host
        host = db.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            logger.error("Host not found: %s", host_id)
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Check if agent is connected
        if host.fqdn not in connection_manager.hostname_to_agent:
            logger.error("Agent not connected for host: %s", host.fqdn)
            raise HTTPException(
                status_code=400, detail=_("Host agent is not connected")
            )

        # Send remove command to agent
        message = Message(
            message_type=MessageType.COMMAND,
            data={
                "command_type": CommandType.REMOVE_ANTIVIRUS,
                "parameters": {},
                "timeout": 300,
            },
        )

        success = await connection_manager.send_to_host(host.id, message.to_dict())
        if not success:
            raise HTTPException(status_code=503, detail=_("Agent is not connected"))

        logger.info("Antivirus remove command sent to host %s", host.fqdn)
        return {"message": _("Antivirus remove command sent successfully")}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error in remove_antivirus: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Internal server error: {str(e)}"
        ) from e
