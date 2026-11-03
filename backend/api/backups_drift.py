# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The drift timeline (Pro+ backup_engine, ROADMAP 24.7).

``GET /host/{id}/backup-drift``: what changed between each snapshot and the
one before it, newest first -- files and packages -- with logs, caches and
the policy's own patterns hidden unless ``hide_expected=false``, and
narrowed to one path with ``path`` (the link from a configuration-drift
finding).  ``POST .../compute`` compares a pair the scheduler missed;
``PUT .../ignore`` sets the policy's patterns.  402 without the engine.
"""

import json
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import _audit, _host_or_404, _ready_policy, _require
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_drift as drift
from backend.services import backup_jobs as jobs
from backend.services import backup_reach as reach
from backend.services import backup_views as views
from backend.services.audit_service import EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])

_SNAPSHOT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,254}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class ComputeBody(BaseModel):
    from_snapshot: Optional[str] = Field(default=None, max_length=255)
    to_snapshot: Optional[str] = Field(default=None, max_length=255)


class IgnoreBody(BaseModel):
    patterns: List[str] = Field(default_factory=list, max_length=200)


def _engine_or_402():
    module = drift.engine()
    if module is None:
        raise HTTPException(
            status_code=402,
            detail=_("The drift timeline needs the Professional+ backup engine"),
        )
    return module


@router.get("/host/{host_id}/backup-drift")
async def drift_timeline(
    host_id: str,
    hide_expected: bool = True,
    path: Optional[str] = None,
    limit: int = 30,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """The host's drift timeline (file names need the Restore Files role,
    as browsing a snapshot does)."""
    _require(current_user, SecurityRoles.RESTORE_FILES)
    module = _engine_or_402()
    if path is not None and (not path.startswith("/") or _CONTROL.search(path)):
        raise HTTPException(status_code=422, detail=_("The path must be absolute"))
    host = _host_or_404(db, host_id)
    policy = _ready_policy(db, host)
    return drift.timeline(db, policy, module, hide_expected, path, limit)


@router.post("/host/{host_id}/backup-drift/compute")
async def drift_compute(
    host_id: str,
    body: Optional[ComputeBody] = None,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Compare two snapshots now (the newest and the one before by default)."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    _engine_or_402()
    body = body or ComputeBody()
    for name in (body.from_snapshot, body.to_snapshot):
        if name is not None and not _SNAPSHOT.match(name):
            raise HTTPException(
                status_code=422, detail=_("The snapshot name is not valid")
            )
    host = _host_or_404(db, host_id)
    policy = _ready_policy(db, host)
    reach.refuse_if_blocked(db, host)  # the host reads its repository
    if "diff" not in jobs.abilities(policy):
        raise HTTPException(
            status_code=409,
            detail=_("This host's restate cannot do this yet; upgrade restate"),
        )
    if jobs.pending(db, policy.id, jobs.DIFF):
        raise HTTPException(
            status_code=409, detail=_("A comparison of snapshots is already running")
        )
    run = drift.queue_diff(
        db, policy, host.id, body.from_snapshot, body.to_snapshot, current_user.userid
    )
    db.commit()
    return views.run_dict(run)


@router.put("/host/{host_id}/backup-drift/ignore")
async def drift_ignore(
    host_id: str,
    body: IgnoreBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Set the paths this host's timeline hides as expected churn."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    module = _engine_or_402()
    try:
        patterns = module.drift_validate_patterns(body.patterns)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    host = _host_or_404(db, host_id)
    policy = _ready_policy(db, host)
    policy.drift_ignore = json.dumps(patterns) if patterns else None
    _audit(db, current_user, EntityType.HOST, host.id, host.fqdn,
           "Backup drift timeline ignore patterns changed",
           {"patterns": patterns})  # fmt: skip
    db.commit()
    return {"ignore": patterns}
