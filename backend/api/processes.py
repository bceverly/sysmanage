"""
Host process-management API (Phase 13.3).

Read the latest running-process snapshot for a host, ask the agent to refresh
it, or terminate a process.  The snapshot itself is collected by the agent and
ingested over the message queue (see ``process_handlers``); the kill/refresh
endpoints enqueue an outbound command for the agent.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from backend.api.error_constants import error_host_not_active, error_host_not_found
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import db as db_module
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import Priority, QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()
queue_ops = QueueOperations()


class ProcessResponse(BaseModel):
    """A single process from a host's latest snapshot."""

    id: str
    pid: int
    parent_pid: Optional[int]
    process_name: str
    username: Optional[str]
    status: Optional[str]
    cpu_percent: Optional[float]
    memory_percent: Optional[float]
    memory_rss_bytes: Optional[int]
    command_line: Optional[str]
    started_at: Optional[str]
    collected_at: Optional[str]


class KillProcessRequest(BaseModel):
    """Optional kill parameters."""

    force: bool = False  # SIGKILL instead of SIGTERM
    expected_name: Optional[str] = None  # guard against PID reuse


class SimpleResult(BaseModel):
    result: bool
    message: str


def _get_active_host(db: Session, host_id: str) -> models.Host:
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())
    if not host.active:
        raise HTTPException(status_code=400, detail=error_host_not_active())
    return host


@router.get(
    "/host/{host_id}/processes",
    dependencies=[Depends(JWTBearer())],
)
async def get_host_processes(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> List[ProcessResponse]:
    """Return the latest running-process snapshot for a host."""
    if not current_user.has_role(SecurityRoles.VIEW_HOST_DETAILS):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: View Host Details role required"),
        )

    # 404 if the host isn't known to this tenant; an empty list is valid
    # (no snapshot yet) and distinct from "unknown host".
    if not db.query(models.Host).filter(models.Host.id == host_id).first():
        raise HTTPException(status_code=404, detail=error_host_not_found())

    rows = (
        db.query(models.HostProcess)
        .filter(models.HostProcess.host_id == host_id)
        .order_by(models.HostProcess.cpu_percent.desc().nullslast())
        .all()
    )
    return [
        ProcessResponse(
            id=str(p.id),
            pid=p.pid,
            parent_pid=p.parent_pid,
            process_name=p.process_name,
            username=p.username,
            status=p.status,
            cpu_percent=p.cpu_percent,
            memory_percent=p.memory_percent,
            memory_rss_bytes=p.memory_rss_bytes,
            command_line=p.command_line,
            started_at=p.started_at.isoformat() if p.started_at else None,
            collected_at=p.collected_at.isoformat() if p.collected_at else None,
        )
        for p in rows
    ]


@router.post(
    "/host/{host_id}/processes/refresh",
    dependencies=[Depends(JWTBearer())],
)
async def refresh_host_processes(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> SimpleResult:
    """Ask the agent to collect and send a fresh process snapshot."""
    if not current_user.has_role(SecurityRoles.VIEW_HOST_DETAILS):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: View Host Details role required"),
        )

    _get_active_host(db, host_id)

    command_message = create_command_message(command_type="collect_processes")
    queue_ops.enqueue_message(
        message_type="command",
        message_data=command_message,
        direction=QueueDirection.OUTBOUND,
        host_id=host_id,
        db=db,
    )
    db.commit()

    return SimpleResult(
        result=True,
        message=_("Process refresh requested. The list will update shortly."),
    )


@router.post(
    "/host/{host_id}/processes/{pid}/kill",
    dependencies=[Depends(JWTBearer())],
)
async def kill_host_process(
    host_id: str,
    pid: int,
    request: KillProcessRequest = KillProcessRequest(),
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> SimpleResult:
    """Terminate a process on a host (enqueues a command to the agent)."""
    if not current_user.has_role(SecurityRoles.KILL_HOST_PROCESS):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: Kill Host Process role required"),
        )

    host = _get_active_host(db, host_id)
    if not host.is_agent_privileged:
        raise HTTPException(
            status_code=400,
            detail=_("Agent must be running in privileged mode to terminate processes"),
        )

    parameters = {"pid": pid, "force": request.force}
    if request.expected_name:
        parameters["expected_name"] = request.expected_name

    command_message = create_command_message(
        command_type="kill_process", parameters=parameters
    )
    queue_ops.enqueue_message(
        message_type="command",
        message_data=command_message,
        direction=QueueDirection.OUTBOUND,
        host_id=host_id,
        priority=Priority.HIGH,
        db=db,
    )
    db.commit()

    # Audit the destructive action on the main engine.
    from backend.services.audit_service import (
        ActionType,
        AuditService,
        EntityType,
        Result,
    )

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )
    with session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.DELETE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
            description=(
                f"Requested termination of PID {pid} "
                f"({'SIGKILL' if request.force else 'SIGTERM'}) on host {host.fqdn}"
            ),
            result=Result.SUCCESS,
        )

    return SimpleResult(
        result=True,
        message=_("Process termination requested. The list will update shortly."),
    )
