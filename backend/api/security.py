# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Security API endpoints for checking system security status and configurations.
"""

import logging
import os
import platform
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import get_current_user
from backend.config import config
from backend.i18n import _
from backend.persistence import db, models

# Known default values that should be changed in production
DEFAULT_JWT_SECRETS = {
    "I+Z74n/CFHser01E47pyrL91OuonEX9hNSvVFr/KLi4=",
}

DEFAULT_PASSWORD_SALTS = {
    "6/InQvDb8f3cM6sao8kWzIiYVHKGH9sqkEJ3uZhIo9Q=",
}

logger = logging.getLogger(__name__)


def _install_root() -> Path:
    """Directory holding backend/ and scripts/ for THIS install."""
    # backend/api/security.py -> backend/api -> backend -> <root>
    return Path(__file__).resolve().parents[2]


def _get_platform_command(script_args=""):
    """The command that actually works ON THIS HOST, absolute and runnable.

    This used to emit a bare ``python3 scripts/migrate-security-config.py``,
    which is only correct when the reader happens to be sitting in a source
    checkout with the right interpreter first on PATH.  A packaged install has
    neither: the interpreter is a specific ports/venv binary and the script
    lives under the install prefix.  ``sys.executable`` is by definition the
    interpreter running this server, and the script sits beside the backend
    package, so both are derived rather than guessed.

    ``--config`` is passed explicitly.  The script's own autodetection prefers
    /etc/sysmanage.yaml, so on a host that also has a development config there,
    it would rewrite that file instead of the one this server is using and
    report success.
    """
    script_path = _install_root() / "scripts" / "migrate-security-config.py"
    config_path = os.environ.get("SYSMANAGE_CONFIG_PATH")
    parts = [sys.executable, str(script_path)]
    if config_path:
        parts += ["--config", config_path]
    if script_args:
        parts.append(script_args)
    # Editing the config requires root everywhere except Windows, which has no
    # sudo and elevates differently.
    if platform.system().lower() != "windows":
        parts.insert(0, "sudo")
    return " ".join(parts)


def _get_restart_command() -> str:
    """How to restart the service on this platform.

    The UI used to say "Restart the server with ./run.sh", which is the
    developer workflow and does not exist in any package.
    """
    system = platform.system().lower()
    if system == "windows":
        return "Restart-Service sysmanage"
    if system in ("freebsd", "netbsd", "openbsd"):
        return "sudo service sysmanage restart"
    if system == "darwin":
        return "sudo brew services restart sysmanage"
    return "sudo systemctl restart sysmanage"


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
    # Commands resolved on the SERVER, for the UI to display verbatim.  The
    # banner previously hardcoded /opt/sysmanage/.venv/bin/python, which is one
    # Linux packaging layout and wrong for the ports, Homebrew and Windows.
    jwtCommand: str = ""
    saltCommand: str = ""
    restartCommand: str = ""


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
        logger.exception("Failed to get user count: %s", e)
        return 0


def _check_security_configuration():
    """
    Comprehensive security configuration check with logging.
    Returns warnings and logs security issues.
    """
    app_config = config.get_config()
    warnings = []

    # Check email integration configuration
    email_enabled = app_config.get("email", {}).get("enabled", False)
    if not email_enabled:
        logger.warning(
            "SECURITY: Email integration is not enabled - users cannot receive password setup emails"
        )
        warnings.append(
            SecurityWarning(
                type="email_integration_required",
                severity="warning",
                message=_(
                    "Email integration must be configured before creating new users"
                ),
                details=_(
                    "Enable email in your YAML configuration file and configure SMTP settings. Without email integration, new users cannot receive password setup instructions and will be unable to log in."
                ),
            )
        )

    # Check default admin credentials
    admin_userid = app_config.get("security", {}).get("admin_userid")
    admin_password = app_config.get("security", {}).get("admin_password")
    has_default_credentials = bool(admin_userid and admin_password)

    if has_default_credentials:
        logger.warning(
            "SECURITY: Default admin credentials found in configuration file"
        )
        warnings.append(
            SecurityWarning(
                type="default_credentials",
                severity="critical",
                message=_("Default admin credentials are configured in your YAML file"),
                details=_(
                    "Remove admin_userid and admin_password from your configuration file and restart the server"
                ),
            )
        )

    # Check JWT secret
    jwt_secret = app_config.get("security", {}).get("jwt_secret")
    has_default_jwt = jwt_secret in DEFAULT_JWT_SECRETS

    if has_default_jwt:
        logger.warning("SECURITY: Default JWT secret detected in configuration")
        warnings.append(
            SecurityWarning(
                type="default_jwt_secret",
                severity="warning",
                message=_("Default JWT secret is being used"),
                details=_("Run: {command}").format(
                    command=_get_platform_command("--jwt-only")
                ),
            )
        )

    # Check password salt
    password_salt = app_config.get("security", {}).get("password_salt")
    has_default_salt = password_salt in DEFAULT_PASSWORD_SALTS
    user_count = _get_database_user_count()

    if has_default_salt:
        logger.warning("SECURITY: Default password salt detected in configuration")
        if user_count > 0:
            warnings.append(
                SecurityWarning(
                    type="default_password_salt",
                    severity="warning",
                    message=_("Default password salt is being used"),
                    details=_("Run: {command} ({count} users will be migrated)").format(
                        command=_get_platform_command(), count=user_count
                    ),
                )
            )
        else:
            warnings.append(
                SecurityWarning(
                    type="default_password_salt",
                    severity="warning",
                    message=_("Default password salt is being used"),
                    details=_("Run: {command}").format(command=_get_platform_command()),
                )
            )

    # Check for mixed security states
    if has_default_jwt and not has_default_salt:
        logger.warning(
            "SECURITY: Mixed security state - JWT secret is default but password salt is custom"
        )
        warnings.append(
            SecurityWarning(
                type="mixed_security_config",
                severity="warning",
                message=_("Inconsistent security configuration detected"),
                details=_(
                    "JWT secret uses default value but password salt has been changed. Run: {command}"
                ).format(command=_get_platform_command("--jwt-only")),
            )
        )
    elif not has_default_jwt and has_default_salt:
        logger.warning(
            "SECURITY: Mixed security state - Password salt is default but JWT secret is custom"
        )
        warnings.append(
            SecurityWarning(
                type="mixed_security_config",
                severity="warning",
                message=_("Inconsistent security configuration detected"),
                details=_(
                    "Password salt uses default value but JWT secret has been changed. Run: {command}"
                ).format(command=_get_platform_command("--salt-only")),
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
        jwtCommand=_get_platform_command("--jwt-only"),
        saltCommand=_get_platform_command("--salt-only"),
        restartCommand=_get_restart_command(),
    )
