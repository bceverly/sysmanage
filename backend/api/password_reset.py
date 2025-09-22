"""
This module provides password reset functionality for the SysManage server.
"""

import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer
from backend.config import config
from backend.i18n import _
from backend.persistence import db, models
from backend.services.email_service import email_service

router = APIRouter()  # Public routes (no authentication)
admin_router = APIRouter()  # Admin routes (require authentication)
argon2_hasher = PasswordHasher()


class ForgotPasswordRequest(BaseModel):
    """Request model for forgot password functionality."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Request model for password reset functionality."""

    token: str
    password: str
    confirm_password: str


class PasswordResetResponse(BaseModel):
    """Response model for password reset operations."""

    success: bool
    message: str


def generate_reset_token() -> str:
    """Generate a secure password reset token."""
    return str(uuid.uuid4())


def create_password_reset_token(user_id: str, session) -> str:
    """Create a password reset token for a user."""
    # Generate token
    token = generate_reset_token()

    # Set expiration (24 hours from now)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    # Create token record
    reset_token = models.PasswordResetToken(
        user_id=user_id,
        token=token,
        created_at=datetime.now(timezone.utc),
        expires_at=expires_at,
        used_at=None,
    )

    session.add(reset_token)
    session.commit()

    return token


def get_valid_reset_token(token: str, session) -> Optional[models.PasswordResetToken]:
    """Get a valid password reset token."""
    reset_token = (
        session.query(models.PasswordResetToken)
        .filter(
            models.PasswordResetToken.token == token,
            models.PasswordResetToken.used_at.is_(None),
            models.PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )

    return reset_token


def get_dynamic_hostname():
    """Get the best available hostname for URL generation, similar to CORS logic."""
    # First try to get FQDN
    try:
        fqdn = socket.getfqdn()
        if fqdn and fqdn != "localhost" and "." in fqdn:
            return fqdn
    except Exception:  # nosec B110
        pass

    # Fall back to hostname if FQDN isn't available
    try:
        hostname = socket.gethostname()
        if hostname and hostname != "localhost":
            return hostname
    except Exception:  # nosec B110
        pass

    # Final fallback to localhost
    return "localhost"


def send_password_reset_email(
    user_email: str, reset_token: str, request: Request
) -> bool:
    """Send password reset email to user."""
    if not email_service.is_enabled():
        return False

    # Get server configuration for building reset URL
    the_config = config.get_config()

    # Build reset URL - use dynamic hostname detection and configuration
    # Check if we have TLS configured to determine protocol
    is_secure = (
        the_config.get("api", {}).get("certFile") is not None
        and len(the_config.get("api", {}).get("certFile", "")) > 0
    )
    protocol = "https" if is_secure else "http"

    # Use dynamic hostname detection instead of config
    hostname = get_dynamic_hostname()
    frontend_port = the_config.get("webui", {}).get("port", 3000)

    base_url = f"{protocol}://{hostname}:{frontend_port}"
    reset_url = f"{base_url}/reset-password?token={reset_token}"

    # Get email templates from configuration with fallbacks
    email_config = the_config.get("email", {})
    templates = email_config.get("templates", {})
    password_reset_template = templates.get("password_reset", {})

    # Email content - use configured templates or fallbacks
    subject = password_reset_template.get("subject", "Password Reset Request")

    # Plain text email body
    body_template = password_reset_template.get(
        "text_body",
        """Hello,

We received a request to reset your password for your SysManage account.

To reset your password, please click the following link:
{reset_url}

This link will expire in 24 hours.

If you did not request this password reset, please ignore this email.

--
SysManage System""",
    )

    body = body_template.format(reset_url=reset_url)

    # HTML email body
    html_template = password_reset_template.get(
        "html_body",
        """<html>
<body>
<p>Hello,</p>

<p>We received a request to reset your password for your SysManage account.</p>

<p>To reset your password, please click the following link:</p>
<p><a href="{reset_url}">Reset Your Password</a></p>

<p>This link will expire in 24 hours.</p>

<p>If you did not request this password reset, please ignore this email.</p>

<hr>
<p><em>SysManage System</em></p>
</body>
</html>""",
    )

    html_body = html_template.format(reset_url=reset_url)

    return email_service.send_email(
        to_addresses=[user_email], subject=subject, body=body, html_body=html_body
    )


def send_initial_setup_email(
    user_email: str, setup_token: str, request: Request
) -> bool:
    """Send initial password setup email to new user."""
    if not email_service.is_enabled():
        return False

    # Get server configuration for building setup URL
    the_config = config.get_config()

    # Build setup URL - use dynamic hostname detection and configuration
    # Check if we have TLS configured to determine protocol
    is_secure = (
        the_config.get("api", {}).get("certFile") is not None
        and len(the_config.get("api", {}).get("certFile", "")) > 0
    )
    protocol = "https" if is_secure else "http"

    # Use dynamic hostname detection instead of config
    hostname = get_dynamic_hostname()
    frontend_port = the_config.get("webui", {}).get("port", 3000)

    base_url = f"{protocol}://{hostname}:{frontend_port}"
    setup_url = f"{base_url}/reset-password?token={setup_token}"

    # Get email templates from configuration with fallbacks
    email_config = the_config.get("email", {})
    templates = email_config.get("templates", {})
    initial_setup_template = templates.get("initial_setup", {})

    # Email content - use configured templates or fallbacks
    subject = initial_setup_template.get(
        "subject", "Welcome to SysManage - Set Your Password"
    )

    # Plain text email body
    body_template = initial_setup_template.get(
        "text_body",
        """Hello,

A SysManage account has been created for you by your system administrator.

To complete your account setup and set your initial password, please click the following link:
{setup_url}

This link will expire in 24 hours.

If you did not expect this email or have questions, please contact your system administrator.

Welcome to SysManage!

--
SysManage System""",
    )

    body = body_template.format(setup_url=setup_url)

    # HTML email body
    html_template = initial_setup_template.get(
        "html_body",
        """<html>
<body>
<p>Hello,</p>

<p>A SysManage account has been created for you by your system administrator.</p>

<p>To complete your account setup and set your initial password, please click the following link:</p>
<p><a href="{setup_url}">Set Up Your Account</a></p>

<p>This link will expire in 24 hours.</p>

<p>If you did not expect this email or have questions, please contact your system administrator.</p>

<p><strong>Welcome to SysManage!</strong></p>

<hr>
<p><em>SysManage System</em></p>
</body>
</html>""",
    )

    html_body = html_template.format(setup_url=setup_url)

    return email_service.send_email(
        to_addresses=[user_email], subject=subject, body=body, html_body=html_body
    )


@router.post("/forgot-password")
async def forgot_password(
    request_data: ForgotPasswordRequest, request: Request
) -> PasswordResetResponse:
    """
    Handle forgot password requests by sending a password reset email.

    Note: For security reasons, we don't reveal whether the email exists or not.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Look for user by email
        user = (
            session.query(models.User)
            .filter(models.User.userid == request_data.email)
            .first()
        )

        if user:
            # User exists - create reset token and send email
            reset_token = create_password_reset_token(user.id, session)

            # Send reset email
            email_sent = send_password_reset_email(
                str(user.userid), reset_token, request
            )

            if not email_sent:
                # Email service failed, but don't reveal this to the user
                pass

    # Always return success message for security (don't reveal if email exists)
    return PasswordResetResponse(
        success=True,
        message=_(
            "If an account with that email exists, a password reset link has been sent."
        ),
    )


@router.post("/reset-password")
async def reset_password(request_data: ResetPasswordRequest) -> PasswordResetResponse:
    """
    Handle password reset using a valid token.
    """
    # Validate password confirmation
    if request_data.password != request_data.confirm_password:
        raise HTTPException(status_code=400, detail=_("Passwords do not match"))

    # Basic password validation
    if len(request_data.password) < 8:
        raise HTTPException(
            status_code=400, detail=_("Password must be at least 8 characters long")
        )

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Get and validate reset token
        reset_token = get_valid_reset_token(request_data.token, session)

        if not reset_token:
            raise HTTPException(
                status_code=400, detail=_("Invalid or expired password reset token")
            )

        # Get the user
        user = session.query(models.User).get(reset_token.user_id)
        if not user:
            raise HTTPException(status_code=400, detail=_("User not found"))

        # Hash the new password
        hashed_password = argon2_hasher.hash(request_data.password)

        # Update user password
        user.hashed_password = hashed_password

        # Mark token as used
        reset_token.used_at = datetime.now(timezone.utc)

        session.commit()

    return PasswordResetResponse(
        success=True,
        message=_(
            "Your password has been successfully reset. You can now log in with your new password."
        ),
    )


@router.get("/validate-reset-token/{token}")
async def validate_reset_token(token: str) -> PasswordResetResponse:
    """
    Validate a password reset token without using it.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        reset_token = get_valid_reset_token(token, session)

        if not reset_token:
            raise HTTPException(
                status_code=400, detail=_("Invalid or expired password reset token")
            )

    return PasswordResetResponse(success=True, message=_("Token is valid"))


@admin_router.post(
    "/admin/reset-user-password/{user_id}", dependencies=[Depends(JWTBearer())]
)
async def admin_reset_user_password(
    user_id: str, request: Request
) -> PasswordResetResponse:
    """
    Admin endpoint to trigger password reset for a specific user.
    This is for use from the user details page.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Get the user
        user = session.query(models.User).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail=_("User not found"))

        # Create reset token
        reset_token = create_password_reset_token(user.id, session)

        # Send reset email
        email_sent = send_password_reset_email(str(user.userid), reset_token, request)

        if not email_sent:
            raise HTTPException(
                status_code=500,
                detail=_(
                    "Failed to send password reset email. Please check email configuration."
                ),
            )

    return PasswordResetResponse(
        success=True,
        message=_("Password reset email has been sent to {email}").format(
            email=user.userid
        ),
    )
