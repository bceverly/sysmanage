# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Restore readiness (ROADMAP 27.1, Enterprise ``backup_ops_engine``).

``GET /backups/readiness`` -- every host's RPO, RTO and proof, worst first,
with counts by state.  ``PUT /host/{id}/backup-readiness`` -- a policy's
recovery point objective.  Both answer 402 without the engine; backups run
the same either way.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import _audit, _host_or_404, _policy_of, _require
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.migration_compat import missing_engine_detail
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_jobs as jobs
from backend.services import backup_readiness as readiness
from backend.services.audit_service import EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])

# An RPO longer than a year is not an objective.
MAX_RPO_HOURS = 24 * 366


def _engine_or_402():
    eng = readiness.engine()
    if eng is None:
        raise HTTPException(
            status_code=402,
            detail=missing_engine_detail(
                readiness.ENGINE,
                _("Restore readiness needs the Enterprise backup operations engine"),
            ),
        )
    return eng


class ReadinessBody(BaseModel):
    # None = the default, twice the policy's interval.
    rpo_hours: Optional[int] = Field(default=None, ge=1, le=MAX_RPO_HOURS)


@router.get("/backups/readiness")
def backups_readiness(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    eng = _engine_or_402()
    return readiness.fleet(db, eng, jobs.now())


@router.put("/host/{host_id}/backup-readiness")
def put_backup_readiness(
    host_id: str,
    body: ReadinessBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    eng = _engine_or_402()
    host = _host_or_404(db, host_id)
    policy = _policy_of(db, host)
    if policy is None:
        raise HTTPException(
            status_code=409, detail=_("This host has no backup policy yet")
        )
    policy.rpo_hours = body.rpo_hours
    policy.updated_at = jobs.now()
    _audit(
        db,
        current_user,
        EntityType.HOST,
        host.id,
        host.fqdn,
        "Backup recovery point objective set",
        body.model_dump(),
    )
    db.commit()
    return eng.assess_readiness(readiness.facts(db, policy), jobs.now())
