"""
Security API endpoints for checking system security status and configurations.
"""

import logging
import platform
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker
from backend.auth.auth_bearer import get_current_user
from backend.config import config
from backend.persistence import db, models

# Known default values that should be changed in production
DEFAULT_JWT_SECRETS = {
    "I+Z74n/CFHser01E47pyrL91OuonEX9hNSvVFr/KLi4=",
}

DEFAULT_PASSWORD_SALTS = {
    "6/InQvDb8f3cM6sao8kWzIiYVHKGH9sqkEJ3uZhIo9Q=",
}

logger = logging.getLogger(__name__)


def _get_platform_command(script_args=""):
    """Generate cross-platform command for running the migration script."""
    system = platform.system().lower()

    if system == "windows":
        # Windows: Try py launcher first, then python
        base_commands = ["py -3", "python"]
    else:
        # Unix-like (Linux, macOS, BSD): Try python3 first, then python
        base_commands = ["python3", "python"]

    script_path = "scripts/migrate-security-config.py"
    return f"{base_commands[0]} {script_path} {script_args}".strip()


class SecurityWarning(BaseModel):
    """Model for individual security warnings."""

    type: str
    severity: str  # "critical", "warning"
    message: str
    details: Optional[str] = None


class SecurityStatusResponse(BaseModel):
    """Response model for security status checks."""

    hasDefaultCredentials: bool
    isLoggedInAsDefault: bool
    defaultUserId: str
    securityWarnings: List[SecurityWarning]
    hasDefaultJwtSecret: bool
    hasDefaultPasswordSalt: bool


router = APIRouter(prefix="/security", tags=["security"])


def _get_database_user_count():
    """Get count of users in database."""
    try:
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db.get_engine()
        )
        with session_local() as session:
            return session.query(models.User).count()
    except Exception as e:
        logger.error("Failed to get user count: %s", e)
        return 0


def _check_security_configuration():
    """
    Comprehensive security configuration check with logging.
    Returns warnings and logs security issues.
    """
    app_config = config.get_config()
    warnings = []
    config_path = config.CONFIG_PATH  # /etc/sysmanage.yaml or fallback

    # Check default admin credentials
    admin_userid = app_config.get("security", {}).get("admin_userid")
    admin_password = app_config.get("security", {}).get("admin_password")
    has_default_credentials = bool(admin_userid and admin_password)

    if has_default_credentials:
        logger.warning("SECURITY: Default admin credentials found in %s", config_path)
        warnings.append(
            SecurityWarning(
                type="default_credentials",
                severity="critical",
                message="Default admin credentials are configured in your YAML file",
                details="Remove admin_userid and admin_password from your configuration file and restart the server",
            )
        )

    # Check JWT secret
    jwt_secret = app_config.get("security", {}).get("jwt_secret")
    has_default_jwt = jwt_secret in DEFAULT_JWT_SECRETS

    if has_default_jwt:
        logger.warning("SECURITY: Default JWT secret detected in %s", config_path)
        warnings.append(
            SecurityWarning(
                type="default_jwt_secret",
                severity="warning",
                message="Default JWT secret is being used",
                details=f"Run: {_get_platform_command('--jwt-only')}",
            )
        )

    # Check password salt
    password_salt = app_config.get("security", {}).get("password_salt")
    has_default_salt = password_salt in DEFAULT_PASSWORD_SALTS
    user_count = _get_database_user_count()

    if has_default_salt:
        logger.warning("SECURITY: Default password salt detected in %s", config_path)
        if user_count > 0:
            warnings.append(
                SecurityWarning(
                    type="default_password_salt",
                    severity="warning",
                    message="Default password salt is being used",
                    details=f"Run: {_get_platform_command()} ({user_count} users will be migrated)",
                )
            )
        else:
            warnings.append(
                SecurityWarning(
                    type="default_password_salt",
                    severity="warning",
                    message="Default password salt is being used",
                    details=f"Run: {_get_platform_command()}",
                )
            )

    # Check for mixed security states
    if has_default_jwt and not has_default_salt:
        logger.warning(
            "SECURITY: Mixed security state in %s: JWT secret is default but password salt is custom",
            config_path,
        )
        warnings.append(
            SecurityWarning(
                type="mixed_security_config",
                severity="warning",
                message="Inconsistent security configuration detected",
                details=f"JWT secret uses default value but password salt has been changed. Run: {_get_platform_command('--jwt-only')}",
            )
        )
    elif not has_default_jwt and has_default_salt:
        logger.warning(
            "SECURITY: Mixed security state in %s: Password salt is default but JWT secret is custom",
            config_path,
        )
        warnings.append(
            SecurityWarning(
                type="mixed_security_config",
                severity="warning",
                message="Inconsistent security configuration detected",
                details=f"Password salt uses default value but JWT secret has been changed. Run: {_get_platform_command('--salt-only')}",
            )
        )

    return warnings, has_default_jwt, has_default_salt


@router.get("/default-credentials-status", response_model=SecurityStatusResponse)
async def get_default_credentials_status(current_user=Depends(get_current_user)):
    """
    Comprehensive security status check including default credentials, JWT secrets, and password salts.

    Returns detailed security information and logs all security issues found.
    """
    app_config = config.get_config()

    # Check if default admin credentials are configured
    admin_userid = app_config.get("security", {}).get("admin_userid")
    admin_password = app_config.get("security", {}).get("admin_password")

    has_default_credentials = bool(admin_userid and admin_password)

    # Check if current user is the default admin user
    current_userid = current_user if current_user else ""
    is_logged_in_as_default = has_default_credentials and current_userid == admin_userid

    # Perform comprehensive security checks
    security_warnings, has_default_jwt, has_default_salt = (
        _check_security_configuration()
    )

    return SecurityStatusResponse(
        hasDefaultCredentials=has_default_credentials,
        isLoggedInAsDefault=is_logged_in_as_default,
        defaultUserId=admin_userid or "",
        securityWarnings=security_warnings,
        hasDefaultJwtSecret=has_default_jwt,
        hasDefaultPasswordSalt=has_default_salt,
    )
