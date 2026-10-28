# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Grandfather-father-son retention (ROADMAP 24.6, Pro+ to set).

Beside ``keep_last``, a policy may keep the newest snapshot of each of the
last N days, ISO weeks and months that have one -- restate's own prune rules,
run by the storage host.  Setting or changing them needs the Pro+ backup
engine; once set they are always sent with the prune (services/backup_jobs
``prune_keep``), so a lapsed license never makes a prune delete history the
operator chose to keep.  The engine also previews what the next prune would
remove, choosing exactly as restate does.

The scheduled-verification cadence (``verify_interval_days``, Pro+ 24.6) is
checked and stored the same way: changing it needs the engine.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.services import backup_jobs as jobs

router = APIRouter(dependencies=[Depends(JWTBearer())])

MAX_VERIFY_DAYS = 365

# The most each count may be (restate takes any; these keep a typo sane).
GFS_LIMITS = {
    "keep_daily": 3650,
    "keep_weekly": 520,
    "keep_monthly": 240,
    "keep_yearly": 100,
}


def _engine():
    return module_loader.get_module("backup_engine")


def _needs_engine() -> HTTPException:
    return HTTPException(
        status_code=402,
        detail=_(
            "Grandfather-father-son retention needs the Professional+ backup engine"
        ),
    )


def gfs_values(body: Any) -> Dict[str, int]:
    """The body's daily / weekly / monthly counts (missing = 0), checked."""
    values = {}
    for key, limit in GFS_LIMITS.items():
        value = getattr(body, key, None) or 0
        if not 0 <= value <= limit:
            raise HTTPException(
                status_code=422,
                detail=_("%(field)s must be a whole number from 0 to %(max)d")
                % {"field": key, "max": limit},
            )
        values[key] = value
    return values


def stored_gfs(policy: Optional[models.BackupPolicy]) -> Dict[str, int]:
    return {
        key: (getattr(policy, key, None) or 0) if policy else 0 for key in GFS_LIMITS
    }


def check_gfs_change(
    policy: Optional[models.BackupPolicy], body: Any
) -> Dict[str, int]:
    """The counts to store; HTTP 402 when they CHANGE without the engine
    (leaving them as they are -- including saving other settings of a policy
    that has them -- is always allowed)."""
    values = gfs_values(body)
    if values != stored_gfs(policy) and _engine() is None:
        raise _needs_engine()
    check_yearly(policy, values)
    values["verify_interval_days"] = check_verify_change(policy, body)
    return values


def check_verify_change(policy: Optional[models.BackupPolicy], body: Any) -> int:
    """The scheduled-verification cadence to store (days, 0 = off); HTTP 422
    out of range, 402 when it CHANGES without the engine."""
    days = getattr(body, "verify_interval_days", None) or 0
    if not 0 <= days <= MAX_VERIFY_DAYS:
        raise HTTPException(
            status_code=422,
            detail=_("%(field)s must be a whole number from 0 to %(max)d")
            % {"field": "verify_interval_days", "max": MAX_VERIFY_DAYS},
        )
    stored = (getattr(policy, "verify_interval_days", None) or 0) if policy else 0
    if days != stored and _engine() is None:
        raise HTTPException(
            status_code=402,
            detail=_("Scheduled verification needs the Professional+ backup engine"),
        )
    return days


def check_yearly(policy: Optional[models.BackupPolicy], values: Dict[str, int]) -> None:
    """A yearly count needs the storage host's restate to honor it (restate
    2.2.0.12, reported at configure time); HTTP 409 otherwise.  Only a new
    or changed count is checked -- a policy that already has one keeps it."""
    yearly = values.get("keep_yearly") or 0
    if not yearly or yearly == stored_gfs(policy).get("keep_yearly"):
        return
    if policy is None or "keep_yearly" not in jobs.storage_abilities(policy):
        raise HTTPException(
            status_code=409,
            detail=_(
                "The storage host's restate cannot keep yearly snapshots yet: "
                "update restate there to 2.2.0.12 or later, then save the "
                "policy without years and set them once it has reported in"
            ),
        )


def apply_gfs(policy: models.BackupPolicy, values: Dict[str, int]) -> None:
    for key, value in values.items():
        setattr(policy, key, value or None)


@router.get("/host/{host_id}/backup-retention-preview")
async def retention_preview(
    host_id: str,
    keep_last: int,
    keep_daily: int = 0,
    keep_weekly: int = 0,
    keep_monthly: int = 0,
    keep_yearly: int = 0,
    db: Session = Depends(get_tenant_db),
) -> Dict[str, Any]:
    """What the next prune would keep and remove from this host's current
    repository under these counts (restate's own choice, ported)."""
    engine = _engine()
    if engine is None or not hasattr(engine, "retention_preview"):
        raise _needs_engine()
    # pylint: disable=import-outside-toplevel
    from backend.api.backups import _host_or_404  # noqa: PLC0415

    host = _host_or_404(db, host_id)
    policy = (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.host_id == host.id)
        .first()
    )
    current = jobs.policy_repo_dir(policy, host) if policy else None
    snapshots = (
        db.query(models.BackupSnapshot)
        .filter(
            models.BackupSnapshot.host_id == host.id,
            models.BackupSnapshot.gone_at.is_(None),
        )
        .all()
    )
    names = [
        s.name
        for s in snapshots
        if current is None or jobs.snapshot_repo_dir(s, host) == current
    ]
    values = {
        "keep_last": keep_last,
        "keep_daily": keep_daily,
        "keep_weekly": keep_weekly,
        "keep_monthly": keep_monthly,
        "keep_yearly": keep_yearly,
    }
    try:
        return engine.retention_preview(names, values)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
