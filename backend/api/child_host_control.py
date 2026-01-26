"""
Child host control API endpoints (start, stop, restart).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api.child_host_utils import (
    audit_log,
    get_host_or_404,
    get_user_with_role_check,
    verify_host_active,
)
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db
from backend.persistence.models import HostChild
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()
queue_ops = QueueOperations()


@router.post(
    "/host/{host_id}/children/{child_id}/start",
    dependencies=[Depends(JWTBearer())],
)
async def start_child_host(
    host_id: str,
    child_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Start a stopped child host.
    Requires START_CHILD_HOST permission.
    """
    return await _child_host_control(
        host_id,
        child_id,
        current_user,
        SecurityRoles.START_CHILD_HOST,
        "start_child_host",
        "start",
        _("Child host start requested."),
    )


@router.post(
    "/host/{host_id}/children/{child_id}/stop",
    dependencies=[Depends(JWTBearer())],
)
async def stop_child_host(
    host_id: str,
    child_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Stop a running child host.
    Requires STOP_CHILD_HOST permission.
    """
    return await _child_host_control(
        host_id,
        child_id,
        current_user,
        SecurityRoles.STOP_CHILD_HOST,
        "stop_child_host",
        "stop",
        _("Child host stop requested."),
    )


@router.post(
    "/host/{host_id}/children/{child_id}/restart",
    dependencies=[Depends(JWTBearer())],
)
async def restart_child_host(
    host_id: str,
    child_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Restart a child host.
    Requires RESTART_CHILD_HOST permission.
    """
    return await _child_host_control(
        host_id,
        child_id,
        current_user,
        SecurityRoles.RESTART_CHILD_HOST,
        "restart_child_host",
        "restart",
        _("Child host restart requested."),
    )


async def _child_host_control(  # NOSONAR - async for interface consistency with callers
    host_id: str,
    child_id: str,
    current_user: str,
    required_role: SecurityRoles,
    command_type: str,
    action: str,
    success_message: str,
):
    """Helper function for start/stop/restart operations."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(session, current_user, required_role)

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        child = (
            session.query(HostChild)
            .filter(
                HostChild.id == child_id,
                HostChild.parent_host_id == host.id,
            )
            .first()
        )
        if not child:
            raise HTTPException(status_code=404, detail=_("Child host not found"))

        # Build parameters
        parameters = {
            "child_host_id": str(child.id),
            "child_type": child.child_type,
            "child_name": child.child_name,
        }

        # Create command message
        command_message = create_command_message(
            command_type=command_type, parameters=parameters
        )

        # Queue the message
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Audit log
        audit_log(
            session,
            user,
            current_user,
            "UPDATE",
            host_id,
            host.fqdn,
            f"Requested {action} of child host '{child.child_name}' "
            f"on host {host.fqdn}",
        )

        session.commit()

        return {"result": True, "message": success_message}
