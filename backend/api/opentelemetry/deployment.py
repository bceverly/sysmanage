"""
OpenTelemetry deployment and removal endpoints.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.host_utils import validate_host_approval_status
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.security.roles import SecurityRoles
from backend.websocket.queue_manager import (
    Priority,
    QueueDirection,
    ServerMessageQueueManager,
)

from .eligibility import check_opentelemetry_eligibility
from .models import OpenTelemetryDeployResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize queue manager
server_queue_manager = ServerMessageQueueManager()


@router.post(
    "/hosts/{host_id}/deploy-opentelemetry",
    dependencies=[Depends(JWTBearer())],
    response_model=OpenTelemetryDeployResponse,
)
async def deploy_opentelemetry(
    host_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Deploy OpenTelemetry to a specific host.

    This endpoint:
    1. Checks if the host is eligible for OpenTelemetry deployment
    2. Retrieves Grafana server configuration
    3. Queues a deployment message to the agent

    Args:
        host_id: The ID of the host to deploy OpenTelemetry to
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
            raise HTTPException(status_code=401, detail=_("User not found"))

        if auth_user._role_cache is None:
            auth_user.load_role_cache(db)

        # Check DEPLOY_OPENTELEMETRY permission
        if not auth_user.has_role(SecurityRoles.DEPLOY_OPENTELEMETRY):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: DEPLOY_OPENTELEMETRY role required"),
            )

        # Validate host exists and is active
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
                detail=_("Host not found or not active"),
            )

        # Validate host approval status
        validate_host_approval_status(host)

        # Check eligibility
        eligibility = await check_opentelemetry_eligibility(host_id, current_user, db)

        if not eligibility.eligible:
            raise HTTPException(
                status_code=400,
                detail=_("Host is not eligible for OpenTelemetry deployment: %s")
                % eligibility.error_message,
            )

        # Get Grafana configuration
        grafana_settings = (
            db.query(models.GrafanaIntegrationSettings).filter_by(enabled=True).first()
        )

        if not grafana_settings:
            raise HTTPException(
                status_code=400,
                detail=_("Grafana integration is not configured"),
            )

        grafana_url = grafana_settings.grafana_url
        if not grafana_url:
            raise HTTPException(
                status_code=400,
                detail=_("Grafana URL is not available"),
            )

        # Prepare the deployment message
        message_data = {
            "command_type": "generic_command",
            "parameters": {
                "command_type": "deploy_opentelemetry",
                "parameters": {
                    "grafana_url": grafana_url,
                    "grafana_host": (
                        grafana_settings.host.fqdn if grafana_settings.host else None
                    ),
                },
            },
        }

        # Queue the message using the server queue manager
        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=message_data,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        # Commit the message to the database
        db.commit()

        logger.info(
            "Queued OpenTelemetry deployment for host %s (FQDN: %s)",
            host_id,
            host.fqdn,
        )

        return OpenTelemetryDeployResponse(
            success=True,
            message=_("OpenTelemetry deployment queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deploying OpenTelemetry: %s", e)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to deploy OpenTelemetry: %s") % str(e),
        ) from e


@router.post(
    "/hosts/{host_id}/remove-opentelemetry",
    dependencies=[Depends(JWTBearer())],
    response_model=OpenTelemetryDeployResponse,
)
async def remove_opentelemetry(
    host_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Remove OpenTelemetry from a specific host.

    Args:
        host_id: The ID of the host to remove OpenTelemetry from
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
            raise HTTPException(status_code=401, detail=_("User not found"))

        if auth_user._role_cache is None:
            auth_user.load_role_cache(db)

        # Check DEPLOY_OPENTELEMETRY permission
        if not auth_user.has_role(SecurityRoles.DEPLOY_OPENTELEMETRY):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: DEPLOY_OPENTELEMETRY role required"),
            )

        # Validate host exists and is active
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
                detail=_("Host not found or not active"),
            )

        # Validate host approval status
        validate_host_approval_status(host)

        # Prepare the removal message
        message_data = {
            "command_type": "generic_command",
            "parameters": {
                "command_type": "remove_opentelemetry",
                "parameters": {},
            },
        }

        # Queue the message
        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=message_data,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        db.commit()

        logger.info(
            "Queued OpenTelemetry removal for host %s (FQDN: %s)",
            host_id,
            host.fqdn,
        )

        return OpenTelemetryDeployResponse(
            success=True,
            message=_("OpenTelemetry removal queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error removing OpenTelemetry: %s", e)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to remove OpenTelemetry: %s") % str(e),
        ) from e
