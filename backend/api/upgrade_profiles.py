"""
Scheduled update profiles API (Phase 8.2).

Five endpoints:

  GET    /api/upgrade-profiles            list
  POST   /api/upgrade-profiles            create
  GET    /api/upgrade-profiles/{id}       get one
  PUT    /api/upgrade-profiles/{id}       update
  DELETE /api/upgrade-profiles/{id}       delete
  POST   /api/upgrade-profiles/{id}/trigger    fire-now (manual)
  POST   /api/upgrade-profiles/tick            scan-all-due-now (driver hook)

The ``tick`` endpoint is the driver hook: an external scheduler (systemd
timer, cron, future APScheduler) calls it on a periodic schedule, and
this API selects every profile where ``next_run <= now AND enabled``,
recomputes ``next_run``, and returns the list of triggered profiles.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.services import upgrade_scheduler
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)
queue_ops = QueueOperations()


router = APIRouter(
    prefix="/api/upgrade-profiles",
    tags=["upgrade-profiles"],
    dependencies=[Depends(JWTBearer())],
)


class UpgradeProfileCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    cron: str = Field(default=models.upgrade_profiles.DEFAULT_CRON)
    enabled: bool = True
    security_only: bool = False
    package_managers: Optional[List[str]] = None
    staggered_window_min: int = Field(default=0, ge=0, le=720)  # 0..12h
    tag_id: Optional[str] = None


class UpgradeProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    cron: Optional[str] = None
    enabled: Optional[bool] = None
    security_only: Optional[bool] = None
    package_managers: Optional[List[str]] = None
    staggered_window_min: Optional[int] = Field(None, ge=0, le=720)
    tag_id: Optional[str] = None


class UpgradeProfileResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    cron: str
    enabled: bool
    security_only: bool
    package_managers: List[str] = []
    staggered_window_min: int
    tag_id: Optional[str] = None
    last_run: Optional[str] = None
    last_status: Optional[str] = None
    next_run: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _get_user(db: Session, current_user: str) -> models.User:
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_("User not found"))
    return user


def _parse_uuid_or_400(value: Optional[str], field: str) -> Optional[uuid.UUID]:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=_("Invalid UUID for %s: %s") % (field, value)
        ) from exc


def _validate_and_compute_next_run(cron: str) -> datetime:
    try:
        upgrade_scheduler.validate_cron(cron)
        return upgrade_scheduler.next_run_from_cron(cron, datetime.now(timezone.utc))
    except upgrade_scheduler.CronParseError as exc:
        raise HTTPException(
            status_code=400, detail=_("Invalid cron expression: %s") % str(exc)
        ) from exc


@router.get("", response_model=List[UpgradeProfileResponse])
async def list_profiles(db: Session = Depends(get_db)):
    rows = db.query(models.UpgradeProfile).order_by(models.UpgradeProfile.name).all()
    return [UpgradeProfileResponse(**r.to_dict()) for r in rows]


@router.post("", response_model=UpgradeProfileResponse)
async def create_profile(
    request: UpgradeProfileCreateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    user = _get_user(db, current_user)
    tag_uuid = _parse_uuid_or_400(request.tag_id, "tag_id")

    next_run = _validate_and_compute_next_run(request.cron)

    profile = models.UpgradeProfile(
        name=request.name,
        description=request.description,
        cron=request.cron,
        enabled=request.enabled,
        security_only=request.security_only,
        package_managers=(
            ",".join(request.package_managers) if request.package_managers else None
        ),
        staggered_window_min=request.staggered_window_min,
        tag_id=tag_uuid,
        next_run=next_run,
        created_by=user.id,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    AuditService.log(
        db=db,
        action_type=ActionType.CREATE,
        entity_type=EntityType.SETTING,
        entity_id=str(profile.id),
        entity_name=profile.name,
        description=_("Created upgrade profile '%s'") % profile.name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return UpgradeProfileResponse(**profile.to_dict())


@router.get("/{profile_id}", response_model=UpgradeProfileResponse)
async def get_profile(profile_id: str, db: Session = Depends(get_db)):
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    profile = (
        db.query(models.UpgradeProfile).filter(models.UpgradeProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_("Upgrade profile not found"))
    return UpgradeProfileResponse(**profile.to_dict())


@router.put("/{profile_id}", response_model=UpgradeProfileResponse)
async def update_profile(
    profile_id: str,
    request: UpgradeProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    user = _get_user(db, current_user)
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    profile = (
        db.query(models.UpgradeProfile).filter(models.UpgradeProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_("Upgrade profile not found"))

    if request.name is not None:
        profile.name = request.name
    if request.description is not None:
        profile.description = request.description
    if request.cron is not None and request.cron != profile.cron:
        profile.cron = request.cron
        profile.next_run = _validate_and_compute_next_run(request.cron)
    if request.enabled is not None:
        profile.enabled = request.enabled
    if request.security_only is not None:
        profile.security_only = request.security_only
    if request.package_managers is not None:
        profile.package_managers = (
            ",".join(request.package_managers) if request.package_managers else None
        )
    if request.staggered_window_min is not None:
        profile.staggered_window_min = request.staggered_window_min
    if request.tag_id is not None:
        profile.tag_id = (
            _parse_uuid_or_400(request.tag_id, "tag_id") if request.tag_id else None
        )

    db.commit()
    db.refresh(profile)
    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_id=str(profile.id),
        entity_name=profile.name,
        description=_("Updated upgrade profile '%s'") % profile.name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return UpgradeProfileResponse(**profile.to_dict())


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    user = _get_user(db, current_user)
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    profile = (
        db.query(models.UpgradeProfile).filter(models.UpgradeProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_("Upgrade profile not found"))
    name = profile.name
    db.delete(profile)
    db.commit()
    AuditService.log(
        db=db,
        action_type=ActionType.DELETE,
        entity_type=EntityType.SETTING,
        entity_id=str(pid),
        entity_name=name,
        description=_("Deleted upgrade profile '%s'") % name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return {"message": _("Upgrade profile deleted"), "id": str(pid)}


def _dispatch_profile_to_hosts(profile, target_host_ids, db: Session) -> int:
    """Enqueue an ``apply_updates`` command for each target host.

    Returns the count of messages queued.  Each host gets one message
    carrying the profile's flags so the agent can do the right thing
    (security-only filter, package-manager allowlist).  Staggered rollout
    is encoded as a per-message ``delay_seconds`` hint computed by
    spreading hosts evenly across the configured window.

    Failures on individual hosts are tolerated — we log + continue
    rather than aborting the whole tick, so one offline host can't
    block the rest of the fleet's update."""
    if not target_host_ids:
        return 0

    window_min = profile.staggered_window_min or 0
    n = len(target_host_ids)
    enqueued = 0
    for idx, host_id in enumerate(target_host_ids):
        # Spread evenly across the window (in seconds).  With window=0,
        # delay is 0 for all hosts → simultaneous launch.  Otherwise:
        # host i gets delay = (i * window_seconds / n).
        delay_seconds = (
            int((idx * window_min * 60) / n) if n > 0 and window_min > 0 else 0
        )

        package_managers = (
            profile.package_managers.split(",") if profile.package_managers else None
        )

        try:
            command_message = create_command_message(
                "apply_updates",
                {
                    "profile_id": str(profile.id),
                    "profile_name": profile.name,
                    "security_only": profile.security_only,
                    "package_managers": package_managers,
                    "delay_seconds": delay_seconds,
                },
            )
            queue_ops.enqueue_message(
                message_type="command",
                message_data=command_message,
                direction=QueueDirection.OUTBOUND,
                host_id=host_id,
                db=db,
            )
            enqueued += 1
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Failed to enqueue apply_updates for host %s (profile %s): %s",
                host_id,
                profile.id,
                exc,
            )
    return enqueued


@router.post("/{profile_id}/trigger")
async def trigger_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Fire a profile NOW.  Resolves the target host set, enqueues an
    ``apply_updates`` command for each (with the profile's flags +
    staggered-window delay), updates last_run / next_run, and returns
    the count of hosts actually dispatched to."""
    user = _get_user(db, current_user)
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    profile = (
        db.query(models.UpgradeProfile).filter(models.UpgradeProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_("Upgrade profile not found"))

    target_ids = upgrade_scheduler.selectors_for_profile(profile, db)
    enqueued = _dispatch_profile_to_hosts(profile, target_ids, db)
    profile.last_run = datetime.now(timezone.utc).replace(tzinfo=None)
    profile.last_status = "SUCCESS"
    profile.next_run = _validate_and_compute_next_run(profile.cron)
    db.commit()

    AuditService.log(
        db=db,
        action_type=ActionType.EXECUTE,
        entity_type=EntityType.SETTING,
        entity_id=str(profile.id),
        entity_name=profile.name,
        description=_("Triggered upgrade profile '%s' against %d host(s)")
        % (profile.name, len(target_ids)),
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
        details={
            "host_ids": [str(h) for h in target_ids],
            "security_only": profile.security_only,
            "staggered_window_min": profile.staggered_window_min,
        },
    )
    return {
        "profile_id": str(profile.id),
        "name": profile.name,
        "host_count": len(target_ids),
        "enqueued_count": enqueued,
        "host_ids": [str(h) for h in target_ids],
        "next_run": profile.next_run.isoformat() if profile.next_run else None,
    }


@router.post("/tick")
async def tick(db: Session = Depends(get_db)):
    """Driver hook for an external scheduler.  Selects every enabled
    profile where ``next_run <= now``, fires it (updates last_run /
    next_run / status), and returns the list of fired profiles.

    Idempotent within a single tick — running the same tick twice in
    quick succession will fire a profile only once because the FIRST
    invocation pushes ``next_run`` forward."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    due = (
        db.query(models.UpgradeProfile)
        .filter(
            models.UpgradeProfile.enabled.is_(True),
            models.UpgradeProfile.next_run.isnot(None),
            models.UpgradeProfile.next_run <= now,
        )
        .all()
    )
    fired = []
    for profile in due:
        try:
            target_ids = upgrade_scheduler.selectors_for_profile(profile, db)
            enqueued = _dispatch_profile_to_hosts(profile, target_ids, db)
            profile.last_run = now
            profile.last_status = "SUCCESS"
            profile.next_run = upgrade_scheduler.next_run_from_cron(
                profile.cron, datetime.now(timezone.utc)
            )
            fired.append(
                {
                    "profile_id": str(profile.id),
                    "name": profile.name,
                    "host_count": len(target_ids),
                    "enqueued_count": enqueued,
                }
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("tick: failed firing profile %s: %s", profile.id, exc)
            profile.last_run = now
            profile.last_status = "FAILURE"
    db.commit()
    return {"fired_count": len(fired), "fired": fired}
