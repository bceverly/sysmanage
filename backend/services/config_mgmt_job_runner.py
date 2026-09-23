# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet job execution: bounded release and completion (Phase 20.1).

The half of fleet-scale config management that is not schema. A job holds a
target per host; this module releases them in waves no wider than the job's
concurrency, closes each one when its result arrives, and decides when the job
as a whole has stopped.

WHY WAVES AND NOT A LOOP
------------------------
``ConfigProfileAssignment`` already queues every matched host in a single pass.
That is correct for tens and wrong for thousands, in two distinct ways: one
transaction holding the whole fleet, and a burst of messages that arrives all
at once whatever the queue, the network and the agents can absorb. Releasing
at most ``concurrency`` at a time fixes both, and costs only that the runner
has to be re-entered -- which it already would be, because results arrive
asynchronously.

WHY THE RUNNER DOES NOT WAIT FOR ANYTHING
-----------------------------------------
Every entry point here is a single non-blocking pass: release what may be
released, close what has closed, return. There is no sleeping on a result and
no per-job task. A job of four thousand targets would otherwise pin a coroutine
for however long the slowest agent takes, and a server restart mid-job would
lose the loop while leaving the rows behind. State lives in the rows, so a
restart resumes by reading them.

WHAT IT DELIBERATELY DOES NOT DECIDE
------------------------------------
* Whether a host may run the command -- ``enqueue_message`` already refuses a
  command a host has not advertised support for (Phase 19). A refusal here is
  an ordinary SKIP, not a failure: it is the expected answer for a host
  without ansible-core, and marking it failed would make every mixed fleet
  look broken.
* Whether now is a safe time to deliver -- ``outbound_processor`` holds
  delivery outside a maintenance window (Phase 14.2). Anything queued the
  normal way inherits that; a second check here could only disagree with it.
* How wide a wave may be, or when a job counts as failed -- both are engine
  rules, in ``config_jobs.pxi``.
"""

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.persistence.models.config_fleet import (
    JOB_CANCELED,
    JOB_PENDING,
    JOB_RUNNING,
    TARGET_FAILED,
    TARGET_IN_FLIGHT,
    TARGET_PENDING,
    TARGET_QUEUED,
    TARGET_SKIPPED,
    TARGET_SUCCEEDED,
)
from backend.persistence.partitions import iter_host_databases
from backend.services import config_mgmt_dispatch as dispatch
from backend.services import config_mgmt_fleet as fleet
from backend.services import config_mgmt_spec_shim as shim

logger = logging.getLogger(__name__)

# Matches the assignment tick. Cron's finest granularity is a minute, and the
# release half of this loop is driven by results arriving rather than by the
# clock, so a tighter cadence buys nothing.
TICK_INTERVAL_SECONDS = 60
ERROR_BACKOFF_SECONDS = 30

# How long a dispatched target may sit without a result before the runner
# gives up on it.
#
# Something must, or a job whose agent went away mid-run stays "running"
# forever, holds slots its concurrency will not release, and shows an
# outstanding count that never moves -- which is worse than a failure, because
# a failure is actionable and a stall just looks like the feature is broken.
#
# Six hours is deliberately generous: it is the engine's own timeout ceiling,
# so a target can only age out after the longest run the product will even
# accept has had time to finish and report. A tighter bound would start
# failing legitimate long conveges.
STALE_TARGET_SECONDS = 21600


def _stale_cutoff():
    return fleet.now_naive() - timedelta(seconds=STALE_TARGET_SECONDS)


# --- creating a job ----------------------------------------------------------


def create_job(
    db_session: Session,
    template,
    profile,
    inventory,
    requested_by: Optional[str],
) -> models.ConfigJob:
    """Build a job and one pending target per selected host.

    Targets are materialized up front rather than discovered wave by wave. It
    costs one insert per host at launch and buys the thing the feature exists
    for: from the first second, the job can say how many hosts it is going to
    touch and which ones. A job that discovers its own size as it goes cannot
    show progress, and progress is what an operator watches a fleet run for.

    ``host_fqdn`` is copied onto every target because the host may be
    decommissioned before anybody reads the job.
    """
    now = fleet.now_naive()
    hosts = fleet.resolve_hosts(db_session, inventory)

    job = models.ConfigJob(
        template_id=getattr(template, "id", None),
        template_name=getattr(template, "name", None),
        profile_id=profile.id,
        profile_name=profile.name,
        inventory_name=inventory.name,
        status=JOB_PENDING,
        check_mode=bool(getattr(template, "check_mode", False)),
        concurrency=fleet.clamp_concurrency(getattr(template, "concurrency", None)),
        timeout_seconds=getattr(template, "timeout_seconds", None),
        total_targets=len(hosts),
        succeeded_count=0,
        failed_count=0,
        skipped_count=0,
        requested_by=requested_by,
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()

    for host in hosts:
        db_session.add(
            models.ConfigJobTarget(
                job_id=job.id,
                host_id=host.id,
                host_fqdn=host.fqdn,
                status=TARGET_PENDING,
            )
        )

    if not hosts:
        # An inventory that selects nothing is worth saying out loud. The
        # engine refuses to CREATE such an inventory, so reaching here means
        # every host it named has since gone inactive or been deleted -- and a
        # job silently reporting success over zero hosts reads as "the fleet is
        # converged", which is the most expensive way this feature can be
        # wrong.
        job.status = "completed"
        job.started_at = now
        job.finished_at = now
        job.detail = "the inventory selected no active hosts"
        logger.warning(
            "Config fleet job %s launched against inventory '%s' which resolved "
            "to zero active hosts; nothing was dispatched",
            job.id,
            inventory.name,
        )
    return job


# --- advancing a job ---------------------------------------------------------


def _pending_targets(db_session: Session, job_id, limit: int) -> List[Any]:
    if limit <= 0:
        return []
    return (
        db_session.query(models.ConfigJobTarget)
        .filter(
            models.ConfigJobTarget.job_id == job_id,
            models.ConfigJobTarget.status == TARGET_PENDING,
        )
        .limit(limit)
        .all()
    )


def _skip(target, detail: str, now) -> None:
    target.status = TARGET_SKIPPED
    target.detail = detail
    target.finished_at = now


def _release(db_session: Session, job, target, parameters, now) -> str:
    """Dispatch one target. Returns the status it ended up in.

    A host that cannot take the command is SKIPPED, not failed, and the reason
    is written to the row. That distinction is the whole reason the detail
    column exists: "this agent does not advertise config-management support"
    is a true and useful answer that must not be filed alongside "the playbook
    blew up".
    """
    if target.host_id is None:
        _skip(target, "the host was removed before this job reached it", now)
        return TARGET_SKIPPED
    try:
        target.command_id = dispatch.queue_apply(db_session, target.host_id, parameters)
    except Exception as exc:  # pylint: disable=broad-except
        # Includes UnsupportedCapabilityError, an ordinary outcome for a host
        # that cannot run playbooks. Logged at info with the host named --
        # loudly enough to explain a skipped count, quietly enough not to fill
        # the log on a fleet where half the hosts are Windows.
        logger.info(
            "Fleet job %s: host %s (%s) could not take the command: %s",
            job.id,
            target.host_fqdn,
            target.host_id,
            exc,
        )
        _skip(target, str(exc)[:500], now)
        return TARGET_SKIPPED

    target.status = TARGET_QUEUED
    target.queued_at = now
    return TARGET_QUEUED


def _expire_stale(db_session: Session, job) -> int:
    """Fail targets dispatched so long ago that no result is coming.

    Returns how many were expired. Without this a job whose agent vanished
    mid-run holds its slots forever and never completes -- an outcome that
    looks like a broken feature rather than a failed host.
    """
    cutoff = _stale_cutoff()
    stale = (
        db_session.query(models.ConfigJobTarget)
        .filter(
            models.ConfigJobTarget.job_id == job.id,
            models.ConfigJobTarget.status.in_(TARGET_IN_FLIGHT),
            models.ConfigJobTarget.queued_at.isnot(None),
            models.ConfigJobTarget.queued_at < cutoff,
        )
        .all()
    )
    now = fleet.now_naive()
    for target in stale:
        target.status = TARGET_FAILED
        target.detail = "no result was reported before the job's time limit"
        target.finished_at = now
        job.failed_count = (job.failed_count or 0) + 1
        logger.warning(
            "Fleet job %s: target %s (%s) expired with no result after %ds",
            job.id,
            target.host_fqdn,
            target.host_id,
            STALE_TARGET_SECONDS,
        )
    return len(stale)


def advance_job(db_session: Session, job) -> Dict[str, int]:
    """Release the next wave of a job and update its status. Never raises.

    One pass: expire what has aged out, release up to the concurrency, then
    recompute the status from what is left. Called both by the tick and
    directly after a result lands, so a fast fleet is paced by results rather
    than by the clock.
    """
    summary = {"released": 0, "skipped": 0, "expired": 0}
    if fleet.job_is_terminal(job.status):
        return summary

    now = fleet.now_naive()
    summary["expired"] = _expire_stale(db_session, job)

    counts = fleet.target_counts(db_session, job.id)
    budget = fleet.next_batch_size(
        job.concurrency, counts["in_flight"], counts["pending"]
    )

    if budget > 0:
        profile = (
            db_session.query(models.ConfigProfile)
            .filter(models.ConfigProfile.id == job.profile_id)
            .first()
        )
        parameters = _parameters_or_fail(db_session, job, profile, now)
        if parameters is None:
            return summary

        for target in _pending_targets(db_session, job.id, budget):
            if job.started_at is None:
                job.started_at = now
            outcome = _release(db_session, job, target, parameters, now)
            if outcome == TARGET_QUEUED:
                summary["released"] += 1
            else:
                summary["skipped"] += 1
                job.skipped_count = (job.skipped_count or 0) + 1

    _recompute_status(db_session, job, now)
    return summary


def _parameters_or_fail(db_session: Session, job, profile, now):
    """The command parameters for this job, failing the job if there are none.

    A profile that was deleted or whose body no longer builds is terminal for
    the job: every remaining target would fail identically, so re-deciding it
    on each tick would just produce an identical failure and a flooded log --
    the same reasoning the assignment tick applies when it advances its cursor
    past an undispatchable profile.
    """
    if profile is None or not profile.is_active:
        _fail_job(
            db_session,
            job,
            "the profile this job runs was deleted or taken out of service",
            now,
        )
        return None
    try:
        return dispatch.parameters_for(
            profile, check_mode=bool(job.check_mode), timeout=job.timeout_seconds
        )
    except dispatch.DispatchError as exc:
        _fail_job(db_session, job, exc.message, now)
        return None


def _fail_job(db_session: Session, job, detail: str, now) -> None:
    """Stop a job that cannot proceed, marking its untouched targets skipped."""
    logger.error("Fleet job %s cannot proceed: %s", job.id, detail)
    remaining = (
        db_session.query(models.ConfigJobTarget)
        .filter(
            models.ConfigJobTarget.job_id == job.id,
            models.ConfigJobTarget.status == TARGET_PENDING,
        )
        .all()
    )
    for target in remaining:
        _skip(target, detail, now)
    job.skipped_count = (job.skipped_count or 0) + len(remaining)
    job.detail = detail
    _recompute_status(db_session, job, now)


def _recompute_status(db_session: Session, job, now) -> None:
    """Ask the engine what status this job now carries, and stamp the end."""
    counts = fleet.target_counts(db_session, job.id)
    status = fleet.job_status_after(
        job.succeeded_count or 0,
        job.failed_count or 0,
        job.skipped_count or 0,
        counts["in_flight"],
        counts["pending"],
        started=job.started_at is not None,
    )
    job.status = status
    if fleet.job_is_terminal(status) and job.finished_at is None:
        job.finished_at = now


def cancel_job(db_session: Session, job, detail: str) -> int:
    """Stop dispatching a job. Returns how many targets were skipped.

    Targets already in flight are LEFT ALONE: the command is with the agent,
    and marking it cancelled here would claim something the server cannot
    make true. Their results still land and still close their targets -- so a
    cancelled job's counts keep moving for a while, which is honest.
    """
    now = fleet.now_naive()
    remaining = (
        db_session.query(models.ConfigJobTarget)
        .filter(
            models.ConfigJobTarget.job_id == job.id,
            models.ConfigJobTarget.status == TARGET_PENDING,
        )
        .all()
    )
    for target in remaining:
        _skip(target, detail, now)
    job.skipped_count = (job.skipped_count or 0) + len(remaining)
    job.status = JOB_CANCELED
    job.detail = detail
    job.finished_at = now
    return len(remaining)


# --- closing a target when its result lands ----------------------------------


def close_target_for_run(db_session: Session, run) -> bool:
    """Attach an arriving run to the job target that dispatched it.

    Returns True when a target was closed. Called from the config-profile
    result handler, inside the same transaction as the run row, so a job's
    progress and the run that produced it are never out of step.

    Matched on ``command_id``, which the agent echoes back from the envelope.
    That is the entire reason ``dispatch.queue_apply`` uses one id for the
    envelope and the queue row -- see its docstring for what happens when
    they differ.
    """
    command_id = getattr(run, "command_id", None)
    if not command_id:
        return False

    target = (
        db_session.query(models.ConfigJobTarget)
        .filter(
            models.ConfigJobTarget.command_id == str(command_id),
            models.ConfigJobTarget.status.in_(TARGET_IN_FLIGHT),
        )
        .first()
    )
    if target is None:
        # Ordinary: most applies are ad-hoc or from an assignment and belong to
        # no job at all. Not logged, or every single result would say so.
        return False

    job = (
        db_session.query(models.ConfigJob)
        .filter(models.ConfigJob.id == target.job_id)
        .first()
    )
    if job is None:
        logger.warning(
            "Config job target %s references job %s, which is gone",
            target.id,
            target.job_id,
        )
        return False

    now = fleet.now_naive()
    target.status = TARGET_SUCCEEDED if run.success else TARGET_FAILED
    target.run_id = run.id
    target.finished_at = now
    if run.success:
        job.succeeded_count = (job.succeeded_count or 0) + 1
    else:
        job.failed_count = (job.failed_count or 0) + 1
        target.detail = (run.reason or "the run reported failure")[:500]

    # Advance immediately rather than waiting for the tick. This is what makes
    # a fleet job paced by how fast the fleet answers instead of by a
    # sixty-second clock: on four thousand hosts the difference between the
    # two is hours.
    advance_job(db_session, job)
    return True


# --- scheduled launches + the background tick --------------------------------


def _is_due(automation, template, now) -> bool:
    """Whether a scheduled template's next occurrence has arrived.

    Derived from ``last_launched_at``, exactly as the assignment tick derives
    its own due-ness, so a server that was down overnight launches ONCE rather
    than replaying every occurrence it slept through.
    """
    anchor = template.last_launched_at or template.created_at
    if anchor is None:
        return True
    try:
        nxt = automation.next_run_from_cron(template.schedule, anchor)
    except Exception:  # pylint: disable=broad-except
        logger.warning(
            "Config job template %s has an unusable cron (%s); skipping",
            template.id,
            template.schedule,
        )
        return False
    if nxt is None:
        return False
    if nxt.tzinfo is not None:
        nxt = nxt.astimezone(tz=None).replace(tzinfo=None)
    return nxt <= now


def _launch_due_templates(db_session: Session, automation, now, summary) -> None:
    """Launch every scheduled template whose occurrence has arrived."""
    templates = (
        db_session.query(models.ConfigJobTemplate)
        .filter(
            models.ConfigJobTemplate.enabled.is_(True),
            models.ConfigJobTemplate.schedule.isnot(None),
        )
        .all()
    )
    for template in templates:
        if not _is_due(automation, template, now):
            continue
        summary["launched"] += 1

        profile = (
            db_session.query(models.ConfigProfile)
            .filter(models.ConfigProfile.id == template.profile_id)
            .first()
        )
        inventory = (
            db_session.query(models.ConfigInventory)
            .filter(models.ConfigInventory.id == template.inventory_id)
            .first()
        )
        if profile is None or inventory is None:
            # Both are CASCADE foreign keys, so this means the row was written
            # directly or the delete raced the tick. Said out loud with the ids
            # rather than skipped silently: a schedule that stops firing with
            # no explanation is the worst failure this feature has.
            logger.error(
                "Config job template %s (%s) is due but its profile (%s) or "
                "inventory (%s) is missing; not launching",
                template.id,
                template.name,
                template.profile_id,
                template.inventory_id,
            )
            template.last_launched_at = now
            continue

        # requested_by is deliberately NULL for a scheduled launch: there is no
        # operator to name, and writing "system" into an audit field would make
        # the record claim somebody acted.
        job = create_job(db_session, template, profile, inventory, None)
        template.last_launched_at = now

        # The first wave goes out now rather than on the next tick, and its
        # counts are folded into the summary. Discarding them would make the
        # tick log report launched=1 released=0 for a launch that dispatched
        # five hundred hosts -- the one line an operator has to tell a working
        # schedule from a stalled one.
        result = advance_job(db_session, job)
        summary["released"] += result["released"]
        summary["skipped"] += result["skipped"]
        summary["expired"] += result["expired"]


def _advance_running(db_session: Session, summary) -> None:
    """Move every job that is still working."""
    jobs = (
        db_session.query(models.ConfigJob)
        .filter(models.ConfigJob.status.in_((JOB_PENDING, JOB_RUNNING)))
        .order_by(models.ConfigJob.created_at.asc())
        .all()
    )
    for job in jobs:
        result = advance_job(db_session, job)
        summary["released"] += result["released"]
        summary["skipped"] += result["skipped"]
        summary["expired"] += result["expired"]
        summary["active"] += 1


def _tick_one_database(db_session: Session, automation, now, summary) -> None:
    """Run the tick against ONE database. Never raises.

    Isolated per database for the same reason the assignment tick is: one
    unreachable tenant must not stop every other tenant's jobs for the rest of
    the tick.
    """
    try:
        if automation is not None:
            _launch_due_templates(db_session, automation, now, summary)
        _advance_running(db_session, summary)
        db_session.commit()
    except Exception:  # pylint: disable=broad-except
        logger.exception("Config fleet job tick failed")
        db_session.rollback()


def run_one_tick() -> Dict[str, Any]:
    """Launch due templates and advance running jobs once. Never raises.

    Public so an operator-facing endpoint or a test can drive exactly one tick
    without waiting a minute for the loop.
    """
    summary: Dict[str, Any] = {
        "launched": 0,
        "active": 0,
        "released": 0,
        "skipped": 0,
        "expired": 0,
        "no_cron_engine": False,
    }

    if shim.engine_module() is None:
        # Jobs cannot be created without the module; nothing to advance.
        return summary

    automation = module_loader_automation()
    if automation is None:
        # Without a cron parser no template can be judged due. Running jobs are
        # still advanced -- they need no cron, and stalling live dispatch
        # because scheduling is unavailable would be a much larger failure than
        # a late launch.
        summary["no_cron_engine"] = True

    now = fleet.now_naive()
    for _label, _tenant, db_session in iter_host_databases():
        try:
            _tick_one_database(db_session, automation, now, summary)
        finally:
            db_session.close()
    return summary


def module_loader_automation():
    """The cron parser, or None. Its own function so tests can replace it."""
    from backend.licensing.module_loader import module_loader  # noqa: PLC0415

    return module_loader.get_module("automation_engine")


async def config_mgmt_job_tick_service() -> None:
    """Background service: one tick every ``TICK_INTERVAL_SECONDS``."""
    logger.info(
        "Starting config fleet job tick service (interval=%ds)",
        TICK_INTERVAL_SECONDS,
    )
    while True:
        try:
            summary = run_one_tick()
            if summary["launched"] or summary["active"] or summary["no_cron_engine"]:
                logger.info(
                    "Config fleet job tick: launched=%d active=%d released=%d "
                    "skipped=%d expired=%d automation_engine_absent=%s",
                    summary["launched"],
                    summary["active"],
                    summary["released"],
                    summary["skipped"],
                    summary["expired"],
                    summary["no_cron_engine"],
                )
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Config fleet job tick service cancelled -- exiting loop")
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception("Config fleet job tick service error -- sleeping")
            await asyncio.sleep(ERROR_BACKOFF_SECONDS)
