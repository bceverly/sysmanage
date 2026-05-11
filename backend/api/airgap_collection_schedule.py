"""
Air-gap collection schedule API (Phase 11 B2).

CRUD + tick driver hook for cron-scheduled recurring collection runs.
The cron parsing is delegated to ``automation_engine.next_run_from_cron``
when that engine is loaded — same pattern Phase 11.4 used for vuln_engine
CVE-feed scheduling — to avoid a third copy of the cron parser.

Routes are gated on ``airgap_collector_engine`` being loaded (the role
we run on must actually be ``collector``).  The tick handler additionally
warns when ``automation_engine`` isn't loaded — schedules persist but
won't auto-fire until the license is fixed.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db
from backend.services.audit_service import (
    ActionType,
    AuditService,
    EntityType,
    Result,
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/v1/airgap/collector/schedules",
    tags=["airgap-collector-schedules"],
    dependencies=[Depends(JWTBearer())],
)


_ERR_NOT_FOUND = "Air-gap collection schedule not found"
_ERR_INVALID_SCHEDULE_UUID = "Invalid UUID for schedule_id: %s"


def _check_collector_module():
    engine = module_loader.get_module("airgap_collector_engine")
    if engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Air-gap collection schedules require a SysManage Professional+ "
                "license with the air-gap collector engine. Please upgrade to "
                "access this feature."
            ),
        )
    return engine


def _get_automation_engine_or_warn():
    """Return the automation_engine module if loaded; else None.

    Schedules stored without automation_engine remain valid — they just
    don't auto-fire.  Operators see a clear warning in the tick response.
    """
    return module_loader.get_module("automation_engine")


def _validate_cron_or_400(cron: str) -> None:
    automation = _get_automation_engine_or_warn()
    if automation is None:
        # Without the cron parser, accept any 5-field-shaped string and
        # defer real validation to when the engine becomes available.
        if len(cron.strip().split()) != 5:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Invalid cron expression: expected 5 fields (m h dom mon dow)"
                ),
            )
        return
    try:
        automation.validate_cron_expression(cron)
    except automation.CronParseError as exc:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid cron expression: %s") % str(exc),
        ) from exc


def _compute_next_run(cron: str) -> Optional[datetime]:
    automation = _get_automation_engine_or_warn()
    if automation is None:
        return None
    return automation.next_run_from_cron(cron, datetime.now(timezone.utc))


class ScheduleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    cron: str = Field(default="0 3 * * *")
    enabled: bool = True
    target_request: dict = Field(
        ...,
        description=(
            "Frozen request body to pass to "
            "engine.build_collection_run_plan on each tick"
        ),
    )


class ScheduleUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    cron: Optional[str] = None
    enabled: Optional[bool] = None
    target_request: Optional[dict] = None


class ScheduleResponse(BaseModel):
    id: str
    name: str
    cron: str
    enabled: bool
    target_request_json: str
    last_run: Optional[str] = None
    last_status: Optional[str] = None
    last_run_id: Optional[str] = None
    next_run: Optional[str] = None


def _get_user(db: Session, current_user: str) -> models.User:
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_("User not found"))
    return user


@router.get("", response_model=List[ScheduleResponse])
async def list_schedules(db: Session = Depends(get_db)):
    _check_collector_module()
    rows = (
        db.query(models.AirgapCollectionSchedule)
        .order_by(models.AirgapCollectionSchedule.name)
        .all()
    )
    return [ScheduleResponse(**r.to_dict()) for r in rows]


@router.post("", response_model=ScheduleResponse)
async def create_schedule(
    request: ScheduleCreateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    engine = _check_collector_module()
    user = _get_user(db, current_user)
    _validate_cron_or_400(request.cron)
    # Validate the target_request shape against the engine before
    # persisting — fail fast with a clear 400 instead of waiting for
    # the first tick to discover the schedule is malformed.
    try:
        engine.validate_collection_request(request.target_request)
    except engine.CollectorConfigError as exc:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid target_request: %s") % str(exc),
        ) from exc
    schedule = models.AirgapCollectionSchedule(
        name=request.name,
        cron=request.cron,
        enabled=request.enabled,
        target_request_json=json.dumps(request.target_request),
        next_run=_compute_next_run(request.cron),
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    AuditService.log(
        db=db,
        action_type=ActionType.CREATE,
        entity_type=EntityType.SETTING,
        entity_id=str(schedule.id),
        entity_name=schedule.name,
        description=_("Created air-gap collection schedule '%s'") % schedule.name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return ScheduleResponse(**schedule.to_dict())


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(schedule_id: str, db: Session = Depends(get_db)):
    _check_collector_module()
    try:
        sid = uuid.UUID(schedule_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_(_ERR_INVALID_SCHEDULE_UUID) % schedule_id,
        ) from exc
    schedule = (
        db.query(models.AirgapCollectionSchedule)
        .filter(models.AirgapCollectionSchedule.id == sid)
        .first()
    )
    if not schedule:
        raise HTTPException(status_code=404, detail=_(_ERR_NOT_FOUND))
    return ScheduleResponse(**schedule.to_dict())


@router.put("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    request: ScheduleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    engine = _check_collector_module()
    user = _get_user(db, current_user)
    try:
        sid = uuid.UUID(schedule_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_(_ERR_INVALID_SCHEDULE_UUID) % schedule_id,
        ) from exc
    schedule = (
        db.query(models.AirgapCollectionSchedule)
        .filter(models.AirgapCollectionSchedule.id == sid)
        .first()
    )
    if not schedule:
        raise HTTPException(status_code=404, detail=_(_ERR_NOT_FOUND))
    if request.name is not None:
        schedule.name = request.name
    if request.cron is not None and request.cron != schedule.cron:
        _validate_cron_or_400(request.cron)
        schedule.cron = request.cron
        schedule.next_run = _compute_next_run(request.cron)
    if request.enabled is not None:
        schedule.enabled = request.enabled
    if request.target_request is not None:
        try:
            engine.validate_collection_request(request.target_request)
        except engine.CollectorConfigError as exc:
            raise HTTPException(
                status_code=400,
                detail=_("Invalid target_request: %s") % str(exc),
            ) from exc
        schedule.target_request_json = json.dumps(request.target_request)
    db.commit()
    db.refresh(schedule)
    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_id=str(schedule.id),
        entity_name=schedule.name,
        description=_("Updated air-gap collection schedule '%s'") % schedule.name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return ScheduleResponse(**schedule.to_dict())


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    _check_collector_module()
    user = _get_user(db, current_user)
    try:
        sid = uuid.UUID(schedule_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_(_ERR_INVALID_SCHEDULE_UUID) % schedule_id,
        ) from exc
    schedule = (
        db.query(models.AirgapCollectionSchedule)
        .filter(models.AirgapCollectionSchedule.id == sid)
        .first()
    )
    if not schedule:
        raise HTTPException(status_code=404, detail=_(_ERR_NOT_FOUND))
    name = schedule.name
    db.delete(schedule)
    db.commit()
    AuditService.log(
        db=db,
        action_type=ActionType.DELETE,
        entity_type=EntityType.SETTING,
        entity_id=str(sid),
        entity_name=name,
        description=_("Deleted air-gap collection schedule '%s'") % name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return {"message": _("Air-gap collection schedule deleted"), "id": str(sid)}


@router.post("/tick")
async def tick(db: Session = Depends(get_db)):
    """Driver hook for an external scheduler.

    Selects every enabled schedule whose ``next_run <= now``, fires it
    (creates an ``AirgapCollectionRun`` row that the operator's
    background runner picks up), updates last_run / next_run, and
    returns the list of fired schedules.
    """
    _check_collector_module()
    automation = _get_automation_engine_or_warn()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    due = (
        db.query(models.AirgapCollectionSchedule)
        .filter(
            models.AirgapCollectionSchedule.enabled.is_(True),
            models.AirgapCollectionSchedule.next_run.isnot(None),
            models.AirgapCollectionSchedule.next_run <= now,
        )
        .all()
    )
    fired = []
    for schedule in due:
        try:
            target_request = json.loads(schedule.target_request_json)
        except (ValueError, TypeError) as exc:
            schedule.last_run = now
            schedule.last_status = "FAILURE"
            logger.exception(
                "tick: schedule %s has malformed target_request_json: %s",
                schedule.id,
                exc,
            )
            continue
        run = models.AirgapCollectionRun(
            iso_label=target_request.get("iso_label", schedule.name),
            media_size_bytes=target_request.get("media_size_bytes", 4_700_000_000),
            include_cve=bool(target_request.get("include_cve", True)),
            include_compliance=bool(target_request.get("include_compliance", True)),
            status="QUEUED",
        )
        db.add(run)
        db.flush()
        schedule.last_run = now
        schedule.last_status = "QUEUED"
        schedule.last_run_id = run.id
        if automation is not None:
            schedule.next_run = automation.next_run_from_cron(
                schedule.cron, datetime.now(timezone.utc)
            )
        fired.append(
            {
                "schedule_id": str(schedule.id),
                "schedule_name": schedule.name,
                "run_id": str(run.id),
            }
        )
    db.commit()
    response = {"fired_count": len(fired), "fired": fired}
    if automation is None:
        response["warning"] = _(
            "automation_engine not loaded; next_run timestamps not advanced. "
            "Schedules will fire only on the current tick window until the "
            "Pro+ license includes automation_engine."
        )
    return response
