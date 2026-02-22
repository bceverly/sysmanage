"""
Reboot orchestration API endpoints for safe parent host reboot.

Open Source: Pre-check endpoint shows running child hosts before reboot.
Pro+: Orchestrated reboot cleanly stops children, reboots, then restarts them.
"""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api.child_host_utils import (
    audit_log,
    get_host_or_404,
    get_user_with_role_check,
)
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import db
from backend.persistence.models import HostChild, RebootOrchestration
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()


def _has_container_engine():
    """Check if container_engine Pro+ module is available (non-throwing)."""
    return module_loader.get_module("container_engine") is not None


def _check_container_module():
    """Check if container_engine Pro+ module is available (throws 402)."""
    if not _has_container_engine():
        raise HTTPException(
            status_code=402,
            detail=_(
                "Orchestrated reboot requires a SysManage Professional+ license. "
                "Please upgrade to access this feature."
            ),
        )


@router.get(
    "/host/{host_id}/reboot/pre-check",
    dependencies=[Depends(JWTBearer())],
)
async def reboot_pre_check(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Pre-check before rebooting a parent host.

    Returns information about running child hosts so the user can make an
    informed decision. This is an open-source endpoint (no Pro+ required).
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        get_user_with_role_check(session, current_user, SecurityRoles.REBOOT_HOST)

        host = get_host_or_404(session, host_id)

        # Get all child hosts for this parent
        all_children = (
            session.query(HostChild).filter(HostChild.parent_host_id == host.id).all()
        )

        running_children = [c for c in all_children if c.status == "running"]

        return {
            "has_running_children": len(running_children) > 0,
            "running_children": [
                {
                    "id": str(c.id),
                    "child_name": c.child_name,
                    "child_type": c.child_type,
                    "status": c.status,
                }
                for c in running_children
            ],
            "running_count": len(running_children),
            "total_children": len(all_children),
            "has_container_engine": _has_container_engine(),
        }


@router.post(
    "/host/{host_id}/reboot/orchestrated",
    dependencies=[Depends(JWTBearer())],
)
async def orchestrated_reboot(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Initiate an orchestrated reboot sequence for a parent host.

    Pro+ feature: Cleanly stops all running child hosts, reboots the parent,
    then automatically restarts the children after the agent reconnects.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.REBOOT_HOST
        )

        host = get_host_or_404(session, host_id)

        if not host.active:
            raise HTTPException(status_code=400, detail=_("Host is not active"))

        # Snapshot running children
        running_children = (
            session.query(HostChild)
            .filter(
                HostChild.parent_host_id == host.id,
                HostChild.status == "running",
            )
            .all()
        )

        if not running_children:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "No running child hosts found. Use the standard reboot endpoint instead."
                ),
            )

        # Build snapshot
        snapshot = [
            {
                "id": str(c.id),
                "child_name": c.child_name,
                "child_type": c.child_type,
                "pre_reboot_status": c.status,
            }
            for c in running_children
        ]

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Create orchestration record
        orchestration = RebootOrchestration(
            id=uuid.uuid4(),
            parent_host_id=host.id,
            status="shutting_down",
            child_hosts_snapshot=json.dumps(snapshot),
            child_hosts_restart_status=None,
            shutdown_timeout_seconds=120,
            initiated_by=current_user,
            initiated_at=now,
        )
        session.add(orchestration)

        # Enqueue stop commands for each running child
        queue_ops = QueueOperations()
        for child in running_children:
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
            _("Orchestrated reboot initiated with %d running child host(s)")
            % len(running_children),
            details={
                "orchestration_id": str(orchestration.id),
                "child_count": len(running_children),
                "children": [c.child_name for c in running_children],
            },
        )

        session.commit()

        return {
            "orchestration_id": str(orchestration.id),
            "status": orchestration.status,
            "child_count": len(running_children),
        }


@router.get(
    "/host/{host_id}/reboot/orchestration/{orchestration_id}",
    dependencies=[Depends(JWTBearer())],
)
async def get_orchestration_status(
    host_id: str,
    orchestration_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Get the current status of a reboot orchestration.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        get_user_with_role_check(session, current_user, SecurityRoles.REBOOT_HOST)

        orchestration = (
            session.query(RebootOrchestration)
            .filter(
                RebootOrchestration.id == orchestration_id,
                RebootOrchestration.parent_host_id == host_id,
            )
            .first()
        )

        if not orchestration:
            raise HTTPException(
                status_code=404, detail=_("Reboot orchestration not found")
            )

        restart_status = None
        if orchestration.child_hosts_restart_status:
            restart_status = json.loads(orchestration.child_hosts_restart_status)

        return {
            "orchestration_id": str(orchestration.id),
            "parent_host_id": str(orchestration.parent_host_id),
            "status": orchestration.status,
            "child_hosts_snapshot": json.loads(orchestration.child_hosts_snapshot),
            "child_hosts_restart_status": restart_status,
            "shutdown_timeout_seconds": orchestration.shutdown_timeout_seconds,
            "initiated_by": orchestration.initiated_by,
            "initiated_at": (
                orchestration.initiated_at.isoformat()
                if orchestration.initiated_at
                else None
            ),
            "shutdown_completed_at": (
                orchestration.shutdown_completed_at.isoformat()
                if orchestration.shutdown_completed_at
                else None
            ),
            "reboot_issued_at": (
                orchestration.reboot_issued_at.isoformat()
                if orchestration.reboot_issued_at
                else None
            ),
            "agent_reconnected_at": (
                orchestration.agent_reconnected_at.isoformat()
                if orchestration.agent_reconnected_at
                else None
            ),
            "restart_completed_at": (
                orchestration.restart_completed_at.isoformat()
                if orchestration.restart_completed_at
                else None
            ),
            "error_message": orchestration.error_message,
        }
