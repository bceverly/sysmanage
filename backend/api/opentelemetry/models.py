"""
Pydantic models for OpenTelemetry API endpoints.
"""

from typing import Optional

from pydantic import BaseModel


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


class OpenTelemetryCoverageResponse(BaseModel):
    """Response model for OpenTelemetry coverage statistics."""

    total_hosts: int
    hosts_with_opentelemetry: int
    hosts_without_opentelemetry: int
    coverage_percentage: float
