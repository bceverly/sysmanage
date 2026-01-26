"""
Host system operations endpoints (reboot, shutdown, software refresh).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api.error_constants import ERROR_HOST_NOT_FOUND, ERROR_USER_NOT_FOUND
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()
queue_ops = QueueOperations()


@router.post("/host/refresh/software/{host_id}", dependencies=[Depends(JWTBearer())])
async def refresh_host_software(
    host_id: str, current_user: str = Depends(get_current_user)
):
    """
    Request software inventory refresh for a specific host.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Get user for audit logging
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=ERROR_USER_NOT_FOUND())

        # Find the host first to ensure it exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=ERROR_HOST_NOT_FOUND())

        # Create command message for software inventory update
        command_message = create_command_message(
            command_type="update_software_inventory", parameters={}
        )

        # Send command to agent via message queue
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Audit log the software refresh request
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
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested software inventory refresh for host {host.fqdn}",
            result=Result.SUCCESS,
        )

        # Commit the session to persist the queued message and audit log
        session.commit()

        return {"result": True, "message": _("Software inventory update requested")}


@router.post("/host/reboot/{host_id}", dependencies=[Depends(JWTBearer())])
async def reboot_host(host_id: str, current_user: str = Depends(get_current_user)):
    """
    Request a system reboot for a specific host.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Check if user has permission to reboot hosts
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

        # Check for REBOOT_HOST role
        if not user.has_role(SecurityRoles.REBOOT_HOST):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: REBOOT_HOST role required"),
            )

        # Find the host first to ensure it exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=ERROR_HOST_NOT_FOUND())

        # Create command message for system reboot
        command_message = create_command_message(
            command_type="reboot_system", parameters={}
        )

        # Send command to agent via message queue
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Audit log the reboot request
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
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested system reboot for host {host.fqdn}",
            result=Result.SUCCESS,
        )

        # Commit the session to persist the queued message and audit log
        session.commit()

        return {"result": True, "message": _("System reboot requested")}


@router.post("/host/shutdown/{host_id}", dependencies=[Depends(JWTBearer())])
async def shutdown_host(host_id: str, current_user: str = Depends(get_current_user)):
    """
    Request a system shutdown for a specific host.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Check if user has permission to shutdown hosts
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

        # Check for SHUTDOWN_HOST role
        if not user.has_role(SecurityRoles.SHUTDOWN_HOST):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: SHUTDOWN_HOST role required"),
            )

        # Find the host first to ensure it exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=ERROR_HOST_NOT_FOUND())

        # Create command message for system shutdown
        command_message = create_command_message(
            command_type="shutdown_system", parameters={}
        )

        # Send command to agent via message queue
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Audit log the shutdown request
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
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested system shutdown for host {host.fqdn}",
            result=Result.SUCCESS,
        )

        # Commit the session to persist the queued message and audit log
        session.commit()

        return {"result": True, "message": _("System shutdown requested")}


@router.post("/host/{host_id}/request-packages", dependencies=[Depends(JWTBearer())])
async def request_packages(host_id: str, current_user: str = Depends(get_current_user)):
    """
    Request available package collection from a specific host.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Check if user is authenticated (no specific permission required for viewing packages)
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=ERROR_USER_NOT_FOUND())

        # Find the host first to ensure it exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=ERROR_HOST_NOT_FOUND())

        # Create command message for package collection
        command_message = create_command_message(
            command_type="collect_available_packages", parameters={}
        )

        # Send command to agent via message queue
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Audit log the package collection request
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
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested package collection for host {host.fqdn}",
            result=Result.SUCCESS,
        )

        # Commit the session to persist the queued message and audit log
        session.commit()

        return {"result": True, "message": _("Package collection requested")}
