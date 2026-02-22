"""
Child host control API endpoints (start, stop, restart).

NOTE: Container/VM lifecycle control is a Pro+ feature. The actual implementation
is provided by the container_engine module. This file provides stub endpoints
that return license-required errors for community users.
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
from backend.licensing.module_loader import module_loader
from backend.persistence import db
from backend.persistence.models import HostChild
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()

MSG_CHILD_HOST_NOT_FOUND = "Child host not found"


def _check_container_module():
    """Check if container_engine Pro+ module is available."""
    container_engine = module_loader.get_module("container_engine")
    if container_engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Container lifecycle management requires a SysManage Professional+ license. "
                "Please upgrade to access this feature."
            ),
        )


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

    This is a Pro+ feature. Requires container_engine module.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.START_CHILD_HOST
        )

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
            raise HTTPException(status_code=404, detail=_(MSG_CHILD_HOST_NOT_FOUND))

        queue_ops = QueueOperations()

        command_message = create_command_message(
            command_type="start_child_host",
            parameters={
                "child_name": child.child_name,
                "child_type": child.child_type,
            },
        )

        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        audit_log(
            session,
            user,
            current_user,
            "UPDATE",
            str(host.id),
            host.fqdn,
            _("Child host start requested: %s") % child.child_name,
        )

        session.commit()

        return {
            "result": True,
            "message": _("Child host start requested"),
        }


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

    This is a Pro+ feature. Requires container_engine module.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.STOP_CHILD_HOST
        )

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
            raise HTTPException(status_code=404, detail=_(MSG_CHILD_HOST_NOT_FOUND))

        queue_ops = QueueOperations()

        command_message = create_command_message(
            command_type="stop_child_host",
            parameters={
                "child_name": child.child_name,
                "child_type": child.child_type,
            },
        )

        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        audit_log(
            session,
            user,
            current_user,
            "UPDATE",
            str(host.id),
            host.fqdn,
            _("Child host stop requested: %s") % child.child_name,
        )

        session.commit()

        return {
            "result": True,
            "message": _("Child host stop requested"),
        }


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

    This is a Pro+ feature. Requires container_engine module.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.RESTART_CHILD_HOST
        )

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
            raise HTTPException(status_code=404, detail=_(MSG_CHILD_HOST_NOT_FOUND))

        queue_ops = QueueOperations()

        command_message = create_command_message(
            command_type="restart_child_host",
            parameters={
                "child_name": child.child_name,
                "child_type": child.child_type,
            },
        )

        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        audit_log(
            session,
            user,
            current_user,
            "UPDATE",
            str(host.id),
            host.fqdn,
            _("Child host restart requested: %s") % child.child_name,
        )

        session.commit()

        return {
            "result": True,
            "message": _("Child host restart requested"),
        }
