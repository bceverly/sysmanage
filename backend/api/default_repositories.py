"""
This module houses the API routes for default repository settings management in SysManage.
Default repositories are applied to new hosts when they are approved, based on their
operating system and package manager.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.persistence.db import get_db
from backend.security.roles import SecurityRoles
from backend.services.audit_service import AuditService, EntityType
from backend.websocket.messages import create_command_message
from backend.websocket.queue_manager import (
    Priority,
    QueueDirection,
    server_queue_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def apply_repository_to_host(
    db_session: Session, host: models.Host, repository_url: str, action: str = "add"
):
    """
    Apply a repository add or delete operation to a specific host.

    Args:
        db_session: Database session
        host: Host model instance
        repository_url: Repository URL/identifier to add or remove
        action: "add" or "delete"
    """
    try:
        if action == "add":
            command_type = "add_third_party_repository"
            parameters = {
                "repository": repository_url,
                "url": None,
            }
        elif action == "delete":
            command_type = "delete_third_party_repositories"
            parameters = {"repositories": [{"name": repository_url}]}
        else:
            logger.error("Invalid action '%s' for apply_repository_to_host", action)
            return

        # Create the command message
        message = create_command_message(
            command_type="generic_command",
            parameters={
                "command_type": command_type,
                "parameters": parameters,
            },
        )

        # Queue the message
        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=message,
            direction=QueueDirection.OUTBOUND,
            host_id=str(host.id),
            priority=Priority.NORMAL,
            db=db_session,
        )

        logger.info(
            "Queued %s repository command for host %s: %s",
            action,
            host.fqdn,
            repository_url,
        )

    except Exception as e:
        logger.error(
            "Failed to queue %s repository command for host %s: %s",
            action,
            host.fqdn,
            e,
        )


async def apply_repository_to_matching_hosts(
    db_session: Session, os_name: str, repository_url: str, action: str = "add"
):
    """
    Apply a repository operation to all hosts matching the given OS name.

    Args:
        db_session: Database session
        os_name: Operating system name (e.g., "Ubuntu", "Ubuntu 25.04")
        repository_url: Repository URL/identifier
        action: "add" or "delete"
    """
    try:
        # Find all approved hosts with matching OS
        # Check both platform and platform_release fields
        hosts = (
            db_session.query(models.Host)
            .filter(
                models.Host.approval_status == "approved",
                (
                    (models.Host.platform_release.like(f"{os_name}%"))
                    | (models.Host.platform == os_name)
                ),
            )
            .all()
        )

        logger.info(
            "Found %d hosts matching OS '%s' for repository %s",
            len(hosts),
            os_name,
            action,
        )

        # Queue commands for each host
        for host in hosts:
            await apply_repository_to_host(db_session, host, repository_url, action)

    except Exception as e:
        logger.error(
            "Error applying repository to matching hosts for OS '%s': %s", os_name, e
        )


async def apply_default_repositories_to_host(db_session: Session, host: models.Host):
    """
    Apply all default repositories for a host's operating system.
    Called when a new host is approved.

    Args:
        db_session: Database session
        host: Host model instance
    """
    try:
        # Determine the OS name to search for
        # Check platform_release first (e.g., "Ubuntu 25.04"), then fall back to platform (e.g., "Ubuntu")
        os_name = host.platform_release or host.platform

        if not os_name:
            logger.warning(
                "Host %s has no platform information, skipping default repository application",
                host.fqdn,
            )
            return

        # Find default repositories matching this OS
        # We need to check both exact matches and prefix matches
        # For example, "Ubuntu" should match "Ubuntu 25.04"
        default_repos = (
            db_session.query(models.DefaultRepository)
            .filter(
                (models.DefaultRepository.os_name == os_name)
                | (
                    # If os_name is like "Ubuntu 25.04", also match "Ubuntu"
                    models.DefaultRepository.os_name.in_(
                        [os_name.split()[0]] if " " in os_name else []
                    )
                )
            )
            .all()
        )

        if not default_repos:
            logger.info(
                "No default repositories found for OS '%s', host %s",
                os_name,
                host.fqdn,
            )
            return

        logger.info(
            "Applying %d default repositories to newly approved host %s (OS: %s)",
            len(default_repos),
            host.fqdn,
            os_name,
        )

        # Queue add commands for each default repository
        for repo in default_repos:
            await apply_repository_to_host(
                db_session, host, repo.repository_url, action="add"
            )

    except Exception as e:
        logger.error("Error applying default repositories to host %s: %s", host.fqdn, e)


# Supported operating systems grouped by type
OS_PACKAGE_MANAGERS = {
    # Linux distributions
    "Ubuntu": ["APT", "snap", "flatpak"],
    "Debian": ["APT", "snap", "flatpak"],
    "RHEL": ["dnf", "yum", "flatpak"],
    "CentOS": ["dnf", "yum", "flatpak"],
    "CentOS Stream": ["dnf", "yum", "flatpak"],
    "Fedora": ["dnf", "flatpak"],
    "Rocky Linux": ["dnf", "yum", "flatpak"],
    "AlmaLinux": ["dnf", "yum", "flatpak"],
    "openSUSE": ["zypper", "flatpak"],
    "SLES": ["zypper"],
    # BSD variants
    "FreeBSD": ["pkg"],
    "OpenBSD": ["pkg_add"],
    "NetBSD": ["pkgin"],
    # macOS
    "macOS": ["homebrew"],
    # Windows
    "Windows": ["winget", "chocolatey"],
}


class DefaultRepositoryResponse(BaseModel):
    """Response model for default repository."""

    id: str
    os_name: str
    package_manager: str
    repository_url: str
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


class DefaultRepositoryCreate(BaseModel):
    """Request model for creating a default repository."""

    os_name: str
    package_manager: str
    repository_url: str

    @validator("os_name")
    def validate_os_name(cls, os_name):  # pylint: disable=no-self-argument
        """Validate OS name."""
        if not os_name or os_name.strip() == "":
            raise ValueError(_("OS name is required"))
        if os_name.strip() not in OS_PACKAGE_MANAGERS:
            raise ValueError(_("Unsupported operating system: %s") % os_name)
        return os_name.strip()

    @validator("package_manager")
    def validate_package_manager(
        cls, package_manager, values
    ):  # pylint: disable=no-self-argument
        """Validate package manager."""
        if not package_manager or package_manager.strip() == "":
            raise ValueError(_("Package manager is required"))
        os_name = values.get("os_name", "").strip()
        if os_name and os_name in OS_PACKAGE_MANAGERS:
            valid_managers = OS_PACKAGE_MANAGERS[os_name]
            if package_manager.strip() not in valid_managers:
                raise ValueError(
                    _("Invalid package manager '%s' for OS '%s'. Valid options: %s")
                    % (package_manager, os_name, ", ".join(valid_managers))
                )
        return package_manager.strip()

    @validator("repository_url")
    def validate_repository_url(
        cls, repository_url
    ):  # pylint: disable=no-self-argument
        """Validate repository URL."""
        if not repository_url or repository_url.strip() == "":
            raise ValueError(_("Repository URL is required"))
        if len(repository_url) > 1000:
            raise ValueError(_("Repository URL must be 1000 characters or less"))
        return repository_url.strip()


class OSPackageManagersResponse(BaseModel):
    """Response model for OS and package manager options."""

    operating_systems: List[str]
    package_managers: dict


@router.get("/os-options", response_model=OSPackageManagersResponse)
async def get_os_options(
    dependencies=Depends(JWTBearer()),
):
    """Get available operating systems and their package managers."""
    return OSPackageManagersResponse(
        operating_systems=sorted(OS_PACKAGE_MANAGERS.keys()),
        package_managers=OS_PACKAGE_MANAGERS,
    )


@router.get("/by-os/{os_name}", response_model=List[DefaultRepositoryResponse])
async def get_default_repositories_by_os(
    os_name: str,
    db_session: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Get default repositories for a specific operating system."""
    # Check if user has permission to view default repositories
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
            raise HTTPException(status_code=401, detail=_("User not found"))
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.VIEW_DEFAULT_REPOSITORIES):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: VIEW_DEFAULT_REPOSITORIES role required"),
            )

    try:
        repositories = (
            db_session.query(models.DefaultRepository)
            .filter(models.DefaultRepository.os_name == os_name)
            .order_by(models.DefaultRepository.package_manager)
            .all()
        )
        return repositories

    except Exception as e:
        logger.error("Error getting default repositories for OS %s: %s", os_name, e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve default repositories: %s") % str(e),
        ) from e


@router.get("/", response_model=List[DefaultRepositoryResponse])
async def get_default_repositories(
    db_session: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Get all default repositories."""
    # Check if user has permission to view default repositories
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
            raise HTTPException(status_code=401, detail=_("User not found"))
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.VIEW_DEFAULT_REPOSITORIES):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: VIEW_DEFAULT_REPOSITORIES role required"),
            )

    try:
        repositories = (
            db_session.query(models.DefaultRepository)
            .order_by(
                models.DefaultRepository.os_name,
                models.DefaultRepository.package_manager,
            )
            .all()
        )
        return repositories

    except Exception as e:
        logger.error("Error getting default repositories: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve default repositories: %s") % str(e),
        ) from e


@router.post("/", response_model=DefaultRepositoryResponse, status_code=201)
async def create_default_repository(
    repo_data: DefaultRepositoryCreate,
    request: Request,
    db_session: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Create a new default repository."""
    # Check if user has permission to add default repositories
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
            raise HTTPException(status_code=401, detail=_("User not found"))
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.ADD_DEFAULT_REPOSITORY):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: ADD_DEFAULT_REPOSITORY role required"),
            )
        auth_user_id = auth_user.id

    try:
        # Create new default repository
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        new_repo = models.DefaultRepository(
            os_name=repo_data.os_name,
            package_manager=repo_data.package_manager,
            repository_url=repo_data.repository_url,
            created_at=now,
            created_by=auth_user_id,
        )
        db_session.add(new_repo)
        db_session.commit()
        db_session.refresh(new_repo)

        logger.info(
            "Default repository created: %s/%s - %s",
            repo_data.os_name,
            repo_data.package_manager,
            repo_data.repository_url,
        )

        # Log audit entry
        AuditService.log_create(
            db=db_session,
            entity_type=EntityType.SETTING,
            entity_name=f"Default Repository for {repo_data.os_name}/{repo_data.package_manager}",
            user_id=auth_user_id,
            username=current_user,
            entity_id=str(new_repo.id),
            details={
                "os_name": repo_data.os_name,
                "package_manager": repo_data.package_manager,
                "repository_url": repo_data.repository_url,
            },
            ip_address=request.client.host if request.client else None,
        )

        # Apply this repository to all existing hosts with matching OS
        await apply_repository_to_matching_hosts(
            db_session, repo_data.os_name, repo_data.repository_url, action="add"
        )

        # Commit to ensure queued messages are persisted
        db_session.commit()

        return new_repo

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error creating default repository: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to create default repository: %s") % str(e),
        ) from e


@router.delete("/{repo_id}")
async def delete_default_repository(
    repo_id: str,
    request: Request,
    db_session: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Delete a default repository."""
    # Check if user has permission to remove default repositories
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
            raise HTTPException(status_code=401, detail=_("User not found"))
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.REMOVE_DEFAULT_REPOSITORY):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: REMOVE_DEFAULT_REPOSITORY role required"),
            )
        auth_user_id = auth_user.id

    try:
        # Parse UUID
        try:
            repo_uuid = uuid.UUID(repo_id)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=_("Invalid repository ID format"),
            ) from e

        # Find the repository
        repo = (
            db_session.query(models.DefaultRepository)
            .filter(models.DefaultRepository.id == repo_uuid)
            .first()
        )

        if not repo:
            raise HTTPException(
                status_code=404,
                detail=_("Default repository not found"),
            )

        # Store info for audit log before deletion
        repo_os_name = repo.os_name
        repo_package_manager = repo.package_manager
        repo_url = repo.repository_url

        db_session.delete(repo)
        db_session.commit()

        logger.info(
            "Default repository deleted: %s/%s - %s",
            repo_os_name,
            repo_package_manager,
            repo_url,
        )

        # Log audit entry
        AuditService.log_delete(
            db=db_session,
            entity_type=EntityType.SETTING,
            entity_name=f"Default Repository for {repo_os_name}/{repo_package_manager}",
            user_id=auth_user_id,
            username=current_user,
            entity_id=repo_id,
            details={
                "os_name": repo_os_name,
                "package_manager": repo_package_manager,
                "repository_url": repo_url,
            },
            ip_address=request.client.host if request.client else None,
        )

        # Remove this repository from all existing hosts with matching OS
        await apply_repository_to_matching_hosts(
            db_session, repo_os_name, repo_url, action="delete"
        )

        # Commit to ensure queued messages are persisted
        db_session.commit()

        return {"message": _("Default repository deleted successfully")}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting default repository %s: %s", repo_id, e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to delete default repository: %s") % str(e),
        ) from e
