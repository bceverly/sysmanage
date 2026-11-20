# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Federation site-side backup STATUS rollup (Phase 27.1).

Backup data is heavy, so each federated site server owns its own backup
target, and every byte of its backups stays at the site.  The coordinator
gets only this status snapshot, the same way it gets the compliance and
vulnerability rollups: hosts covered, hosts needing attention, the oldest
last good backup (the site's worst recovery point), total repository size
and the verification states, plus a short list of the hosts that need a
look, and (27.3) each of its targets by name, location, use and health.  No
paths, storage hosts, snapshot names, file lists or keys leave the site.

The snapshot is built from the Backups page's own overview, which reads
every host's runs; the sync tick runs every few seconds, so a new snapshot
is taken at most once per ``REFRESH_SECONDS`` per database.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.services import federation_coordinator_service as coord_svc
from backend.services import federation_sync_queue_service as sync_svc

BACKUP_ROLLUP_PAYLOAD_TYPE = "backup_rollup"
BACKUP_ROLLUP_DEDUP_KEY = "backup_rollup:self"
REFRESH_SECONDS = 300.0
# How many hosts needing attention are named (the rest are counted).
MAX_ATTENTION_HOSTS = 10

# When each database's snapshot was last taken (time.monotonic()).
_last_taken: Dict[str, float] = {}


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _last_good_at(row: Dict[str, Any]) -> Optional[str]:
    good = row.get("last_good_capture") or {}
    return good.get("finished_at")


def _attention_hosts(rows: List[Dict[str, Any]], statuses) -> List[Dict[str, Any]]:
    """The hosts needing a look, oldest last good backup first (never
    backed up first of all), at most MAX_ATTENTION_HOSTS."""
    wanted = [row for row in rows if row["status"] in statuses]
    wanted.sort(key=lambda row: (_last_good_at(row) is not None, _last_good_at(row)))
    return [
        {
            "host_id": row["host_id"],
            "fqdn": row["fqdn"],
            "status": row["status"],
            "last_good_at": _last_good_at(row),
        }
        for row in wanted[:MAX_ATTENTION_HOSTS]
    ]


def collect_backup_rollup(session: Session) -> Dict[str, Any]:
    """This site's backup status, as the coordinator stores it."""
    from backend.services import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
        backup_views as views,
    )

    data = views.overview(session)
    covered = [row for row in data["hosts"] if row["policy"]]
    status_counts: Dict[str, int] = {}
    verification_counts: Dict[str, int] = {}
    for row in covered:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        state = (row.get("verification") or {}).get("state")
        if state:
            verification_counts[state] = verification_counts.get(state, 0) + 1
    good_times = [
        when for when in (_parse(_last_good_at(row)) for row in covered) if when
    ]
    return {
        "configured": data["target"] is not None,
        "target_problem": views.target_problem(data),
        "hosts_with_policy": len(covered),
        "attention_count": views.attention_count(data),
        "never_backed_up": sum(1 for row in covered if not _last_good_at(row)),
        "repository_bytes": sum(
            int(row["policy"].get("repository_bytes") or 0) for row in covered
        ),
        "oldest_last_good_at": min(good_times).isoformat() if good_times else None,
        "status_counts": status_counts,
        "verification_counts": verification_counts,
        "attention_hosts": _attention_hosts(covered, views.ATTENTION_STATUSES),
        "readiness_counts": _readiness_counts(session),
        "targets": _targets(data),
    }


# How many of a site's targets are reported (the rest are left out).
MAX_TARGETS = 20


def _targets(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Each of this site's targets (27.3): its name and location, whether it
    is the default, how many hosts use it, whether its storage side has a
    problem, and how full it is -- never its paths or storage host."""
    found = []
    for target in (data.get("targets") or [])[:MAX_TARGETS]:
        space = ((target.get("storage_health") or {}).get("space")) or {}
        found.append(
            {
                "name": target.get("name"),
                "location": target.get("location"),
                "is_default": bool(target.get("is_default")),
                "hosts": int(target.get("hosts") or 0),
                "problem": bool(target.get("problem")),
                "used_percent": space.get("used_percent"),
            }
        )
    return found


def _readiness_counts(session: Session) -> Optional[Dict[str, int]]:
    """Hosts by restore readiness (27.1) where this site has the Enterprise
    backup_ops_engine; None elsewhere.  Never fails the snapshot."""
    from backend.services import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
        backup_jobs,
        backup_readiness,
    )

    eng = backup_readiness.engine()
    if eng is None:
        return None
    try:
        return backup_readiness.fleet(session, eng, backup_jobs.now())["counts"]
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def _database_key(session: Session) -> str:
    bind = session.get_bind()
    return str(getattr(bind, "url", id(bind)))


def enqueue_backup_rollup(session: Session, *, force: bool = False) -> Optional[Any]:
    """Queue this site's backup status for the coordinator, if enrolled and
    the last snapshot is older than REFRESH_SECONDS (``force`` skips that
    wait).  A queued snapshot not yet sent is replaced (dedup key)."""
    if not coord_svc.is_enrolled(session):
        return None
    key = _database_key(session)
    now = time.monotonic()
    taken = _last_taken.get(key)
    if not force and taken is not None and now - taken < REFRESH_SECONDS:
        return None
    row = sync_svc.enqueue(
        session,
        payload_type=BACKUP_ROLLUP_PAYLOAD_TYPE,
        payload=collect_backup_rollup(session),
        dedup_key=BACKUP_ROLLUP_DEDUP_KEY,
    )
    _last_taken[key] = now
    return row
