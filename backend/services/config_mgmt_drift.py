# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Turning check-mode runs into drift findings (Phase 20.2).

A check-mode run already answers "what would change on this host" -- which is
the definition of drift against that profile. So there is no second collection
path here: this module reconciles the run that just landed against the open
findings for that (host, profile) pair.

RULES, AND WHY EACH ONE
-----------------------
* **Only CHECK-MODE runs produce findings.** A live run that changed something
  is not drift, it is a change we just made. Counting it would report the
  system's own remediation as a new problem.

* **Only a SUCCESSFUL run may resolve.** A check run that failed does not know
  the host's state, so treating its silence as "the drift is gone" would close
  findings on the strength of an error. A failed run is allowed to OPEN
  findings for whatever it did observe, but never to close any.

* **Only `changed` counts.** A failed task is an error, not a divergence.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from backend.persistence import models

logger = logging.getLogger(__name__)

# Task detail is truncated on ingest for long playbooks, so a finding's detail
# is capped too -- it is a hint pointing at the run, not a second copy of it.
MAX_DETAIL_CHARS = 1000


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def changed_tasks(tasks: Iterable[Any]) -> List[Dict[str, Any]]:
    """The tasks in a run that represent a divergence.

    A task counts when it reports ``changed``. In check mode "changed" means
    "would have changed", which is exactly the finding we want; a task that
    FAILED is an error to investigate, not a difference to remediate.
    """
    out: List[Dict[str, Any]] = []
    for task in tasks or []:
        if not isinstance(task, dict):
            continue
        if not task.get("changed"):
            continue
        name = task.get("task")
        if not name:
            # Without a name there is no identity to track across runs, so a
            # row here would be a new "finding" on every single tick.
            continue
        out.append({"name": str(name)[:500], "detail": task.get("msg")})
    return out


def _load_findings(db_session, run) -> Dict[str, Any]:
    """Existing findings for this (host, profile), keyed by task name."""
    return {
        row.task_name: row
        for row in db_session.query(models.ConfigDriftFinding)
        .filter(
            models.ConfigDriftFinding.host_id == run.host_id,
            models.ConfigDriftFinding.profile_id == run.profile_id,
        )
        .all()
    }


def _record_sighting(db_session, run, existing, task, now, summary) -> None:
    """Open a finding, or refresh the one that already tracks this task."""
    detail = task["detail"]
    detail = str(detail)[:MAX_DETAIL_CHARS] if detail else None
    row = existing.get(task["name"])

    if row is None:
        db_session.add(
            models.ConfigDriftFinding(
                host_id=run.host_id,
                profile_id=run.profile_id,
                profile_name=run.profile_name,
                task_name=task["name"],
                detail=detail,
                first_seen_at=now,
                last_seen_at=now,
                last_run_id=run.id,
            )
        )
        summary["opened"] += 1
        return

    if row.resolved_at is not None:
        # A REGRESSION. Clear the resolution and restart the clock: "drifting
        # since" must describe the current episode, or it claims continuous
        # drift across a period when the host was actually compliant.
        row.resolved_at = None
        row.first_seen_at = now
        summary["opened"] += 1
    else:
        summary["still_open"] += 1

    row.last_seen_at = now
    row.last_run_id = run.id
    row.detail = detail
    row.profile_name = run.profile_name


def _resolve_unseen(existing, observed_names, run, now, summary) -> None:
    """Close findings a SUCCESSFUL run no longer reports.

    Only a successful run may close anything: a failed check does not know the
    host's state, so treating its silence as "the drift is gone" would resolve
    findings on the strength of an error.
    """
    if not run.success:
        return
    for name, row in existing.items():
        if name not in observed_names and row.resolved_at is None:
            row.resolved_at = now
            row.last_run_id = run.id
            summary["resolved"] += 1


def reconcile_run(
    db_session, run, tasks: Iterable[Any], *, module_loaded: bool
) -> Dict[str, int]:
    """Update drift findings from one just-recorded run.

    Returns a summary for logging. Never raises: a drift bookkeeping problem
    must not fail the result handler and cost us the run record itself, which
    is the more valuable of the two.
    """
    summary = {"opened": 0, "still_open": 0, "resolved": 0}

    # Drift is Enterprise. Without the module there are no profiles to drift
    # from, so there is nothing to reconcile. A LIVE run is not drift either --
    # it changed things because we told it to.
    if not module_loaded or not run.check_mode or not run.profile_id:
        return summary

    try:
        now = _now()
        observed = changed_tasks(tasks)
        existing = _load_findings(db_session, run)

        for task in observed:
            _record_sighting(db_session, run, existing, task, now, summary)

        _resolve_unseen(existing, {t["name"] for t in observed}, run, now, summary)
    except Exception:  # pylint: disable=broad-except
        # The run row is the more valuable record; losing drift bookkeeping is
        # recoverable on the next check, losing the run is not.
        logger.exception("Drift reconciliation failed for run %s", run.id)

    return summary


def open_findings_for_host(db_session, host_id) -> List[models.ConfigDriftFinding]:
    """Unresolved findings for one host, longest-running first.

    Oldest-first because drift that has persisted is the interesting kind: a
    divergence seen once may be a race with a deploy, one standing for weeks
    is a configuration nobody is managing.
    """
    return (
        db_session.query(models.ConfigDriftFinding)
        .filter(
            models.ConfigDriftFinding.host_id == host_id,
            models.ConfigDriftFinding.resolved_at.is_(None),
        )
        .order_by(models.ConfigDriftFinding.first_seen_at.asc())
        .all()
    )


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Stamp a naive-UTC row value as UTC.

    Rows are stored naive; handing a naive value to a browser renders it as
    LOCAL time, which for this feature would misreport how long a host has
    been drifting -- the one number the dashboard exists to show.
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def finding_to_dict(row, host_fqdn: Optional[str] = None) -> Dict[str, Any]:
    """Serialise a finding for the API."""
    utc = as_utc
    return {
        "id": str(row.id),
        "host_id": str(row.host_id),
        "host_fqdn": host_fqdn,
        "profile_id": str(row.profile_id) if row.profile_id else None,
        "profile_name": row.profile_name,
        "task_name": row.task_name,
        "detail": row.detail,
        "first_seen_at": utc(row.first_seen_at),
        "last_seen_at": utc(row.last_seen_at),
        "resolved_at": utc(row.resolved_at),
        "last_run_id": str(row.last_run_id) if row.last_run_id else None,
    }
