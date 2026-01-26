"""
Host account and group management endpoints.
Allows creating users and groups on remote hosts via the agent.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.api.error_constants import (
    ERROR_HOST_NOT_ACTIVE,
    ERROR_HOST_NOT_FOUND,
    ERROR_USER_NOT_FOUND,
)
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()
queue_ops = QueueOperations()


class CreateHostUserRequest(BaseModel):
    """Request model for creating a user on a remote host."""

    username: str
    full_name: Optional[str] = None
    # Unix-specific fields
    home_directory: Optional[str] = None
    shell: Optional[str] = None
    create_home_dir: Optional[bool] = True
    uid: Optional[int] = None
    primary_group: Optional[str] = None
    # Windows-specific fields
    password: Optional[str] = None
    password_never_expires: Optional[bool] = False
    user_must_change_password: Optional[bool] = True
    account_disabled: Optional[bool] = False


class CreateHostGroupRequest(BaseModel):
    """Request model for creating a group on a remote host."""

    group_name: str
    gid: Optional[int] = None
    description: Optional[str] = None


@router.post("/host/{host_id}/accounts", dependencies=[Depends(JWTBearer())])
async def create_host_user(  # NOSONAR - complex business logic
    host_id: str,
    request: CreateHostUserRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Create a new user account on a remote host.
    Requires ADD_HOST_ACCOUNT permission and the host agent must be running
    in privileged mode.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Get user for permission check and audit logging
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=ERROR_USER_NOT_FOUND())

        # Load role cache if not already loaded
        if user._role_cache is None:
            user.load_role_cache(session)

        # Check for ADD_HOST_ACCOUNT role
        if not user.has_role(SecurityRoles.ADD_HOST_ACCOUNT):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: ADD_HOST_ACCOUNT role required"),
            )

        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=ERROR_HOST_NOT_FOUND())

        # Verify host is active
        if not host.active:
            raise HTTPException(
                status_code=400,
                detail=ERROR_HOST_NOT_ACTIVE(),
            )

        # Verify agent is running in privileged mode
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Agent must be running in privileged mode to manage user accounts"
                ),
            )

        # Build parameters for the command
        parameters = {
            "username": request.username,
        }

        # Add optional fields if provided
        if request.full_name:
            parameters["full_name"] = request.full_name
        if request.home_directory:
            parameters["home_directory"] = request.home_directory
        if request.shell:
            parameters["shell"] = request.shell
        if request.create_home_dir is not None:
            parameters["create_home_dir"] = request.create_home_dir
        if request.uid is not None:
            parameters["uid"] = request.uid
        if request.primary_group:
            parameters["primary_group"] = request.primary_group
        if request.password:
            parameters["password"] = request.password
        if request.password_never_expires is not None:
            parameters["password_never_expires"] = request.password_never_expires
        if request.user_must_change_password is not None:
            parameters["user_must_change_password"] = request.user_must_change_password
        if request.account_disabled is not None:
            parameters["account_disabled"] = request.account_disabled

        # Create command message
        command_message = create_command_message(
            command_type="create_host_user", parameters=parameters
        )

        # Queue the message for delivery to the agent
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Audit log the user creation request
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        AuditService.log(
            db=session,
            user_id=user.id,
            username=current_user,
            action_type=ActionType.CREATE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=(
                f"Requested user account creation for '{request.username}' "
                f"on host {host.fqdn}"
            ),
            result=Result.SUCCESS,
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "User account creation requested. "
                "The user list will update automatically after creation."
            ),
        }


@router.post("/host/{host_id}/groups", dependencies=[Depends(JWTBearer())])
async def create_host_group(
    host_id: str,
    request: CreateHostGroupRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Create a new group on a remote host.
    Requires ADD_HOST_GROUP permission and the host agent must be running
    in privileged mode.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Get user for permission check and audit logging
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=ERROR_USER_NOT_FOUND())

        # Load role cache if not already loaded
        if user._role_cache is None:
            user.load_role_cache(session)

        # Check for ADD_HOST_GROUP role
        if not user.has_role(SecurityRoles.ADD_HOST_GROUP):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: ADD_HOST_GROUP role required"),
            )

        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=ERROR_HOST_NOT_FOUND())

        # Verify host is active
        if not host.active:
            raise HTTPException(
                status_code=400,
                detail=ERROR_HOST_NOT_ACTIVE(),
            )

        # Verify agent is running in privileged mode
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_("Agent must be running in privileged mode to manage groups"),
            )

        # Build parameters for the command
        parameters = {
            "group_name": request.group_name,
        }

        # Add optional fields if provided
        if request.gid is not None:
            parameters["gid"] = request.gid
        if request.description:
            parameters["description"] = request.description

        # Create command message
        command_message = create_command_message(
            command_type="create_host_group", parameters=parameters
        )

        # Queue the message for delivery to the agent
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Audit log the group creation request
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        AuditService.log(
            db=session,
            user_id=user.id,
            username=current_user,
            action_type=ActionType.CREATE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=(
                f"Requested group creation for '{request.group_name}' "
                f"on host {host.fqdn}"
            ),
            result=Result.SUCCESS,
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "Group creation requested. "
                "The group list will update automatically after creation."
            ),
        }


@router.delete(
    "/host/{host_id}/accounts/{username}", dependencies=[Depends(JWTBearer())]
)
async def delete_host_user(
    host_id: str,
    username: str,
    delete_default_group: bool = True,
    current_user: str = Depends(get_current_user),
):
    """
    Delete a user account from a remote host.
    Requires DELETE_HOST_ACCOUNT permission and the host agent must be running
    in privileged mode.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Get user for permission check and audit logging
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=ERROR_USER_NOT_FOUND())

        # Load role cache if not already loaded
        if user._role_cache is None:
            user.load_role_cache(session)

        # Check for DELETE_HOST_ACCOUNT role
        if not user.has_role(SecurityRoles.DELETE_HOST_ACCOUNT):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: DELETE_HOST_ACCOUNT role required"),
            )

        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=ERROR_HOST_NOT_FOUND())

        # Verify host is active
        if not host.active:
            raise HTTPException(
                status_code=400,
                detail=ERROR_HOST_NOT_ACTIVE(),
            )

        # Verify agent is running in privileged mode
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Agent must be running in privileged mode to delete user accounts"
                ),
            )

        # Build parameters for the command
        parameters = {
            "username": username,
            "delete_default_group": delete_default_group,
        }

        # Create command message
        command_message = create_command_message(
            command_type="delete_host_user", parameters=parameters
        )

        # Queue the message for delivery to the agent
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Audit log the user deletion request
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        AuditService.log(
            db=session,
            user_id=user.id,
            username=current_user,
            action_type=ActionType.DELETE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=(
                f"Requested user account deletion for '{username}' "
                f"on host {host.fqdn}"
            ),
            result=Result.SUCCESS,
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "User account deletion requested. "
                "The user list will update automatically after deletion."
            ),
        }


@router.delete(
    "/host/{host_id}/groups/{group_name}", dependencies=[Depends(JWTBearer())]
)
async def delete_host_group(
    host_id: str,
    group_name: str,
    current_user: str = Depends(get_current_user),
):
    """
    Delete a group from a remote host.
    Requires DELETE_HOST_GROUP permission and the host agent must be running
    in privileged mode.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Get user for permission check and audit logging
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=ERROR_USER_NOT_FOUND())

        # Load role cache if not already loaded
        if user._role_cache is None:
            user.load_role_cache(session)

        # Check for DELETE_HOST_GROUP role
        if not user.has_role(SecurityRoles.DELETE_HOST_GROUP):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: DELETE_HOST_GROUP role required"),
            )

        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=ERROR_HOST_NOT_FOUND())

        # Verify host is active
        if not host.active:
            raise HTTPException(
                status_code=400,
                detail=ERROR_HOST_NOT_ACTIVE(),
            )

        # Verify agent is running in privileged mode
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_("Agent must be running in privileged mode to delete groups"),
            )

        # Build parameters for the command
        parameters = {
            "group_name": group_name,
        }

        # Create command message
        command_message = create_command_message(
            command_type="delete_host_group", parameters=parameters
        )

        # Queue the message for delivery to the agent
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Audit log the group deletion request
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        AuditService.log(
            db=session,
            user_id=user.id,
            username=current_user,
            action_type=ActionType.DELETE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=(
                f"Requested group deletion for '{group_name}' on host {host.fqdn}"
            ),
            result=Result.SUCCESS,
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "Group deletion requested. "
                "The group list will update automatically after deletion."
            ),
        }
