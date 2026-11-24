# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet restore jobs (ROADMAP 27.2, Enterprise ``backup_ops_engine``).

``POST /backups/fleet-restores`` -- one restore asked of many hosts;
``GET /backups/fleet-restores`` -- the latest jobs; ``GET .../{id}`` -- one
job with each host's outcome; ``POST .../{id}/cancel`` -- stop releasing
hosts.  Restore Files role; 402 without the engine.  See
``backend/services/backup_fleet_restore.py``.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import RestoreBody, _audit, _require, _validate_restore
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.migration_compat import missing_engine_detail
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_fleet_restore as fleet
from backend.services import backup_four_eyes as four_eyes
from backend.services.audit_service import EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])


class FleetRestoreBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    host_ids: List[str] = Field(min_length=1)
    include: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)
    # Each host's newest snapshot taken before this moment; None = newest.
    before: Optional[datetime] = None
    in_place: bool = False
    acknowledge_in_place: bool = False
    dry_run: bool = False
    acknowledge_unsigned: bool = False
    concurrency: Optional[int] = None


def _engine_or_402():
    eng = fleet.engine()
    if eng is None:
        raise HTTPException(
            status_code=402,
            detail=missing_engine_detail(
                fleet.ENGINE,
                _("Fleet restores need the Enterprise backup operations engine"),
            ),
        )
    return eng


def _naive_utc(moment: Optional[datetime]) -> Optional[datetime]:
    if moment is None or moment.tzinfo is None:
        return moment
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def _hosts(db: Session, eng, ids: List[str]) -> List[models.Host]:
    keys = []
    for raw in dict.fromkeys(ids):  # in order, once each
        try:
            keys.append(uuid.UUID(str(raw)))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=_("Host not found")) from exc
    if len(keys) > eng.FLEET_HOSTS_MAX:
        raise HTTPException(
            status_code=400,
            detail=_("At most %d hosts can be restored in one job")
            % eng.FLEET_HOSTS_MAX,
        )
    hosts = []
    for key in keys:
        host = db.get(models.Host, key)
        if host is None:
            raise HTTPException(status_code=404, detail=_("Host not found"))
        hosts.append(host)
    return hosts


def _job_or_404(db: Session, job_id: str) -> models.BackupFleetRestore:
    try:
        job = db.get(models.BackupFleetRestore, uuid.UUID(job_id))
    except ValueError:
        job = None
    if job is None:
        raise HTTPException(status_code=404, detail=_("Fleet restore not found"))
    return job


@router.post("/backups/fleet-restores")
def create_fleet_restore(
    body: FleetRestoreBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.RESTORE_FILES)
    eng = _engine_or_402()
    # The same rules as one host's restore (paths, in place), said once.
    _validate_restore(RestoreBody(
        snapshot="fleet", include=body.include, exclude=body.exclude,
        dry_run=body.dry_run, in_place=body.in_place,
        acknowledge_in_place=body.acknowledge_in_place,
    ))  # fmt: skip
    hosts = _hosts(db, eng, body.host_ids)
    job = fleet.create(
        db, current_user, eng, name=body.name, hosts=hosts, include=body.include,
        exclude=body.exclude, before=_naive_utc(body.before), in_place=body.in_place,
        dry_run=body.dry_run, allow_unsigned=body.acknowledge_unsigned,
        concurrency=body.concurrency,
    )  # fmt: skip
    _audit(
        db, current_user, EntityType.SETTING, job.id, job.name,
        "Fleet restore created", fleet.view(db, job),
    )  # fmt: skip
    db.commit()
    return fleet.view(db, job, hosts=True)


@router.get("/backups/fleet-restores")
def list_fleet_restores(
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.RESTORE_FILES)
    _engine_or_402()
    jobs_ = (
        db.query(models.BackupFleetRestore)
        .order_by(models.BackupFleetRestore.created_at.desc())
        .limit(50)
        .all()
    )
    return {"jobs": [fleet.view(db, job) for job in jobs_]}


@router.get("/backups/fleet-restores/{job_id}")
def get_fleet_restore(
    job_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.RESTORE_FILES)
    _engine_or_402()
    return fleet.view(db, _job_or_404(db, job_id), hosts=True)


@router.post("/backups/fleet-restores/{job_id}/cancel")
def cancel_fleet_restore(
    job_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.RESTORE_FILES)
    _engine_or_402()
    job = _job_or_404(db, job_id)
    canceled = fleet.cancel(db, job)
    _audit(
        db, current_user, EntityType.SETTING, job.id, job.name,
        "Fleet restore canceled", {"hosts_canceled": canceled},
    )  # fmt: skip
    db.commit()
    return fleet.view(db, job, hosts=True)


def _perform_approved(db: Session, current_user, request, _host) -> Dict[str, Any]:
    """Four-eyes approved a held fleet restore: start it."""
    eng = _engine_or_402()
    job = _job_or_404(db, json.loads(request.body)["job_id"])
    if job.status != fleet.AWAITING:
        raise HTTPException(
            status_code=409, detail=_("This fleet restore is no longer waiting")
        )
    fleet.approve(db, eng, job, current_user.userid)
    return {"id": str(job.id)}


four_eyes.register(
    fleet.KIND,
    four_eyes.Kind(
        role=SecurityRoles.RESTORE_FILES,
        perform=_perform_approved,
        refusals={
            "own_request": lambda: _(
                "A fleet restore you asked for must be approved by someone else"
            ),
            "expired": lambda: _(
                "This fleet restore request has expired; ask for it again"
            ),
        },
    ),
)
