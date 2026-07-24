# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Repository-mirroring engine-path result-apply handlers.

Extracted from ``backend.services.proplus_dispatch`` to keep that module under
pylint's max-module-lines cap.  Everything here is re-imported back into
``proplus_dispatch`` under its original private name, so the result-router and
its ``_SIMPLE_RESULT_HANDLERS`` table are unchanged.

These handlers translate a completed ``repository_mirroring_engine`` plan
``outcome`` into the OSS ``mirror_repository`` / ``mirror_setup_status`` /
``mirror_snapshot`` row updates.  A handful of dispatch primitives
(``enqueue_apply_plan``, ``_register_correlation``, ``_now_naive``,
``_best_failure_text``, ``_parse_rsync_stats``) live in ``proplus_dispatch`` and
are imported lazily inside the functions that need them to avoid a circular
import at module load.
"""

import logging
from typing import Any, Dict

from backend.licensing.module_loader import module_loader
from backend.persistence import db, models

logger = logging.getLogger(__name__)


def _apply_repo_mirror_op_result(
    primary_id: str, host_id: str, outcome: Dict[str, Any]
) -> None:
    """Handle completion of a repository_mirroring_engine plan.

    ``primary_id`` is ``"<action>:<mirror_id>"``.  Action drives which
    OSS row gets updated:

      sync / snapshot / restore / integrity_check / gc
          → update ``mirror_repository.last_sync_status`` /
            ``last_sync_error`` for the named mirror_id.

      setup_check
          → parse the probe stdout (key=value lines) and upsert
            ``mirror_setup_status`` for the host.

      setup_install
          → mark the install as ``succeeded`` / ``failed`` on the
            ``mirror_setup_status`` row, then queue a follow-up
            ``setup_check`` so the UI reflects post-install tool
            presence without a manual refresh.
    """
    if ":" not in primary_id:
        action, mirror_id = primary_id, ""
    else:
        action, mirror_id = primary_id.split(":", 1)

    session_local = db.get_session_local()
    with session_local() as session:
        if action in ("sync", "snapshot", "restore", "integrity_check", "gc"):
            _apply_mirror_sync_status(session, action, mirror_id, outcome)
        elif action == "snap_capture":
            _apply_snap_capture_result(session, mirror_id, outcome)
        elif action == "setup_check":
            _apply_mirror_setup_check(session, host_id, outcome)
        elif action == "setup_install":
            _apply_mirror_setup_install(session, host_id, outcome)
        elif action in ("default_apply", "default_revert"):
            # Phase 10.4.4 — pointing a client host at (or away from)
            # the locally-hosted mirror.  No row update needed on the
            # OSS side since the assignment was committed BEFORE the
            # plan was queued; the result here is informational only.
            # We log success/failure so a future audit-log endpoint
            # can surface it.
            if outcome["status"] != "succeeded":
                logger.warning(
                    "Mirror default %s failed for host %s: %s",
                    action,
                    host_id,
                    outcome["stderr"] or outcome["error"],
                )
        else:
            logger.warning(
                "Unknown repo_mirror_op action %r (mirror_id=%s host_id=%s)",
                action,
                mirror_id,
                host_id,
            )
            return
        session.commit()

    if action == "setup_install" and outcome["status"] == "succeeded":
        _queue_followup_setup_check(host_id, session_local)


def _queue_followup_setup_check(host_id: str, session_local) -> None:
    """Auto-chain a setup_check after a successful install so the card
    reflects the new tool presence.  The follow-up message rides the
    same outbound queue + result-routing path.  Stamp
    ``last_check_message_id`` on the row before returning, or the
    frontend's polling loop (which keys off non-NULL message_id markers)
    sees both flags clear and stops polling before the auto-probe result
    lands."""
    # pylint: disable=import-outside-toplevel
    from backend.services.proplus_dispatch import (
        _register_correlation,
        enqueue_apply_plan,
    )

    try:
        mirror_engine = module_loader.get_module("repository_mirroring_engine")
        if mirror_engine is None:
            return
        probe_plan = mirror_engine.build_mirror_setup_check_plan()
        msg_id = enqueue_apply_plan(host_id=str(host_id), plan=probe_plan, timeout=60)
        _register_correlation(msg_id, "repo_mirror_op", "setup_check:", str(host_id))
        with session_local() as probe_session:
            row = (
                probe_session.query(models.MirrorSetupStatus)
                .filter(models.MirrorSetupStatus.host_id == host_id)
                .first()
            )
            if row is not None:
                row.last_check_message_id = msg_id
                probe_session.commit()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Failed to queue follow-up setup_check after install on host %s: %s",
            host_id,
            exc,
        )


# Map a plan ``action`` string to the column prefix on
# ``mirror_repository`` that records its outcome.  ``integrity_check``
# is collapsed to ``integrity`` for shorter column names.
_ACTION_COLUMN_PREFIX = {
    "sync": "last_sync",
    "snapshot": "last_snapshot",
    "restore": "last_restore",
    "integrity_check": "last_integrity",
    "gc": "last_gc",
}


def _apply_snap_capture_result(
    session, mirror_id: str, outcome: Dict[str, Any]
) -> None:
    """Flip a mirror's in-flight (DISPATCHED) ``mirror_snap_content`` rows to
    CAPTURED / FAILED after a ``snap_proxy_engine`` capture plan completes.

    The capture plan captures all of a mirror's tracked snaps in one dispatch,
    so the whole DISPATCHED set for the mirror moves together.  On success the
    blobs + assertions are on disk under the mirror's ``snaps`` dir (a later
    content-view publish materializes them into the version store); on failure
    the error text is recorded so the UI can surface it.
    """
    # pylint: disable=import-outside-toplevel
    from backend.services.proplus_dispatch import _best_failure_text, _now_naive

    if not mirror_id:
        return
    rows = (
        session.query(models.MirrorSnapContent)
        .filter(
            models.MirrorSnapContent.repository_id == mirror_id,
            models.MirrorSnapContent.capture_status == "DISPATCHED",
        )
        .all()
    )
    if not rows:
        return
    now = _now_naive()
    succeeded = outcome["status"] == "succeeded"
    error_value = None if succeeded else _best_failure_text(outcome)[:8000]
    for row in rows:
        row.capture_status = "CAPTURED" if succeeded else "FAILED"
        row.last_capture_at = now
        row.error_message = error_value
        row.last_capture_message_id = None
        row.updated_at = now


def _apply_mirror_sync_status(
    session, action: str, mirror_id: str, outcome: Dict[str, Any]
) -> None:
    """Update the action-specific ``mirror_repository.last_<action>_*`` group.

    Each action (sync/snapshot/restore/integrity_check/gc) writes to
    its own ``_at`` / ``_status`` / ``_error`` / ``_message_id`` columns
    so a failed snapshot no longer overwrites a previously successful
    sync — the UI shows one chip per action.

    Side effects for snapshot:
        * Always clears the in-flight ``_message_id``.
        * On success, parses rsync ``--stats`` output (the second
          command in the snapshot plan) and populates the matching
          ``MirrorSnapshot`` row's ``size_bytes`` + ``file_count``.
        * On failure, deletes the placeholder ``MirrorSnapshot`` row
          (inserted at dispatch time) so the snapshots list doesn't
          accumulate ghosts.
    """
    # pylint: disable=import-outside-toplevel
    from backend.services.proplus_dispatch import _best_failure_text, _now_naive

    if not mirror_id:
        return
    row = (
        session.query(models.MirrorRepository)
        .filter(models.MirrorRepository.id == mirror_id)
        .first()
    )
    if row is None:
        logger.info("Mirror %s no longer exists; dropping %s result", mirror_id, action)
        return
    prefix = _ACTION_COLUMN_PREFIX.get(action)
    if prefix is None:
        logger.warning(
            "Mirror result for unknown action %r (mirror_id=%s) — no column to write",
            action,
            mirror_id,
        )
        return

    now = _now_naive()
    succeeded = outcome["status"] == "succeeded"
    status_value = "SUCCESS" if succeeded else "FAILED"
    error_value = None if succeeded else _best_failure_text(outcome)[:8000]

    setattr(row, f"{prefix}_at", now)
    setattr(row, f"{prefix}_status", status_value)
    setattr(row, f"{prefix}_error", error_value)
    # Clear the in-flight marker regardless of outcome — the operator
    # needs the UI to leave the spinner state either way.
    setattr(row, f"{prefix}_message_id", None)

    # Track consecutive sync failures so ``tick_mirrors`` can back off
    # and eventually auto-disable a mirror that keeps failing (e.g. one
    # too large to sync without OOMing its host) instead of redispatching
    # it every cron tick.  Reset on success.
    if action == "sync":
        if succeeded:
            row.consecutive_sync_failures = 0
        else:
            row.consecutive_sync_failures = (row.consecutive_sync_failures or 0) + 1

    if action == "snapshot":
        _post_snapshot_outcome(session, mirror_id, succeeded, outcome)
    elif action == "restore":
        _post_restore_outcome(session, mirror_id, succeeded)


def _post_snapshot_outcome(
    session, mirror_id: str, succeeded: bool, outcome: Dict[str, Any]
) -> None:
    """Reconcile the ``MirrorSnapshot`` placeholder row with the agent result.

    The dispatch endpoint inserts a snapshot row eagerly (so the UI
    can show "in progress") — here we either fill in its size/file
    count on success, or delete it on failure so the list doesn't
    accumulate phantom snapshots.
    """
    # pylint: disable=import-outside-toplevel
    from backend.services.proplus_dispatch import _parse_rsync_stats

    # The placeholder row is the most recently created snapshot for
    # this mirror; the dispatch endpoint stamps ``taken_at = now`` so
    # ordering by ``taken_at`` desc gives us the right one.
    placeholder = (
        session.query(models.MirrorSnapshot)
        .filter(models.MirrorSnapshot.repository_id == mirror_id)
        .order_by(models.MirrorSnapshot.taken_at.desc())
        .first()
    )
    if placeholder is None:
        return
    if not succeeded:
        session.delete(placeholder)
        return
    # On success, parse rsync ``--stats`` output from the rsync
    # command in the plan (description starts with "rsync live tree").
    for cmd in outcome.get("commands") or []:
        description = cmd.get("description") or ""
        if "rsync" in description and cmd.get("success"):
            stats = _parse_rsync_stats(cmd.get("stdout") or "")
            if stats["size_bytes"] is not None:
                placeholder.size_bytes = stats["size_bytes"]
            if stats["file_count"] is not None:
                placeholder.file_count = stats["file_count"]
            break


def _post_restore_outcome(session, mirror_id: str, succeeded: bool) -> None:
    """Hook for future restore-side bookkeeping.

    Currently a no-op — the restore action doesn't have per-snapshot
    state to reconcile.  Carved out so the snapshot-side logic stays
    in its own helper and a future "mark snapshot as restored from"
    feature has an obvious place to live.
    """
    _ = session, mirror_id, succeeded  # documenting intent


_PROBE_TOOL_KEYS = {
    "apt-mirror",
    "apt-mirror2",
    "reposync",
    "createrepo_c",
    "trickle",
    "rsync",
    "curl",
    "sha256sum",
    "xz",
    "gzip",
    "bzip2",
}


def _parse_setup_check_stdout(stdout: str) -> Dict[str, Any]:
    """Parse the probe's ``key=value`` lines into a structured dict.

    Returns ``{"tools": {<tool>: "present"|"missing"}, "platform": str,
    "distro": str}``.  Unknown keys are dropped so a malicious agent
    can't inject arbitrary fields into the JSON column.
    """
    tools: Dict[str, str] = {}
    platform = ""
    distro = ""
    for line in (stdout or "").splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key in _PROBE_TOOL_KEYS and value in ("present", "missing"):
            tools[key] = value
        elif key == "platform":
            platform = value[:40]
        elif key == "distro":
            distro = value[:40]
    return {"tools": tools, "platform": platform, "distro": distro}


def _apply_mirror_setup_check(session, host_id: str, outcome: Dict[str, Any]) -> None:
    """Upsert ``mirror_setup_status`` from the probe's stdout."""
    # pylint: disable=import-outside-toplevel
    from backend.services.proplus_dispatch import _now_naive

    parsed = _parse_setup_check_stdout(outcome["stdout"])
    now = _now_naive()
    row = (
        session.query(models.MirrorSetupStatus)
        .filter(models.MirrorSetupStatus.host_id == host_id)
        .first()
    )
    if row is None:
        row = models.MirrorSetupStatus(host_id=host_id)
        session.add(row)
    row.tools = parsed["tools"]
    row.platform = parsed["platform"] or row.platform
    row.distro = parsed["distro"] or row.distro
    row.last_check_at = now
    row.last_check_message_id = None  # probe completed; clear in-flight marker
    if outcome["status"] == "succeeded":
        row.last_check_error = None
    else:
        row.last_check_error = (
            outcome["stderr"] or outcome["error"] or "probe failed"
        )[:8000]


def _apply_mirror_setup_install(session, host_id: str, outcome: Dict[str, Any]) -> None:
    """Stamp install_status + clear the in-flight marker."""
    # pylint: disable=import-outside-toplevel
    from backend.services.proplus_dispatch import _now_naive

    now = _now_naive()
    row = (
        session.query(models.MirrorSetupStatus)
        .filter(models.MirrorSetupStatus.host_id == host_id)
        .first()
    )
    if row is None:
        row = models.MirrorSetupStatus(host_id=host_id)
        session.add(row)
    row.last_install_at = now
    row.last_install_message_id = None
    if outcome["status"] == "succeeded":
        row.install_status = "succeeded"
        row.last_install_error = None
    else:
        row.install_status = "failed"
        row.last_install_error = (
            outcome["stderr"] or outcome["error"] or "install failed"
        )[:8000]
