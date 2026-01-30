"""
Host hostname change endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.api.error_constants import error_host_not_found, error_user_not_found
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()
queue_ops = QueueOperations()


class ChangeHostnameRequest(BaseModel):
    """Request body for hostname change."""

    new_hostname: str


@router.post("/host/{host_id}/change-hostname", dependencies=[Depends(JWTBearer())])
async def change_hostname(
    host_id: str,
    request: ChangeHostnameRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Request a hostname change for a specific host.

    Requires:
    - EDIT_HOST_HOSTNAME role
    - Host must exist and be active
    - Host agent must be running in privileged mode
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Check if user has permission to change hostnames
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=error_user_not_found())

        # Load role cache if not already loaded
        if user._role_cache is None:
            user.load_role_cache(session)

        # Check for EDIT_HOST_HOSTNAME role
        if not user.has_role(SecurityRoles.EDIT_HOST_HOSTNAME):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: EDIT_HOST_HOSTNAME role required"),
            )

        # Find the host first to ensure it exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=error_host_not_found())

        # Check if host is active
        if not host.active:
            raise HTTPException(
                status_code=400,
                detail=_("Host is not active"),
            )

        # Check if agent is running in privileged mode
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_("Host agent is not running in privileged mode"),
            )

        # Validate hostname
        new_hostname = request.new_hostname.strip()
        if not new_hostname:
            raise HTTPException(
                status_code=400,
                detail=_("Hostname cannot be empty"),
            )

        # Basic hostname validation (alphanumeric, hyphens, dots for FQDN)
        import re

        if not re.match(
            r"^[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$", new_hostname
        ):
            raise HTTPException(
                status_code=400,
                detail=_("Invalid hostname format"),
            )

        # Create command message for hostname change
        command_message = create_command_message(
            command_type="change_hostname",
            parameters={"new_hostname": new_hostname},
        )

        # Send command to agent via message queue
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Audit log the hostname change request
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        AuditService.log(
            db=session,
            user_id=user.id,
            username=current_user,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested hostname change from {host.fqdn} to {new_hostname}",
            result=Result.SUCCESS,
        )

        # Commit the session to persist the queued message and audit log
        session.commit()

        return {"result": True, "message": _("Hostname change requested")}
