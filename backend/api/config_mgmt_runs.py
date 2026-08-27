# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Read config-profile run history (Phase 20.1).

WHY HISTORY RATHER THAN CURRENT STATE
-------------------------------------
The value of desired-state config management is being able to see that a
profile has stopped changing anything.  That is a statement about a SEQUENCE of
runs, so the API returns a list, newest first, and the unchanged runs are the
interesting ones -- a UI that showed only "last result" could never display the
quiet streak that means the host has converged.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from backend.api.error_constants import error_host_not_found, error_invalid_host_id
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import db as persistence_db
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import config_mgmt_plan_builder as planner
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.utils.verbosity_logger import sanitize_log
from backend.websocket.messages import CommandType, Message, MessageType
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)

router = APIRouter()
queue_ops = QueueOperations()

# The history panel shows a page, not an archive.  Capped so a caller cannot
# ask for every run a long-lived host ever recorded in one request.
DEFAULT_LIMIT = 25
MAX_LIMIT = 200


class ConfigProfileRunResponse(BaseModel):
    """One recorded application of a profile."""

    id: str
    host_id: str
    profile_id: Optional[str] = None
    profile_name: Optional[str] = None
    executor: Optional[str] = None
    check_mode: bool = False
    success: bool = False
    changed: bool = False
    exit_code: Optional[int] = None
    tasks_ok: int = 0
    tasks_changed: int = 0
    tasks_failed: int = 0
    tasks_skipped: int = 0
    tasks_unreachable: int = 0
    reason: Optional[str] = None
    completed_at: Optional[datetime] = None


class ConfigProfileRunDetailResponse(ConfigProfileRunResponse):
    """A single run, including its per-task detail."""

    tasks: List[Dict[str, Any]] = []
    error_output: Optional[str] = None


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Stamp naive timestamps as UTC.

    Rows are stored naive-UTC, and handing a naive datetime to a browser makes
    it render in local time as though it were local -- a run would appear to
    have happened hours from now.
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _base_fields(run) -> Dict[str, Any]:
    return {
        "id": str(run.id),
        "host_id": str(run.host_id),
        "profile_id": str(run.profile_id) if run.profile_id else None,
        "profile_name": run.profile_name,
        "executor": run.executor,
        "check_mode": bool(run.check_mode),
        "success": bool(run.success),
        "changed": bool(run.changed),
        "exit_code": run.exit_code,
        "tasks_ok": run.tasks_ok or 0,
        "tasks_changed": run.tasks_changed or 0,
        "tasks_failed": run.tasks_failed or 0,
        "tasks_skipped": run.tasks_skipped or 0,
        "tasks_unreachable": run.tasks_unreachable or 0,
        "reason": run.reason,
        "completed_at": _as_utc(run.completed_at),
    }


def _require_host(db_session: Session, host_id: str):
    try:
        host_uuid = uuid.UUID(host_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=error_invalid_host_id()) from exc
    host = db_session.query(models.Host).filter(models.Host.id == host_uuid).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())
    return host


@router.get(
    "/hosts/{host_id}/config-management/runs",
    response_model=List[ConfigProfileRunResponse],
    dependencies=[Depends(JWTBearer())],
)
async def list_config_profile_runs(
    host_id: str,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db_session: Session = Depends(get_tenant_db),
):
    """Recent profile applications for one host, newest first."""
    host = _require_host(db_session, host_id)
    runs = (
        db_session.query(models.ConfigProfileRun)
        .filter(models.ConfigProfileRun.host_id == host.id)
        .order_by(models.ConfigProfileRun.completed_at.desc())
        .limit(limit)
        .all()
    )
    return [ConfigProfileRunResponse(**_base_fields(run)) for run in runs]


@router.get(
    "/config-management/runs/{run_id}",
    response_model=ConfigProfileRunDetailResponse,
    dependencies=[Depends(JWTBearer())],
)
async def get_config_profile_run(
    run_id: str,
    db_session: Session = Depends(get_tenant_db),
):
    """One run, with the per-task detail the list view omits."""
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid run ID format") from exc

    run = (
        db_session.query(models.ConfigProfileRun)
        .filter(models.ConfigProfileRun.id == run_uuid)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Configuration run not found")

    tasks: List[Dict[str, Any]] = []
    if run.task_detail:
        try:
            decoded = json.loads(run.task_detail)
            # Detail is TRUNCATED on ingest when a playbook is long, so this is
            # expected to fail sometimes.  An unreadable tail must degrade to
            # "no per-task detail", never to a 500 on a run that really ran.
            if isinstance(decoded, list):
                tasks = decoded
        except ValueError:
            logger.debug("Run %s has unparsable (likely truncated) detail", run_id)

    return ConfigProfileRunDetailResponse(
        **_base_fields(run), tasks=tasks, error_output=run.error_output
    )


class ConfigProfileApplyRequest(BaseModel):
    """An ad-hoc profile to apply to one host.

    Exactly one of ``playbook`` (POSIX) or ``resources`` (Windows/DSC) is
    expected, and it must match the host's executor -- see the route.
    """

    playbook: Optional[str] = None
    resources: Optional[List[Dict[str, Any]]] = None
    profile_name: Optional[str] = None
    check_mode: bool = False
    timeout: Optional[int] = None


class ConfigProfileApplyResponse(BaseModel):
    """Result of queuing a profile application."""

    host_id: str
    queued: bool
    check_mode: bool
    message: str


@router.post(
    "/hosts/{host_id}/config-management/apply",
    response_model=ConfigProfileApplyResponse,
)
async def apply_config_profile(
    host_id: str,
    request: ConfigProfileApplyRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Queue an ad-hoc configuration profile for one host.

    Gated on RUN_SCRIPT, deliberately, and not on a softer config-specific
    role: a playbook can run anything the agent can, so the blast radius is
    identical to executing a script. Inventing a weaker permission for the same
    capability would be a privilege-escalation path dressed up as a feature.
    """
    if not current_user.has_role(SecurityRoles.RUN_SCRIPT):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: RUN_SCRIPT role required"),
        )

    host = _require_host(db_session, host_id)
    if not host.active:
        # Queuing for an inactive host buries the work in a queue that may
        # never drain, and the operator sees "queued" and assumes it ran.
        raise HTTPException(status_code=400, detail=_("Host is not active"))

    host_info = {
        "platform": host.platform,
        "platform_release": host.platform_release,
        "platform_version": host.platform_version,
    }
    executor = planner.executor_for(host_info)

    # Refuse a payload the host's executor cannot consume, rather than letting
    # it fail at the far end where the reason is far less obvious.
    if executor == planner.WINDOWS_EXECUTOR:
        if not request.resources:
            raise HTTPException(
                status_code=400,
                detail=_("This host uses DSC; provide 'resources', not 'playbook'"),
            )
        profile: Dict[str, Any] = {"resources": request.resources}
    else:
        if not request.playbook or not request.playbook.strip():
            raise HTTPException(
                status_code=400,
                detail=_("This host uses ansible-core; provide 'playbook'"),
            )
        profile = {"playbook": request.playbook}

    parameters: Dict[str, Any] = {
        "profile": profile,
        "check_mode": bool(request.check_mode),
    }
    if request.profile_name:
        parameters["profile_name"] = request.profile_name
    if request.timeout:
        parameters["timeout"] = request.timeout

    command_message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.APPLY_CONFIG_PROFILE,
            "parameters": parameters,
        },
    )
    queue_ops.enqueue_message(
        message_type="command",
        message_data=command_message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db_session,
    )
    db_session.commit()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=persistence_db.get_engine()
    )
    with session_local() as audit_session:
        AuditService.log(
            db=audit_session,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=str(host.id),
            entity_name=host.fqdn,
            description=f"Applied configuration profile to host {host.fqdn}",
            result=Result.SUCCESS,
            # The profile body is NOT audited: it can carry secrets, and the
            # audit log is readable by more people than the profile is.
            details={
                "executor": executor,
                "check_mode": bool(request.check_mode),
                "profile_name": request.profile_name,
            },
        )

    logger.info(
        "Config profile queued for host %s (%s), check_mode=%s",
        host.fqdn,
        sanitize_log(str(host.id)),
        bool(request.check_mode),
    )
    return ConfigProfileApplyResponse(
        host_id=str(host.id),
        queued=True,
        check_mode=bool(request.check_mode),
        message=_("Configuration profile was queued for this host"),
    )
