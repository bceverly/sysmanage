# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Set up backups for many hosts at once (2026-10-29, Bryan).

Each picked host that can run backups and has no policy yet gets one with the
sane defaults -- the same ones the policy dialog offers a new host: daily, from
06:00 UTC (the scheduler spreads hosts through the window), and with the Pro+
backup engine grandfather-father-son retention (the newest 7, plus the newest
of each of the last 14 days, 8 weeks, 12 months and 3 years -- years left
out where the storage host has said its restate cannot keep them), else the
newest 30.
Pausing services is left off: which hooks a host has is only known once its
restate has reported, so that is set per host afterwards.  Hosts that cannot
take it come back with why, like the other bulk actions.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api import backups_retention as retention
from backend.api.backups import (
    PolicyBody,
    _apply_policy,
    _audit,
    _host_or_404,
    _policy_of,
    _require,
)
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_jobs as jobs
from backend.services import backup_reach as reach
from backend.services import backup_tick
from backend.services.audit_service import EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])

DEFAULT_START_HOUR = 6  # UTC
GFS_DEFAULTS = {
    "keep_last": 7,
    "keep_daily": 14,
    "keep_weekly": 8,
    "keep_monthly": 12,
    "keep_yearly": 3,
}
COMMUNITY_KEEP_LAST = 30


class BulkSetupBody(BaseModel):
    host_ids: List[str] = Field(min_length=1, max_length=500)


def default_body(storage_abilities: Optional[List[str]] = None) -> PolicyBody:
    """The policy a host gets from the bulk action (and, in the UI, a new
    host's dialog): GFS with the Pro+ engine, a month of dailies without."""
    counts: Dict[str, int] = (
        dict(GFS_DEFAULTS)
        if retention._engine() is not None  # pylint: disable=protected-access
        else {"keep_last": COMMUNITY_KEEP_LAST}
    )
    if storage_abilities is not None and "keep_yearly" not in storage_abilities:
        counts.pop("keep_yearly", None)
    return PolicyBody(window_start_hour=DEFAULT_START_HOUR, **counts)


def _skip_reason(db: Session, host: models.Host) -> str:
    """Why this host does not get a policy from the bulk action, or ""."""
    if not jobs.equipped(host)[0]:
        return "not_equipped"
    if _policy_of(db, host) is not None:
        return "has_policy"
    return reach.UNREACHABLE if reach.blocked(db, host) else ""


@router.post("/backups/setup")
async def bulk_backup_setup(
    body: BulkSetupBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Give each picked host that can run backups, and has no policy, the
    default policy; the rest come back with why."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    target = jobs.the_target(db)
    if target is None:
        raise HTTPException(status_code=409, detail=_("Set up the backup target first"))
    defaults = default_body(jobs.target_storage_abilities(db, target.id))
    gfs = retention.gfs_values(defaults)
    created, skipped = 0, []
    for host_id in dict.fromkeys(body.host_ids):
        try:
            host = _host_or_404(db, host_id)
        except HTTPException:
            skipped.append({"host_id": host_id, "fqdn": None, "reason": "no_host"})
            continue
        reason = _skip_reason(db, host)
        if reason:
            skipped.append({"host_id": host_id, "fqdn": host.fqdn, "reason": reason})
            continue
        policy = models.BackupPolicy(
            host_id=host.id,
            target_id=target.id,
            config_version=1,
            host_acked_version=0,
            storage_acked_version=0,
            created_at=jobs.now(),
            created_by=current_user.userid,
        )
        db.add(policy)
        _apply_policy(policy, defaults)
        retention.apply_gfs(policy, gfs)
        created += 1
        _audit(
            db,
            current_user,
            EntityType.HOST,
            host.id,
            host.fqdn,
            "Backup policy set (bulk setup with the defaults)",
            defaults.model_dump(),
        )
    if created:
        backup_tick.configure_now(db)
    db.commit()
    return {"requested": len(body.host_ids), "created": created, "skipped": skipped}
