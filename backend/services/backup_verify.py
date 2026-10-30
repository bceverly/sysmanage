# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Scheduled verification (ROADMAP 24.6, Pro+ backup_engine).

restate's ``check --read-all`` on its own cadence: a periodic test restore
that writes nothing.  It runs on the backed-up HOST, not the storage host --
an encrypted repository can only be read with its secret keys, the storage
host has never held one, and the host already receives keys for one job at
a time (24.6 S4).  It reads every pack through the host's mount, so each pass
costs the repository's size in NFS traffic (restate, 2026-10-28): hence a
cadence in days, never while a capture of that host is queued or running,
and a day's wait after a failed pass.

Setting the cadence needs the Pro+ backup engine; without the engine nothing
is queued (nothing could release the keys) and a repository whose last good
pass is older than its cadence shows "unverified".
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import backup_jobs as jobs

logger = logging.getLogger(__name__)

VERIFY = jobs.VERIFY
# The dialog's suggestion when an operator turns it on (a full read of the
# repository each time); 0 / NULL = off.
DEFAULT_INTERVAL_DAYS = 30
MAX_INTERVAL_DAYS = 365
FAILED_RETRY = timedelta(hours=24)
# Refused because the storage host was pruning or checking the repository
# (production, mail.archive, 2026-10-29: right after its first capture):
# nothing failed, so try again soon, as the storage-side jobs do.
BUSY_RETRY = timedelta(minutes=30)
GOOD = ("ok",)

OFF, VERIFIED, UNVERIFIED, FAILED, RUNNING = (
    "off",
    "verified",
    "unverified",
    "failed",
    "running",
)


def _engine():
    # pylint: disable=import-outside-toplevel
    from backend.licensing.module_loader import module_loader  # noqa: PLC0415

    return module_loader.get_module("backup_engine")


def interval(policy: models.BackupPolicy) -> int:
    return int(getattr(policy, "verify_interval_days", None) or 0)


def _ended(run: Optional[models.BackupRun]) -> Optional[datetime]:
    return (run.finished_at or run.queued_at) if run is not None else None


def state(db: Session, policy: models.BackupPolicy, now: datetime) -> Dict[str, Any]:
    """The repository's verification state for the UI and alerts."""
    days = interval(policy)
    latest = jobs.latest_run(db, policy.id, VERIFY)
    good = jobs.latest_run(db, policy.id, VERIFY, statuses=GOOD)
    out: Dict[str, Any] = {
        "interval_days": days,
        "last_good_at": _iso(_ended(good)),
        "last_status": latest.status if latest is not None else None,
        "last_at": _iso(_ended(latest)),
        "last_message": latest.message if latest is not None else None,
    }
    if not days:
        out["state"] = OFF
    elif latest is not None and latest.status in jobs.PENDING:
        out["state"] = RUNNING
    elif latest is not None and latest.status not in GOOD:
        out["state"] = FAILED
    elif good is not None and _ended(good) + timedelta(days=days) > now:
        out["state"] = VERIFIED
    else:
        out["state"] = UNVERIFIED
    return out


def _iso(when: Optional[datetime]) -> Optional[str]:
    return when.isoformat() if when is not None else None


def due(db: Session, policy: models.BackupPolicy, now: datetime) -> bool:
    """A pass is due: a cadence is set, the engine is loaded, the repository
    holds a good capture, nothing that would collide is pending, the last
    pass is older than the cadence, and a failed one was not moments ago."""
    days = interval(policy)
    if not days or _engine() is None:
        return False
    if jobs.latest_run(db, policy.id, "capture", statuses=jobs.GOOD_CAPTURE) is None:
        return False
    if jobs.pending(db, policy.id, VERIFY) or jobs.pending(db, policy.id, "capture"):
        return False
    latest = jobs.latest_run(db, policy.id, VERIFY)
    if latest is not None and latest.status not in GOOD:
        wait = BUSY_RETRY if latest.status == "busy" else FAILED_RETRY
        if _ended(latest) + wait > now:
            return False
    good = jobs.latest_run(db, policy.id, VERIFY, statuses=GOOD)
    return good is None or _ended(good) + timedelta(days=days) <= now


def maybe_verify(
    db: Session, policy: models.BackupPolicy, host: models.Host, now: datetime
) -> bool:
    """Queue a pass when due and the host can run it; True when queued."""
    if not due(db, policy, now):
        return False
    abilities = jobs.abilities(policy)
    if "verify" not in abilities:
        logger.debug(
            "Backup policy %s: verification due, but host %s's restate cannot "
            "run a check job yet",
            policy.id,
            host.id,
        )
        return False
    needs_key = jobs.needs_secret_key(jobs.CURRENT, policy)
    if needs_key and "decrypt" not in abilities:
        logger.debug(
            "Backup policy %s: verification due, but host %s's restate cannot "
            "take a key yet",
            policy.id,
            host.id,
        )
        return False
    jobs.queue_verify(db, policy, host.id, needs_key=needs_key)
    return True
