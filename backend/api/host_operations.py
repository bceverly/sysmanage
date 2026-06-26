"""
Host system operations endpoints (reboot, shutdown, software refresh).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from backend.api.error_constants import error_host_not_found
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import db as db_module
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()
queue_ops = QueueOperations()


@router.post("/host/refresh/software/{host_id}", dependencies=[Depends(JWTBearer())])
async def refresh_host_software(
    host_id: str,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """
    Request software inventory refresh for a specific host.
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the host/queue data routes to the tenant engine via
    # ``tenant_db``.
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    # Find the host first to ensure it exists (tenant-scoped data)
    host = tenant_db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    # Create command message for software inventory update
    command_message = create_command_message(
        command_type="update_software_inventory", parameters={}
    )

    # Send command to agent via message queue (tenant-scoped)
    queue_ops.enqueue_message(
        message_type="command",
        message_data=command_message,
        direction=QueueDirection.OUTBOUND,
        host_id=host_id,
        db=tenant_db,
    )

    # Commit the queued message on the tenant engine
    tenant_db.commit()

    # Audit log the software refresh request (on the main engine)
    with session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested software inventory refresh for host {host.fqdn}",
            result=Result.SUCCESS,
        )

    return {"result": True, "message": _("Software inventory update requested")}


@router.post("/host/reboot/{host_id}", dependencies=[Depends(JWTBearer())])
async def reboot_host(
    host_id: str,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """
    Request a system reboot for a specific host.
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the host/queue data routes to the tenant engine via
    # ``tenant_db``.
    if not current_user.has_role(SecurityRoles.REBOOT_HOST):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: REBOOT_HOST role required"),
        )

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    # Find the host first to ensure it exists (tenant-scoped data)
    host = tenant_db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    # Create command message for system reboot
    command_message = create_command_message(
        command_type="reboot_system", parameters={}
    )

    # Send command to agent via message queue (tenant-scoped)
    queue_ops.enqueue_message(
        message_type="command",
        message_data=command_message,
        direction=QueueDirection.OUTBOUND,
        host_id=host_id,
        db=tenant_db,
    )

    # Commit the queued message on the tenant engine
    tenant_db.commit()

    # Audit log the reboot request (on the main engine)
    with session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested system reboot for host {host.fqdn}",
            result=Result.SUCCESS,
        )

    return {"result": True, "message": _("System reboot requested")}


@router.post("/host/shutdown/{host_id}", dependencies=[Depends(JWTBearer())])
async def shutdown_host(
    host_id: str,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """
    Request a system shutdown for a specific host.
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the host/queue data routes to the tenant engine via
    # ``tenant_db``.
    if not current_user.has_role(SecurityRoles.SHUTDOWN_HOST):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: SHUTDOWN_HOST role required"),
        )

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    # Find the host first to ensure it exists (tenant-scoped data)
    host = tenant_db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    # Create command message for system shutdown
    command_message = create_command_message(
        command_type="shutdown_system", parameters={}
    )

    # Send command to agent via message queue (tenant-scoped)
    queue_ops.enqueue_message(
        message_type="command",
        message_data=command_message,
        direction=QueueDirection.OUTBOUND,
        host_id=host_id,
        db=tenant_db,
    )

    # Commit the queued message on the tenant engine
    tenant_db.commit()

    # Audit log the shutdown request (on the main engine)
    with session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested system shutdown for host {host.fqdn}",
            result=Result.SUCCESS,
        )

    return {"result": True, "message": _("System shutdown requested")}


@router.post("/host/update-agent/{host_id}", dependencies=[Depends(JWTBearer())])
async def update_agent(
    host_id: str,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """
    Request agent update for a specific host.
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the host/queue data routes to the tenant engine via
    # ``tenant_db``.
    if not current_user.has_role(SecurityRoles.UPDATE_AGENT):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: UPDATE_AGENT role required"),
        )

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    # Find the host first to ensure it exists (tenant-scoped data)
    host = tenant_db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    # Create command message for agent update
    command_message = create_command_message(command_type="update_agent", parameters={})

    # Send command to agent via message queue (tenant-scoped)
    queue_ops.enqueue_message(
        message_type="command",
        message_data=command_message,
        direction=QueueDirection.OUTBOUND,
        host_id=host_id,
        db=tenant_db,
    )

    # Commit the queued message on the tenant engine
    tenant_db.commit()

    # Audit log the agent update request (on the main engine)
    with session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested agent update for host {host.fqdn}",
            result=Result.SUCCESS,
        )

    return {"result": True, "message": _("Agent update requested")}


@router.post("/host/{host_id}/request-packages", dependencies=[Depends(JWTBearer())])
async def request_packages(
    host_id: str,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """
    Request available package collection from a specific host.
    """
    # No specific permission required for viewing packages, but the user must be
    # authenticated.  Authorization is resolved on the MAIN engine by
    # require_authenticated_user (server-global); the audit trail also stays on
    # the main engine, while the host/queue data routes to the tenant engine via
    # ``tenant_db``.
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    # Find the host first to ensure it exists (tenant-scoped data)
    host = tenant_db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    # Create command message for package collection
    command_message = create_command_message(
        command_type="collect_available_packages", parameters={}
    )

    # Send command to agent via message queue (tenant-scoped)
    queue_ops.enqueue_message(
        message_type="command",
        message_data=command_message,
        direction=QueueDirection.OUTBOUND,
        host_id=host_id,
        db=tenant_db,
    )

    # Commit the queued message on the tenant engine
    tenant_db.commit()

    # Audit log the package collection request (on the main engine)
    with session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=f"Requested package collection for host {host.fqdn}",
            result=Result.SUCCESS,
        )

    return {"result": True, "message": _("Package collection requested")}
