# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Legal hold (ROADMAP 27.2, Enterprise ``backup_ops_engine``).

``GET /backups/legal-holds`` -- holds still in force and recently released;
``POST /host/{id}/backup-snapshots/{name}/hold`` -- place one, with an owner
and a reason; ``POST /backups/legal-holds/{id}/release``.  Placing and
releasing answer 402 without the engine.  HONORING a hold is not here and
needs no license: every prune of the repository keeps a held snapshot
(``backup_jobs.prune_keep``), so a lapse never deletes held data.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import (
    _audit,
    _host_or_404,
    _policy_of,
    _require,
    _uuid_or_404,
)
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.migration_compat import missing_engine_detail
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_jobs as jobs
from backend.services import backup_tick
from backend.services.audit_service import EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])
ENGINE = "backup_ops_engine"

_REFUSALS = {
    "storage_cannot_hold": (
        409,
        lambda: _(
            "The storage host's restate cannot keep a held snapshot through a "
            "prune; upgrade it to 3.4.0.0 or later first"
        ),
    ),
    "snapshot_gone": (404, lambda: _("Snapshot not found")),
    "already_held": (409, lambda: _("This snapshot is already on hold")),
    "owner_needed": (422, lambda: _("Say whose hold this is")),
    "reason_needed": (422, lambda: _("Say why the snapshot is held")),
    "already_released": (409, lambda: _("This hold has already been released")),
}


def _engine_or_402():
    eng = module_loader.get_module(ENGINE)
    if not hasattr(eng, "hold_refusal"):  # unlicensed, or an older build
        raise HTTPException(
            status_code=402,
            detail=missing_engine_detail(
                ENGINE, _("Legal hold needs the Enterprise backup operations engine")
            ),
        )
    return eng


def _refuse(code) -> None:
    if code:
        status, text = _REFUSALS[code]
        raise HTTPException(status_code=status, detail=text())


def _iso(when):
    return when.isoformat() if when is not None else None


def _hold_dict(hold: models.BackupLegalHold, fqdn) -> Dict[str, Any]:
    return {
        "id": str(hold.id),
        "host_id": str(hold.host_id),
        "fqdn": fqdn,
        "snapshot": hold.snapshot,
        "owner": hold.owner,
        "reason": hold.reason,
        "placed_by": hold.placed_by,
        "placed_at": _iso(hold.placed_at),
        "released_by": hold.released_by,
        "released_at": _iso(hold.released_at),
    }


def _reconfigure(db: Session, policy: models.BackupPolicy) -> None:
    """The storage host's prune job must list the holds: re-send it now."""
    policy.config_version += 1
    policy.updated_at = jobs.now()
    backup_tick.configure_now(db)


class HoldBody(BaseModel):
    owner: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=1000)


@router.get("/backups/legal-holds")
def list_legal_holds(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    _engine_or_402()
    rows = (
        db.query(models.BackupLegalHold, models.Host.fqdn)
        .outerjoin(models.Host, models.Host.id == models.BackupLegalHold.host_id)
        .order_by(models.BackupLegalHold.placed_at.desc())
        .limit(200)
        .all()
    )
    holds: List[Dict[str, Any]] = [_hold_dict(hold, fqdn) for hold, fqdn in rows]
    holds.sort(key=lambda h: h["released_at"] is not None)  # in force first
    return {"holds": holds}


@router.post("/host/{host_id}/backup-snapshots/{snapshot}/hold")
def place_legal_hold(
    host_id: str,
    snapshot: str,
    body: HoldBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    eng = _engine_or_402()
    host = _host_or_404(db, host_id)
    policy = _policy_of(db, host)
    if policy is None:
        raise HTTPException(status_code=404, detail=_("Snapshot not found"))
    present = (
        db.query(models.BackupSnapshot)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.name == snapshot,
            models.BackupSnapshot.gone_at.is_(None),
        )
        .first()
        is not None
    )
    _refuse(
        eng.hold_refusal(
            jobs.storage_abilities(policy),
            present,
            snapshot in jobs.held_snapshots(policy),
            body.owner,
            body.reason,
        )
    )
    hold = models.BackupLegalHold(
        policy_id=policy.id,
        host_id=host.id,
        snapshot=snapshot,
        owner=body.owner.strip(),
        reason=body.reason.strip(),
        placed_by=current_user.userid,
        placed_at=jobs.now(),
    )
    db.add(hold)
    db.flush()
    _reconfigure(db, policy)
    _audit(
        db,
        current_user,
        EntityType.HOST,
        host.id,
        host.fqdn,
        "Backup snapshot placed on legal hold",
        {"hold_id": str(hold.id), "snapshot": snapshot,
         "owner": hold.owner, "reason": hold.reason},
    )  # fmt: skip
    db.commit()
    return _hold_dict(hold, host.fqdn)


@router.post("/backups/legal-holds/{hold_id}/release")
def release_legal_hold(
    hold_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    eng = _engine_or_402()
    key = _uuid_or_404(hold_id, _("Legal hold not found"))
    hold = db.get(models.BackupLegalHold, key)
    if hold is None:
        raise HTTPException(status_code=404, detail=_("Legal hold not found"))
    _refuse(eng.release_refusal({"released_at": hold.released_at}))
    hold.released_by, hold.released_at = current_user.userid, jobs.now()
    policy = db.get(models.BackupPolicy, hold.policy_id)
    if policy is not None:
        _reconfigure(db, policy)
    host = db.get(models.Host, hold.host_id)
    _audit(
        db,
        current_user,
        EntityType.HOST,
        hold.host_id,
        host.fqdn if host else None,
        "Backup snapshot released from legal hold",
        {"hold_id": str(hold.id), "snapshot": hold.snapshot, "owner": hold.owner},
    )
    db.commit()
    return _hold_dict(hold, host.fqdn if host else None)
