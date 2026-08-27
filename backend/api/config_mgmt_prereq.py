# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Config-management prerequisite status and one-button install (Phase 20.1).

Phase 20.1 applies desired state PULL-style: the server ships a profile down
the existing WebSocket and the agent applies it locally with an executor that
has to be present on the host.  These two routes are what the UI card uses to
say "ansible-core is needed here", offer a button, and then say it is fine.

Status is DERIVED from the software inventory the agent already reports -- see
``backend.services.config_mgmt_prereq`` for why that is preferable to a new
agent probe, and for the freshness caveat it buys.

Install reuses ``APPLY_DEPLOYMENT_PLAN``, the same declarative path the
antivirus and OpenTelemetry deployments take.  Nothing new lands on the agent.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from backend.api.error_constants import error_host_not_found, error_invalid_host_id
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import db as persistence_db
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import config_mgmt_engines as engines
from backend.services import config_mgmt_plan_builder as planner
from backend.services import config_mgmt_prereq as prereq
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.utils.verbosity_logger import sanitize_log
from backend.websocket.messages import (
    CommandType,
    Message,
    MessageType,
    create_command_message,
)
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)

router = APIRouter()
queue_ops = QueueOperations()


class ConfigMgmtPrereqResponse(BaseModel):
    """What the UI card needs to render one host's readiness."""

    host_id: str
    executor: str
    status: str
    installed_version: Optional[str] = None
    minimum_version: Optional[str] = None
    can_install: bool = False
    detail: Optional[str] = None
    package_name: Optional[str] = None


class ConfigMgmtEngineStatus(BaseModel):
    """Readiness of one engine on one host."""

    engine: str
    status: str
    installed_version: Optional[str] = None
    minimum_version: Optional[str] = None
    can_install: bool = False
    detail: Optional[str] = None
    package_name: Optional[str] = None
    # True for the Puppet/Salt/Chef adapters. The row is still returned so an
    # evaluator can SEE the engine is supported; it just cannot be installed
    # or dispatched without the config_management_engine module.
    requires_license: bool = False


class ConfigMgmtEnginesResponse(BaseModel):
    """Every engine that could run on a host, readiest first."""

    host_id: str
    default_engine: str
    engines: List[ConfigMgmtEngineStatus] = []


class ConfigMgmtPrereqInstallResponse(BaseModel):
    """Result of queuing the prerequisite install."""

    host_id: str
    queued: bool
    message: str


def _host_info(host: models.Host) -> Dict[str, Any]:
    """Pack a Host's OS fields into the dict the planner expects."""
    return {
        "platform": host.platform,
        "platform_release": host.platform_release,
        "platform_version": host.platform_version,
    }


def _load_host(db_session: Session, host_id: str) -> models.Host:
    """Fetch a host by string id, raising the standard 400/404 for the API."""
    try:
        host_uuid = uuid.UUID(host_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=error_invalid_host_id()) from exc

    host = db_session.query(models.Host).filter(models.Host.id == host_uuid).first()
    if not host:
        raise HTTPException(status_code=404, detail=error_host_not_found())
    return host


def _candidate_packages(
    db_session: Session, host: models.Host, pattern: Optional[str]
) -> List[Dict[str, Any]]:
    """Installed packages that could satisfy ``pattern``, as plain dicts.

    The LIKE prefilter exists so this does not drag a host's entire software
    inventory (thousands of rows on a full desktop) into memory to find one
    package.  It is a PREFILTER only -- the authoritative match is the fnmatch
    in the evaluator, because ``py3*-ansible-core`` needs glob semantics that
    SQL LIKE does not give us.
    """
    if not pattern:
        return []
    # Anchor on the fixed tail of the pattern; every pattern we build ends in
    # the real package name.
    like = "%" + pattern.split("*")[-1]
    rows = (
        db_session.query(models.SoftwarePackage)
        .filter(
            models.SoftwarePackage.host_id == host.id,
            models.SoftwarePackage.package_name.like(like),
        )
        .all()
    )
    return [
        {
            "package_name": row.package_name,
            "package_version": row.package_version,
            "package_manager": row.package_manager,
        }
        for row in rows
    ]


@router.get(
    "/hosts/{host_id}/config-management/prerequisite",
    response_model=ConfigMgmtPrereqResponse,
    dependencies=[Depends(JWTBearer())],
)
async def get_config_mgmt_prerequisite(
    host_id: str,
    db_session: Session = Depends(get_tenant_db),
):
    """Report whether this host has the config-management executor it needs."""
    host = _load_host(db_session, host_id)
    host_info = _host_info(host)
    packages = _candidate_packages(
        db_session, host, planner.expected_package_pattern(host_info)
    )
    result = prereq.evaluate(host_info, packages)
    return ConfigMgmtPrereqResponse(host_id=str(host.id), **result)


@router.post(
    "/hosts/{host_id}/config-management/prerequisite/install",
    response_model=ConfigMgmtPrereqInstallResponse,
)
async def install_config_mgmt_prerequisite(
    host_id: str,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Queue the plan that installs this host's config-management executor.

    Gated on ADD_PACKAGE rather than a new role: what this does IS install a
    package on a managed host, and anyone entitled to do that by hand should
    not need a second entitlement to do it by button.
    """
    if not current_user.has_role(SecurityRoles.ADD_PACKAGE):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: ADD_PACKAGE role required"),
        )

    host = _load_host(db_session, host_id)
    host_info = _host_info(host)

    plan = planner.build_install_plan(host_info)
    if plan is None:
        # Either nothing to install (Windows vendors dsc.exe) or we have no
        # measured install path for this platform.  Both are 400s: the caller
        # asked for something that is not a thing here.  The status route
        # already distinguishes the two for display.
        raise HTTPException(
            status_code=400,
            detail=_(
                "No config-management prerequisite install is available for this platform"
            ),
        )

    command_message = Message(
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.APPLY_DEPLOYMENT_PLAN,
            "parameters": {"plan": plan},
        },
    )
    queue_ops.enqueue_message(
        message_type="command",
        message_data=command_message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db_session,
    )

    # Queue an inventory refresh BEHIND the install.  Status here is derived
    # from the software inventory, so without this the card would keep saying
    # "missing" until the next scheduled collection -- an operator presses the
    # button, the install succeeds, and the UI appears not to have noticed.
    # Worst case the refresh runs too early and the periodic collection
    # corrects it; that is strictly better than always being stale.
    queue_ops.enqueue_message(
        message_type="command",
        message_data=create_command_message("update_software_inventory", {}),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db_session,
    )
    db_session.commit()

    # The audit trail lives on the MAIN engine; host data routed to the tenant
    # engine via ``db_session`` above.
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
            description=f"Requested config-management prerequisite install for host {host.fqdn}",
            result=Result.SUCCESS,
            details={"executor": planner.executor_for(host_info)},
        )

    logger.info(
        "Config-management prerequisite install queued for host %s (%s)",
        host.fqdn,
        sanitize_log(str(host.id)),
    )
    return ConfigMgmtPrereqInstallResponse(
        host_id=str(host.id),
        queued=True,
        message=_("Installation of the config-management prerequisite was requested"),
    )


@router.get(
    "/hosts/{host_id}/config-management/engines",
    response_model=ConfigMgmtEnginesResponse,
    dependencies=[Depends(JWTBearer())],
)
async def list_config_mgmt_engines(
    host_id: str,
    db_session: Session = Depends(get_tenant_db),
):
    """Which config-management engines this host can run, and their readiness.

    Returns a LIST rather than the single executor the older endpoint reports:
    a host may have several engines installed, and which one applies is a
    property of the profile. The list is ordered readiest-first so the UI leads
    with what the host has rather than with what it lacks.
    """
    host = _load_host(db_session, host_id)
    host_info = _host_info(host)

    # One inventory read covering every engine's pattern, rather than a query
    # per engine: the whole point of the prefilter is to avoid dragging a
    # desktop's software list into memory, and doing it five times would undo
    # that.
    packages: List[Dict[str, Any]] = []
    seen = set()
    for engine in engines.applicable(planner.platform_kind(host_info)):
        pattern = prereq.engine_package_pattern(engine, host_info)
        if not pattern or pattern in seen:
            continue
        seen.add(pattern)
        packages.extend(_candidate_packages(db_session, host, pattern))

    results = prereq.evaluate_all(host_info, packages)
    return ConfigMgmtEnginesResponse(
        host_id=str(host.id),
        default_engine=engines.default_engine(planner.platform_kind(host_info)),
        engines=[ConfigMgmtEngineStatus(**row) for row in results],
    )
