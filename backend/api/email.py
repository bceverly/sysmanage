"""
Email configuration and testing API endpoints.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from backend.auth.auth_bearer import get_current_user
from backend.config import config
from backend.services.email_service import email_service

logger = logging.getLogger(__name__)


class EmailTestRequest(BaseModel):
    """Request model for testing email configuration."""

    to_address: EmailStr


class EmailConfigResponse(BaseModel):
    """Response model for email configuration status."""

    enabled: bool
    smtp_host: str
    smtp_port: int
    from_address: str
    from_name: str
    subject_prefix: str
    configured: bool  # Whether SMTP is properly configured


class EmailTestResponse(BaseModel):
    """Response model for email test results."""

    success: bool
    message: str


router = APIRouter(prefix="/email", tags=["email"])


@router.get("/config", response_model=EmailConfigResponse)
async def get_email_config(current_user=Depends(get_current_user)):
    """
    Get email configuration status (read-only view for UI).
    Returns configuration details without sensitive information.
    """
    try:
        email_config = config.get_email_config()
        smtp_config = config.get_smtp_config()

        # Check if SMTP is properly configured (has host and credentials if not localhost)
        smtp_host = smtp_config.get("host", "")
        smtp_username = smtp_config.get("username", "")
        smtp_password = smtp_config.get("password", "")

        # Consider it configured if:
        # 1. Host is localhost (no auth needed), OR
        # 2. Host is set and both username/password are provided
        is_configured = smtp_host == "localhost" or (
            smtp_host and smtp_username and smtp_password
        )

        enabled_value = email_config.get("enabled", False)

        return EmailConfigResponse(
            enabled=bool(enabled_value),  # Ensure it's a boolean
            smtp_host=smtp_host,
            smtp_port=smtp_config.get("port", 587),
            from_address=email_config.get("from_address", ""),
            from_name=email_config.get("from_name", ""),
            subject_prefix=email_config.get("templates", {}).get("subject_prefix", ""),
            configured=bool(is_configured),  # Ensure it's a boolean
        )
    except Exception as e:
        logger.error("Failed to get email configuration: %s", str(e))
        raise HTTPException(
            status_code=500, detail="Failed to get email configuration"
        ) from e


@router.post("/test", response_model=EmailTestResponse)
async def test_email_config(
    request: EmailTestRequest, current_user=Depends(get_current_user)
):
    """
    Send a test email to verify SMTP configuration.
    """
    try:
        if not email_service.is_enabled():
            return EmailTestResponse(
                success=False,
                message="Email service is disabled. Enable it in the configuration file.",
            )

        # Send test email
        success = email_service.send_test_email(request.to_address)

        if success:
            return EmailTestResponse(
                success=True,
                message=f"Test email sent successfully to {request.to_address}",
            )
        return EmailTestResponse(
            success=False,
            message="Failed to send test email. Please check your SMTP configuration.",
        )

    except Exception as e:
        logger.error("Failed to send test email: %s", e)
        return EmailTestResponse(
            success=False, message=f"Error sending test email: {str(e)}"
        )
