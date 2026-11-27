# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Automatic updates: holds, opt-outs and runs (ROADMAP 26.1, Enterprise).

  GET  /auto-updates/settings                 holds, retry hours, counts
  PUT  /auto-updates/hold-all                 hold (or release) every policy
  PUT  /auto-updates/settings                 retry hours, reboot timeout
  PUT  /auto-updates/profiles/{id}/hold       hold (or release) one policy
  PUT  /auto-updates/hosts/{id}/opt-out       never (or again) patch a host
  GET  /auto-updates/hosts/{id}               a host's policy and its runs
  GET  /auto-updates/runs                     runs, newest first (filters)
  POST /auto-updates/runs/{id}/acknowledge    "someone looked": retry now

Rollouts (26.4) are in ``auto_update_rollouts``.

Every change is audited.  Gated like upgrade profiles on the Enterprise
``automation_engine`` (402 without it).
"""

import uuid
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.upgrade_profiles import (
    _check_automation_module,
    _parse_uuid_or_400,
    _require_apply_role,
)
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.services import auto_update_runner as runner
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.services.maintenance_window_service import next_window_for_host

router = APIRouter(tags=["auto-updates"], dependencies=[Depends(JWTBearer())])

_PROBLEMS = ("failed", "partial", "timed_out")


class HoldRequest(BaseModel):
    hold: bool
    reason: Optional[str] = Field(default=None, max_length=1000)


class OptOutRequest(BaseModel):
    opt_out: bool
    reason: Optional[str] = Field(default=None, max_length=1000)


class SettingsRequest(BaseModel):
    retry_after_hours: Optional[int] = Field(default=None, ge=1, le=720)
    reboot_timeout_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    critical_threshold: Optional[str] = Field(default=None, pattern="^(critical|high)$")
    # 27.8: after a run, remove old kernels and unneeded packages (apply),
    # only plan it (report), or nothing (off).
    cleanup_mode: Optional[str] = Field(default=None, pattern="^(apply|report|off)$")


def _reason_or_400(request) -> Optional[str]:
    reason = (request.reason or "").strip()
    if getattr(request, "hold", False) or getattr(request, "opt_out", False):
        if not reason:
            raise HTTPException(status_code=400, detail=_("A reason is required"))
    return reason or None


def _audit(db, user, description, entity_type, entity_id, name, details=None):
    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        entity_name=name,
        description=description,
        user_id=user.id,
        username=user.userid,
        result=Result.SUCCESS,
        details=details,
    )


def _counts(db) -> dict:
    since = runner.now_naive() - timedelta(days=7)
    runs = models.AutoUpdateRun
    return {
        "failed_recent": db.query(runs)
        .filter(
            runs.status.in_(_PROBLEMS),
            runs.queued_at >= since,
            runs.acknowledged_at.is_(None),
        )
        .count(),
        "queued": db.query(runs).filter(runs.status == "queued").count(),
        "waiting": db.query(runs).filter(runs.status == "waiting").count(),
        "reboot_not_back": db.query(runs)
        .filter(runs.reboot_status == "not_back", runs.acknowledged_at.is_(None))
        .count(),
        "opted_out_hosts": db.query(models.Host)
        .filter(models.Host.auto_update_opt_out.is_(True))
        .count(),
        # 26.5: hosts whose automatic reboot waits for its window, and
        # rollouts in progress or halted at a fleet's health gate (26.4).
        "reboot_waiting": db.query(runs)
        .filter(runs.reboot_status == "next_window")
        .count(),
        "rollouts_running": db.query(models.AutoUpdateRollout)
        .filter(models.AutoUpdateRollout.status == "running")
        .count(),
        "rollouts_halted": db.query(models.AutoUpdateRollout)
        .filter(models.AutoUpdateRollout.status == "halted")
        .count(),
    }


@router.get("/settings")
def get_settings(db: Session = Depends(get_tenant_db)):
    _check_automation_module()
    row = runner.settings_row(db)
    db.commit()
    return {**row.to_dict(), "counts": _counts(db)}


@router.put("/hold-all")
def hold_all(
    request: HoldRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Stop (or restart) every automatic run at once."""
    _check_automation_module()
    _require_apply_role(current_user)
    reason = _reason_or_400(request)
    row = runner.settings_row(db)
    row.hold_all = request.hold
    row.hold_reason = reason if request.hold else None
    row.hold_by = current_user.userid if request.hold else None
    row.hold_at = runner.now_naive() if request.hold else None
    row.updated_at = runner.now_naive()
    db.commit()
    _audit(
        db,
        current_user,
        (
            _("Held every automatic update policy: %s") % reason
            if request.hold
            else _("Released the hold on every automatic update policy")
        ),
        EntityType.UPDATE_POLICY,
        row.id,
        "auto_update_settings",
    )
    return row.to_dict()


@router.put("/settings")
def put_settings(
    request: SettingsRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    _check_automation_module()
    _require_apply_role(current_user)
    row = runner.settings_row(db)
    if request.retry_after_hours is not None:
        row.retry_after_hours = request.retry_after_hours
    if request.reboot_timeout_minutes is not None:
        row.reboot_timeout_minutes = request.reboot_timeout_minutes
    if request.critical_threshold is not None:
        row.critical_threshold = request.critical_threshold
    if request.cleanup_mode is not None:
        row.cleanup_mode = request.cleanup_mode
    row.updated_at = runner.now_naive()
    db.commit()
    _audit(
        db,
        current_user,
        _("Changed the automatic update settings"),
        EntityType.UPDATE_POLICY,
        row.id,
        "auto_update_settings",
        details=request.model_dump(exclude_none=True),
    )
    return row.to_dict()


@router.put("/profiles/{profile_id}/hold")
def hold_profile(
    profile_id: str,
    request: HoldRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    _check_automation_module()
    _require_apply_role(current_user)
    reason = _reason_or_400(request)
    profile = db.get(
        models.UpgradeProfile, _parse_uuid_or_400(profile_id, "profile_id")
    )
    if profile is None:
        raise HTTPException(status_code=404, detail=_("Upgrade profile not found"))
    profile.held = request.hold
    profile.hold_reason = reason if request.hold else None
    profile.hold_by = current_user.userid if request.hold else None
    profile.hold_at = runner.now_naive() if request.hold else None
    db.commit()
    _audit(
        db,
        current_user,
        (
            _("Held automatic update policy '%(policy)s': %(reason)s")
            % {"policy": profile.name, "reason": reason}
            if request.hold
            else _("Released the hold on automatic update policy '%s'") % profile.name
        ),
        EntityType.UPDATE_POLICY,
        profile.id,
        profile.name,
    )
    return profile.to_dict()


@router.put("/hosts/{host_id}/opt-out")
def opt_out(
    host_id: str,
    request: OptOutRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """A host that is never patched unattended, whatever policy covers it."""
    _check_automation_module()
    _require_apply_role(current_user)
    reason = _reason_or_400(request)
    host = db.get(models.Host, _parse_uuid_or_400(host_id, "host_id"))
    if host is None:
        raise HTTPException(status_code=404, detail=_("Host not found"))
    host.auto_update_opt_out = request.opt_out
    host.auto_update_opt_out_reason = reason if request.opt_out else None
    db.commit()
    _audit(
        db,
        current_user,
        (
            _("%(host)s will never be updated automatically: %(reason)s")
            % {"host": host.fqdn, "reason": reason}
            if request.opt_out
            else _("%s may be updated automatically again") % host.fqdn
        ),
        EntityType.HOST,
        host.id,
        host.fqdn,
    )
    return {
        "host_id": str(host.id),
        "opt_out": host.auto_update_opt_out,
        "reason": host.auto_update_opt_out_reason,
    }


def _pending(db, engine, host, profile) -> Optional[dict]:
    """Each pending update under the host's policy: applied on the next
    run, left out and why, or waiting until when (26.3: shown, not
    guessed).  None with an engine older than 26.3."""
    if not hasattr(engine, "classify_updates"):
        return None
    from backend.services import (  # pylint: disable=import-outside-toplevel
        auto_update_evidence,
    )

    settings = runner.settings_dict(runner.settings_row(db))
    updates = runner.update_dicts(db, host.id)
    sources = auto_update_evidence.attach(db, host.id, updates)
    now = runner.now_naive()
    packages, skipped = engine.classify_updates(updates, profile, settings, now)
    rows = [
        {
            "package_name": p["package_name"],
            "package_manager": p["package_manager"],
            "available_version": p.get("available_version"),
            "reason": None,
            "kind": p.get("kind"),
            "fix_id": p.get("fix_id"),
            "eligible_at": None,
        }
        for p in packages
    ]
    rows += [
        {
            "package_name": s["package_name"],
            "package_manager": s["package_manager"],
            "reason": s["reason"],
            "kind": s.get("kind"),
            "fix_id": s.get("fix_id"),
            "eligible_at": s.get("eligible_at"),
        }
        for s in skipped
    ]
    return {
        "updates": sorted(rows, key=lambda r: (r["package_name"] or "")),
        "sources": sources,
        "critical_threshold": settings["critical_threshold"],
    }


@router.get("/hosts/{host_id}")
def host_view(
    host_id: str,
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_tenant_db),
):
    """The policy a host follows (and why), its opt-out, its recent runs."""
    engine = _check_automation_module()
    host = db.get(models.Host, _parse_uuid_or_400(host_id, "host_id"))
    if host is None:
        raise HTTPException(status_code=404, detail=_("Host not found"))
    tags = [
        str(row[0])
        for row in db.query(models.HostTag.tag_id).filter(
            models.HostTag.host_id == host.id
        )
    ]
    policies = runner.auto_profiles(db)
    resolved = engine.resolve_policy({"id": str(host.id), "tag_ids": tags}, policies)
    policy, pending = None, None
    if resolved:
        chosen = next(p for p in policies if p["id"] == resolved["profile_id"])
        policy = {"id": chosen["id"], "name": chosen["name"], "rule": resolved["rule"],
                  "candidates": resolved["candidates"],
                  "wait_days_regular": chosen["wait_days_regular"],
                  "wait_days_critical": chosen["wait_days_critical"],
                  "critical_source": chosen["critical_source"],
                  "reboot_mode": chosen["reboot_mode"]}  # fmt: skip
        pending = _pending(db, engine, host, chosen)
    runs = (
        db.query(models.AutoUpdateRun)
        .filter(models.AutoUpdateRun.host_id == host.id)
        .order_by(models.AutoUpdateRun.queued_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "host_id": str(host.id),
        "opt_out": bool(host.auto_update_opt_out),
        "opt_out_reason": host.auto_update_opt_out_reason,
        "policy": policy,
        "hold_all": bool(runner.settings_row(db).hold_all),
        "runs": [r.to_dict() for r in runs],
        "pending": pending,
        "window": next_window_for_host(db, host.id, runner.now_naive()),
    }


@router.get("/runs")
def list_runs(
    host_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    status: Optional[str] = Query(None, max_length=16),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_tenant_db),
):
    _check_automation_module()
    query = db.query(models.AutoUpdateRun)
    if host_id:
        query = query.filter(
            models.AutoUpdateRun.host_id == _parse_uuid_or_400(host_id, "host_id")
        )
    if profile_id:
        query = query.filter(
            models.AutoUpdateRun.profile_id
            == _parse_uuid_or_400(profile_id, "profile_id")
        )
    if status:
        query = query.filter(models.AutoUpdateRun.status == status)
    rows = query.order_by(models.AutoUpdateRun.queued_at.desc()).limit(limit).all()
    hosts = {
        str(h.id): h.fqdn
        for h in db.query(models.Host.id, models.Host.fqdn).filter(
            models.Host.id.in_({r.host_id for r in rows} or {uuid.uuid4()})
        )
    }
    return [{**r.to_dict(), "hostname": hosts.get(str(r.host_id))} for r in rows]


@router.post("/runs/{run_id}/acknowledge")
def acknowledge_run(
    run_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Someone looked at a failed run: the host may be tried again on the
    next schedule instead of waiting out the retry hours."""
    _check_automation_module()
    _require_apply_role(current_user)
    run = db.get(models.AutoUpdateRun, _parse_uuid_or_400(run_id, "run_id"))
    if run is None:
        raise HTTPException(status_code=404, detail=_("Run not found"))
    run.acknowledged_by = current_user.userid
    run.acknowledged_at = runner.now_naive()
    db.commit()
    host = db.get(models.Host, run.host_id)
    _audit(
        db,
        current_user,
        _("Acknowledged the automatic update run on %s")
        % (host.fqdn if host else run.host_id),
        EntityType.HOST,
        run.host_id,
        host.fqdn if host else None,
        details={"run_id": str(run.id), "status": run.status},
    )
    return run.to_dict()
