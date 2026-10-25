# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Browse a snapshot and see what changed since one (ROADMAP 24.2 / 24.9).

Both are read-only jobs on the backed-up host (restate 2.1.0.4+ runs
``list`` and ``status`` from a job file): ``list`` reads one directory of a
snapshot from its index alone -- no pack is read, so it takes seconds and is
what the restore dialog's folder browser asks for; ``status`` compares the
host as it is now with a snapshot (the newest by default).  The run comes
back as usual and its result carries restate's ``list`` / ``diff``; the
client polls ``GET /backups/runs/{id}``.

Offered only where the host's restate reported the ability (its configure
reply's ``abilities``), so an older restate is never asked.
"""

import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import (
    _audit,
    _host_or_404,
    _readable_repository,
    key_needed,
    _ready_policy,
    _require,
)
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_jobs as jobs
from backend.services import backup_views as views
from backend.services.audit_service import EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])

_SNAPSHOT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,254}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class BrowseBody(BaseModel):
    snapshot: str = Field(min_length=1, max_length=255)
    path: str = Field(default="/", max_length=4096)


class ChangesBody(BaseModel):
    snapshot: Optional[str] = Field(default=None, max_length=255)


def _able(policy: models.BackupPolicy, ability: str) -> None:
    if ability not in jobs.abilities(policy):
        raise HTTPException(
            status_code=409,
            detail=_("This host's restate cannot do this yet; upgrade restate"),
        )


def _snapshot_or_404(db: Session, policy, name: str) -> models.BackupSnapshot:
    found = (
        db.query(models.BackupSnapshot)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.name == name,
            models.BackupSnapshot.gone_at.is_(None),
        )
        .first()
    )
    if found is None:
        raise HTTPException(status_code=404, detail=_("Snapshot not found"))
    return found


@router.post("/host/{host_id}/backup-browse")
async def browse_snapshot(
    host_id: str,
    body: BrowseBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """List one directory of a snapshot (seeing file names needs the
    Restore Files role, as restoring them does)."""
    _require(current_user, SecurityRoles.RESTORE_FILES)
    if not _SNAPSHOT.match(body.snapshot):
        raise HTTPException(status_code=422, detail=_("The snapshot name is not valid"))
    if not body.path.startswith("/") or _CONTROL.search(body.path):
        raise HTTPException(status_code=422, detail=_("The path must be absolute"))
    host = _host_or_404(db, host_id)
    policy = _ready_policy(db, host)
    _able(policy, "list")
    snapshot = _snapshot_or_404(db, policy, body.snapshot)
    where = _readable_repository(snapshot, policy, host)
    run = jobs.queue_browse(
        db, policy, host, jobs.LIST, snapshot.name, body.path, current_user.userid,
        previous=where == jobs.PREVIOUS, needs_key=key_needed(where, policy),
    )  # fmt: skip
    db.commit()
    return views.run_dict(run)


@router.post("/host/{host_id}/backup-changes")
async def backup_changes(
    host_id: str,
    body: Optional[ChangesBody] = None,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """What changed on the host since a snapshot (the newest by default)."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    host = _host_or_404(db, host_id)
    policy = _ready_policy(db, host)
    _able(policy, "status")
    name = (body or ChangesBody()).snapshot
    if name:
        named = _snapshot_or_404(db, policy, name)
        if _readable_repository(named, policy, host) != jobs.CURRENT:
            raise HTTPException(
                status_code=409,
                detail=_("What changed compares with the current repository only"),
            )
        name = named.name
    needs_key = key_needed(jobs.CURRENT, policy)
    if jobs.pending(db, policy.id, jobs.STATUS):
        raise HTTPException(
            status_code=409, detail=_("A check of what changed is already running")
        )
    run = jobs.queue_browse(
        db, policy, host, jobs.STATUS, name, None, current_user.userid,
        needs_key=needs_key,
    )  # fmt: skip
    _audit(
        db,
        current_user,
        EntityType.HOST,
        host.id,
        host.fqdn,
        "Backup what-changed check requested",
        {"run_id": str(run.id), "snapshot": name},
    )
    db.commit()
    return views.run_dict(run)
