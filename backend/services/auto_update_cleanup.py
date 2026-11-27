# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Automatic updates clean up after themselves (ROADMAP 27.8).

Once a host's automatic update run is finished -- applied, and any reboot it
asked for has come back -- the host's old kernels and unneeded packages are
removed (``cleanup_mode`` "apply", the default) or only planned ("report").
The safety model is ``kernel_boots.protected``: while the host's running
kernel is not yet proven (it has just booted it) nothing is sent, and the
tick tries again a minute later; the kernel the host last booted
successfully is always kept.  The apply is an ordinary maintenance-window-
gated command, so it runs inside the host's window like the update did.

One cleanup per finished run; a run older than ``HORIZON`` is left alone.
"""

import logging
from datetime import timedelta

from backend.persistence import models
from backend.services import kernel_boots, package_cleanup

logger = logging.getLogger(__name__)

HORIZON = timedelta(days=3)
FINISHED = ("succeeded", "partial", "nothing_to_do")
# A reboot that is still to happen (or happening) is not finished.
REBOOT_PENDING = ("queued", "next_window", "unsafe")


def _wants_cleanup(db, run) -> bool:
    if run.reboot_status in REBOOT_PENDING or run.reboot_status == "not_back":
        return False
    done = (
        db.query(models.PackageCleanupRun.id)
        .filter(models.PackageCleanupRun.host_id == run.host_id,
                models.PackageCleanupRun.trigger == "auto_update",
                models.PackageCleanupRun.created_at >= run.completed_at)
        .first()
    )  # fmt: skip
    return done is None


def after_runs(db, now, mode: str) -> int:
    """Queue the cleanup for each finished run; returns how many."""
    if mode not in ("apply", "report"):
        return 0
    queued = 0
    runs = (
        db.query(models.AutoUpdateRun)
        .filter(models.AutoUpdateRun.status.in_(FINISHED),
                models.AutoUpdateRun.completed_at >= now - HORIZON)
        .order_by(models.AutoUpdateRun.completed_at.desc())
        .all()
    )  # fmt: skip
    seen = set()
    for run in runs:
        if run.host_id in seen:
            continue  # only a host's latest finished run
        seen.add(run.host_id)
        host = db.get(models.Host, run.host_id)
        if host is None or not _wants_cleanup(db, run):
            continue
        refusal, _keep = kernel_boots.protected(
            db, host, package_cleanup.installed_kernels(db, host)
        )
        if refusal:
            continue  # not proven yet (just rebooted) or no history: next tick
        package_cleanup.request(
            db, host, "apply" if mode == "apply" else "plan", None,
            trigger="auto_update", approve_plan=True,
        )  # fmt: skip
        queued += 1
    return queued
