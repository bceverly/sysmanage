# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The drift timeline (Pro+ backup_engine, ROADMAP 24.7).

After each good capture the host compares the new snapshot with the one
before it -- restate ``diff --packages`` as a host job, read from the two
indexes (keys released for that one run when the repository is encrypted)
-- and the result is kept as a ``backup_snapshot_diff`` row: what was added,
deleted and modified, and which packages were installed, removed or
upgraded, the file changes they account for left out.  The timeline is those
rows, newest first; the engine filters out expected churn (logs, caches,
the policy's own ignore patterns) and narrows to a path when asked.

The OSS side only queues, stores and serves; without the engine nothing is
queued and the API answers 402.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.websocket.messages import CommandType

logger = logging.getLogger(__name__)

# What restate keeps of a diff in its result (the first 1000 of each).
_MAX_STORED = 1000
_OK = ("ok", "different")  # restate exit 0 (none) and 1 (they differ)


def engine():
    """The Pro+ backup engine when it can build the timeline, else None."""
    module = module_loader.get_module("backup_engine")
    return module if module is not None and hasattr(module, "drift_view") else None


def _name(value: Any) -> Optional[str]:
    """A snapshot name from restate's ``REPO::NAME`` (or a bare name)."""
    if not isinstance(value, str) or not value:
        return None
    return value.rsplit("::", 1)[-1][:255]


def queue_diff(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session,
    policy: models.BackupPolicy,
    host_id: Any,
    from_name: Optional[str],
    to_name: Optional[str],
    actor: str = jobs.SYSTEM_ACTOR,
) -> models.BackupRun:
    """Compare two snapshots of the host's current repository on the host
    (``to`` the newest and ``from`` the one before when not named)."""
    params: Dict[str, Any] = {"policy_id": str(policy.id), "action": jobs.DIFF}
    if from_name:
        params["from"] = from_name
    if to_name:
        params["to"] = to_name
    if jobs.encrypted(policy):
        params["needs_key"] = True  # fetched by the agent, never sent here
    return jobs._queue(  # pylint: disable=protected-access
        db, policy, host_id, jobs.DIFF, CommandType.BACKUP_RUN, params, actor
    )


def _in_current(policy: models.BackupPolicy):
    snapshot = models.BackupSnapshot
    if policy.repository_dir is None:
        return snapshot.repository_dir.is_(None)
    return snapshot.repository_dir == policy.repository_dir


def previous_snapshot(
    db: Session, policy: models.BackupPolicy, name: str
) -> Optional[str]:
    """The live snapshot of the current repository just before ``name``
    (snapshot names sort by time: ``YYYYMMDDTHHMMSSZ``)."""
    snapshot = models.BackupSnapshot
    row = (
        db.query(snapshot.name)
        .filter(
            snapshot.policy_id == policy.id,
            snapshot.gone_at.is_(None),
            snapshot.name < name,
            _in_current(policy),
        )
        .order_by(snapshot.name.desc())
        .first()
    )
    return row[0] if row else None


def _known(db: Session, policy, from_name: str, to_name: str) -> bool:
    diff = models.BackupSnapshotDiff
    return (
        db.query(diff.id)
        .filter(
            diff.policy_id == policy.id,
            diff.from_snapshot == from_name,
            diff.to_snapshot == to_name,
        )
        .first()
        is not None
    )


def after_capture(
    db: Session, policy: models.BackupPolicy, run: models.BackupRun
) -> None:
    """A good capture: compare it with the snapshot before it, when the
    engine is licensed and the host's restate can (``diff`` ability)."""
    if not run.snapshot or engine() is None or "diff" not in jobs.abilities(policy):
        return
    before = previous_snapshot(db, policy, run.snapshot)
    if before is None or _known(db, policy, before, run.snapshot):
        return
    if jobs.pending(db, policy.id, jobs.DIFF):
        return  # one at a time; the timeline offers to compare a missed pair
    queue_diff(db, policy, run.host_id, before, run.snapshot)


def _count(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _entries(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [e for e in value[:_MAX_STORED] if isinstance(e, dict)]


def after_diff(
    db: Session, run: models.BackupRun, policy: models.BackupPolicy, result: Dict
) -> None:
    """Keep a finished diff as the pair's row (replacing a failed one)."""
    params = json.loads(run.parameters or "{}")
    from_name = _name(result.get("from")) or params.get("from")
    to_name = _name(result.get("to")) or params.get("to")
    if not from_name or not to_name:
        logger.warning(
            "Backup diff %s for policy %s named no snapshots", run.id, policy.id
        )
        return
    diff = models.BackupSnapshotDiff
    row = (
        db.query(diff)
        .filter(
            diff.policy_id == policy.id,
            diff.from_snapshot == from_name,
            diff.to_snapshot == to_name,
        )
        .first()
    )
    if row is None:
        row = diff(policy_id=policy.id, host_id=run.host_id, from_snapshot=from_name,
                   to_snapshot=to_name)  # fmt: skip
        db.add(row)
    body = result.get("diff") if isinstance(result.get("diff"), dict) else {}
    row.run_id = run.id
    row.computed_at = jobs.now()
    row.status = "ok" if run.status in _OK else "failed"
    row.message = None if row.status == "ok" else (run.message or "")[:2000]
    for field in ("added", "deleted", "modified", "packages_changed", "explained"):
        setattr(row, field, _count(body.get(field)))
    row.changes = json.dumps(_entries(body.get("changes")))
    row.packages = json.dumps(_entries(body.get("packages")))
    row.truncated = body.get("truncated") is True
    row.packages_truncated = body.get("packages_truncated") is True
    db.flush()  # one row per pair, even for two results in one transaction


def ignore_patterns(policy: models.BackupPolicy) -> List[str]:
    """The policy's own expected-churn patterns."""
    try:
        found = json.loads(policy.drift_ignore or "[]")
    except ValueError:
        return []
    return [p for p in found if isinstance(p, str)] if isinstance(found, list) else []


def _row_dict(row: models.BackupSnapshotDiff) -> Dict[str, Any]:
    def load(text):
        try:
            value = json.loads(text or "[]")
        except ValueError:
            return []
        return value if isinstance(value, list) else []

    return {
        "from": row.from_snapshot,
        "to": row.to_snapshot,
        "status": row.status,
        "message": row.message,
        "computed_at": row.computed_at.isoformat() + "Z" if row.computed_at else None,
        "added": row.added,
        "deleted": row.deleted,
        "modified": row.modified,
        "packages_changed": row.packages_changed,
        "explained": row.explained,
        "truncated": bool(row.truncated),
        "packages_truncated": bool(row.packages_truncated),
        "changes": load(row.changes),
        "packages": load(row.packages),
    }


def missing_pairs(db: Session, policy: models.BackupPolicy) -> List[Dict[str, str]]:
    """Consecutive live snapshots of the current repository with no diff."""
    snapshot = models.BackupSnapshot
    names = [
        r[0]
        for r in db.query(snapshot.name)
        .filter(
            snapshot.policy_id == policy.id,
            snapshot.gone_at.is_(None),
            _in_current(policy),
        )
        .order_by(snapshot.name)
        .all()
    ]
    pairs = list(zip(names, names[1:]))
    return [{"from": a, "to": b} for a, b in pairs if not _known(db, policy, a, b)]


def timeline(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session,
    policy: models.BackupPolicy,
    module,
    hide_expected: bool = True,
    path: Optional[str] = None,
    limit: int = 30,
) -> Dict[str, Any]:
    """The policy's diffs, newest first, filtered by the engine."""
    diff = models.BackupSnapshotDiff
    rows = (
        db.query(diff)
        .filter(diff.policy_id == policy.id)
        .order_by(diff.to_snapshot.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    view = module.drift_view(
        [_row_dict(r) for r in rows],
        ignore_patterns(policy),
        hide_expected=hide_expected,
        path=path,
    )
    view["ignore"] = ignore_patterns(policy)
    view["missing"] = missing_pairs(db, policy)
    view["running"] = jobs.pending(db, policy.id, jobs.DIFF)
    return view
