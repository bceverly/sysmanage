# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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
from backend.persistence.partitions import get_tenant_db, request_sessionmaker

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
        # Host + software inventory + roles are tenant-scoped — route them to the
        # active tenant's database.  Grafana settings (below) are a server-global
        # singleton and stay on the bootstrap session.
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

            # Check if OpenTelemetry is deployed
            opentelemetry_installed = (
                tenant_session.query(models.SoftwarePackage)
                .filter(
                    models.SoftwarePackage.host_id == host_id,
                    models.SoftwarePackage.package_name.ilike("%otel%")
                    | models.SoftwarePackage.package_name.ilike("%opentelemetry%"),
                )
                .first()
            ) is not None

            # Get service status from host_roles table
            # The agent's collect_roles() automatically detects and reports status
            service_status = "unknown"

            if opentelemetry_installed:
                # Query the host_roles table for otelcol service status
                otel_role = (
                    tenant_session.query(models.HostRole)
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

        # Check if Grafana is configured (server-global singleton).
        grafana_settings = (
            db.query(models.GrafanaIntegrationSettings).filter_by(enabled=True).first()
        )
        grafana_configured = grafana_settings is not None
        grafana_url = grafana_settings.grafana_url if grafana_settings else None

        return OpenTelemetryStatusResponse(
            deployed=opentelemetry_installed,
            service_status=service_status,
            grafana_url=grafana_url,
            grafana_configured=grafana_configured,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting OpenTelemetry status: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to get OpenTelemetry status: %s") % str(e),
        ) from e


@router.get(
    "/opentelemetry-coverage",
    response_model=OpenTelemetryCoverageResponse,
    dependencies=[Depends(JWTBearer())],
)
async def get_opentelemetry_coverage(db: Session = Depends(get_tenant_db)):
    """
    Get OpenTelemetry coverage statistics across all registered hosts.

    Returns:
        OpenTelemetryCoverageResponse with coverage statistics
    """
    try:
        total_hosts = db.query(models.Host).count()

        if total_hosts == 0:
            return OpenTelemetryCoverageResponse(
                total_hosts=0,
                hosts_with_opentelemetry=0,
                hosts_without_opentelemetry=0,
                coverage_percentage=0.0,
            )

        # Bulk-fetch instead of one query per host (the previous loop
        # issued 2N queries and was the worst N+1 site flagged in the
        # Phase 6 audit).  Two queries total now, regardless of fleet
        # size.
        host_ids_with_otel_pkg = {
            row[0]
            for row in db.query(models.SoftwarePackage.host_id)
            .filter(
                models.SoftwarePackage.package_name.ilike("%otel%")
                | models.SoftwarePackage.package_name.ilike("%opentelemetry%")
            )
            .distinct()
            .all()
        }
        host_ids_with_running_otelcol = {
            row[0]
            for row in db.query(models.HostRole.host_id)
            .filter(
                models.HostRole.package_name.ilike("%otelcol%"),
                models.HostRole.service_status == "running",
            )
            .all()
        }

        hosts_with_opentelemetry = len(
            host_ids_with_otel_pkg & host_ids_with_running_otelcol
        )
        hosts_without_opentelemetry = total_hosts - hosts_with_opentelemetry
        coverage_percentage = hosts_with_opentelemetry / total_hosts * 100

        return OpenTelemetryCoverageResponse(
            total_hosts=total_hosts,
            hosts_with_opentelemetry=hosts_with_opentelemetry,
            hosts_without_opentelemetry=hosts_without_opentelemetry,
            coverage_percentage=round(coverage_percentage, 2),
        )

    except Exception as e:
        logger.exception("Error getting OpenTelemetry coverage statistics: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve OpenTelemetry coverage: %s") % str(e),
        ) from e
