# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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
from backend.i18n import N_, _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import auto_update_rollout, auto_update_runner
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

logger = logging.getLogger(__name__)


# Phase 13.2.1: prefix moved to registration (_include_versioned) so this router
# serves natively under /api/v1/upgrade-profiles with a deprecated /api alias.
router = APIRouter(
    tags=["upgrade-profiles"],
    dependencies=[Depends(JWTBearer())],
)


# Reused 404 detail string -- extracted so the wording can't drift
# between handlers and so SonarQube's duplication scanner is happy.
_ERR_UPGRADE_PROFILE_NOT_FOUND = N_("Upgrade profile not found")


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


class RolloutStageRequest(BaseModel):
    """One fleet of a rollout (26.4): the hosts carrying ``tag_id``."""

    name: str = Field(..., min_length=1, max_length=120)
    tag_id: str
    soak_hours: float = Field(default=0, ge=0, le=720)


class UpgradeProfileCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    cron: str = Field(default=models.upgrade_profiles.DEFAULT_CRON)
    enabled: bool = True
    security_only: bool = False
    package_managers: Optional[List[str]] = None
    staggered_window_min: int = Field(default=0, ge=0, le=720)  # 0..12h
    tag_id: Optional[str] = None
    # 26.1 automatic application (Enterprise)
    auto_apply: bool = False
    reboot_mode: str = Field(default="never", pattern="^(never|when_needed|in_window)$")
    excluded_packages: Optional[str] = Field(default=None, max_length=4000)
    require_backup_hours: Optional[int] = Field(default=None, ge=1, le=720)
    host_ids: Optional[List[str]] = None
    # 26.3 waiting periods (Enterprise)
    wait_days_regular: int = Field(default=0, ge=0, le=365)
    wait_days_critical: int = Field(default=0, ge=0, le=365)
    critical_source: str = Field(
        default="either", pattern="^(vulnerability|advisory|either)$"
    )
    # 26.4 fleet-by-fleet rollout (Enterprise)
    rollout_enabled: bool = False
    rollout_max_failure_pct: int = Field(default=0, ge=0, le=100)
    rollout_stages: Optional[List[RolloutStageRequest]] = Field(
        default=None, max_length=20
    )


class UpgradeProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    cron: Optional[str] = None
    enabled: Optional[bool] = None
    security_only: Optional[bool] = None
    package_managers: Optional[List[str]] = None
    staggered_window_min: Optional[int] = Field(None, ge=0, le=720)
    tag_id: Optional[str] = None
    auto_apply: Optional[bool] = None
    reboot_mode: Optional[str] = Field(None, pattern="^(never|when_needed|in_window)$")
    excluded_packages: Optional[str] = Field(None, max_length=4000)
    require_backup_hours: Optional[int] = Field(None, ge=0, le=720)  # 0 = off
    host_ids: Optional[List[str]] = None
    wait_days_regular: Optional[int] = Field(None, ge=0, le=365)
    wait_days_critical: Optional[int] = Field(None, ge=0, le=365)
    critical_source: Optional[str] = Field(
        None, pattern="^(vulnerability|advisory|either)$"
    )
    rollout_enabled: Optional[bool] = None
    rollout_max_failure_pct: Optional[int] = Field(None, ge=0, le=100)
    rollout_stages: Optional[List[RolloutStageRequest]] = Field(None, max_length=20)


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
    auto_apply: bool = False
    reboot_mode: str = "never"
    excluded_packages: str = ""
    require_backup_hours: Optional[int] = None
    held: bool = False
    hold_reason: Optional[str] = None
    hold_by: Optional[str] = None
    hold_at: Optional[str] = None
    host_ids: List[str] = []
    wait_days_regular: int = 0
    wait_days_critical: int = 0
    critical_source: str = "either"
    rollout_enabled: bool = False
    rollout_max_failure_pct: int = 0
    rollout_stages: List[dict] = []


def _parse_uuid_or_400(value: Optional[str], field: str) -> Optional[uuid.UUID]:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid UUID for %(field)s: %(value)s")
            % {"field": field, "value": value},
        ) from exc


def _validate_and_compute_next_run(cron: str) -> datetime:
    """Validate ``cron`` and compute its next-run datetime via the
    ``automation_engine`` Pro+ module (Phase 10.6 migration).

    The OSS ``upgrade_scheduler`` module is kept as a no-op shell --
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


def _response(profile, db: Session) -> UpgradeProfileResponse:
    hosts = auto_update_runner.profile_host_ids(db, [profile.id])
    stages = [s.to_dict() for s in auto_update_rollout.stage_rows(db, profile.id)]
    return UpgradeProfileResponse(
        **profile.to_dict(), host_ids=hosts.get(str(profile.id), []),
        rollout_stages=stages,
    )  # fmt: skip


def _require_apply_role(user) -> None:
    """Automatic application changes hosts unattended: the same role as
    applying an update by hand (26.1)."""
    if not user.has_role(SecurityRoles.APPLY_SOFTWARE_UPDATE):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: APPLY_SOFTWARE_UPDATE role required"),
        )


def _audit_details(request) -> dict:
    """What changed, for the audit log: every field the request set."""
    return {k: v for k, v in request.model_dump().items() if v is not None}


_AUTOMATIC_FIELDS = ("auto_apply", "reboot_mode", "excluded_packages",
                     "require_backup_hours", "host_ids", "wait_days_regular",
                     "wait_days_critical", "critical_source", "rollout_enabled",
                     "rollout_max_failure_pct", "rollout_stages")  # fmt: skip
_SIMPLE_AUTOMATIC = ("auto_apply", "reboot_mode", "wait_days_regular",
                     "wait_days_critical", "critical_source", "rollout_enabled",
                     "rollout_max_failure_pct")  # fmt: skip


def _apply_automatic_fields(db: Session, profile, request, user) -> None:
    touches = any(getattr(request, f) is not None for f in _AUTOMATIC_FIELDS)
    if touches and (request.auto_apply or profile.auto_apply):
        _require_apply_role(user)
    for field in _SIMPLE_AUTOMATIC:
        if getattr(request, field) is not None:
            setattr(profile, field, getattr(request, field))
    if request.excluded_packages is not None:
        profile.excluded_packages = request.excluded_packages or None
    if request.require_backup_hours is not None:
        profile.require_backup_hours = request.require_backup_hours or None
    _set_hosts(db, profile, request.host_ids)
    _set_stages(db, profile, request.rollout_stages)


def _set_stages(db: Session, profile, stages) -> None:
    """Replace the policy's fleets (26.4).  Each needs its own tag; a rollout
    needs at least one fleet."""
    if stages is not None:
        tags = [_parse_uuid_or_400(s.tag_id, "rollout_stages.tag_id") for s in stages]
        if len(set(tags)) != len(tags):
            raise HTTPException(
                status_code=400, detail=_("Each fleet of a rollout needs its own tag")
            )
        db.query(models.UpgradeProfileRolloutStage).filter(
            models.UpgradeProfileRolloutStage.profile_id == profile.id
        ).delete()
        for position, (stage, tag) in enumerate(zip(stages, tags)):
            db.add(
                models.UpgradeProfileRolloutStage(
                    profile_id=profile.id,
                    position=position,
                    name=stage.name.strip(),
                    tag_id=tag,
                    soak_minutes=int(round(stage.soak_hours * 60)),
                )
            )
        db.flush()
    if profile.rollout_enabled and not auto_update_rollout.stage_rows(db, profile.id):
        raise HTTPException(
            status_code=400, detail=_("A rollout needs at least one fleet")
        )


def _set_hosts(db: Session, profile, host_ids: Optional[List[str]]) -> None:
    if host_ids is None:
        return
    wanted = {_parse_uuid_or_400(h, "host_ids") for h in host_ids}
    db.query(models.UpgradeProfileHost).filter(
        models.UpgradeProfileHost.profile_id == profile.id
    ).delete()
    for host_id in sorted(wanted, key=str):
        db.add(models.UpgradeProfileHost(profile_id=profile.id, host_id=host_id))


@router.get("", response_model=List[UpgradeProfileResponse])
async def list_profiles(db: Session = Depends(get_tenant_db)):
    _check_automation_module()
    rows = db.query(models.UpgradeProfile).order_by(models.UpgradeProfile.name).all()
    return [_response(r, db) for r in rows]


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
    if request.auto_apply:
        _require_apply_role(current_user)
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
        auto_apply=request.auto_apply,
        reboot_mode=request.reboot_mode,
        excluded_packages=request.excluded_packages or None,
        require_backup_hours=request.require_backup_hours,
        wait_days_regular=request.wait_days_regular,
        wait_days_critical=request.wait_days_critical,
        critical_source=request.critical_source,
        rollout_enabled=request.rollout_enabled,
        rollout_max_failure_pct=request.rollout_max_failure_pct,
    )
    db.add(profile)
    db.flush()
    _set_hosts(db, profile, request.host_ids)
    _set_stages(db, profile, request.rollout_stages)
    db.commit()
    db.refresh(profile)
    AuditService.log(
        db=db,
        action_type=ActionType.CREATE,
        entity_type=EntityType.UPDATE_POLICY,
        entity_id=str(profile.id),
        entity_name=profile.name,
        description=_("Created upgrade profile '%s'") % profile.name,
        user_id=current_user.id,
        username=current_user.userid,
        result=Result.SUCCESS,
        details=_audit_details(request),
    )
    return _response(profile, db)


@router.get("/{profile_id}", response_model=UpgradeProfileResponse)
async def get_profile(profile_id: str, db: Session = Depends(get_tenant_db)):
    _check_automation_module()
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    profile = (
        db.query(models.UpgradeProfile).filter(models.UpgradeProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_(_ERR_UPGRADE_PROFILE_NOT_FOUND))
    return _response(profile, db)


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
    _apply_automatic_fields(db, profile, request, current_user)

    db.commit()
    db.refresh(profile)
    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.UPDATE_POLICY,
        entity_id=str(profile.id),
        entity_name=profile.name,
        description=_("Updated upgrade profile '%s'") % profile.name,
        user_id=current_user.id,
        username=current_user.userid,
        result=Result.SUCCESS,
        details=_audit_details(request),
    )
    return _response(profile, db)


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
        entity_type=EntityType.UPDATE_POLICY,
        entity_id=str(pid),
        entity_name=name,
        description=_("Deleted upgrade profile '%s'") % name,
        user_id=current_user.id,
        username=current_user.userid,
        result=Result.SUCCESS,
    )
    return {"message": _("Upgrade profile deleted"), "id": str(pid)}


@router.post("/{profile_id}/trigger")
async def trigger_profile(
    profile_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Run a profile NOW on every host it covers (26.1: through the same
    planner as the schedule -- the host's eligible pending updates, named in
    the command, staggered).  Before 26.1 this queued ``apply_updates`` with
    no package names, which every agent refuses."""
    engine = _check_automation_module()
    _require_apply_role(current_user)
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    profile = (
        db.query(models.UpgradeProfile).filter(models.UpgradeProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_(_ERR_UPGRADE_PROFILE_NOT_FOUND))

    if auto_update_rollout.enabled(engine, profile) and (
        auto_update_rollout.open_rollout(db, profile.id) is not None
    ):
        raise HTTPException(
            status_code=409,
            detail=_("A rollout of this policy is still running or halted"),
        )
    now = auto_update_runner.now_naive()
    summary = auto_update_runner.fire_profile(
        db, engine, profile, now, triggered_by=current_user.userid
    )
    profile.last_run = now
    profile.last_status = "SUCCESS"
    db.commit()

    AuditService.log(
        db=db,
        action_type=ActionType.EXECUTE,
        entity_type=EntityType.UPDATE_POLICY,
        entity_id=str(profile.id),
        entity_name=profile.name,
        description=_("Ran upgrade profile '%s' now") % profile.name,
        user_id=current_user.id,
        username=current_user.userid,
        result=Result.SUCCESS,
        details=summary,
    )
    return {
        "profile_id": str(profile.id),
        "name": profile.name,
        **summary,
        "next_run": profile.next_run.isoformat() if profile.next_run else None,
    }


@router.post("/tick")
async def tick():
    """One pass of the automatic update driver, now (26.1: the server runs it
    every minute on its own; this endpoint is for tests and operators)."""
    _check_automation_module()
    return auto_update_runner.run_one_tick()
