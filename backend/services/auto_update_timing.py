# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Automatic runs inside maintenance windows (ROADMAP 26.2, Enterprise).

For a host that maintenance windows apply to, a run starts only inside a
window -- and only if it is expected to finish before the window closes.  A
policy that fires while the host's window is closed records the run as
``waiting`` with the time its window opens; when that time comes, the tick
plans the run again (so it applies what is pending and eligible *then*, not
what was a week earlier) and sends it.  A blackout always wins, and an
emergency override never lets an automatic run or reboot through (see
``outbound_processor.automatic_held``).

A host no window applies to behaves exactly as 26.1.  Every decision is the
``automation_engine``'s (``window_start``, ``estimate_run_minutes``); an
engine older than 26.2 leaves runs unaligned, as 26.1.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from backend.persistence import models
from backend.services.maintenance_window_service import host_timing

logger = logging.getLogger(__name__)

WAITING = "waiting"
NO_WINDOW = "no_window_long_enough"
POLICY_CHANGED = "policy_changed"
START_TOLERANCE = timedelta(seconds=90)
HISTORY_RUNS = 5


def aligned(eng) -> bool:
    """Does this engine know about windows (26.2)?"""
    return eng is not None and hasattr(eng, "window_start")


def history(db, host_id) -> list:
    """The host's recent finished runs, as ``{"packages", "minutes"}``, for
    the engine's estimate of how long the next one takes."""
    runs = (
        db.query(models.AutoUpdateRun)
        .filter(
            models.AutoUpdateRun.host_id == host_id,
            models.AutoUpdateRun.status.in_(("succeeded", "partial")),
            models.AutoUpdateRun.completed_at.isnot(None),
        )
        .order_by(models.AutoUpdateRun.completed_at.desc())
        .limit(HISTORY_RUNS)
        .all()
    )
    out = []
    for run in runs:
        started = run.release_at or run.queued_at
        packages = (run.applied_count or 0) + (run.failed_count or 0)
        if started is None or not packages:
            continue
        out.append(
            {
                "packages": packages,
                "minutes": (run.completed_at - started).total_seconds() / 60,
            }
        )
    return out


def slot(db, eng, host, profile: Dict[str, Any], count: int, now, offset=0):
    """When a run of ``count`` packages on ``host`` may start, as the
    engine's ``window_start`` answer -- or None when the engine predates
    26.2 (then the run is released as in 26.1)."""
    if not aligned(eng):
        return None
    minutes = eng.estimate_run_minutes(
        count,
        history(db, host.id),
        profile.get("reboot_mode") == "in_window",
    )
    return eng.window_start(host_timing(db, host.id, now), now, offset, minutes)


def reboot_fits_now(db, eng, host, now) -> bool:
    """With "reboot only inside a maintenance window": is the host inside a
    window with time left for a reboot?"""
    if not aligned(eng):
        return True
    answer = eng.window_start(host_timing(db, host.id, now), now, 0, eng.REBOOT_MINUTES)
    return answer["start"] is not None and answer["start"] <= now


def waiting_host_ids(db) -> set:
    """Hosts with a run waiting for its window: a policy firing again leaves
    them alone instead of planning a second run."""
    return {
        str(host_id)
        for (host_id,) in db.query(models.AutoUpdateRun.host_id).filter(
            models.AutoUpdateRun.status == WAITING
        )
    }


def _close(run, status, reason, now, skipped=None) -> None:
    run.status, run.reason, run.completed_at = status, reason, now
    run.packages = []
    if skipped is not None:
        run.skipped = skipped


def _profile(db, run) -> Optional[models.UpgradeProfile]:
    return db.get(models.UpgradeProfile, run.profile_id) if run.profile_id else None


def start_waiting_runs(db, eng, now) -> int:
    """Send each run whose window has opened, planned again now.  A held
    policy's run keeps waiting; one whose policy was turned off or deleted
    is closed.  Returns how many were sent."""
    from backend.services import (  # pylint: disable=import-outside-toplevel
        auto_update_runner as runner,
    )

    started = 0
    due = (
        db.query(models.AutoUpdateRun)
        .filter(
            models.AutoUpdateRun.status == WAITING,
            models.AutoUpdateRun.release_at <= now,
        )
        .all()
    )
    settings = runner.settings_dict(runner.settings_row(db))
    for run in due:
        row = _profile(db, run)
        host = db.get(models.Host, run.host_id)
        if row is None or host is None or not (row.enabled and row.auto_apply):
            _close(run, "skipped", POLICY_CHANGED, now)
            continue
        if row.held:
            continue
        hosts = runner.profile_host_ids(db, [row.id]).get(str(row.id))
        profile = runner.profile_dict(row, hosts)
        plan = runner.plan(db, eng, host, profile, settings, now)
        if plan["action"] == "skip":
            _close(run, "skipped", plan["reason"], now, plan.get("skipped") or [])
            continue
        if plan["action"] == "nothing":
            _close(run, "nothing_to_do", None, now, plan.get("skipped") or [])
            continue
        answer = slot(db, eng, host, profile, len(plan["packages"]), now)
        if answer is not None and answer["start"] is None:
            _close(run, "skipped", NO_WINDOW, now, plan.get("skipped") or [])
            continue
        if answer is not None and answer["start"] > now + START_TOLERANCE:
            run.release_at = answer["start"]  # the window closed meanwhile
            continue
        runner.send(db, host, run, plan, now, now)
        started += 1
    return started
