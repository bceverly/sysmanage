# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backups as fleet coverage for the posture punch list (ROADMAP 24.6).

Four ``sm_coverage`` rows the advisor engine's PM-BACKUP-* checks read, one
state per APPROVED host -- ok, failing, unknown, or None when the control
does not apply to that host:

* ``backup_policy``     a host restate can back up has an enabled policy
                        (a host restate cannot back up does not count);
* ``backup_healthy``    its last backup did not fail and is not overdue
                        (a first backup still to come is unknown, never ok);
* ``backup_verified``   a full-read verification passed within 30 days, the
                        same bar as compliance check SYSMANAGE-BACKUP-1
                        (only where the Pro+ backup engine can verify);
* ``backup_key_escrow`` an encrypted host's keys were exported (break-glass)
                        after its newest key was made -- an export from
                        before a rotation lacks the key newer snapshots need.

What a host's backup status IS comes from the Backups page's own reading
(``backup_views``), so the posture item and the page never disagree.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_verify
from backend.services import backup_views as views

BACKUP_COVERAGE_KEYS = (
    "backup_policy",
    "backup_healthy",
    "backup_verified",
    "backup_key_escrow",
)
VERIFIED_WITHIN = timedelta(days=30)  # SYSMANAGE-BACKUP-1's max_age_days
# The audit entry backup_engine writes for each host in a break-glass export.
BREAK_GLASS_AUDIT = "Backup keys exported (break-glass)"

_FAILING_STATUSES = ("failed", "overdue")


def _naive(when: Optional[datetime]) -> Optional[datetime]:
    if when is not None and when.tzinfo is not None:
        return when.astimezone(timezone.utc).replace(tzinfo=None)
    return when


def _policy_state(host, policy) -> Optional[str]:
    if views.coverage(host) == "unsupported":
        return None  # restate cannot back it up: not a gap
    return "ok" if policy is not None and policy.enabled else "failing"


def _healthy_state(db: Session, host, policy, now: datetime) -> Optional[str]:
    if policy is None or not policy.enabled:
        return None
    if not jobs.equipped(host)[0]:
        return "failing"  # it cannot back up at all
    last = jobs.latest_run(db, policy.id, "capture", statuses=jobs.FINAL)
    status = views._status(db, policy, last, now)  # pylint: disable=protected-access
    if status in _FAILING_STATUSES:
        return "failing"
    return "unknown" if status == "never" else "ok"


def _verified_state(db: Session, policy, now: datetime) -> Optional[str]:
    if policy is None or not policy.enabled:
        return None
    good = jobs.latest_run(
        db, policy.id, backup_verify.VERIFY, statuses=backup_verify.GOOD
    )
    ended = _naive((good.finished_at or good.queued_at) if good is not None else None)
    return "ok" if ended is not None and now - ended <= VERIFIED_WITHIN else "failing"


def _newest_key_at(db: Session, policy) -> Optional[datetime]:
    made = (
        db.query(func.max(models.BackupPolicyKey.created_at))
        .filter(models.BackupPolicyKey.policy_id == policy.id)
        .scalar()
    )
    candidates = [
        _naive(t) for t in (made, policy.encrypted_at, policy.encrypt_rotated_at) if t
    ]
    return max(candidates) if candidates else None


def _escrow_state(db: Session, host, policy) -> Optional[str]:
    if policy is None or not policy.encrypt_fingerprint:
        return None
    since = _newest_key_at(db, policy)
    exported = (
        db.query(func.max(models.AuditLog.timestamp))
        .filter(
            models.AuditLog.entity_id == str(host.id),
            models.AuditLog.description == BREAK_GLASS_AUDIT,
        )
        .scalar()
    )
    exported = _naive(exported)
    if exported is None:
        return "failing"
    return "ok" if since is None or exported > since else "failing"


def _verification_possible() -> bool:
    """Full-read verification is a Pro+ backup engine job: without it no
    host can pass, so the control does not apply rather than failing all."""
    return backup_verify._engine() is not None  # pylint: disable=protected-access


def coverage(
    db: Session,
    hosts: List[Any],
    now: datetime,
    counted: Callable[[str, List[Optional[str]]], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """The four backup coverage rows for ``hosts`` (approved), built with the
    posture gatherer's own ``counted`` (``posture_evidence._coverage``)."""
    policies = {
        str(p.host_id): p
        for p in db.query(models.BackupPolicy).filter(
            models.BackupPolicy.host_id.in_([h.id for h in hosts])
        )
    }
    can_verify = _verification_possible()
    states: Dict[str, List[Optional[str]]] = {k: [] for k in BACKUP_COVERAGE_KEYS}
    for host in hosts:
        policy = policies.get(str(host.id))
        states["backup_policy"].append(_policy_state(host, policy))
        states["backup_healthy"].append(_healthy_state(db, host, policy, now))
        states["backup_verified"].append(
            _verified_state(db, policy, now) if can_verify else None
        )
        states["backup_key_escrow"].append(_escrow_state(db, host, policy))
    return [counted(key, states[key]) for key in BACKUP_COVERAGE_KEYS]
