# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Host system operations endpoints (reboot, shutdown, software refresh).

These handlers are plain ``def``, not ``async def``: they only make blocking
database calls, and FastAPI runs a plain handler in its thread pool.  As
``async def`` a handler waiting for a pooled connection waited ON THE EVENT
LOOP, so nothing else ran -- including the work that would have returned a
connection.  Production stalled 30 s that way on 2026-11-18 when all its hosts
were asked to upgrade their agents at once (a tenant pool of 2 + 6, two
connections per request).  Each handler now uses ONE connection: the audit
entry is written on the request's own tenant session.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.error_constants import error_host_not_found
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
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
def refresh_host_software(
    host_id: str,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """
    Request software inventory refresh for a specific host.
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the host, the queue AND the audit entry
    # go through ``tenant_db`` -- one connection, which the audit service would
    # have routed to the tenant database anyway.
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

    # Audit log the software refresh request (on the request's own tenant session)
    AuditService.log(
        db=tenant_db,
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
def reboot_host(
    host_id: str,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """
    Request a system reboot for a specific host.
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the host, the queue AND the audit entry
    # go through ``tenant_db`` -- one connection, which the audit service would
    # have routed to the tenant database anyway.
    if not current_user.has_role(SecurityRoles.REBOOT_HOST):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: REBOOT_HOST role required"),
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

    # Audit log the reboot request (on the request's own tenant session)
    AuditService.log(
        db=tenant_db,
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
def shutdown_host(
    host_id: str,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """
    Request a system shutdown for a specific host.
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the host, the queue AND the audit entry
    # go through ``tenant_db`` -- one connection, which the audit service would
    # have routed to the tenant database anyway.
    if not current_user.has_role(SecurityRoles.SHUTDOWN_HOST):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: SHUTDOWN_HOST role required"),
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

    # Audit log the shutdown request (on the request's own tenant session)
    AuditService.log(
        db=tenant_db,
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
def update_agent(
    host_id: str,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """
    Request agent update for a specific host.
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the host, the queue AND the audit entry
    # go through ``tenant_db`` -- one connection, which the audit service would
    # have routed to the tenant database anyway.
    if not current_user.has_role(SecurityRoles.UPDATE_AGENT):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: UPDATE_AGENT role required"),
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

    # Audit log the agent update request (on the request's own tenant session)
    AuditService.log(
        db=tenant_db,
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
def request_packages(
    host_id: str,
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """
    Request available package collection from a specific host.
    """
    # No specific permission required for viewing packages, but the user must be
    # authenticated.  Authorization is resolved on the MAIN engine by
    # require_authenticated_user (server-global); the host, the queue and the
    # audit entry all go through ``tenant_db`` (one connection).

    # Find the host first to ensure it exists (tenant-scoped data)
    host = tenant_db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())

    # Create command message for package collection.  Hand back the fingerprint
    # of the catalog we already hold so the agent can skip transmitting ~89k
    # packages (~11 MB) unchanged -- and send a small delta when only a few
    # entries moved.  Without it EVERY manual refresh costs a full catalog.
    command_message = create_command_message(
        command_type="collect_available_packages",
        parameters={"known_fingerprint": host.available_packages_fingerprint},
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

    # Audit log the package collection request (on the request's own tenant session)
    AuditService.log(
        db=tenant_db,
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
