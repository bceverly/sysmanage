"""
Telemetry API endpoints for monitoring OpenTelemetry and Prometheus status.
"""

import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.auth.auth_bearer import JWTBearer
from backend.telemetry.otel_config import is_telemetry_enabled

router = APIRouter()
logger = logging.getLogger(__name__)


class OpenTelemetryStatus(BaseModel):
    """Model for OpenTelemetry status information."""

    enabled: bool
    collector_url: Optional[str] = None
    prometheus_port: Optional[int] = None
    instrumentation: Optional[dict] = None


class PrometheusStatus(BaseModel):
    """Model for Prometheus status information."""

    running: bool
    version: Optional[str] = None
    url: Optional[str] = None
    scrape_interval: Optional[str] = None
    retention_time: Optional[str] = None
    targets_count: Optional[int] = None
    healthy_targets: Optional[int] = None


@router.get("/opentelemetry/status", dependencies=[Depends(JWTBearer())])
async def get_opentelemetry_status():
    """
    Get OpenTelemetry instrumentation status.
    """
    enabled = is_telemetry_enabled()

    status = OpenTelemetryStatus(enabled=enabled)

    if enabled:
        # Get configuration from environment
        status.collector_url = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
        )
        status.prometheus_port = int(os.getenv("OTEL_PROMETHEUS_PORT", "9090"))

        # Report instrumentation status (these are all enabled when OTEL is enabled)
        status.instrumentation = {
            "fastapi": True,
            "sqlalchemy": True,
            "requests": True,
            "logging": True,
        }

    return status


@router.get("/prometheus/status", dependencies=[Depends(JWTBearer())])
async def get_prometheus_status():  # NOSONAR - complex business logic
    """
    Get Prometheus server status by checking the Prometheus API.
    """
    prometheus_url = os.getenv("PROMETHEUS_URL", "http://localhost:9091")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Try to get Prometheus status
            status_response = await client.get(f"{prometheus_url}/-/healthy")

            if status_response.status_code == 200:
                # Prometheus is running, try to get more info
                running = True
                version = None
                targets_count = None
                healthy_targets = None

                # Try to get build info
                try:
                    buildinfo_response = await client.get(
                        f"{prometheus_url}/api/v1/status/buildinfo"
                    )
                    if buildinfo_response.status_code == 200:
                        build_data = buildinfo_response.json()
                        if build_data.get("status") == "success":
                            version = build_data.get("data", {}).get("version")
                except Exception as e:  # pylint: disable=broad-except
                    logger.debug("Could not fetch Prometheus build info: %s", e)

                # Try to get targets info
                try:
                    targets_response = await client.get(
                        f"{prometheus_url}/api/v1/targets"
                    )
                    if targets_response.status_code == 200:
                        targets_data = targets_response.json()
                        if targets_data.get("status") == "success":
                            active_targets = targets_data.get("data", {}).get(
                                "activeTargets", []
                            )
                            targets_count = len(active_targets)
                            healthy_targets = sum(
                                1
                                for target in active_targets
                                if target.get("health") == "up"
                            )
                except Exception as e:  # pylint: disable=broad-except
                    logger.debug("Could not fetch Prometheus targets: %s", e)

                return PrometheusStatus(
                    running=running,
                    version=version,
                    url=prometheus_url,
                    scrape_interval="15s",  # Default from config
                    retention_time="15d",  # Default from config
                    targets_count=targets_count,
                    healthy_targets=healthy_targets,
                )

            return PrometheusStatus(running=False)

    except httpx.ConnectError:
        logger.debug("Prometheus not reachable at %s", prometheus_url)
        return PrometheusStatus(running=False)
    except Exception as e:  # pylint: disable=broad-except
        logger.error("Error checking Prometheus status: %s", e)
        return PrometheusStatus(running=False)
