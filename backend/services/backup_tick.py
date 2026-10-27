# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The backup scheduler tick (ROADMAP Phase 24, Community).

Every five minutes, in every host database, for each enabled policy on an
approved, active host whose agent can run backups:

1. job files -- (re)send ``backup_configure`` to the host and to the storage
   host until each has acknowledged the policy's ``config_version``;
2. capture -- a host's first scheduled one only once restate's estimate
   says it fits the target's free space (``backup_first_fit``); then, when
   due: ``interval_hours`` after the last good capture
   (sooner after a failure, later after ``busy``), inside the policy's UTC
   window when it has one, spread across the hour by ``host_offset`` so a
   fleet does not start at once, and never more than the target's
   ``max_concurrent`` captures at a time;
3. storage upkeep, on the storage host only: finish a seal-then-prune a
   capture's result could not queue, and ``check`` every
   ``check_interval_days``;
4. with Pro+ backup_engine, rotate the encryption keys that are due.

Runs that got no result twelve hours after their command was sent are
marked failed and logged; a run a maintenance window holds is waiting, not
stuck.
No target, or no equipped host, is a clean no-op.  Community: always runs.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.persistence.partitions import iter_host_databases
from backend.services import backup_first_fit as first_fit
from backend.services import backup_jobs as jobs
from backend.services import queue_clock
from backend.startup.leadership import singleton_task
from backend.startup.tick_runner import run_periodic
from backend.utils.host_spread import host_offset
from backend.websocket.queue_enums import QueueStatus

logger = logging.getLogger(__name__)

# Queue states that mean "this command will never be delivered".
UNDELIVERED = (QueueStatus.FAILED, QueueStatus.EXPIRED)

TICK_INTERVAL_SECONDS = 300
ERROR_BACKOFF_SECONDS = 60
STUCK_AFTER = timedelta(hours=12)
BUSY_RETRY = timedelta(minutes=30)
FAILED_RETRY = timedelta(hours=1)
WINDOW_HOURS = 6

_TASK: Optional[asyncio.Task] = None


def fail_stuck(db: Session, now: datetime) -> int:
    """Close runs no result will ever answer, loudly.

    The twelve hours count from when the command was SENT: a run held by
    the host's maintenance window, or waiting for its agent to come back,
    is not stuck -- failing it queued a second one, and the host got both
    when the window opened (services/queue_clock.py)."""
    candidates = (
        db.query(models.BackupRun)
        .filter(
            models.BackupRun.status.in_(jobs.PENDING),
            models.BackupRun.queued_at < now - STUCK_AFTER,
        )
        .all()
    )
    sent = queue_clock.deliveries(db, [run.command_id for run in candidates])
    stuck = []
    for run in candidates:
        started = queue_clock.clock_start(sent.get(str(run.command_id)), run.queued_at)
        if started is not None and started < now - STUCK_AFTER:
            stuck.append(run)
    for run in stuck:
        run.status = "failed"
        run.finished_at = now
        run.message = "no result within 12 hours"
        logger.error(
            "Backup %s run %s for policy %s on host %s got no result in 12 hours; "
            "marked failed",
            run.action,
            run.id,
            run.policy_id,
            run.host_id,
        )
    return len(stuck)


def fail_undeliverable(db: Session, now: datetime) -> int:
    """Close runs whose command the queue gave up delivering.

    The queue retries a command that is not acknowledged and then marks it
    failed; nothing answered the backup run, which stayed queued until the
    12-hour sweep -- holding back every other job for the policy (Prepare
    storage was disabled and the configure was never re-sent; production,
    ubiquiti, 2026-10-25, its connection dropping every few minutes).  Failed
    now, the next tick sends a fresh one."""
    pending = (
        db.query(models.BackupRun)
        .filter(
            models.BackupRun.status.in_(jobs.PENDING),
            models.BackupRun.command_id.isnot(None),
        )
        .all()
    )
    if not pending:
        return 0
    given_up = {
        row.message_id
        for row in db.query(models.MessageQueue.message_id)
        .filter(
            models.MessageQueue.message_id.in_([run.command_id for run in pending]),
            models.MessageQueue.status.in_(UNDELIVERED),
        )
        .all()
    }
    closed = 0
    for run in pending:
        if run.command_id not in given_up:
            continue
        run.status = "failed"
        run.finished_at = now
        run.message = "the host never acknowledged this command; it is sent again"
        logger.error(
            "Backup %s run %s for policy %s on host %s: the queue gave up "
            "delivering command %s; marked failed so it is sent again",
            run.action, run.id, run.policy_id, run.host_id, run.command_id,
        )  # fmt: skip
        closed += 1
    return closed


def in_window(policy: models.BackupPolicy, now: datetime) -> bool:
    if policy.window_start_hour is None:
        return True
    return (now.hour - policy.window_start_hour) % 24 < WINDOW_HOURS


def spread(policy: models.BackupPolicy) -> timedelta:
    """This host's fixed slice of the first hour (at most a quarter interval)."""
    span = min(timedelta(hours=1), timedelta(hours=policy.interval_hours) / 4)
    return span * host_offset(policy.host_id)


def capture_due_at(db: Session, policy: models.BackupPolicy) -> Optional[datetime]:
    """When the next capture may start; None = as soon as possible."""
    last = jobs.latest_run(db, policy.id, "capture", statuses=jobs.FINAL)
    if last is None:
        return None
    ended = last.finished_at or last.queued_at
    if last.status == "busy":
        return ended + BUSY_RETRY
    if last.status not in jobs.GOOD_CAPTURE:
        return ended + FAILED_RETRY
    good = jobs.latest_run(db, policy.id, "capture", statuses=jobs.GOOD_CAPTURE)
    base = good.finished_at or good.queued_at
    return base + timedelta(hours=policy.interval_hours) + spread(policy)


def running_captures(db: Session, target_id) -> int:
    return (
        db.query(models.BackupRun)
        .join(models.BackupPolicy, models.BackupPolicy.id == models.BackupRun.policy_id)
        .filter(
            models.BackupPolicy.target_id == target_id,
            models.BackupRun.action == "capture",
            models.BackupRun.status.in_(jobs.PENDING),
        )
        .count()
    )


def _configure(db, policy, target, host, storage_ready: bool) -> bool:
    """Send outdated job files.  True when the HOST's are current."""
    if jobs.address_changed(policy, host):
        # The export must follow the host: re-send the storage side's job
        # files (and, on its acknowledgment, re-prepare -- backup_results).
        logger.info(
            "Backup policy %s: host %s moved from %s to %s; re-sending storage jobs",
            policy.id, host.id, policy.storage_client_address, jobs.host_address(host),
        )  # fmt: skip
        policy.config_version += 1
        policy.storage_client_address = jobs.host_address(host)
    if policy.host_acked_version < policy.config_version and not jobs.pending(
        db, policy.id, jobs.CONFIGURE, host.id
    ):
        jobs.queue_configure(db, policy, target, host, "host")
    if (
        storage_ready
        and policy.storage_acked_version < policy.config_version
        and not jobs.pending(db, policy.id, jobs.CONFIGURE, target.storage_host_id)
    ):
        jobs.queue_configure(db, policy, target, host, "storage")
    return policy.host_acked_version >= 1


def _maybe_capture(db, policy, target, host, now: datetime) -> bool:
    if jobs.pending(db, policy.id, "capture") or not in_window(policy, now):
        return False
    due = capture_due_at(db, policy)
    if due is not None and due > now:
        return False
    if running_captures(db, target.id) >= max(1, target.max_concurrent or 1):
        logger.info("Backup capture for host %s waits: target is at capacity", host.id)
        return False
    decision = first_fit.first_capture_decision(db, policy, target, now)
    if decision == first_fit.RUN_ESTIMATE:
        # A first backup: learn whether it fits before writing anything.
        jobs.queue_run(db, policy, host.id, first_fit.ESTIMATE)
        return True
    if decision == first_fit.HOLD:
        return False
    jobs.queue_run(db, policy, host.id, "capture")
    return True


def _last_finished(db, policy, action, statuses=None) -> Optional[datetime]:
    run = jobs.latest_run(db, policy.id, action, statuses=statuses)
    return (run.finished_at or run.queued_at) if run else None


def _storage_retry_ok(db, policy, action, now: datetime) -> bool:
    """Not pending, and not a ``busy``/failed one moments ago."""
    if jobs.pending(db, policy.id, action):
        return False
    last = jobs.latest_run(db, policy.id, action)
    if last is None or last.status in ("ok", "different", "incomplete"):
        return True
    ended = last.finished_at or last.queued_at
    wait = BUSY_RETRY if last.status == "busy" else FAILED_RETRY
    return ended + wait <= now


def _upkeep_action(db, policy, target, now: datetime) -> Optional[str]:
    """The one storage-side job this policy needs now, if any."""
    captured = _last_finished(db, policy, "capture", jobs.GOOD_CAPTURE)
    pruned = _last_finished(db, policy, "prune", ("ok",))
    if captured and (pruned is None or pruned < captured):
        sealing = (target.seal_mode or "none") != "none"
        sealed = _last_finished(db, policy, "seal", ("ok",))
        if sealing and (sealed is None or sealed < captured):
            return "seal"
        return "prune"
    if captured is None:
        return None
    checked = _last_finished(db, policy, "check", ("ok", "different"))
    if checked is None or checked + timedelta(days=policy.check_interval_days) <= now:
        return "check"
    return None


def _storage_upkeep(db, policy, target, now: datetime) -> Optional[str]:
    if policy.storage_acked_version < 1:
        return None
    action = _upkeep_action(db, policy, target, now)
    if action is None or not _storage_retry_ok(db, policy, action, now):
        return None
    if any(jobs.pending(db, policy.id, a) for a in jobs.STORAGE_ACTIONS):
        return None  # one storage job per repository at a time
    jobs.queue_run(db, policy, target.storage_host_id, action)
    return action


def _eligible(host: Optional[models.Host]) -> bool:
    return (
        host is not None
        and host.approval_status == "approved"
        and bool(host.active)
        and jobs.equipped(host)[0]
    )


def _target_policies(db: Session, target) -> List[models.BackupPolicy]:
    return (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.target_id == target.id)
        .all()
    )


def _policy_host(db: Session, policy) -> Optional[models.Host]:
    return db.query(models.Host).filter(models.Host.id == policy.host_id).first()


def _requested(db: Session, target) -> List[models.BackupPolicy]:
    return (
        db.query(models.BackupPolicy)
        .filter(
            models.BackupPolicy.target_id == target.id,
            models.BackupPolicy.capture_requested_at.isnot(None),
        )
        .order_by(models.BackupPolicy.capture_requested_at)
        .all()
    )


def start_requested(db: Session, actor: str = jobs.SYSTEM_ACTOR) -> int:
    """Start requested captures (a bulk "Back up now") oldest first, while
    the target has a free slot.  The rest keep waiting: each finished
    capture calls this again, and so does every tick.  A request a host can
    no longer run is dropped, loudly."""
    db.flush()
    target = jobs.the_target(db)
    if target is None:
        return 0
    free = max(1, target.max_concurrent or 1) - running_captures(db, target.id)
    started = 0
    for policy in _requested(db, target):
        host = _policy_host(db, policy)
        if not _eligible(host) or policy.host_acked_version < 1:
            logger.warning(
                "Backup now for policy %s dropped: host %s can no longer run it",
                policy.id,
                policy.host_id,
            )
            policy.capture_requested_at = None
            continue
        if jobs.pending(db, policy.id, "capture"):
            policy.capture_requested_at = None  # already running: satisfied
            continue
        if started >= free:
            break
        jobs.queue_run(db, policy, host.id, "capture", actor)
        policy.capture_requested_at = None
        started += 1
    return started


def configure_now(db: Session) -> None:
    """Send outdated job files at once rather than on the next tick: a saved
    target or policy takes effect while the operator is watching.  Queues
    configuration only -- never a capture."""
    db.flush()
    target = jobs.the_target(db)
    if target is None:
        return
    storage_ready = _eligible(jobs.storage_host(db, target))
    for policy in _target_policies(db, target):
        host = _policy_host(db, policy)
        if _eligible(host):
            _configure(db, policy, target, host, storage_ready)


def reconcile(db: Session, now: Optional[datetime] = None) -> int:
    """One database's pass; how many jobs were queued.

    Every policy is configured, enabled or not: a host backed up only by
    "Back up now" still needs its job files.  ``enabled`` governs only the
    scheduled captures.  Storage upkeep (seal, prune, check) follows any
    capture, scheduled or manual.
    """
    now = now or jobs.now()
    fail_stuck(db, now)
    fail_undeliverable(db, now)
    removed = jobs.prune_run_history(db, now)
    if removed:
        logger.info("Backup job history: removed %d runs older than %d days",
                    removed, jobs.RUN_RETENTION_DAYS)  # fmt: skip
    target = jobs.the_target(db)
    if target is None:
        return 0
    # First, so a rotated key's job files go out on this same pass.
    rotate_keys(db, target, now)
    storage_ready = _eligible(jobs.storage_host(db, target))
    queued = start_requested(db)  # asked for first, then the schedule
    for policy in _target_policies(db, target):
        host = _policy_host(db, policy)
        if not _eligible(host):
            continue
        if not _configure(db, policy, target, host, storage_ready):
            continue
        if policy.enabled:
            queued += int(_maybe_capture(db, policy, target, host, now))
        if storage_ready and _storage_upkeep(db, policy, target, now):
            queued += 1
    return queued


def _encryption_engine():
    """backup_engine when it is loaded and backup encryption is licensed."""
    # pylint: disable=import-outside-toplevel
    from backend.licensing.module_loader import module_loader  # noqa: PLC0415

    engine = module_loader.get_module("backup_engine")
    if engine is None or not hasattr(engine, "rotate_due"):
        return None
    try:
        from backend.licensing.features import FeatureCode  # noqa: PLC0415
        from backend.licensing.license_service import (  # noqa: PLC0415
            license_service,
        )

        if not license_service.has_feature(FeatureCode.BACKUP_ENCRYPTION):
            return None
    except Exception:  # pylint: disable=broad-except
        logger.debug("license check failed; no key rotation", exc_info=True)
        return None
    return engine


def rotate_keys(db: Session, target, now: datetime) -> int:
    """Pro+ backup_engine (24.6 S5): rotate the encryption keys that are due
    (every ``key_rotation_days`` of the target, default 365).  The engine
    logs and retries its own failures; anything else is logged here and
    never stops the backups this tick queued."""
    engine = _encryption_engine()
    if engine is None:
        return 0
    policies = [p for p in _target_policies(db, target) if p.encrypt_public_key]
    if not policies:
        return 0
    try:
        return engine.rotate_due(db, target, policies, now=now, logger=logger)
    except Exception:  # pylint: disable=broad-except
        logger.exception("Backup key rotation failed for target %s", target.id)
        return 0


def run_one_tick() -> int:
    """One pass over every host database.  Never raises."""
    queued = 0
    for label, _, db in iter_host_databases():
        try:
            queued += reconcile(db)
            db.commit()
        except Exception:  # pylint: disable=broad-except
            logger.exception("Backup scheduling failed for %s", label)
            db.rollback()
        finally:
            db.close()
    return queued


async def backup_tick_service() -> None:
    await run_periodic(
        "Backup tick",
        run_one_tick,
        TICK_INTERVAL_SECONDS,
        ERROR_BACKOFF_SECONDS,
        logger=logger,
    )


def start_if_licensed():
    """Community: always starts.  The task, or None when it cannot."""
    global _TASK  # pylint: disable=global-statement
    if _TASK is not None and not _TASK.done():
        return _TASK
    try:
        _TASK = singleton_task(backup_tick_service())
        logger.info("Backup scheduler tick started")
        return _TASK
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Backup tick did not start: %s", exc)
        return None
