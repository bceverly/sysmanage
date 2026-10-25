# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Will a host's first backup fit on the target? (ROADMAP 24.8, Community)

A first capture keeps everything the host's rules record, which on a
workstation can be tens of gigabytes; one that does not fit fills the storage
for every other host on the target.  So before a host's first SCHEDULED
backup the scheduler asks the host for restate's ``estimate`` (it walks the
tree and reads no file), and compares what it would keep with the free space
under the target's storage path (from the storage host's disk inventory):

* no estimate yet, or one older than ``ESTIMATE_FRESH``: run one first;
* the estimate failed: go ahead -- a failed estimate must not stop backups
  (fail-open, logged);
* it does not fit: hold the scheduled first backup and say so on the host's
  card, the Backups page and the dashboard, with the largest directories as
  the place to start leaving things out.

"Back up now" is never held: it is the operator's own decision.  restate
compresses and de-duplicates, so a first backup usually needs less than the
estimate; "may not fit" is the honest wording.  Once a host has a good
backup this check is over.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_storage_health as storage_health

logger = logging.getLogger(__name__)

ESTIMATE = "estimate"
ESTIMATE_FRESH = timedelta(hours=24)
KEPT_DIRS = 10  # stored with the estimate
SHOWN_DIRS = 5  # suggested on the card
_PATH_LIMIT = 1024

GO = "go"
RUN_ESTIMATE = "estimate"
HOLD = "hold"


def first_capture_pending(db: Session, policy: models.BackupPolicy) -> bool:
    """The host has never had a good backup."""
    return jobs.latest_run(db, policy.id, "capture", statuses=jobs.GOOD_CAPTURE) is None


def largest_dirs(by_dir: Any, limit: int = KEPT_DIRS) -> List[Dict[str, Any]]:
    """restate's ``by_dir`` (``{path: bytes}``) as the biggest first."""
    if not isinstance(by_dir, dict):
        return []
    found = [
        {"path": path[:_PATH_LIMIT], "bytes": size}
        for path, size in by_dir.items()
        if isinstance(path, str) and isinstance(size, int) and size >= 0
    ]
    found.sort(key=lambda item: item["bytes"], reverse=True)
    return found[:limit]


def stored_dirs(policy: models.BackupPolicy) -> List[Dict[str, Any]]:
    try:
        found = json.loads(policy.estimate_dirs or "[]")
    except ValueError:
        return []
    return found if isinstance(found, list) else []


def free_bytes(db: Session, target: models.BackupTarget) -> Optional[int]:
    """Free space under the storage path, from the storage host's disks."""
    storage = jobs.storage_host(db, target)
    if storage is None:
        return None
    space = storage_health.storage_space(db, storage.id, target.storage_path)
    return space["available_bytes"] if space else None


def fit(
    db: Session, policy: models.BackupPolicy, target: Optional[models.BackupTarget]
) -> Optional[Dict[str, Any]]:
    """For a host with no good backup yet and an estimate: does it fit?
    None when there is nothing to compare."""
    if target is None or policy.estimate_bytes is None:
        return None
    if not first_capture_pending(db, policy):
        return None
    free = free_bytes(db, target)
    if free is None:
        return None
    return {
        "estimate_bytes": policy.estimate_bytes,
        "available_bytes": free,
        "fits": policy.estimate_bytes <= free,
        "largest": stored_dirs(policy)[:SHOWN_DIRS],
    }


def _estimate_recent(db: Session, policy, now: datetime):
    run = jobs.latest_run(db, policy.id, ESTIMATE, statuses=jobs.FINAL)
    if run is None:
        return None
    ended = run.finished_at or run.queued_at
    return run if ended and now - ended < ESTIMATE_FRESH else None


def first_capture_decision(
    db: Session, policy: models.BackupPolicy, target: models.BackupTarget, now: datetime
) -> str:
    """GO, RUN_ESTIMATE or HOLD for a SCHEDULED capture."""
    if not first_capture_pending(db, policy):
        return GO
    if jobs.pending(db, policy.id, ESTIMATE):
        return HOLD  # its answer is on the way
    recent = _estimate_recent(db, policy, now)
    if recent is None:
        return RUN_ESTIMATE
    if recent.status != "ok":
        logger.warning(
            "Backup policy %s: the first-backup estimate ended %s on host %s; "
            "backing up without it",
            policy.id,
            recent.status,
            policy.host_id,
        )
        return GO
    found = fit(db, policy, target)
    if found is None or found["fits"]:
        return GO
    logger.warning(
        "Backup policy %s: host %s's first backup may not fit -- about %d bytes "
        "to keep, %d free under %s; held until there is room or paths are left "
        "out (Back up now still runs it)",
        policy.id,
        policy.host_id,
        found["estimate_bytes"],
        found["available_bytes"],
        target.storage_path,
    )
    return HOLD
