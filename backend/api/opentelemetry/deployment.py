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
from backend.persistence.partitions import request_sessionmaker
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.services.observability_shim import (
    try_engine_otel_deploy,
    try_engine_otel_remove,
)
from backend.utils.verbosity_logger import sanitize_log

from .eligibility import check_opentelemetry_eligibility
from .models import OpenTelemetryDeployResponse

router = APIRouter()
logger = logging.getLogger(__name__)


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

        # Host data + the engine platform probe (which samples SoftwarePackage)
        # are tenant-scoped — route them to the active tenant's database.  User
        # RBAC (above), Grafana settings, and the audit trail (below) are
        # server-global and stay on the bootstrap ``db`` session.
        with request_sessionmaker()() as tenant_session:
            # Validate host exists and is active
            host = (
                tenant_session.query(models.Host)
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
            eligibility = await check_opentelemetry_eligibility(
                host_id, current_user, db
            )

            if not eligibility.eligible:
                raise HTTPException(
                    status_code=400,
                    detail=_("Host is not eligible for OpenTelemetry deployment: %s")
                    % eligibility.error_message,
                )

            # Get Grafana configuration (server-global singleton — bootstrap db)
            grafana_settings = (
                db.query(models.GrafanaIntegrationSettings)
                .filter_by(enabled=True)
                .first()
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

            # Capture host scalars for audit/logging after the session closes.
            host_fqdn = host.fqdn

            # Engine path only (Phase 10.2 step 7 close-out, 2026-05-14).
            # The legacy ``deploy_opentelemetry`` WS-command branch was
            # removed alongside the agent's ``opentelemetry_operations.py``
            # / ``otel_deploy_*.py`` modules.  An unlicensed OSS instance
            # (or one whose Pro+ engine .so isn't loaded) will see this
            # endpoint return 503 with a clear "engine required" message,
            # which is more honest than queuing a WS command the agent
            # has no handler for.  The platform probe samples SoftwarePackage,
            # so it runs on the tenant session.
            engine_msg_id = try_engine_otel_deploy(host, grafana_url, tenant_session)
            if engine_msg_id is None:
                raise HTTPException(
                    status_code=503,
                    detail=_(
                        "OpenTelemetry deployment requires the Pro+ "
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
            entity_name=host_fqdn,
            description=f"Requested OpenTelemetry deployment for host {host_fqdn}",
            result=Result.SUCCESS,
            details={"grafana_url": grafana_url, "dispatch_path": "engine_plan"},
        )
        db.commit()

        logger.info(
            "Queued OpenTelemetry deployment for host %s (FQDN: %s) via engine_plan",
            sanitize_log(host_id),
            host_fqdn,
        )

        return OpenTelemetryDeployResponse(
            success=True,
            message=_("OpenTelemetry deployment queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deploying OpenTelemetry: %s", e)
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

        # Host data + the engine platform probe (SoftwarePackage) are
        # tenant-scoped; User RBAC (above) and the audit trail (below) are
        # server-global and stay on the bootstrap ``db`` session.
        with request_sessionmaker()() as tenant_session:
            # Validate host exists and is active
            host = (
                tenant_session.query(models.Host)
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

            # Capture host scalars for audit/logging after the session closes.
            host_fqdn = host.fqdn

            # Engine path only — see deploy_opentelemetry above for rationale.
            engine_msg_id = try_engine_otel_remove(host, tenant_session)
            if engine_msg_id is None:
                raise HTTPException(
                    status_code=503,
                    detail=_(
                        "OpenTelemetry removal requires the Pro+ "
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
            entity_name=host_fqdn,
            description=f"Requested OpenTelemetry removal for host {host_fqdn}",
            result=Result.SUCCESS,
            details={"dispatch_path": "engine_plan"},
        )
        db.commit()

        logger.info(
            "Queued OpenTelemetry removal for host %s (FQDN: %s) via engine_plan",
            sanitize_log(host_id),
            host_fqdn,
        )

        return OpenTelemetryDeployResponse(
            success=True,
            message=_("OpenTelemetry removal queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error removing OpenTelemetry: %s", e)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to remove OpenTelemetry: %s") % str(e),
        ) from e
