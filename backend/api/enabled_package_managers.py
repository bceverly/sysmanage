"""
This module houses the API routes for enabled package manager settings management in SysManage.
Enabled package managers represent additional (non-default) package managers that should be
available on hosts based on their operating system. For example, enabling snap or flatpak
on Ubuntu in addition to the default APT.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session, sessionmaker

from backend.api.error_constants import error_user_not_found
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.persistence.db import get_db
from backend.security.roles import SecurityRoles
from backend.services.audit_service import AuditService, EntityType
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)

router = APIRouter()


# Default package managers for each OS (always enabled, not configurable)
OS_DEFAULT_PACKAGE_MANAGERS = {
    "Ubuntu": "APT, snap",
    "Debian": "APT",
    "RHEL": "dnf",
    "CentOS": "dnf",
    "CentOS Stream": "dnf",
    "Fedora": "dnf",
    "Rocky Linux": "dnf",
    "AlmaLinux": "dnf",
    "Oracle Linux": "dnf",
    "openSUSE": "zypper",
    "SLES": "zypper",
    "FreeBSD": "pkg",
    "OpenBSD": "pkg_add",
    "NetBSD": "pkgin",
    "macOS": None,  # No default, homebrew is optional
    "Windows": "winget",
}

# Optional package managers that can be enabled per OS
OS_OPTIONAL_PACKAGE_MANAGERS = {
    "Ubuntu": ["flatpak", "homebrew"],  # snap is a builtin default on Ubuntu
    "Debian": ["snap", "flatpak"],
    "RHEL": ["flatpak", "snap"],
    "CentOS": ["flatpak", "snap"],
    "CentOS Stream": ["flatpak", "snap"],
    "Fedora": ["flatpak", "snap"],
    "Rocky Linux": ["flatpak", "snap"],
    "AlmaLinux": ["flatpak", "snap"],
    "Oracle Linux": ["flatpak", "snap"],
    "openSUSE": ["flatpak", "snap"],
    "SLES": ["flatpak"],
    "FreeBSD": [],  # No optional managers
    "OpenBSD": [],  # No optional managers
    "NetBSD": [],  # No optional managers
    "macOS": ["homebrew"],
    "Windows": ["chocolatey", "scoop"],
}


class EnabledPackageManagerResponse(BaseModel):
    """Response model for enabled package manager."""

    id: str
    os_name: str
    package_manager: str
    created_at: datetime
    created_by: Optional[str] = None

    @validator("id", "created_by", pre=True)
    def convert_uuid_to_string(cls, value):  # pylint: disable=no-self-argument
        """Convert UUID objects to strings."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    class Config:
        from_attributes = True


class EnabledPackageManagerCreate(BaseModel):
    """Request model for creating an enabled package manager."""

    os_name: str
    package_manager: str

    @validator("os_name")
    def validate_os_name(cls, os_name):  # pylint: disable=no-self-argument
        """Validate OS name."""
        if not os_name or os_name.strip() == "":
            raise ValueError(_("OS name is required"))
        if os_name.strip() not in OS_OPTIONAL_PACKAGE_MANAGERS:
            raise ValueError(_("Unsupported operating system: %s") % os_name)
        return os_name.strip()

    @validator("package_manager")
    def validate_package_manager(
        cls, package_manager, values
    ):  # pylint: disable=no-self-argument
        """Validate package manager is an optional one for the selected OS."""
        if not package_manager or package_manager.strip() == "":
            raise ValueError(_("Package manager is required"))
        os_name = values.get("os_name", "").strip()
        if os_name and os_name in OS_OPTIONAL_PACKAGE_MANAGERS:
            valid_managers = OS_OPTIONAL_PACKAGE_MANAGERS[os_name]
            if package_manager.strip() not in valid_managers:
                raise ValueError(
                    _("Invalid package manager '%s' for OS '%s'. Valid options: %s")
                    % (package_manager, os_name, ", ".join(valid_managers))
                )
        return package_manager.strip()


class OSOptionsResponse(BaseModel):
    """Response model for OS and optional package manager options."""

    operating_systems: List[str]
    default_package_managers: dict
    optional_package_managers: dict


def get_approved_privileged_hosts_by_os(db_session: Session, os_name: str) -> List:
    """
    Get all approved, privileged hosts that match the given OS distribution.

    The os_name is matched against the 'distribution' field in the host's os_details JSON.
    """
    hosts = (
        db_session.query(models.Host)
        .filter(
            models.Host.approval_status == "approved",
            models.Host.is_agent_privileged
            == True,  # noqa: E712 - SQLAlchemy requires == for boolean
            models.Host.os_details.isnot(None),
        )
        .all()
    )

    matching_hosts = []
    for host in hosts:
        try:
            os_details = json.loads(host.os_details) if host.os_details else {}
            distribution = os_details.get("distribution", "")
            if distribution == os_name:
                matching_hosts.append(host)
        except (json.JSONDecodeError, TypeError):
            continue

    return matching_hosts


def send_enable_package_manager_to_hosts(
    db_session: Session, hosts: List, package_manager: str, os_name: str
) -> int:
    """
    Send enable_package_manager command to a list of hosts.

    Returns the number of messages queued.
    """
    if not hosts:
        return 0

    queue_ops = QueueOperations()
    queued_count = 0

    for host in hosts:
        try:
            command_message = create_command_message(
                command_type="enable_package_manager",
                parameters={
                    "package_manager": package_manager,
                    "os_name": os_name,
                },
            )

            queue_ops.enqueue_message(
                message_type="command",
                message_data=command_message,
                direction=QueueDirection.OUTBOUND,
                host_id=str(host.id),
                db=db_session,
            )
            queued_count += 1
        except Exception as e:
            logger.error(
                "Error queueing enable_package_manager for host %s: %s", host.fqdn, e
            )

    return queued_count


@router.get("/os-options", response_model=OSOptionsResponse)
async def get_os_options(
    dependencies=Depends(JWTBearer()),
):
    """Get available operating systems and their optional package managers."""
    # Only include OSes that have optional package managers
    os_with_options = [
        os for os, options in OS_OPTIONAL_PACKAGE_MANAGERS.items() if options
    ]
    return OSOptionsResponse(
        operating_systems=sorted(os_with_options),
        default_package_managers=OS_DEFAULT_PACKAGE_MANAGERS,
        optional_package_managers={
            os: pms for os, pms in OS_OPTIONAL_PACKAGE_MANAGERS.items() if pms
        },
    )


@router.get("/", response_model=List[EnabledPackageManagerResponse])
async def get_enabled_package_managers(
    db_session: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Get all enabled package managers."""
    # Check if user has permission to view enabled package managers
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.get_bind()
    )
    with session_local() as session:
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=error_user_not_found())
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.VIEW_ENABLED_PACKAGE_MANAGERS):
            raise HTTPException(
                status_code=403,
                detail=_(
                    "Permission denied: VIEW_ENABLED_PACKAGE_MANAGERS role required"
                ),
            )

    try:
        enabled_pms = (
            db_session.query(models.EnabledPackageManager)
            .order_by(
                models.EnabledPackageManager.os_name,
                models.EnabledPackageManager.package_manager,
            )
            .all()
        )
        return enabled_pms

    except Exception as e:
        logger.error("Error getting enabled package managers: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve enabled package managers: %s") % str(e),
        ) from e


@router.post("/", response_model=EnabledPackageManagerResponse, status_code=201)
async def create_enabled_package_manager(
    pm_data: EnabledPackageManagerCreate,
    request: Request,
    db_session: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Create a new enabled package manager."""
    # Check if user has permission to add enabled package managers
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.get_bind()
    )
    with session_local() as session:
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=error_user_not_found())
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.ADD_ENABLED_PACKAGE_MANAGER):
            raise HTTPException(
                status_code=403,
                detail=_(
                    "Permission denied: ADD_ENABLED_PACKAGE_MANAGER role required"
                ),
            )
        auth_user_id = auth_user.id

    try:
        # Check if this combination already exists
        existing = (
            db_session.query(models.EnabledPackageManager)
            .filter(
                models.EnabledPackageManager.os_name == pm_data.os_name,
                models.EnabledPackageManager.package_manager == pm_data.package_manager,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=_("Package manager '%s' is already enabled for OS '%s'")
                % (pm_data.package_manager, pm_data.os_name),
            )

        # Create new enabled package manager
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        new_pm = models.EnabledPackageManager(
            os_name=pm_data.os_name,
            package_manager=pm_data.package_manager,
            created_at=now,
            created_by=auth_user_id,
        )
        db_session.add(new_pm)
        db_session.commit()
        db_session.refresh(new_pm)

        logger.info(
            "Enabled package manager created: %s/%s",
            pm_data.os_name,
            pm_data.package_manager,
        )

        # Log audit entry
        AuditService.log_create(
            db=db_session,
            entity_type=EntityType.SETTING,
            entity_name=f"Enabled Package Manager: {pm_data.package_manager} for {pm_data.os_name}",
            user_id=auth_user_id,
            username=current_user,
            entity_id=str(new_pm.id),
            details={
                "os_name": pm_data.os_name,
                "package_manager": pm_data.package_manager,
            },
            ip_address=request.client.host if request.client else None,
        )

        db_session.commit()

        # Send enable_package_manager command to all approved, privileged hosts with this OS
        try:
            matching_hosts = get_approved_privileged_hosts_by_os(
                db_session, pm_data.os_name
            )
            if matching_hosts:
                queued_count = send_enable_package_manager_to_hosts(
                    db_session,
                    matching_hosts,
                    pm_data.package_manager,
                    pm_data.os_name,
                )
                db_session.commit()
                logger.info(
                    "Queued enable_package_manager commands for %d hosts with OS %s",
                    queued_count,
                    pm_data.os_name,
                )
        except Exception as e:
            # Don't fail the creation if we can't queue the messages
            logger.error("Error queueing enable_package_manager commands: %s", e)

        return new_pm

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error creating enabled package manager: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to create enabled package manager: %s") % str(e),
        ) from e


@router.delete("/{pm_id}")
async def delete_enabled_package_manager(
    pm_id: str,
    request: Request,
    db_session: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Delete an enabled package manager."""
    # Check if user has permission to remove enabled package managers
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.get_bind()
    )
    with session_local() as session:
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=error_user_not_found())
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.REMOVE_ENABLED_PACKAGE_MANAGER):
            raise HTTPException(
                status_code=403,
                detail=_(
                    "Permission denied: REMOVE_ENABLED_PACKAGE_MANAGER role required"
                ),
            )
        auth_user_id = auth_user.id

    try:
        # Parse UUID
        try:
            pm_uuid = uuid.UUID(pm_id)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=_("Invalid package manager ID format"),
            ) from e

        # Find the package manager
        pm = (
            db_session.query(models.EnabledPackageManager)
            .filter(models.EnabledPackageManager.id == pm_uuid)
            .first()
        )

        if not pm:
            raise HTTPException(
                status_code=404,
                detail=_("Enabled package manager not found"),
            )

        # Store info for audit log before deletion
        pm_os_name = pm.os_name
        pm_package_manager = pm.package_manager

        db_session.delete(pm)
        db_session.commit()

        logger.info(
            "Enabled package manager deleted: %s/%s",
            pm_os_name,
            pm_package_manager,
        )

        # Log audit entry
        AuditService.log_delete(
            db=db_session,
            entity_type=EntityType.SETTING,
            entity_name=f"Enabled Package Manager: {pm_package_manager} for {pm_os_name}",
            user_id=auth_user_id,
            username=current_user,
            entity_id=pm_id,
            details={
                "os_name": pm_os_name,
                "package_manager": pm_package_manager,
            },
            ip_address=request.client.host if request.client else None,
        )

        db_session.commit()

        return {"message": _("Enabled package manager deleted successfully")}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting enabled package manager %s: %s", pm_id, e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to delete enabled package manager: %s") % str(e),
        ) from e
