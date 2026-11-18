# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet-by-fleet rollouts of automatic updates (ROADMAP 26.4, Enterprise).

  GET  /auto-updates/rollouts                 rollouts, newest first
  POST /auto-updates/rollouts/{id}/resume     past a halted fleet (reason)
  POST /auto-updates/rollouts/{id}/cancel     no further fleet (reason)

Each rollout lists its fleets in order with every host's latest run, so a
fleet that is "done" shows which hosts applied and why the rest did not.
Resuming and canceling are audited and need the role that applies updates.
"""

import uuid
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
from backend.services import auto_update_rollout as rollouts
from backend.services import auto_update_runner as runner

router = APIRouter(tags=["auto-updates"], dependencies=[Depends(JWTBearer())])


class RolloutActionRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


def _host_row(host_id, hostname, run) -> dict:
    """One host of a fleet, with its latest run in the rollout (or none yet)."""
    row = {"host_id": host_id, "hostname": hostname, "run_id": None, "status": None,
           "reason": None, "reboot_status": None, "release_at": None}  # fmt: skip
    if run is not None:
        row.update(
            run_id=str(run.id),
            status=run.status,
            reason=run.reason,
            reboot_status=run.reboot_status,
            release_at=run.release_at.isoformat() if run.release_at else None,
        )
    return row


def _view(db, rollout) -> dict:
    """The rollout with each started fleet's hosts and their latest runs."""
    out = rollout.to_dict()
    ids = {h for stage in out["stages"] for h in stage.get("host_ids", [])}
    names = {
        str(h.id): h.fqdn
        for h in db.query(models.Host.id, models.Host.fqdn).filter(
            models.Host.id.in_([uuid.UUID(h) for h in ids] or [uuid.uuid4()])
        )
    }
    runs = {
        (str(run.host_id), run.rollout_stage): run
        for run in db.query(models.AutoUpdateRun)
        .filter(models.AutoUpdateRun.rollout_id == rollout.id)
        .order_by(models.AutoUpdateRun.queued_at)
    }
    for index, stage in enumerate(out["stages"]):
        stage["hosts"] = [
            _host_row(host_id, names.get(host_id), runs.get((host_id, index)))
            for host_id in stage.get("host_ids", [])
        ]
    return out


@router.get("/rollouts")
def list_rollouts(
    profile_id: Optional[str] = None,
    status: Optional[str] = Query(None, max_length=16),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_tenant_db),
):
    _check_automation_module()
    query = db.query(models.AutoUpdateRollout)
    if profile_id:
        query = query.filter(
            models.AutoUpdateRollout.profile_id
            == _parse_uuid_or_400(profile_id, "profile_id")
        )
    if status:
        query = query.filter(models.AutoUpdateRollout.status == status)
    rows = query.order_by(models.AutoUpdateRollout.started_at.desc()).limit(limit)
    return [_view(db, r) for r in rows]


def _rollout_or_404(db, rollout_id):
    rollout = db.get(
        models.AutoUpdateRollout, _parse_uuid_or_400(rollout_id, "rollout_id")
    )
    if rollout is None:
        raise HTTPException(status_code=404, detail=_("Rollout not found"))
    return rollout


@router.post("/rollouts/{rollout_id}/resume")
def resume_rollout(
    rollout_id: str,
    request: RolloutActionRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """A person looked at the halted fleet: the rollout moves on to the
    next one."""
    _check_automation_module()
    _require_apply_role(current_user)
    rollout = _rollout_or_404(db, rollout_id)
    if rollout.status != rollouts.HALTED:
        raise HTTPException(
            status_code=409, detail=_("Only a halted rollout can resume")
        )
    rollouts.resume(
        db, rollout, current_user.userid, request.reason.strip(), runner.now_naive()
    )
    db.commit()
    return _view(db, rollout)


@router.post("/rollouts/{rollout_id}/cancel")
def cancel_rollout(
    rollout_id: str,
    request: RolloutActionRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """No further fleet is patched; runs already queued still go out."""
    _check_automation_module()
    _require_apply_role(current_user)
    rollout = _rollout_or_404(db, rollout_id)
    if rollout.status not in rollouts.OPEN:
        raise HTTPException(status_code=409, detail=_("This rollout has already ended"))
    rollouts.end(
        db, rollout, rollouts.CANCELED, runner.now_naive(), current_user.userid,
        request.reason.strip(),
    )  # fmt: skip
    db.commit()
    return _view(db, rollout)
