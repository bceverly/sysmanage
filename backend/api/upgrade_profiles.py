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

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db, iter_host_databases
from backend.services import upgrade_scheduler
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)
queue_ops = QueueOperations()


# Phase 13.2.1: prefix moved to registration (_include_versioned) so this router
# serves natively under /api/v1/upgrade-profiles with a deprecated /api alias.
router = APIRouter(
    tags=["upgrade-profiles"],
    dependencies=[Depends(JWTBearer())],
)


# Reused 404 detail string — extracted so the wording can't drift
# between handlers and so SonarQube's duplication scanner is happy.
_ERR_UPGRADE_PROFILE_NOT_FOUND = "Upgrade profile not found"


def _check_automation_module():
    """Refuse the request when the Pro+ automation_engine module isn't loaded.

    Phase 10.6 moved upgrade-profile cron evaluation and per-host dispatch
    into the engine; without it loaded, the OSS routes have no business
    logic to execute, so they short-circuit with a 402.  Mirrors the
    Phase 2.3 secrets_engine pattern (``backend/api/secrets/crud.py``).
    """
    engine = module_loader.get_module("automation_engine")
    if engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Scheduled upgrade profiles require a SysManage Professional+ license. "
                "Please upgrade to access this feature."
            ),
        )
    return engine


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
    """Validate ``cron`` and compute its next-run datetime via the
    ``automation_engine`` Pro+ module (Phase 10.6 migration).

    The OSS ``upgrade_scheduler`` module is kept as a no-op shell —
    every route here is gated by ``_check_automation_module()`` first,
    so the engine is guaranteed to be loaded by the time we reach this
    helper.
    """
    engine = _check_automation_module()
    try:
        engine.validate_cron_expression(cron)
        return engine.next_run_from_cron(cron, datetime.now(timezone.utc))
    except engine.CronParseError as exc:
        raise HTTPException(
            status_code=400, detail=_("Invalid cron expression: %s") % str(exc)
        ) from exc


@router.get("", response_model=List[UpgradeProfileResponse])
async def list_profiles(db: Session = Depends(get_tenant_db)):
    _check_automation_module()
    rows = db.query(models.UpgradeProfile).order_by(models.UpgradeProfile.name).all()
    return [UpgradeProfileResponse(**r.to_dict()) for r in rows]


@router.post("", response_model=UpgradeProfileResponse)
async def create_profile(
    request: UpgradeProfileCreateRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    # Authorization/identity is resolved on the MAIN engine by
    # require_authenticated_user (user data is server-global); the profile data
    # and its audit trail route to the tenant engine via ``db``.
    _check_automation_module()
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
        created_by=current_user.id,
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
        user_id=current_user.id,
        username=current_user.userid,
        result=Result.SUCCESS,
    )
    return UpgradeProfileResponse(**profile.to_dict())


@router.get("/{profile_id}", response_model=UpgradeProfileResponse)
async def get_profile(profile_id: str, db: Session = Depends(get_tenant_db)):
    _check_automation_module()
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    profile = (
        db.query(models.UpgradeProfile).filter(models.UpgradeProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_(_ERR_UPGRADE_PROFILE_NOT_FOUND))
    return UpgradeProfileResponse(**profile.to_dict())


@router.put("/{profile_id}", response_model=UpgradeProfileResponse)
async def update_profile(
    profile_id: str,
    request: UpgradeProfileUpdateRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    # Identity resolved on the MAIN engine; profile + audit data routes to the
    # tenant engine via ``db``.
    _check_automation_module()
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    profile = (
        db.query(models.UpgradeProfile).filter(models.UpgradeProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_(_ERR_UPGRADE_PROFILE_NOT_FOUND))

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
        user_id=current_user.id,
        username=current_user.userid,
        result=Result.SUCCESS,
    )
    return UpgradeProfileResponse(**profile.to_dict())


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    # Identity resolved on the MAIN engine; profile + audit data routes to the
    # tenant engine via ``db``.
    _check_automation_module()
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    profile = (
        db.query(models.UpgradeProfile).filter(models.UpgradeProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_(_ERR_UPGRADE_PROFILE_NOT_FOUND))
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
        user_id=current_user.id,
        username=current_user.userid,
        result=Result.SUCCESS,
    )
    return {"message": _("Upgrade profile deleted"), "id": str(pid)}


def _dispatch_profile_to_hosts(profile, target_host_ids, db: Session) -> int:
    """Enqueue an ``apply_updates`` command for each target host.

    Phase 10.6: the per-host message-building (staggered window math,
    flag forwarding, command shape) lives in
    ``automation_engine.build_upgrade_profile_dispatch``.  This OSS
    helper is just a thin enqueue loop — caller is already
    license-gated by ``_check_automation_module`` so the engine is
    guaranteed to be loaded.

    Returns the count of messages queued.  Failures on individual hosts
    are tolerated — log + continue, so one offline host can't block
    the rest of the fleet's update.
    """
    if not target_host_ids:
        return 0

    engine = _check_automation_module()
    profile_dict = {
        "id": profile.id,
        "name": profile.name,
        "security_only": profile.security_only,
        "package_managers": profile.package_managers,
        "staggered_window_min": profile.staggered_window_min,
    }
    dispatches = engine.build_upgrade_profile_dispatch(
        profile_dict, list(target_host_ids)
    )

    enqueued = 0
    for entry in dispatches:
        try:
            command_message = create_command_message(
                entry["command_type"], entry["parameters"]
            )
            queue_ops.enqueue_message(
                message_type="command",
                message_data=command_message,
                direction=QueueDirection.OUTBOUND,
                host_id=entry["host_id"],
                db=db,
            )
            enqueued += 1
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Failed to enqueue apply_updates for host %s (profile %s): %s",
                entry["host_id"],
                profile.id,
                exc,
            )
    return enqueued


@router.post("/{profile_id}/trigger")
async def trigger_profile(
    profile_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Fire a profile NOW.  Resolves the target host set, enqueues an
    ``apply_updates`` command for each (with the profile's flags +
    staggered-window delay), updates last_run / next_run, and returns
    the count of hosts actually dispatched to."""
    # Identity resolved on the MAIN engine; profile + audit data routes to the
    # tenant engine via ``db``.
    _check_automation_module()
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    profile = (
        db.query(models.UpgradeProfile).filter(models.UpgradeProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_(_ERR_UPGRADE_PROFILE_NOT_FOUND))

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
        user_id=current_user.id,
        username=current_user.userid,
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


def _tick_profiles_one_db(session, now):
    """Run the upgrade-profile tick against a SINGLE host database.

    Returns the list of fired profiles for this database.  Selecting due
    profiles, resolving each profile's target hosts, and enqueuing the
    ``apply_updates`` commands all run on ``session`` — so a tenant's profiles,
    its hosts, and its outbound queue stay together in that tenant's DB.
    Commits ``session`` on the way out.
    """
    due = (
        session.query(models.UpgradeProfile)
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
            target_ids = upgrade_scheduler.selectors_for_profile(profile, session)
            enqueued = _dispatch_profile_to_hosts(profile, target_ids, session)
            profile.last_run = now
            profile.last_status = "SUCCESS"
            # Phase 10.6: cron re-compute goes through automation_engine
            # (matches ``trigger_profile`` and the docstring above; the OSS
            # ``upgrade_scheduler`` parser is preserved as a tested utility
            # but is not on the runtime path once the engine is loaded).
            profile.next_run = _validate_and_compute_next_run(profile.cron)
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
    session.commit()
    return fired


@router.post("/tick")
async def tick():
    """Driver hook for an external scheduler.  Selects every enabled
    profile where ``next_run <= now``, fires it (updates last_run /
    next_run / status), and returns the list of fired profiles.

    Phase 10.6: gated on the ``automation_engine`` Pro+ module — the
    cron-recompute and per-host dispatch live there now.

    Phase 13.1: no logged-in user / active-tenant context here (an external
    scheduler drives this), so — like the heartbeat sweep — it fans out across
    EVERY host database via ``iter_host_databases()`` (bootstrap + each
    provisioned tenant DB).  A tenant's profiles and hosts live in its tenant
    database, so the bootstrap pass alone would never see them.  One bad tenant
    DB is logged and skipped without stalling the rest of the sweep.

    Idempotent within a single tick — running the same tick twice in
    quick succession will fire a profile only once because the FIRST
    invocation pushes ``next_run`` forward."""
    _check_automation_module()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fired = []
    for label, _tenant_id, session in iter_host_databases():
        try:
            fired.extend(_tick_profiles_one_db(session, now))
        except Exception:  # pylint: disable=broad-exception-caught
            session.rollback()
            logger.exception("tick: failed for database %s", label)
        finally:
            session.close()
    return {"fired_count": len(fired), "fired": fired}
