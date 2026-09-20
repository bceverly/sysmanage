# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Job templates and fleet jobs (Phase 20.1).

A template names a profile, an inventory and how hard to run it; launching one
produces a job with a row per host. Inventories live in
``config_mgmt_inventories``.

LICENCE-GATED AT THE ROUTER, like every other config-management router and for
the same reason: an endpoint added here is gated by default, which is the safe
direction to fail.

ROLES reuse the SCRIPT entitlements. Authoring a template is EDIT_SCRIPT-class
work; LAUNCHING one runs executable content on every host it names, so it is
RUN_SCRIPT -- the same permission as applying a profile to a single host,
because it is that operation with a larger blast radius rather than a
different one.

WHY LAUNCH DISPATCHES ITS FIRST WAVE INLINE
-------------------------------------------
``launch`` creates the job and immediately calls ``advance_job``, so the first
``concurrency`` hosts are queued before the response returns. Leaving it to the
tick would mean an operator pressing Launch watches a job sit at zero for up to
a minute, which reads as a broken button -- and the first thing they would do
is press it again.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.feature_gate import require_module_loaded
from backend.licensing.features import ModuleCode
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import config_mgmt_fleet as fleet
from backend.services import config_mgmt_job_runner as runner

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[
        Depends(JWTBearer()),
        Depends(require_module_loaded(ModuleCode.CONFIG_MANAGEMENT_ENGINE)),
    ]
)

# The jobs list is a dashboard, not an archive.
DEFAULT_JOB_LIMIT = 25
MAX_JOB_LIMIT = 200
# A job of four thousand targets must not render as four thousand rows in one
# response; the UI pages through them.
DEFAULT_TARGET_LIMIT = 100
MAX_TARGET_LIMIT = 1000


class TemplateRequest(BaseModel):
    """A launchable profile-plus-inventory."""

    name: str
    profile_id: str
    inventory_id: str
    description: Optional[str] = None
    check_mode: bool = False
    concurrency: Optional[int] = None
    timeout_seconds: Optional[int] = None
    schedule: Optional[str] = None
    enabled: bool = True


class TemplateUpdateRequest(BaseModel):
    """Fields to change. Omitted fields are left alone."""

    name: Optional[str] = None
    description: Optional[str] = None
    profile_id: Optional[str] = None
    inventory_id: Optional[str] = None
    check_mode: Optional[bool] = None
    concurrency: Optional[int] = None
    timeout_seconds: Optional[int] = None
    schedule: Optional[str] = None
    enabled: Optional[bool] = None


class TemplateResponse(BaseModel):
    """A stored job template."""

    id: str
    name: str
    description: Optional[str] = None
    profile_id: str
    inventory_id: str
    check_mode: bool
    concurrency: int
    timeout_seconds: Optional[int] = None
    schedule: Optional[str] = None
    enabled: bool
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_launched_at: Optional[datetime] = None


class JobResponse(BaseModel):
    """One fan-out across an inventory."""

    id: str
    template_id: Optional[str] = None
    template_name: Optional[str] = None
    profile_id: Optional[str] = None
    profile_name: Optional[str] = None
    inventory_name: Optional[str] = None
    status: str
    check_mode: bool
    concurrency: int
    total_targets: int
    succeeded_count: int
    failed_count: int
    skipped_count: int
    outstanding_count: int
    requested_by: Optional[str] = None
    detail: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class JobTargetResponse(BaseModel):
    """One host within a job."""

    id: str
    job_id: str
    host_id: Optional[str] = None
    host_fqdn: Optional[str] = None
    status: str
    command_id: Optional[str] = None
    run_id: Optional[str] = None
    detail: Optional[str] = None
    queued_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class CancelRequest(BaseModel):
    """Why a job was stopped. Recorded on the job, so it is worth asking for."""

    reason: Optional[str] = None


# --- helpers -----------------------------------------------------------------


def _require_role(user, role) -> None:
    if not user.has_role(role):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required") % role.value,
        )


def _as_uuid(value: str, message: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=message) from exc


def _load_template(db_session: Session, template_id: str):
    row = (
        db_session.query(models.ConfigJobTemplate)
        .filter(
            models.ConfigJobTemplate.id
            == _as_uuid(template_id, _("Invalid job template ID format"))
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_("Job template not found"))
    return row


def _load_job(db_session: Session, job_id: str):
    row = (
        db_session.query(models.ConfigJob)
        .filter(models.ConfigJob.id == _as_uuid(job_id, _("Invalid job ID format")))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_("Job not found"))
    return row


def _require_profile(db_session: Session, profile_id: str):
    row = (
        db_session.query(models.ConfigProfile)
        .filter(
            models.ConfigProfile.id
            == _as_uuid(profile_id, _("Invalid profile ID format"))
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_("Profile not found"))
    return row


def _require_inventory(db_session: Session, inventory_id: str):
    row = (
        db_session.query(models.ConfigInventory)
        .filter(
            models.ConfigInventory.id
            == _as_uuid(inventory_id, _("Invalid inventory ID format"))
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_("Inventory not found"))
    return row


def _name_taken(db_session: Session, name: str, exclude_id=None) -> bool:
    query = db_session.query(models.ConfigJobTemplate).filter(
        models.ConfigJobTemplate.name == (name or "").strip()
    )
    if exclude_id is not None:
        query = query.filter(models.ConfigJobTemplate.id != exclude_id)
    return query.first() is not None


# --- job templates -----------------------------------------------------------


@router.get("/config-management/job-templates", response_model=List[TemplateResponse])
async def list_templates(db_session: Session = Depends(get_tenant_db)):
    """Every job template, by name."""
    rows = (
        db_session.query(models.ConfigJobTemplate)
        .order_by(models.ConfigJobTemplate.name.asc())
        .all()
    )
    return [TemplateResponse(**fleet.template_to_dict(row)) for row in rows]


@router.post("/config-management/job-templates", response_model=TemplateResponse)
async def create_template(
    request: TemplateRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Store a job template."""
    _require_role(current_user, SecurityRoles.ADD_SCRIPT)

    problem = fleet.validate_job_template(
        request.name, request.profile_id, request.inventory_id, request.schedule
    )
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    if _name_taken(db_session, request.name):
        raise HTTPException(
            status_code=409,
            detail=_("A job template named '%s' already exists") % request.name,
        )

    profile = _require_profile(db_session, request.profile_id)
    inventory = _require_inventory(db_session, request.inventory_id)

    now = fleet.now_naive()
    row = models.ConfigJobTemplate(
        name=request.name.strip(),
        description=request.description,
        profile_id=profile.id,
        inventory_id=inventory.id,
        check_mode=bool(request.check_mode),
        # Clamped, not validated: an operator who types 10,000 means "as fast
        # as possible", and the stored value shows them what they got.
        concurrency=fleet.clamp_concurrency(request.concurrency),
        timeout_seconds=fleet.clamp_timeout(request.timeout_seconds),
        schedule=(request.schedule or "").strip() or None,
        enabled=bool(request.enabled),
        created_by=current_user.userid,
        updated_by=current_user.userid,
        created_at=now,
        updated_at=now,
    )
    db_session.add(row)
    db_session.commit()
    logger.info("Config job template created: %s", row.name)
    return TemplateResponse(**fleet.template_to_dict(row))


@router.get(
    "/config-management/job-templates/{template_id}", response_model=TemplateResponse
)
async def get_template(template_id: str, db_session: Session = Depends(get_tenant_db)):
    """One job template."""
    return TemplateResponse(
        **fleet.template_to_dict(_load_template(db_session, template_id))
    )


@router.put(
    "/config-management/job-templates/{template_id}", response_model=TemplateResponse
)
async def update_template(
    template_id: str,
    request: TemplateUpdateRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Change a job template."""
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    row = _load_template(db_session, template_id)
    changes = request.model_dump(exclude_unset=True)

    # Validated against the template the change WOULD produce, not the delta:
    # a request that changes only the schedule still has to be valid alongside
    # the existing profile and inventory.
    problem = fleet.validate_job_template(
        changes.get("name", row.name),
        changes.get("profile_id", row.profile_id),
        changes.get("inventory_id", row.inventory_id),
        changes.get("schedule", row.schedule),
    )
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    if "name" in changes and _name_taken(
        db_session, changes["name"], exclude_id=row.id
    ):
        raise HTTPException(
            status_code=409,
            detail=_("A job template named '%s' already exists") % changes["name"],
        )

    if "profile_id" in changes:
        row.profile_id = _require_profile(db_session, changes["profile_id"]).id
    if "inventory_id" in changes:
        row.inventory_id = _require_inventory(db_session, changes["inventory_id"]).id
    if "name" in changes:
        row.name = str(changes["name"]).strip()
    if "description" in changes:
        row.description = changes["description"]
    if "check_mode" in changes:
        row.check_mode = bool(changes["check_mode"])
    if "concurrency" in changes:
        row.concurrency = fleet.clamp_concurrency(changes["concurrency"])
    if "timeout_seconds" in changes:
        row.timeout_seconds = fleet.clamp_timeout(changes["timeout_seconds"])
    if "schedule" in changes:
        row.schedule = (changes["schedule"] or "").strip() or None
    if "enabled" in changes:
        row.enabled = bool(changes["enabled"])

    row.updated_by = current_user.userid
    row.updated_at = fleet.now_naive()
    db_session.commit()
    return TemplateResponse(**fleet.template_to_dict(row))


@router.delete("/config-management/job-templates/{template_id}")
async def delete_template(
    template_id: str,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Delete a job template.

    Job HISTORY survives: ``config_job.template_id`` is ON DELETE SET NULL and
    the template's name is denormalised onto every job it launched, so the
    record that a fleet-wide change happened stays readable afterwards.
    """
    _require_role(current_user, SecurityRoles.DELETE_SCRIPT)
    row = _load_template(db_session, template_id)
    name = row.name
    db_session.delete(row)
    db_session.commit()
    logger.info("Config job template deleted: %s", name)
    return {"success": True, "message": _("Job template deleted")}


@router.post(
    "/config-management/job-templates/{template_id}/launch", response_model=JobResponse
)
async def launch_template(
    template_id: str,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Launch a template now, dispatching its first wave before returning."""
    _require_role(current_user, SecurityRoles.RUN_SCRIPT)
    template = _load_template(db_session, template_id)

    profile = (
        db_session.query(models.ConfigProfile)
        .filter(models.ConfigProfile.id == template.profile_id)
        .first()
    )
    if profile is None or not profile.is_active:
        # Launching a profile somebody deliberately retired would undo a
        # decision rather than enforce one -- the same rule remediation
        # follows.
        raise HTTPException(
            status_code=400,
            detail=_("The profile this template runs is not active"),
        )

    inventory = (
        db_session.query(models.ConfigInventory)
        .filter(models.ConfigInventory.id == template.inventory_id)
        .first()
    )
    if inventory is None:
        raise HTTPException(status_code=404, detail=_("Inventory not found"))

    job = runner.create_job(
        db_session, template, profile, inventory, current_user.userid
    )
    template.last_launched_at = job.created_at
    # The first wave goes out before the response returns: a job that sat at
    # zero for up to a minute would read as a broken button.
    runner.advance_job(db_session, job)
    db_session.commit()

    logger.info(
        "Config fleet job %s launched from template '%s' against %d host(s)",
        job.id,
        template.name,
        job.total_targets,
    )
    return JobResponse(**fleet.job_to_dict(job))


# --- jobs --------------------------------------------------------------------


@router.get("/config-management/jobs", response_model=List[JobResponse])
async def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(DEFAULT_JOB_LIMIT, ge=1, le=MAX_JOB_LIMIT),
    db_session: Session = Depends(get_tenant_db),
):
    """Recent jobs, newest first."""
    query = db_session.query(models.ConfigJob)
    if status:
        query = query.filter(models.ConfigJob.status == status.strip().lower())
    rows = query.order_by(models.ConfigJob.created_at.desc()).limit(limit).all()
    return [JobResponse(**fleet.job_to_dict(row)) for row in rows]


@router.get("/config-management/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db_session: Session = Depends(get_tenant_db)):
    """One job."""
    return JobResponse(**fleet.job_to_dict(_load_job(db_session, job_id)))


@router.get(
    "/config-management/jobs/{job_id}/targets",
    response_model=List[JobTargetResponse],
)
async def list_job_targets(
    job_id: str,
    status: Optional[str] = None,
    limit: int = Query(DEFAULT_TARGET_LIMIT, ge=1, le=MAX_TARGET_LIMIT),
    offset: int = Query(0, ge=0),
    db_session: Session = Depends(get_tenant_db),
):
    """The hosts in a job, failures first.

    Ordered by status rather than by hostname because the question an operator
    opens this page with is "which ones went wrong". Alphabetical order buries
    twelve failures among four thousand successes.
    """
    job = _load_job(db_session, job_id)
    query = db_session.query(models.ConfigJobTarget).filter(
        models.ConfigJobTarget.job_id == job.id
    )
    if status:
        query = query.filter(models.ConfigJobTarget.status == status.strip().lower())

    rows = (
        query.order_by(
            # "failed" sorts before "pending"/"queued"/"skipped"/"succeeded"
            # alphabetically, which happens to be exactly the order wanted and
            # is pinned by a test so it stays deliberate rather than lucky.
            models.ConfigJobTarget.status.asc(),
            models.ConfigJobTarget.host_fqdn.asc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [JobTargetResponse(**fleet.target_to_dict(row)) for row in rows]


@router.post("/config-management/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: str,
    request: CancelRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Stop dispatching a job.

    Targets already in flight are LEFT ALONE -- the command is with the agent
    and the server cannot recall it, so claiming otherwise would be a status
    that lies. Their results still land and still close their targets, which
    is why a cancelled job's counts keep moving for a while.
    """
    _require_role(current_user, SecurityRoles.RUN_SCRIPT)
    job = _load_job(db_session, job_id)

    if fleet.job_is_terminal(job.status):
        raise HTTPException(status_code=400, detail=_("This job has already finished"))

    reason = (request.reason or "").strip() or _("Cancelled by an operator")
    skipped = runner.cancel_job(db_session, job, reason)
    db_session.commit()

    logger.info(
        "Config fleet job %s cancelled by %s; %d target(s) were never dispatched",
        job.id,
        current_user.userid,
        skipped,
    )
    return JobResponse(**fleet.job_to_dict(job))
