# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""An automatic run's results and the reboot after it (ROADMAP 26.1).

``note_results`` is called by the ``update_apply_result`` handler once the
packages' execution logs are marked: a run whose logs are all decided is
closed (succeeded / partial / failed, with the failures and the agent's own
error text), and -- when its policy allows rebooting and the host needs it
-- one ``reboot_system`` is queued and audited.

``follow_reboots`` (every tick) then says whether each reboot came back:
the host's boot time from its heartbeat is later than the request (``back``),
or the policy's timeout passed without one (``not_back``: the host is
flagged on its run, and in the log).  A host whose need to reboot is only
reported after the run closed (Linux's reboot-required check runs on its
own) is rebooted then, within ``LATE_REBOOT_MINUTES``.
"""

import logging
import uuid
from datetime import timedelta, timezone
from typing import Iterable, Optional

from backend.i18n import _
from backend.persistence import models
from backend.services.agent_capability_service import host_supports
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)
queue_ops = QueueOperations()

ACTOR = "automatic updates"
LATE_REBOOT_MINUTES = 30


def naive_utc(value):
    """A timestamp as naive UTC.  Some columns come back timezone-aware on
    PostgreSQL (``host.reboot_required_updated_at``) and naive on SQLite;
    comparing the two raised in the lab (2026-11-16) and stopped every
    automatic run in the tenant."""
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _engine():
    from backend.services.auto_update_runner import (  # pylint: disable=import-outside-toplevel
        engine,
    )

    return engine()


def _profile(db, run) -> Optional[models.UpgradeProfile]:
    return db.get(models.UpgradeProfile, run.profile_id) if run.profile_id else None


def _reboot_pending(db, run) -> bool:
    """Another run already asked this host to reboot and is waiting for it."""
    return (
        db.query(models.AutoUpdateRun)
        .filter(
            models.AutoUpdateRun.host_id == run.host_id,
            models.AutoUpdateRun.id != run.id,
            models.AutoUpdateRun.reboot_status == "queued",
        )
        .first()
        is not None
    )


def queue_reboot(db, run, host, now) -> None:
    """One audited ``reboot_system`` for ``run``'s host -- never a second one
    while another run's reboot is still pending (lab, 2026-11-16: two runs
    each sent one, and the second rebooted the host again)."""
    if _reboot_pending(db, run):
        run.reboot_status, run.reboot_queued_at = "queued", now
        return
    if host_supports(host, "reboot_system") is False:
        run.reboot_status = "not_wanted"  # this agent cannot take a reboot
        return
    queue_ops.enqueue_message(
        message_type="command",
        message_data=create_command_message("reboot_system", {}),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )
    run.reboot_status, run.reboot_queued_at = "queued", now
    AuditService.log(
        db=db,
        action_type=ActionType.EXECUTE,
        entity_type=EntityType.HOST,
        entity_id=str(host.id),
        entity_name=host.fqdn,
        description=_("Automatic reboot of %(host)s after policy '%(policy)s'")
        % {"host": host.fqdn, "policy": run.profile_name},
        result=Result.SUCCESS,
        username=ACTOR,
        details={"run_id": str(run.id)},
        commit=False,
    )


def _close(db, eng, run, host, requires_reboot: bool, now) -> None:
    logs = (
        db.query(models.UpdateExecutionLog)
        .filter(models.UpdateExecutionLog.run_id == run.id)
        .all()
    )
    if any(log.execution_status == "pending" for log in logs):
        return  # more results to come
    failed = [log for log in logs if log.execution_status == "failed"]
    run.applied_count = sum(1 for log in logs if log.execution_status == "success")
    run.failed_count = len(failed)
    run.failures = [
        {
            "package_name": log.package_name,
            "package_manager": log.package_manager,
            "error": (log.error_log or "")[-2000:],
        }
        for log in failed
    ]
    run.status = eng.run_outcome(len(logs), run.applied_count, run.failed_count)
    run.completed_at = now
    run.reboot_needed = bool(requires_reboot or host.reboot_required)
    profile = _profile(db, run)
    reboot_mode = profile.reboot_mode if profile is not None else "never"
    if not eng.reboot_wanted(reboot_mode, True):
        # Decided now, under the policy as it is: changing the policy later
        # must not reboot a host for an old run (lab, 2026-11-16).
        run.reboot_status = "not_wanted"
    elif run.applied_count and run.reboot_needed:
        queue_reboot(db, run, host, now)


def note_results(db, host_id, run_ids: Iterable, requires_reboot: bool, now) -> None:
    """Close each run these results finished.  Never raises: a failure here
    must not lose the update results the caller already recorded."""
    run_ids = {r for r in run_ids if r}
    if not run_ids:
        return
    eng = _engine()
    try:
        host = db.get(models.Host, host_id)
        for run in db.query(models.AutoUpdateRun).filter(
            models.AutoUpdateRun.id.in_([uuid.UUID(str(r)) for r in run_ids]),
            models.AutoUpdateRun.status == "queued",
        ):
            if eng is None:
                run.status, run.completed_at = "failed", now
                continue
            _close(db, eng, run, host, requires_reboot, now)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Automatic updates: closing runs for host %s failed", host_id)


def _late_reboots(db, eng, now) -> None:
    since = now - timedelta(minutes=LATE_REBOOT_MINUTES)
    for run in db.query(models.AutoUpdateRun).filter(
        models.AutoUpdateRun.status.in_(("succeeded", "partial")),
        models.AutoUpdateRun.reboot_status == "none",
        models.AutoUpdateRun.completed_at >= since,
    ):
        host = db.get(models.Host, run.host_id)
        profile = _profile(db, run)
        if host is None or profile is None or not host.reboot_required:
            continue
        newer = (
            db.query(models.AutoUpdateRun.id)
            .filter(
                models.AutoUpdateRun.host_id == run.host_id,
                models.AutoUpdateRun.queued_at > run.queued_at,
                models.AutoUpdateRun.status != "skipped",
            )
            .first()
        )
        if newer is not None:
            continue  # only a host's latest run may still reboot it
        reported = naive_utc(host.reboot_required_updated_at)
        if reported is None or reported < naive_utc(run.completed_at):
            continue
        if eng.reboot_wanted(profile.reboot_mode, True):
            run.reboot_needed = True
            queue_reboot(db, run, host, now)


def follow_reboots(db, eng, now) -> None:
    """Late reboots, then whether each queued reboot came back."""
    _late_reboots(db, eng, now)
    settings = db.query(models.AutoUpdateSettings).first()
    timeout = settings.reboot_timeout_minutes if settings else None
    for run in db.query(models.AutoUpdateRun).filter(
        models.AutoUpdateRun.reboot_status == "queued"
    ):
        host = db.get(models.Host, run.host_id)
        if host is None:
            continue
        state = eng.reboot_state(
            naive_utc(run.reboot_queued_at),
            naive_utc(host.boot_time),
            naive_utc(host.last_access),
            now,
            timeout,
        )
        if state == "back":
            run.reboot_status, run.reboot_back_at = "back", now
        elif state == "not_back":
            run.reboot_status = "not_back"
            logger.warning(
                "Automatic updates: %s did not come back from its reboot (run %s)",
                host.fqdn,
                run.id,
            )
