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
from backend.licensing.feature_gate import require_module
from backend.licensing.features import ModuleCode
from backend.i18n import _
from backend.persistence import db as persistence_db
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.utils.log_sanitize import scrub
from backend.services import config_mgmt_engines as engines
from backend.services import config_mgmt_plan_builder as planner
from backend.services import config_mgmt_spec_shim as spec_shim
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
            logger.debug(
                "Run %s has unparsable (likely truncated) detail", scrub(run_id)
            )

    return ConfigProfileRunDetailResponse(
        **_base_fields(run), tasks=tasks, error_output=run.error_output
    )


class ConfigProfileApplyRequest(BaseModel):
    """A profile to apply to one host, stored or ad-hoc.

    Two shapes, and ``profile_id`` decides which:

    * **Stored (Enterprise).** ``profile_id`` names a saved profile; the
      server reads its engine and body, so the browser never round-trips a
      body it already stored, and the run is recorded AGAINST that profile.
    * **Ad-hoc (open source).** Exactly one of ``playbook`` (POSIX) or
      ``resources`` (Windows/DSC), matching the host's executor.
    """

    profile_id: Optional[str] = None
    playbook: Optional[str] = None
    resources: Optional[List[Dict[str, Any]]] = None
    # Which engine to apply with. Omitted, the host's platform default is used
    # -- which is what keeps every existing caller working. Ignored when
    # profile_id is given: the stored profile's own engine wins, because a
    # profile written for Puppet is not a thing you can run with Salt.
    engine: Optional[str] = None
    profile_name: Optional[str] = None
    check_mode: bool = False
    timeout: Optional[int] = None


class ConfigProfileApplyResponse(BaseModel):
    """Result of queuing a profile application."""

    host_id: str
    queued: bool
    check_mode: bool
    message: str


def _dsc_resources(profile):
    """A stored DSC profile's body as a resource list, or None.

    DSC bodies are stored as the JSON text the author typed. Parsing here
    turns a bad stored body into a 400 naming the profile, rather than an
    opaque failure on the host hours later.
    """
    if profile.engine != engines.DSC:
        return None
    try:
        parsed = json.loads(profile.content)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_("Profile '%s' does not contain valid JSON") % profile.name,
        ) from exc
    if not isinstance(parsed, list):
        raise HTTPException(
            status_code=400,
            detail=_("Profile '%s' must contain a JSON array of DSC resources")
            % profile.name,
        )
    return parsed


def _load_stored_profile(db_session, profile_id: str):
    """The stored profile named by an apply request.

    Licence-gated HERE rather than at the router: ad-hoc apply is open source
    and must keep working on an unlicensed server, so only the stored-profile
    path can demand the module.
    """
    require_module(ModuleCode.CONFIG_MANAGEMENT_ENGINE)
    try:
        wanted = uuid.UUID(str(profile_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(
            status_code=400, detail=_("Invalid profile ID format")
        ) from exc

    profile = (
        db_session.query(models.ConfigProfile)
        .filter(models.ConfigProfile.id == wanted)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_("Profile not found"))
    if not profile.is_active:
        # An inactive profile is one somebody deliberately took out of service.
        # Applying it anyway would make the flag decorative.
        raise HTTPException(status_code=400, detail=_("This profile is not active"))
    return profile


def _resolve_executor(host, request: "ConfigProfileApplyRequest") -> str:
    """The engine this apply will use, or 400/402 explaining why not."""
    host_info = {
        "platform": host.platform,
        "platform_release": host.platform_release,
        "platform_version": host.platform_version,
    }
    kind = planner.platform_kind(host_info)
    executor = (request.engine or "").strip().lower() or engines.default_engine(kind)

    if not engines.is_known(executor):
        raise HTTPException(
            status_code=400,
            detail=_("Unknown configuration management engine: %s") % executor,
        )

    # Puppet/Salt/Chef are the licensed adapters. Refuse BEFORE queueing, so an
    # unlicensed install never gets a half-applied profile and an operator gets
    # a clear reason rather than a far-end failure.
    if engines.requires_license(executor):
        require_module(ModuleCode.CONFIG_MANAGEMENT_ENGINE)

    return executor


def _build_profile(
    executor: str, request: "ConfigProfileApplyRequest"
) -> Dict[str, Any]:
    """The profile body for this executor.

    Refuses a payload the host's executor cannot consume, rather than letting
    it fail at the far end where the reason is far less obvious.
    """
    if executor == engines.DSC:
        if not request.resources:
            raise HTTPException(
                status_code=400,
                detail=_("This host uses DSC; provide 'resources', not 'playbook'"),
            )
        return {"resources": request.resources}

    if not request.playbook or not request.playbook.strip():
        raise HTTPException(
            status_code=400,
            detail=_("This host uses ansible-core; provide 'playbook'"),
        )
    return {"playbook": request.playbook}


def _licensed_spec(executor: str, request: "ConfigProfileApplyRequest"):
    """The execution spec for a licensed engine, or 503 if it cannot be built.

    A licensed engine is driven by a SPEC the Pro+ module builds. The agent
    deliberately does not know how to run Puppet/Salt/Chef -- see
    sysmanage-agent operations/config_mgmt_spec.py for why that indirection
    exists -- so without a spec there is nothing to dispatch.
    """
    spec = spec_shim.build_licensed_spec(
        executor,
        request.playbook or "",
        check_mode=bool(request.check_mode),
        timeout=request.timeout,
    )
    if spec is None:
        # The licence check has already passed, so this is a broken install
        # (module not loaded for this Python version) rather than an
        # unlicensed customer. 503, not 403 -- they need an administrator,
        # not a salesperson.
        raise HTTPException(
            status_code=503,
            detail=_(
                "The configuration management engine is licensed but not "
                "available on this server"
            ),
        )
    return spec


def _build_parameters(
    executor: str, request: "ConfigProfileApplyRequest"
) -> Dict[str, Any]:
    """The command parameters the agent will receive."""
    parameters: Dict[str, Any] = {
        "profile": _build_profile(executor, request),
        "check_mode": bool(request.check_mode),
    }
    if engines.requires_license(executor):
        parameters["spec"] = _licensed_spec(executor, request)
    if request.profile_name:
        parameters["profile_name"] = request.profile_name
    if request.timeout:
        parameters["timeout"] = request.timeout
    return parameters


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

    stored = (
        _load_stored_profile(db_session, request.profile_id)
        if request.profile_id
        else None
    )
    if stored is not None:
        # Rewrite the request into the ad-hoc shape so exactly one code path
        # builds the command. Two paths would drift, and the stored one is the
        # one nobody exercises by hand.
        request = request.model_copy(
            update={
                "engine": stored.engine,
                "playbook": stored.content,
                "resources": _dsc_resources(stored),
                "profile_name": stored.name,
            }
        )

    executor = _resolve_executor(host, request)
    parameters = _build_parameters(executor, request)
    if stored is not None:
        # Recorded on the run so history links back to the profile -- the
        # column exists for exactly this.
        parameters["profile_id"] = str(stored.id)

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
