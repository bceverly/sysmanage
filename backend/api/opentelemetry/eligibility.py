"""
OpenTelemetry eligibility check endpoints.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.security.roles import SecurityRoles

from .models import OpenTelemetryEligibilityResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/hosts/{host_id}/opentelemetry-eligible",
    dependencies=[Depends(JWTBearer())],
    response_model=OpenTelemetryEligibilityResponse,
)
async def check_opentelemetry_eligibility(  # NOSONAR - complex business logic
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
