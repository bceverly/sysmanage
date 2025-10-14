"""
OpenTelemetry status check endpoints.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db

from .models import OpenTelemetryCoverageResponse, OpenTelemetryStatusResponse

router = APIRouter()
logger = logging.getLogger(__name__)


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


@router.get(
    "/opentelemetry-coverage",
    response_model=OpenTelemetryCoverageResponse,
    dependencies=[Depends(JWTBearer())],
)
async def get_opentelemetry_coverage(db: Session = Depends(get_db)):
    """
    Get OpenTelemetry coverage statistics across all registered hosts.

    Returns:
        OpenTelemetryCoverageResponse with coverage statistics
    """
    try:
        # Get all registered hosts
        all_hosts = db.query(models.Host).all()
        total_hosts = len(all_hosts)

        if total_hosts == 0:
            return OpenTelemetryCoverageResponse(
                total_hosts=0,
                hosts_with_opentelemetry=0,
                hosts_without_opentelemetry=0,
                coverage_percentage=0.0,
            )

        # Count hosts with OpenTelemetry deployed AND running
        hosts_with_opentelemetry = 0

        for host in all_hosts:
            # Check if OpenTelemetry is installed
            opentelemetry_installed = (
                db.query(models.SoftwarePackage)
                .filter(
                    models.SoftwarePackage.host_id == host.id,
                    models.SoftwarePackage.package_name.ilike("%otel%")
                    | models.SoftwarePackage.package_name.ilike("%opentelemetry%"),
                )
                .first()
            ) is not None

            if opentelemetry_installed:
                # Check if service is running
                otel_role = (
                    db.query(models.HostRole)
                    .filter(
                        models.HostRole.host_id == host.id,
                        models.HostRole.package_name.ilike("%otelcol%"),
                    )
                    .first()
                )

                # Count as deployed if installed and running
                if otel_role and otel_role.service_status == "running":
                    hosts_with_opentelemetry += 1

        hosts_without_opentelemetry = total_hosts - hosts_with_opentelemetry
        coverage_percentage = (
            (hosts_with_opentelemetry / total_hosts * 100) if total_hosts > 0 else 0.0
        )

        return OpenTelemetryCoverageResponse(
            total_hosts=total_hosts,
            hosts_with_opentelemetry=hosts_with_opentelemetry,
            hosts_without_opentelemetry=hosts_without_opentelemetry,
            coverage_percentage=round(coverage_percentage, 2),
        )

    except Exception as e:
        logger.error("Error getting OpenTelemetry coverage statistics: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve OpenTelemetry coverage: %s") % str(e),
        ) from e
