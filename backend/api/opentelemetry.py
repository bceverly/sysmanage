"""
OpenTelemetry deployment API endpoints for SysManage.
"""

# pylint: disable=too-many-lines

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize queue manager
server_queue_manager = ServerMessageQueueManager()


class OpenTelemetryEligibilityResponse(BaseModel):
    """Response model for OpenTelemetry eligibility check."""

    eligible: bool
    has_permission: bool  # User has DEPLOY_OPENTELEMETRY role
    grafana_enabled: bool
    opentelemetry_installed: bool
    agent_privileged: bool
    error_message: Optional[str] = None


class OpenTelemetryDeployResponse(BaseModel):
    """Response model for OpenTelemetry deployment request."""

    success: bool
    message: str


class OpenTelemetryStatusResponse(BaseModel):
    """Response model for OpenTelemetry status check."""

    deployed: bool
    service_status: str  # "running", "stopped", "unknown"
    grafana_url: Optional[str] = None
    grafana_configured: bool


@router.get(
    "/hosts/{host_id}/opentelemetry-eligible",
    dependencies=[Depends(JWTBearer())],
    response_model=OpenTelemetryEligibilityResponse,
)
async def check_opentelemetry_eligibility(
    host_id: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Check if a host is eligible for OpenTelemetry deployment.

    Eligibility requirements:
    - User has DEPLOY_OPENTELEMETRY role
    - Grafana integration must be enabled and configured
    - OpenTelemetry must not already be deployed
    - Agent must be running in privileged mode

    Args:
        host_id: The ID of the host to check
        current_user: Current authenticated user
        db: Database session

    Returns:
        OpenTelemetryEligibilityResponse with eligibility details
    """
    try:
        # Check RBAC permissions
        with db.begin_nested():
            user = (
                db.query(models.User).filter(models.User.userid == current_user).first()
            )
            if not user:
                raise HTTPException(status_code=401, detail=_("User not found"))

            if user._role_cache is None:
                user.load_role_cache(db)

            logger.info(
                "User %s has roles: %s",
                current_user,
                user._role_cache.get_role_names() if user._role_cache else "None",
            )
            logger.info(
                "Checking for DEPLOY_OPENTELEMETRY role: %s",
                user.has_role(SecurityRoles.DEPLOY_OPENTELEMETRY),
            )

            has_permission = user.has_role(SecurityRoles.DEPLOY_OPENTELEMETRY)

            if not has_permission:
                logger.warning(
                    "User %s lacks DEPLOY_OPENTELEMETRY role for eligibility check",
                    current_user,
                )
                return OpenTelemetryEligibilityResponse(
                    eligible=False,
                    has_permission=False,
                    grafana_enabled=False,
                    opentelemetry_installed=False,
                    agent_privileged=False,
                    error_message=_(
                        "Permission denied: DEPLOY_OPENTELEMETRY role required"
                    ),
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

        # Check Grafana integration settings
        grafana_settings = (
            db.query(models.GrafanaIntegrationSettings).filter_by(enabled=True).first()
        )

        grafana_enabled = grafana_settings is not None

        # Check if agent is privileged
        agent_privileged = host.is_agent_privileged or False

        # Check if OS is supported (exclude OpenBSD and NetBSD)
        os_supported = True
        platform = (host.platform or "").lower()
        if "openbsd" in platform or "netbsd" in platform:
            os_supported = False

        # Check if OpenTelemetry is already installed
        # We check the software packages table for opentelemetry-related packages
        opentelemetry_installed = (
            db.query(models.SoftwarePackage)
            .filter(
                models.SoftwarePackage.host_id == host_id,
                models.SoftwarePackage.package_name.ilike("%otel%")
                | models.SoftwarePackage.package_name.ilike("%opentelemetry%")
                | models.SoftwarePackage.package_name.ilike("%alloy%"),
            )
            .first()
        ) is not None

        # Determine overall eligibility
        eligible = (
            grafana_enabled
            and not opentelemetry_installed
            and agent_privileged
            and os_supported
        )

        logger.info(
            "OpenTelemetry eligibility for host %s: grafana_enabled=%s, opentelemetry_installed=%s, agent_privileged=%s, eligible=%s",
            host_id,
            grafana_enabled,
            opentelemetry_installed,
            agent_privileged,
            eligible,
        )

        error_message = None
        if not eligible:
            reasons = []
            if not grafana_enabled:
                reasons.append(_("Grafana integration is not enabled"))
            if opentelemetry_installed:
                reasons.append(_("OpenTelemetry is already installed"))
            if not agent_privileged:
                reasons.append(_("Agent is not running in privileged mode"))
            if not os_supported:
                reasons.append(_("Operating system not supported (OpenBSD/NetBSD)"))

            if reasons:
                error_message = "; ".join(reasons)

        return OpenTelemetryEligibilityResponse(
            eligible=eligible,
            has_permission=True,  # User has DEPLOY_OPENTELEMETRY role if we got here
            grafana_enabled=grafana_enabled,
            opentelemetry_installed=opentelemetry_installed,
            agent_privileged=agent_privileged,
            error_message=error_message,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error checking OpenTelemetry eligibility: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to check OpenTelemetry eligibility: %s") % str(e),
        ) from e


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


@router.get(
    "/hosts/{host_id}/opentelemetry-status",
    dependencies=[Depends(JWTBearer())],
    response_model=OpenTelemetryStatusResponse,
)
async def get_opentelemetry_status(
    host_id: str,
    db: Session = Depends(get_db),
):
    """
    Get OpenTelemetry deployment and service status for a host.

    Args:
        host_id: The ID of the host to check
        db: Database session

    Returns:
        OpenTelemetryStatusResponse with status details
    """
    try:
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

        # Check if Grafana is configured
        grafana_settings = (
            db.query(models.GrafanaIntegrationSettings).filter_by(enabled=True).first()
        )
        grafana_configured = grafana_settings is not None
        grafana_url = grafana_settings.grafana_url if grafana_settings else None

        # Check if OpenTelemetry is deployed
        opentelemetry_installed = (
            db.query(models.SoftwarePackage)
            .filter(
                models.SoftwarePackage.host_id == host_id,
                models.SoftwarePackage.package_name.ilike("%otel%")
                | models.SoftwarePackage.package_name.ilike("%opentelemetry%"),
            )
            .first()
        ) is not None

        # Get service status from host_roles table
        # The agent's collect_roles() automatically detects and reports service status
        service_status = "unknown"

        if opentelemetry_installed:
            # Query the host_roles table for otelcol service status
            otel_role = (
                db.query(models.HostRole)
                .filter(
                    models.HostRole.host_id == host_id,
                    models.HostRole.package_name.ilike("%otelcol%"),
                )
                .first()
            )

            if otel_role and otel_role.service_status:
                service_status = otel_role.service_status
            else:
                # If no role entry exists yet, default to stopped
                # The agent will update this on next collect_roles call
                service_status = "stopped"

        return OpenTelemetryStatusResponse(
            deployed=opentelemetry_installed,
            service_status=service_status,
            grafana_url=grafana_url,
            grafana_configured=grafana_configured,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting OpenTelemetry status: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to get OpenTelemetry status: %s") % str(e),
        ) from e


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
            raise HTTPException(status_code=401, detail=_("User not found"))

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
                detail=_("Host not found or not active"),
            )

        validate_host_approval_status(host)

        # Queue the start service message
        message_data = {
            "command_type": "generic_command",
            "parameters": {
                "command_type": "start_opentelemetry_service",
                "parameters": {},
            },
        }

        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=message_data,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        logger.info(
            "Queued OpenTelemetry start for host %s (FQDN: %s)",
            host_id,
            host.fqdn,
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
            raise HTTPException(status_code=401, detail=_("User not found"))

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
                detail=_("Host not found or not active"),
            )

        validate_host_approval_status(host)

        # Queue the stop service message
        message_data = {
            "command_type": "generic_command",
            "parameters": {
                "command_type": "stop_opentelemetry_service",
                "parameters": {},
            },
        }

        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=message_data,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        logger.info(
            "Queued OpenTelemetry stop for host %s (FQDN: %s)",
            host_id,
            host.fqdn,
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
            raise HTTPException(status_code=401, detail=_("User not found"))

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
                detail=_("Host not found or not active"),
            )

        validate_host_approval_status(host)

        # Queue the restart service message
        message_data = {
            "command_type": "generic_command",
            "parameters": {
                "command_type": "restart_opentelemetry_service",
                "parameters": {},
            },
        }

        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=message_data,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        logger.info(
            "Queued OpenTelemetry restart for host %s (FQDN: %s)",
            host_id,
            host.fqdn,
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


@router.post(
    "/hosts/{host_id}/opentelemetry/connect",
    dependencies=[Depends(JWTBearer())],
    response_model=OpenTelemetryDeployResponse,
)
async def connect_opentelemetry_to_grafana(
    host_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Connect OpenTelemetry to Grafana server.

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
            raise HTTPException(status_code=401, detail=_("User not found"))

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
                detail=_("Host not found or not active"),
            )

        validate_host_approval_status(host)

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

        # Queue the connect message
        message_data = {
            "command_type": "generic_command",
            "parameters": {
                "command_type": "connect_opentelemetry_grafana",
                "parameters": {
                    "grafana_url": grafana_url,
                },
            },
        }

        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=message_data,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        logger.info(
            "Queued OpenTelemetry Grafana connection for host %s (FQDN: %s)",
            host_id,
            host.fqdn,
        )

        return OpenTelemetryDeployResponse(
            success=True,
            message=_("OpenTelemetry Grafana connection queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error connecting OpenTelemetry to Grafana: %s", e)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to connect OpenTelemetry to Grafana: %s") % str(e),
        ) from e


@router.post(
    "/hosts/{host_id}/opentelemetry/disconnect",
    dependencies=[Depends(JWTBearer())],
    response_model=OpenTelemetryDeployResponse,
)
async def disconnect_opentelemetry_from_grafana(
    host_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Disconnect OpenTelemetry from Grafana server.

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
            raise HTTPException(status_code=401, detail=_("User not found"))

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
                detail=_("Host not found or not active"),
            )

        validate_host_approval_status(host)

        # Queue the disconnect message
        message_data = {
            "command_type": "generic_command",
            "parameters": {
                "command_type": "disconnect_opentelemetry_grafana",
                "parameters": {},
            },
        }

        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=message_data,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        logger.info(
            "Queued OpenTelemetry Grafana disconnection for host %s (FQDN: %s)",
            host_id,
            host.fqdn,
        )

        return OpenTelemetryDeployResponse(
            success=True,
            message=_("OpenTelemetry Grafana disconnection queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error disconnecting OpenTelemetry from Grafana: %s", e)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to disconnect OpenTelemetry from Grafana: %s") % str(e),
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
