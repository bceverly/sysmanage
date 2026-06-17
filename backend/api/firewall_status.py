"""
This module houses the API routes for firewall status management in SysManage.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session, sessionmaker

from backend.api.error_constants import (
    error_host_not_found,
    error_invalid_host_id,
    error_permission_denied,
)
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import db as db_module
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import firewall_plan_builder
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import CommandType, Message, MessageType
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations
from backend.utils.verbosity_logger import sanitize_log


def _host_info_for_planner(host: models.Host) -> dict:
    """Pack a Host's OS fields into the dict the plan builder expects."""
    return {
        "platform": host.platform,
        "platform_release": host.platform_release,
        "platform_version": host.platform_version,
    }


def _queue_apply_deployment_plan(
    db: Session, host: models.Host, plan: dict, timeout: int = 300
) -> None:
    """Wrap a deployment plan in an APPLY_DEPLOYMENT_PLAN message and queue it."""
    message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.APPLY_DEPLOYMENT_PLAN,
            "parameters": {"plan": plan},
            "timeout": timeout,
        },
    )
    queue_ops.enqueue_message(
        message_type="command",
        message_data=message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )


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
    def convert_uuid_to_string(
        cls, value
    ):  # pylint: disable=no-self-argument  # lgtm[py/not-named-self]
        """Convert UUID objects to strings."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    @validator("last_updated", pre=True)
    def add_utc_timezone(
        cls, value
    ):  # pylint: disable=no-self-argument  # lgtm[py/not-named-self]
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
    db: Session = Depends(get_tenant_db),
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
        logger.exception(
            "Error getting firewall status for host %s: %s", sanitize_log(host_id), e
        )
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
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Enable firewall on a specific host."""
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the host/queue data routes to the tenant engine via ``db``.
    if not current_user.has_role(SecurityRoles.ENABLE_FIREWALL):
        raise HTTPException(status_code=403, detail=error_permission_denied())

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    # Get host
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    # Build a declarative enable plan and queue it via apply_deployment_plan.
    plan = firewall_plan_builder.build_enable_plan(_host_info_for_planner(host))
    _queue_apply_deployment_plan(db, host, plan)

    # Commit the session to persist the queued message
    db.commit()

    # Audit log the firewall enable command (on the main engine)
    with session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=str(host.id),
            entity_name=host.fqdn,
            description=f"Requested firewall enable for host {host.fqdn}",
            result=Result.SUCCESS,
        )

    logger.info("Firewall enable command sent to host %s", host.fqdn)
    return {"message": _("Firewall enable command sent successfully")}


@router.post(
    "/hosts/{host_id}/firewall/disable",
    dependencies=[Depends(JWTBearer())],
)
async def disable_firewall(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Disable firewall on a specific host."""
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the host/queue data routes to the tenant engine via ``db``.
    if not current_user.has_role(SecurityRoles.DISABLE_FIREWALL):
        raise HTTPException(status_code=403, detail=error_permission_denied())

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    # Get host
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    plan = firewall_plan_builder.build_disable_plan(_host_info_for_planner(host))
    _queue_apply_deployment_plan(db, host, plan)

    db.commit()

    # Audit log the firewall disable command (on the main engine)
    with session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=str(host.id),
            entity_name=host.fqdn,
            description=f"Requested firewall disable for host {host.fqdn}",
            result=Result.SUCCESS,
        )

    logger.info("Firewall disable command sent to host %s", host.fqdn)
    return {"message": _("Firewall disable command sent successfully")}


@router.post(
    "/hosts/{host_id}/firewall/restart",
    dependencies=[Depends(JWTBearer())],
)
async def restart_firewall(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Restart firewall on a specific host."""
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the host/queue data routes to the tenant engine via ``db``.
    if not current_user.has_role(SecurityRoles.RESTART_FIREWALL):
        raise HTTPException(status_code=403, detail=error_permission_denied())

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    # Get host
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    plan = firewall_plan_builder.build_restart_plan(_host_info_for_planner(host))
    _queue_apply_deployment_plan(db, host, plan)

    db.commit()

    # Audit log the firewall restart command (on the main engine)
    with session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=str(host.id),
            entity_name=host.fqdn,
            description=f"Requested firewall restart for host {host.fqdn}",
            result=Result.SUCCESS,
        )

    logger.info("Firewall restart command sent to host %s", host.fqdn)
    return {"message": _("Firewall restart command sent successfully")}


@router.post(
    "/hosts/{host_id}/firewall/deploy",
    dependencies=[Depends(JWTBearer())],
)
async def deploy_firewall(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Deploy firewall on a specific host."""
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the host/queue data routes to the tenant engine via ``db``.
    if not current_user.has_role(SecurityRoles.DEPLOY_FIREWALL):
        raise HTTPException(status_code=403, detail=error_permission_denied())

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    # Get host
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    plan = firewall_plan_builder.build_deploy_plan(_host_info_for_planner(host))
    message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.APPLY_DEPLOYMENT_PLAN,
            "parameters": {"plan": plan},
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

    db.commit()

    # Audit log the firewall deployment command (on the main engine)
    with session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=str(host.id),
            entity_name=host.fqdn,
            description=f"Requested firewall deployment for host {host.fqdn}",
            result=Result.SUCCESS,
        )

    logger.info("Firewall deploy command sent to host %s", host.fqdn)
    return {"message": _("Firewall deploy command sent successfully")}
