"""
OpenTelemetry Grafana connection endpoints (connect/disconnect).
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
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.utils.verbosity_logger import sanitize_log
from backend.services.observability_shim import (
    try_engine_otel_grafana_connection,
)

from .models import OpenTelemetryDeployResponse

router = APIRouter()
logger = logging.getLogger(__name__)


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

        # Engine path only (Phase 10.2 step 7 close-out, 2026-05-14).
        # Plan is restart-only (matches legacy semantics — config
        # was pinned at deploy time, connect just triggers a service
        # restart so any out-of-band edits take effect).
        engine_msg_id = try_engine_otel_grafana_connection(
            host, "connect", grafana_url, db
        )
        if engine_msg_id is None:
            raise HTTPException(
                status_code=503,
                detail=_(
                    "OpenTelemetry Grafana connection requires the Pro+ "
                    "observability_engine to be loaded on the server."
                ),
            )

        AuditService.log(
            db=db,
            user_id=auth_user.id,
            username=current_user,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=(
                f"Requested OpenTelemetry → Grafana connection for host {host.fqdn}"
            ),
            result=Result.SUCCESS,
            details={
                "dispatch_path": "engine_plan",
                "grafana_url": grafana_url,
                "grafana_action": "connect",
            },
        )
        db.commit()

        logger.info(
            "Queued OpenTelemetry Grafana connection for host %s (FQDN: %s) via engine_plan",
            sanitize_log(host_id),
            host.fqdn,
        )

        return OpenTelemetryDeployResponse(
            success=True,
            message=_("OpenTelemetry Grafana connection queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error connecting OpenTelemetry to Grafana: %s", e)
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

        # Engine path only — see connect endpoint above for rationale.
        engine_msg_id = try_engine_otel_grafana_connection(host, "disconnect", "", db)
        if engine_msg_id is None:
            raise HTTPException(
                status_code=503,
                detail=_(
                    "OpenTelemetry Grafana disconnection requires the Pro+ "
                    "observability_engine to be loaded on the server."
                ),
            )

        AuditService.log(
            db=db,
            user_id=auth_user.id,
            username=current_user,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=(
                f"Requested OpenTelemetry → Grafana disconnection for host {host.fqdn}"
            ),
            result=Result.SUCCESS,
            details={"dispatch_path": "engine_plan", "grafana_action": "disconnect"},
        )
        db.commit()

        logger.info(
            "Queued OpenTelemetry Grafana disconnection for host %s "
            "(FQDN: %s) via engine_plan",
            sanitize_log(host_id),
            host.fqdn,
        )

        return OpenTelemetryDeployResponse(
            success=True,
            message=_("OpenTelemetry Grafana disconnection queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error disconnecting OpenTelemetry from Grafana: %s", e)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to disconnect OpenTelemetry from Grafana: %s") % str(e),
        ) from e
