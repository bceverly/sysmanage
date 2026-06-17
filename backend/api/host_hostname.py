"""
Host hostname change endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.api.error_constants import error_host_not_found
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import db, models
from backend.persistence.partitions import get_request_engine
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
    current_user=Depends(require_authenticated_user),
):
    """
    Request a hostname change for a specific host.

    Requires:
    - EDIT_HOST_HOSTNAME role
    - Host must exist and be active
    - Host agent must be running in privileged mode
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global).
    if not current_user.has_role(SecurityRoles.EDIT_HOST_HOSTNAME):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: EDIT_HOST_HOSTNAME role required"),
        )

    # Phase 13.1: host data + outbound command queue route to the active tenant's
    # database when multi-tenancy is enabled.  Capture the active tenant in the
    # request's async context and bind the data session to the tenant engine
    # (collapsed/OSS mode == the main engine, so existing tests are unaffected).
    from backend.persistence.tenant_context import get_active_tenant

    tenant_id = get_active_tenant()
    bind = db.get_engine() if tenant_id is None else get_request_engine(tenant_id)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=bind)

    with session_local() as session:
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

        # Commit the session to persist the queued message
        session.commit()

        # Audit log the hostname change request on the MAIN engine (audit trail
        # is server-global, like authz).
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        audit_session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db.get_engine()
        )
        with audit_session_local() as audit_session:
            AuditService.log(
                db=audit_session,
                user_id=current_user.id,
                username=current_user.userid,
                action_type=ActionType.UPDATE,
                entity_type=EntityType.HOST,
                entity_id=host_id,
                entity_name=host.fqdn,
                description=f"Requested hostname change from {host.fqdn} to {new_hostname}",
                result=Result.SUCCESS,
            )

        return {"result": True, "message": _("Hostname change requested")}
