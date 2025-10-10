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
