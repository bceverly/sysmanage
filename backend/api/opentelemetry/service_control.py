"""
OpenTelemetry service control endpoints (start/stop/restart).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.error_constants import (
    error_host_not_found_or_not_active,
    error_user_not_found,
)
from backend.api.host_utils import validate_host_approval_status
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.services.observability_shim import try_engine_otel_service_control
from backend.websocket.messages import create_command_message
from backend.websocket.queue_manager import (
    Priority,
    QueueDirection,
    ServerMessageQueueManager,
)

from .models import OpenTelemetryDeployResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize queue manager
server_queue_manager = ServerMessageQueueManager()


@router.post(
    "/hosts/{host_id}/opentelemetry/start",
    dependencies=[Depends(JWTBearer())],
    response_model=OpenTelemetryDeployResponse,
)
async def start_opentelemetry(
    host_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Start OpenTelemetry service on a host.

    Args:
        host_id: The ID of the host
        db: Database session
        current_user: Current authenticated user

    Returns:
        OpenTelemetryDeployResponse indicating success or failure
    """
    try:
        # Check user permissions
        auth_user = (
            db.query(models.User).filter(models.User.userid == current_user).first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=error_user_not_found())

        if auth_user._role_cache is None:
            auth_user.load_role_cache(db)

        if not auth_user.has_role(SecurityRoles.START_OPENTELEMETRY_SERVICE):
            raise HTTPException(
                status_code=403,
                detail=_(
                    "Permission denied: START_OPENTELEMETRY_SERVICE role required"
                ),
            )

        # Validate host
        host = (
            db.query(models.Host)
            .filter(
                models.Host.id == host_id,
                models.Host.active.is_(True),
            )
            .first()
        )

        if not host:
            raise HTTPException(
                status_code=404,
                detail=error_host_not_found_or_not_active(),
            )

        validate_host_approval_status(host)

        # Engine-first dispatch (Phase 10.2 step 7 close-out, item A):
        # try the engine path before queuing the legacy WS command.
        # ``try_engine_otel_service_control`` returns the queued
        # message_id on success or ``None`` if the engine isn't loaded
        # / the platform isn't detectable / build fails — in which
        # case we fall through to the legacy ``start_opentelemetry_service``
        # WS command path below.
        engine_msg_id = try_engine_otel_service_control(host, "start", db)
        if engine_msg_id is None:
            command_message = create_command_message(
                command_type="generic_command",
                parameters={
                    "command_type": "start_opentelemetry_service",
                    "parameters": {},
                },
            )
            server_queue_manager.enqueue_message(
                message_type="command",
                message_data=command_message,
                direction=QueueDirection.OUTBOUND,
                host_id=host_id,
                priority=Priority.NORMAL,
                db=db,
            )
            dispatch_path = "legacy_ws_command"
        else:
            dispatch_path = "engine_plan"

        AuditService.log(
            db=db,
            user_id=auth_user.id,
            username=current_user,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested OpenTelemetry start for host {host.fqdn}",
            result=Result.SUCCESS,
            details={"dispatch_path": dispatch_path, "service_action": "start"},
        )
        db.commit()

        logger.info(
            "Queued OpenTelemetry start for host %s (FQDN: %s) via %s",
            host_id,
            host.fqdn,
            dispatch_path,
        )

        return OpenTelemetryDeployResponse(
            success=True,
            message=_("OpenTelemetry start command queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error starting OpenTelemetry: %s", e)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to start OpenTelemetry: %s") % str(e),
        ) from e


@router.post(
    "/hosts/{host_id}/opentelemetry/stop",
    dependencies=[Depends(JWTBearer())],
    response_model=OpenTelemetryDeployResponse,
)
async def stop_opentelemetry(
    host_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Stop OpenTelemetry service on a host.

    Args:
        host_id: The ID of the host
        db: Database session
        current_user: Current authenticated user

    Returns:
        OpenTelemetryDeployResponse indicating success or failure
    """
    try:
        # Check user permissions
        auth_user = (
            db.query(models.User).filter(models.User.userid == current_user).first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=error_user_not_found())

        if auth_user._role_cache is None:
            auth_user.load_role_cache(db)

        if not auth_user.has_role(SecurityRoles.STOP_OPENTELEMETRY_SERVICE):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: STOP_OPENTELEMETRY_SERVICE role required"),
            )

        # Validate host
        host = (
            db.query(models.Host)
            .filter(
                models.Host.id == host_id,
                models.Host.active.is_(True),
            )
            .first()
        )

        if not host:
            raise HTTPException(
                status_code=404,
                detail=error_host_not_found_or_not_active(),
            )

        validate_host_approval_status(host)

        # Engine-first dispatch — see start endpoint above for rationale.
        engine_msg_id = try_engine_otel_service_control(host, "stop", db)
        if engine_msg_id is None:
            command_message = create_command_message(
                command_type="generic_command",
                parameters={
                    "command_type": "stop_opentelemetry_service",
                    "parameters": {},
                },
            )
            server_queue_manager.enqueue_message(
                message_type="command",
                message_data=command_message,
                direction=QueueDirection.OUTBOUND,
                host_id=host_id,
                priority=Priority.NORMAL,
                db=db,
            )
            dispatch_path = "legacy_ws_command"
        else:
            dispatch_path = "engine_plan"

        AuditService.log(
            db=db,
            user_id=auth_user.id,
            username=current_user,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested OpenTelemetry stop for host {host.fqdn}",
            result=Result.SUCCESS,
            details={"dispatch_path": dispatch_path, "service_action": "stop"},
        )
        db.commit()

        logger.info(
            "Queued OpenTelemetry stop for host %s (FQDN: %s) via %s",
            host_id,
            host.fqdn,
            dispatch_path,
        )

        return OpenTelemetryDeployResponse(
            success=True,
            message=_("OpenTelemetry stop command queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error stopping OpenTelemetry: %s", e)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to stop OpenTelemetry: %s") % str(e),
        ) from e


@router.post(
    "/hosts/{host_id}/opentelemetry/restart",
    dependencies=[Depends(JWTBearer())],
    response_model=OpenTelemetryDeployResponse,
)
async def restart_opentelemetry(
    host_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Restart OpenTelemetry service on a host.

    Args:
        host_id: The ID of the host
        db: Database session
        current_user: Current authenticated user

    Returns:
        OpenTelemetryDeployResponse indicating success or failure
    """
    try:
        # Check user permissions
        auth_user = (
            db.query(models.User).filter(models.User.userid == current_user).first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=error_user_not_found())

        if auth_user._role_cache is None:
            auth_user.load_role_cache(db)

        if not auth_user.has_role(SecurityRoles.RESTART_OPENTELEMETRY_SERVICE):
            raise HTTPException(
                status_code=403,
                detail=_(
                    "Permission denied: RESTART_OPENTELEMETRY_SERVICE role required"
                ),
            )

        # Validate host
        host = (
            db.query(models.Host)
            .filter(
                models.Host.id == host_id,
                models.Host.active.is_(True),
            )
            .first()
        )

        if not host:
            raise HTTPException(
                status_code=404,
                detail=error_host_not_found_or_not_active(),
            )

        validate_host_approval_status(host)

        # Engine-first dispatch — see start endpoint above for rationale.
        engine_msg_id = try_engine_otel_service_control(host, "restart", db)
        if engine_msg_id is None:
            command_message = create_command_message(
                command_type="generic_command",
                parameters={
                    "command_type": "restart_opentelemetry_service",
                    "parameters": {},
                },
            )
            server_queue_manager.enqueue_message(
                message_type="command",
                message_data=command_message,
                direction=QueueDirection.OUTBOUND,
                host_id=host_id,
                priority=Priority.NORMAL,
                db=db,
            )
            dispatch_path = "legacy_ws_command"
        else:
            dispatch_path = "engine_plan"

        AuditService.log(
            db=db,
            user_id=auth_user.id,
            username=current_user,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested OpenTelemetry restart for host {host.fqdn}",
            result=Result.SUCCESS,
            details={"dispatch_path": dispatch_path, "service_action": "restart"},
        )
        db.commit()

        logger.info(
            "Queued OpenTelemetry restart for host %s (FQDN: %s) via %s",
            host_id,
            host.fqdn,
            dispatch_path,
        )

        return OpenTelemetryDeployResponse(
            success=True,
            message=_("OpenTelemetry restart command queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error restarting OpenTelemetry: %s", e)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to restart OpenTelemetry: %s") % str(e),
        ) from e
