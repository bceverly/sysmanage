"""
API routes for third-party repository management in SysManage.
Provides endpoints for listing, adding, and deleting third-party repositories.
"""

import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db as db_module
from backend.persistence import models
from backend.persistence.db import get_db
from backend.persistence.models import Host
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import create_command_message
from backend.websocket.queue_manager import (
    Priority,
    QueueDirection,
    server_queue_manager,
)

# Authenticated router for third-party repository management
router = APIRouter(dependencies=[Depends(JWTBearer())])


class ThirdPartyRepository(BaseModel):
    """Repository information model for API responses."""

    name: str
    type: str
    url: str
    enabled: bool
    file_path: Optional[str] = None


class RepositoryListResponse(BaseModel):
    """Response model for repository list."""

    success: bool
    repositories: List[ThirdPartyRepository]
    count: int


class AddRepositoryRequest(BaseModel):
    """Request model for adding a repository."""

    repository: str
    url: Optional[str] = None  # Required for Zypper/OBS repositories


class AddRepositoryResponse(BaseModel):
    """Response model for adding a repository."""

    success: bool
    message: str


class DeleteRepositoriesRequest(BaseModel):
    """Request model for deleting repositories."""

    repositories: List[dict]  # List of repository objects to delete


class DeleteRepositoriesResponse(BaseModel):
    """Response model for deleting repositories."""

    success: bool
    message: str
    results: Optional[List[dict]] = None


class EnableDisableRepositoriesRequest(BaseModel):
    """Request model for enabling/disabling repositories."""

    repositories: List[dict]  # List of repository objects to enable/disable


class EnableDisableRepositoriesResponse(BaseModel):
    """Response model for enabling/disabling repositories."""

    success: bool
    message: str


def _list_third_party_repositories_sync(host_id: str):
    """
    Synchronous helper function to retrieve third-party repositories.
    This runs in a thread pool to avoid blocking the event loop.
    """
    # Get a fresh session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    with session_local() as db:
        # Validate host exists and is active
        host = (
            db.query(Host)
            .filter(
                Host.id == host_id,
                Host.active.is_(True),
                Host.approval_status == "approved",
            )
            .first()
        )

        if not host:
            raise HTTPException(
                status_code=404,
                detail=_("Host not found or not active"),
            )

        # Check if host has privileged mode enabled
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=403,
                detail=_("Repository management requires privileged agent mode"),
            )

        # Queue message to request fresh repository data from agent
        command_message = create_command_message(
            command_type="generic_command",
            parameters={
                "command_type": "list_third_party_repositories",
                "parameters": {},
            },
        )

        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        # Commit the session to persist the queued message
        db.commit()

        # Query third-party repositories from database
        from backend.persistence.models import (
            ThirdPartyRepository as ThirdPartyRepositoryModel,
        )

        repositories = (
            db.query(ThirdPartyRepositoryModel)
            .filter(ThirdPartyRepositoryModel.host_id == host_id)
            .all()
        )

        # Convert database objects to response model
        repo_list = [
            ThirdPartyRepository(
                name=repo.name,
                type=repo.type,
                url=repo.url or "",
                enabled=repo.enabled,
                file_path=repo.file_path,
            )
            for repo in repositories
        ]

        return RepositoryListResponse(
            success=True,
            repositories=repo_list,
            count=len(repo_list),
        )


@router.get("/hosts/{host_id}/third-party-repos", response_model=RepositoryListResponse)
async def list_third_party_repositories(
    host_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    List all third-party repositories for a specific host.

    Requires the host to be approved and active.
    Runs the database query in a thread pool to avoid blocking the event loop.
    """
    try:
        # Run the synchronous database operation in a thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _list_third_party_repositories_sync, host_id
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=_("Failed to list third-party repositories: %s") % str(e),
        ) from e


@router.post("/hosts/{host_id}/third-party-repos", response_model=AddRepositoryResponse)
async def add_third_party_repository(
    host_id: str,
    request: AddRepositoryRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Add a third-party repository to a specific host.

    Requires ADD_THIRD_PARTY_REPOSITORY permission and privileged agent mode.
    """
    try:
        # Check if user has permission to add repositories
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        with session_local() as session:
            user = (
                session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if not user:
                raise HTTPException(status_code=401, detail=_("User not found"))

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.ADD_THIRD_PARTY_REPOSITORY):
                raise HTTPException(
                    status_code=403,
                    detail=_(
                        "Permission denied: ADD_THIRD_PARTY_REPOSITORY role required"
                    ),
                )

        # Validate host exists and is active
        host = (
            db.query(Host)
            .filter(
                Host.id == host_id,
                Host.active.is_(True),
                Host.approval_status == "approved",
            )
            .first()
        )

        if not host:
            raise HTTPException(
                status_code=404,
                detail=_("Host not found or not active"),
            )

        # Check if host has privileged mode enabled
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=403,
                detail=_("Repository management requires privileged agent mode"),
            )

        # Validate repository identifier
        if not request.repository:
            raise HTTPException(
                status_code=400,
                detail=_("Repository identifier is required"),
            )

        # Create command message to add repository
        command_message = create_command_message(
            command_type="generic_command",
            parameters={
                "command_type": "add_third_party_repository",
                "parameters": {
                    "repository": request.repository,
                    "url": request.url,
                },
            },
        )

        # Queue the message
        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        # Commit the session to persist the queued message
        db.commit()

        # Get user for audit logging
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        with session_local() as session:
            auth_user = (
                session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if auth_user:
                # Log audit entry for repository addition
                AuditService.log_create(
                    db=session,
                    entity_type=EntityType.REPOSITORY,
                    entity_name=request.repository,
                    user_id=auth_user.id,
                    username=current_user,
                    details={
                        "host_id": host_id,
                        "host_name": host.fqdn,
                        "repository": request.repository,
                        "url": request.url,
                    },
                )

        return AddRepositoryResponse(
            success=True,
            message=_("Repository add request queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=_("Failed to queue repository addition: %s") % str(e),
        ) from e


@router.delete(
    "/hosts/{host_id}/third-party-repos", response_model=DeleteRepositoriesResponse
)
async def delete_third_party_repositories(
    host_id: str,
    request: DeleteRepositoriesRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Delete third-party repositories from a specific host.

    Requires DELETE_THIRD_PARTY_REPOSITORY permission and privileged agent mode.
    Supports batch deletion of multiple repositories.
    """
    try:
        # Check if user has permission to delete repositories
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        with session_local() as session:
            user = (
                session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if not user:
                raise HTTPException(status_code=401, detail=_("User not found"))

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.DELETE_THIRD_PARTY_REPOSITORY):
                raise HTTPException(
                    status_code=403,
                    detail=_(
                        "Permission denied: DELETE_THIRD_PARTY_REPOSITORY role required"
                    ),
                )

        # Validate host exists and is active
        host = (
            db.query(Host)
            .filter(
                Host.id == host_id,
                Host.active.is_(True),
                Host.approval_status == "approved",
            )
            .first()
        )

        if not host:
            raise HTTPException(
                status_code=404,
                detail=_("Host not found or not active"),
            )

        # Check if host has privileged mode enabled
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=403,
                detail=_("Repository management requires privileged agent mode"),
            )

        # Validate repositories list
        if not request.repositories:
            raise HTTPException(
                status_code=400,
                detail=_("No repositories specified for deletion"),
            )

        # Import the model for database operations
        from backend.persistence.models import (
            ThirdPartyRepository as ThirdPartyRepositoryModel,
        )

        # Delete repositories from the database immediately for responsive UI
        deleted_count = 0
        for repo in request.repositories:
            repo_name = repo.get("name")
            repo_file_path = repo.get("file_path")

            # Try to find and delete by file_path first (most specific), then by name
            query = db.query(ThirdPartyRepositoryModel).filter(
                ThirdPartyRepositoryModel.host_id == host_id
            )

            if repo_file_path:
                query = query.filter(
                    ThirdPartyRepositoryModel.file_path == repo_file_path
                )
            elif repo_name:
                query = query.filter(ThirdPartyRepositoryModel.name == repo_name)
            else:
                continue

            deleted = query.delete(synchronize_session=False)
            deleted_count += deleted

        # Create command message to delete repositories on the agent
        command_message = create_command_message(
            command_type="generic_command",
            parameters={
                "command_type": "delete_third_party_repositories",
                "parameters": {
                    "repositories": request.repositories,
                },
            },
        )

        # Queue the message
        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        # Commit both the database deletions and the queued message
        db.commit()

        # Get user for audit logging
        session_local_audit = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        with session_local_audit() as session:
            auth_user = (
                session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if auth_user:
                # Log audit entry for repository deletion
                for repo in request.repositories:
                    AuditService.log_delete(
                        db=session,
                        entity_type=EntityType.REPOSITORY,
                        entity_name=repo.get("name", "Unknown"),
                        user_id=auth_user.id,
                        username=current_user,
                        details={
                            "host_id": host_id,
                            "host_name": host.fqdn,
                            "repository": repo,
                        },
                    )

        return DeleteRepositoriesResponse(
            success=True,
            message=_("Repository deletion request queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=_("Failed to queue repository deletion: %s") % str(e),
        ) from e


@router.post(
    "/hosts/{host_id}/third-party-repos/enable",
    response_model=EnableDisableRepositoriesResponse,
)
async def enable_third_party_repositories(
    host_id: str,
    request: EnableDisableRepositoriesRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Enable third-party repositories on a specific host.

    Requires ENABLE_THIRD_PARTY_REPOSITORY permission and privileged agent mode.
    """
    try:
        # Check if user has permission to enable repositories
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        with session_local() as session:
            user = (
                session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if not user:
                raise HTTPException(status_code=401, detail=_("User not found"))

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.ENABLE_THIRD_PARTY_REPOSITORY):
                raise HTTPException(
                    status_code=403,
                    detail=_(
                        "Permission denied: ENABLE_THIRD_PARTY_REPOSITORY role required"
                    ),
                )

        # Validate host exists and is active
        host = (
            db.query(Host)
            .filter(
                Host.id == host_id,
                Host.active.is_(True),
                Host.approval_status == "approved",
            )
            .first()
        )

        if not host:
            raise HTTPException(
                status_code=404,
                detail=_("Host not found or not active"),
            )

        # Check if host has privileged mode enabled
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=403,
                detail=_("Repository management requires privileged agent mode"),
            )

        # Validate repositories list
        if not request.repositories:
            raise HTTPException(
                status_code=400,
                detail=_("No repositories specified"),
            )

        # Create command message to enable repositories
        command_message = create_command_message(
            command_type="generic_command",
            parameters={
                "command_type": "enable_third_party_repositories",
                "parameters": {
                    "repositories": request.repositories,
                },
            },
        )

        # Queue the message
        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        # Commit the session to persist the queued message
        db.commit()

        # Get user for audit logging
        session_local_audit = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        with session_local_audit() as session:
            auth_user = (
                session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if auth_user:
                # Log audit entry for repository enable
                for repo in request.repositories:
                    AuditService.log_update(
                        db=session,
                        entity_type=EntityType.REPOSITORY,
                        entity_name=repo.get("name", "Unknown"),
                        user_id=auth_user.id,
                        username=current_user,
                        details={
                            "host_id": host_id,
                            "host_name": host.fqdn,
                            "repository": repo,
                            "action": "enable",
                        },
                    )

        return EnableDisableRepositoriesResponse(
            success=True,
            message=_("Repository enable request queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=_("Failed to queue repository enable: %s") % str(e),
        ) from e


@router.post(
    "/hosts/{host_id}/third-party-repos/disable",
    response_model=EnableDisableRepositoriesResponse,
)
async def disable_third_party_repositories(
    host_id: str,
    request: EnableDisableRepositoriesRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Disable third-party repositories on a specific host.

    Requires DISABLE_THIRD_PARTY_REPOSITORY permission and privileged agent mode.
    """
    try:
        # Check if user has permission to disable repositories
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        with session_local() as session:
            user = (
                session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if not user:
                raise HTTPException(status_code=401, detail=_("User not found"))

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.DISABLE_THIRD_PARTY_REPOSITORY):
                raise HTTPException(
                    status_code=403,
                    detail=_(
                        "Permission denied: DISABLE_THIRD_PARTY_REPOSITORY role required"
                    ),
                )

        # Validate host exists and is active
        host = (
            db.query(Host)
            .filter(
                Host.id == host_id,
                Host.active.is_(True),
                Host.approval_status == "approved",
            )
            .first()
        )

        if not host:
            raise HTTPException(
                status_code=404,
                detail=_("Host not found or not active"),
            )

        # Check if host has privileged mode enabled
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=403,
                detail=_("Repository management requires privileged agent mode"),
            )

        # Validate repositories list
        if not request.repositories:
            raise HTTPException(
                status_code=400,
                detail=_("No repositories specified"),
            )

        # Create command message to disable repositories
        command_message = create_command_message(
            command_type="generic_command",
            parameters={
                "command_type": "disable_third_party_repositories",
                "parameters": {
                    "repositories": request.repositories,
                },
            },
        )

        # Queue the message
        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        # Commit the session to persist the queued message
        db.commit()

        # Get user for audit logging
        session_local_audit = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )
        with session_local_audit() as session:
            auth_user = (
                session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if auth_user:
                # Log audit entry for repository disable
                for repo in request.repositories:
                    AuditService.log_update(
                        db=session,
                        entity_type=EntityType.REPOSITORY,
                        entity_name=repo.get("name", "Unknown"),
                        user_id=auth_user.id,
                        username=current_user,
                        details={
                            "host_id": host_id,
                            "host_name": host.fqdn,
                            "repository": repo,
                            "action": "disable",
                        },
                    )

        return EnableDisableRepositoriesResponse(
            success=True,
            message=_("Repository disable request queued successfully"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=_("Failed to queue repository disable: %s") % str(e),
        ) from e
