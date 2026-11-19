# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The automatic update driver (ROADMAP 26.1, Enterprise).

Before 26.1 nothing ran an upgrade profile on its schedule (the ``tick``
endpoint waited for "an external scheduler" that never existed), and a
profile's dispatch never worked: it sent ``apply_updates`` with no package
names, which every agent refuses ("No packages specified").

Now one leader-elected tick a minute, in every tenant database:

  1. closes runs that never reported (``RUN_TIMEOUT_HOURS``) and follows the
     reboots it asked for (``auto_update_results``);
  2. unless every policy is on hold, fires each due policy (``auto_apply``
     on, not held, ``next_run`` passed): every host it covers that follows
     it (``resolve_policy``) gets a run -- skipped with a reason, "nothing to
     do", or the exact pending updates the engine chose, named in an
     ``apply_updates`` command released on the profile's stagger.

Every decision is the Enterprise ``automation_engine``'s; this module only
reads and writes the database and the queue.  Without the engine nothing is
applied automatically (and the routes answer 402).
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import iter_host_databases
from backend.services.agent_capability_service import host_supports
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations
from backend.startup.tick_runner import run_periodic

logger = logging.getLogger(__name__)
queue_ops = QueueOperations()

TICK_INTERVAL_SECONDS = 60
ERROR_BACKOFF_SECONDS = 30
RUN_TIMEOUT_HOURS = 12
ACTOR = "automatic updates"
AGENT_CANNOT_APPLY = "agent_cannot_apply"


def now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def engine():
    """The Enterprise automation engine, or None."""
    from backend.licensing.module_loader import (  # pylint: disable=import-outside-toplevel
        module_loader,
    )

    return module_loader.get_module("automation_engine")


def settings_row(db) -> models.AutoUpdateSettings:
    """The tenant's one settings row, made on first use."""
    row = db.query(models.AutoUpdateSettings).first()
    if row is None:
        row = models.AutoUpdateSettings(
            id=uuid.uuid4(),
            hold_all=False,
            retry_after_hours=24,
            reboot_timeout_minutes=30,
        )
        db.add(row)
        db.flush()
    return row


def settings_dict(row: models.AutoUpdateSettings) -> Dict[str, Any]:
    return {
        "retry_after_hours": row.retry_after_hours,
        "reboot_timeout_minutes": row.reboot_timeout_minutes,
        "critical_threshold": row.critical_threshold or "critical",
    }


# ---------------------------------------------------------------------------
# reading: profiles, hosts, updates as the engine's dicts
# ---------------------------------------------------------------------------


def profile_host_ids(db, profile_ids) -> Dict[str, List[str]]:
    rows = (
        db.query(
            models.UpgradeProfileHost.profile_id, models.UpgradeProfileHost.host_id
        )
        .filter(models.UpgradeProfileHost.profile_id.in_(list(profile_ids)))
        .all()
    )
    out: Dict[str, List[str]] = {}
    for profile_id, host_id in rows:
        out.setdefault(str(profile_id), []).append(str(host_id))
    return out


def profile_dict(profile, host_ids=None) -> Dict[str, Any]:
    return {
        "id": str(profile.id),
        "name": profile.name,
        "auto_apply": bool(profile.auto_apply),
        "tag_id": str(profile.tag_id) if profile.tag_id else None,
        "host_ids": list(host_ids or []),
        "security_only": bool(profile.security_only),
        "package_managers": (
            profile.package_managers.split(",") if profile.package_managers else []
        ),
        "excluded_packages": profile.excluded_packages or "",
        "reboot_mode": profile.reboot_mode or "never",
        "require_backup_hours": profile.require_backup_hours,
        "staggered_window_min": profile.staggered_window_min or 0,
        "wait_days_regular": profile.wait_days_regular or 0,
        "wait_days_critical": profile.wait_days_critical or 0,
        "critical_source": profile.critical_source or "either",
    }


def auto_profiles(db) -> List[Dict[str, Any]]:
    """Every enabled policy that applies automatically, as dicts (for
    resolution).  A disabled policy claims no host: it used to take part,
    so a disabled but more conservative policy won the host and nothing
    patched it (lab, 2026-11-17).  A held policy still claims its hosts --
    a hold pauses them, it does not hand them to another policy."""
    rows = (
        db.query(models.UpgradeProfile)
        .filter(
            models.UpgradeProfile.auto_apply.is_(True),
            models.UpgradeProfile.enabled.is_(True),
        )
        .all()
    )
    hosts = profile_host_ids(db, [r.id for r in rows])
    return [profile_dict(r, hosts.get(str(r.id))) for r in rows]


def _tag_ids(db, host_ids) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    if not host_ids:
        return out
    for host_id, tag_id in (
        db.query(models.HostTag.host_id, models.HostTag.tag_id)
        .filter(models.HostTag.host_id.in_(list(host_ids)))
        .all()
    ):
        out.setdefault(str(host_id), []).append(str(tag_id))
    return out


def last_run(db, host_id) -> Optional[models.AutoUpdateRun]:
    return (
        db.query(models.AutoUpdateRun)
        .filter(
            models.AutoUpdateRun.host_id == host_id,
            models.AutoUpdateRun.status.notin_(("skipped", "waiting")),
        )
        .order_by(models.AutoUpdateRun.queued_at.desc())
        .first()
    )


def _last_good_backup(db, host_id):
    from backend.services import (  # pylint: disable=import-outside-toplevel
        backup_jobs as jobs,
    )

    row = (
        db.query(models.BackupRun)
        .filter(
            models.BackupRun.host_id == host_id,
            models.BackupRun.action == "capture",
            models.BackupRun.status.in_(jobs.GOOD_CAPTURE),
        )
        .order_by(models.BackupRun.queued_at.desc())
        .first()
    )
    if row is None:
        return None
    from backend.services.auto_update_results import (  # pylint: disable=import-outside-toplevel
        naive_utc,
    )

    return naive_utc(row.finished_at or row.queued_at)


def host_dict(db, host, tag_ids, profile) -> Dict[str, Any]:
    previous = last_run(db, host.id)
    ctx = {
        "id": str(host.id),
        "tag_ids": tag_ids,
        "active": bool(host.active),
        "approval_status": host.approval_status,
        "opted_out": bool(host.auto_update_opt_out),
        "image_mode": bool(getattr(host, "is_image_mode", False)),
        "needs_repair": bool(host.package_manager_needs_repair),
        "last_run": None,
        "last_good_backup_at": None,
    }
    if previous is not None:
        ctx["last_run"] = {
            "status": previous.status,
            "queued_at": previous.queued_at,
            "completed_at": previous.completed_at,
            "acknowledged": previous.acknowledged_at is not None,
        }
    if profile.get("require_backup_hours"):
        ctx["last_good_backup_at"] = _last_good_backup(db, host.id)
    return ctx


def as_written(value):
    """``PackageUpdate.discovered_at`` as it was written (naive UTC).  On
    PostgreSQL the column is ``timestamptz``: the naive UTC the handlers
    write is read back labeled with the session's time zone, and comparing
    that with the engine's naive ``now`` raised and stopped every policy
    from firing (lab, 2026-11-17).  Dropping the label recovers the value
    that was written."""
    if value is not None and getattr(value, "tzinfo", None) is not None:
        return value.replace(tzinfo=None)
    return value


def update_dicts(db, host_id) -> List[Dict[str, Any]]:
    rows = (
        db.query(models.PackageUpdate)
        .filter(models.PackageUpdate.host_id == host_id)
        .order_by(models.PackageUpdate.package_name)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "package_name": r.package_name,
            "package_manager": r.package_manager,
            "bundle_id": r.bundle_id,
            "update_type": r.update_type,
            "status": r.status,
            "held": bool(r.held),
            "requires_reboot": bool(r.requires_reboot),
            "current_version": r.current_version,
            "available_version": r.available_version,
            "discovered_at": as_written(r.discovered_at),
        }
        for r in rows
    ]


def covered_hosts(db, profile: Dict[str, Any]) -> List[models.Host]:
    query = db.query(models.Host)
    if profile["host_ids"]:
        query = query.filter(
            models.Host.id.in_([uuid.UUID(h) for h in profile["host_ids"]])
        )
    elif profile["tag_id"]:
        query = query.join(
            models.HostTag, models.HostTag.host_id == models.Host.id
        ).filter(models.HostTag.tag_id == uuid.UUID(profile["tag_id"]))
    return query.order_by(models.Host.fqdn).all()


# ---------------------------------------------------------------------------
# writing: a run, its execution logs, its command
# ---------------------------------------------------------------------------


def _package_record(update: Dict[str, Any]) -> Dict[str, Any]:
    record = {k: update.get(k) for k in ("package_name", "package_manager",
                                         "current_version", "available_version",
                                         "update_type", "kind", "fix_id")}  # fmt: skip
    # When the update first appeared: the report's "time from a critical
    # patch appearing to its being applied" (26.5) counts from it.
    seen = update.get("discovered_at")
    record["first_seen"] = seen.isoformat() if hasattr(seen, "isoformat") else seen
    return record


def _record(db, profile, host, plan, status, triggered_by, now, release_at=None,
            rollout=None):  # fmt: skip
    run = models.AutoUpdateRun(
        id=uuid.uuid4(),
        profile_id=uuid.UUID(profile["id"]),
        profile_name=profile["name"],
        host_id=host.id,
        status=status,
        reason=plan.get("reason"),
        triggered_by=triggered_by,
        packages=[_package_record(p) for p in plan.get("packages", [])],
        skipped=plan.get("skipped") or [],
        queued_at=now,
        release_at=release_at,
        completed_at=None if status in ("queued", "waiting") else now,
        rollout_id=rollout[0] if rollout else None,
        rollout_stage=rollout[1] if rollout else None,
    )
    db.add(run)
    return run


def _command_package(update: Dict[str, Any]) -> Dict[str, Any]:
    package = {
        "package_name": update["package_name"],
        "bundle_id": update.get("bundle_id"),
        "package_manager": update["package_manager"],
    }
    if update["package_manager"] == "fwupd":
        package["device_id"] = update.get("bundle_id")
    return package


def _queue_apply(db, host, run, packages, release_at, now):
    for update in packages:
        row = db.get(models.PackageUpdate, uuid.UUID(update["id"]))
        if row is not None:
            row.status = "updating"
            row.updated_at = now
        db.add(
            models.UpdateExecutionLog(
                host_id=host.id,
                package_name=update["package_name"],
                package_manager=update["package_manager"],
                from_version=update.get("current_version") or "unknown",
                to_version=update.get("available_version") or "unknown",
                execution_status="pending",
                executed_by=run.triggered_by or ACTOR,
                execution_method="automatic",
                run_id=run.id,
                created_at=now,
                updated_at=now,
            )
        )
    message = create_command_message(
        "apply_updates", {"packages": [_command_package(p) for p in packages]}
    )
    run.command_id = message.get("message_id")
    queue_ops.enqueue_message(
        message_type="command",
        message_data=message,
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
        scheduled_at=release_at if release_at and release_at > now else None,
        # Marks the message automatic: no emergency override lets it past a
        # closed window (26.2, outbound_processor.automatic_held).
        correlation_id=str(run.id),
    )
    AuditService.log(
        db=db,
        action_type=ActionType.EXECUTE,
        entity_type=EntityType.HOST,
        entity_id=str(host.id),
        entity_name=host.fqdn,
        description=_("Automatic update queued on %(host)s by policy '%(policy)s'")
        % {"host": host.fqdn, "policy": run.profile_name},
        result=Result.SUCCESS,
        username=run.triggered_by or ACTOR,
        details={
            "run_id": str(run.id),
            "packages": [p["package_name"] for p in packages],
            "skipped": run.skipped,
        },
        commit=False,
    )


def plan(db, eng, host, profile, settings, now, tag_ids=None) -> Dict[str, Any]:
    """The engine's plan for one host under ``profile`` now -- with what its
    pending updates fix (26.3: the waiting periods; 26.5: every applied
    critical-CVE patch is recorded as such, waiting or not, for the report's
    "critical patch to applied"), and a skip when the agent cannot apply
    updates at all."""
    if tag_ids is None:
        tag_ids = _tag_ids(db, [host.id]).get(str(host.id), [])
    ctx = host_dict(db, host, tag_ids, profile)
    updates = update_dicts(db, host.id)
    if hasattr(eng, "update_eligibility"):
        from backend.services import (  # pylint: disable=import-outside-toplevel
            auto_update_evidence,
        )

        auto_update_evidence.attach(db, host.id, updates)
    result = eng.plan_host_run(ctx, profile, updates, settings, now)
    if result["action"] == "apply" and host_supports(host, "apply_updates") is False:
        # An agent that does not advertise apply_updates refuses it at
        # queue time; raised here it aborted the whole policy and every
        # other host's run with it (screenshot VM, 2026-11-16).
        result = {**result, "action": "skip", "reason": AGENT_CANNOT_APPLY,
                  "packages": []}  # fmt: skip
    return result


def send(db, host, run, result, release_at, now) -> None:
    """Queue ``run``'s ``apply_updates`` with the packages ``result`` chose."""
    run.packages = [_package_record(p) for p in result["packages"]]
    run.skipped = result.get("skipped") or []
    run.status, run.release_at = "queued", release_at
    db.flush()
    _queue_apply(db, host, run, result["packages"], release_at, now)


def _place(db, eng, profile, host, result, triggered_by, now, offset, summary,
           rollout=None):  # fmt: skip
    """Record and (when its window allows) send one host's run (26.2)."""
    from backend.services import (  # pylint: disable=import-outside-toplevel
        auto_update_timing as timing,
    )

    release_at = now + timedelta(seconds=offset)
    answer = timing.slot(db, eng, host, profile, len(result["packages"]), now, offset)
    if answer is not None and answer["start"] is None:
        skipped = {**result, "reason": timing.NO_WINDOW, "packages": []}
        _record(db, profile, host, skipped, "skipped", triggered_by, now, None, rollout)
        summary["skipped"] += 1
        return
    if answer is not None:
        release_at = answer["start"]
    if answer is not None and answer["waits"]:
        _record(db, profile, host, result, timing.WAITING, triggered_by, now,
                release_at, rollout)  # fmt: skip
        summary["waiting"] += 1
        return
    run = _record(db, profile, host, result, "queued", triggered_by, now, release_at,
                  rollout)  # fmt: skip
    db.flush()
    _queue_apply(db, host, run, result["packages"], release_at, now)
    summary["queued"] += 1


def _adopt_waiting(db, profile, host, triggered_by, now, rollout) -> None:
    """A rollout's host whose run already waits for its window (26.2): the
    run joins the rollout -- or, when another policy's run is the one
    waiting, this policy's run says so."""
    run = (
        db.query(models.AutoUpdateRun)
        .filter(models.AutoUpdateRun.host_id == host.id,
                models.AutoUpdateRun.status == "waiting")  # fmt: skip
        .first()
    )
    if run is not None and str(run.profile_id) == profile["id"]:
        run.rollout_id, run.rollout_stage = rollout
        return
    skipped = {"reason": "previous_run_pending", "packages": []}
    _record(db, profile, host, skipped, "skipped", triggered_by, now, None, rollout)


def _record_unapplied(db, profile, host, result, context, summary) -> None:
    """A host skipped, or with nothing to apply: its run says so.
    ``context`` is ``(triggered_by, now, rollout)``."""
    triggered_by, now, rollout = context
    skipped = result["action"] == "skip"
    _record(db, profile, host, result, "skipped" if skipped else "nothing_to_do",
            triggered_by, now, None, rollout)  # fmt: skip
    summary["skipped" if skipped else "nothing"] += 1


def fire_hosts(db, eng, profile, hosts, tags, settings, now, triggered_by, summary,
               rollout=None):  # fmt: skip
    """Plan every host in ``hosts`` under ``profile`` and record (and, when
    its window allows, send) each one's run.  ``rollout`` is ``(rollout id,
    fleet index)`` when the hosts are a rollout's fleet (26.4)."""
    from backend.services import (  # pylint: disable=import-outside-toplevel
        auto_update_timing as timing,
    )

    for key in ("queued", "skipped", "nothing", "waiting"):
        summary.setdefault(key, 0)
    waiting = timing.waiting_host_ids(db)
    applying = []
    for host in hosts:
        if str(host.id) in waiting:
            summary["waiting"] += 1  # its run already waits for its window
            if rollout is not None:
                _adopt_waiting(db, profile, host, triggered_by, now, rollout)
            continue
        result = plan(db, eng, host, profile, settings, now, tags.get(str(host.id), []))
        if result["action"] in ("skip", "nothing"):
            _record_unapplied(db, profile, host, result, (triggered_by, now, rollout),
                              summary)  # fmt: skip
        else:
            applying.append((host, result))
    offsets = eng.stagger_offsets(len(applying), profile["staggered_window_min"])
    for (host, result), offset in zip(applying, offsets):
        _place(db, eng, profile, host, result, triggered_by, now, offset, summary,
               rollout)  # fmt: skip


def fire_profile(db, eng, profile_row, now, triggered_by=None) -> Dict[str, int]:
    """Run one policy now.  On the schedule (``triggered_by`` None) a host
    another policy wins for is left to that policy; a person's "run now"
    applies the profile they chose to every host it covers.  Either way a
    host with maintenance windows starts only inside one (26.2), and a
    policy that rolls out fleet by fleet starts a rollout (26.4)."""
    from backend.services import (  # pylint: disable=import-outside-toplevel
        auto_update_rollout as rollouts,
    )

    settings = settings_dict(settings_row(db))
    policies = auto_profiles(db)
    host_ids = profile_host_ids(db, [profile_row.id]).get(str(profile_row.id))
    profile = profile_dict(profile_row, host_ids)
    hosts = covered_hosts(db, profile)
    tags = _tag_ids(db, [h.id for h in hosts])
    summary = {"queued": 0, "skipped": 0, "nothing": 0, "other_policy": 0,
               "waiting": 0}  # fmt: skip
    chosen = []
    for host in hosts:
        if triggered_by is None:
            winner = eng.resolve_policy(
                {"id": str(host.id), "tag_ids": tags.get(str(host.id), [])}, policies
            )
            if not winner or winner["profile_id"] != profile["id"]:
                summary["other_policy"] += 1
                continue
        chosen.append(host)
    if rollouts.enabled(eng, profile_row):
        rollouts.start(db, eng, profile_row, chosen, tags, now,
                       triggered_by, summary)  # fmt: skip
        return summary
    fire_hosts(db, eng, profile, chosen, tags, settings, now, triggered_by, summary)
    return summary


# ---------------------------------------------------------------------------
# the tick
# ---------------------------------------------------------------------------


def expire_stale_runs(db, now) -> int:
    """Runs that never reported back within ``RUN_TIMEOUT_HOURS`` of their
    release are timed out, and their pending packages failed: an agent that
    restarted mid-update never answers, and a run left "queued" would block
    the host's every later run."""
    cutoff = now - timedelta(hours=RUN_TIMEOUT_HOURS)
    stale = (
        db.query(models.AutoUpdateRun)
        .filter(models.AutoUpdateRun.status == "queued")
        .all()
    )
    expired = 0
    for run in stale:
        if (run.release_at or run.queued_at) > cutoff:
            continue
        run.status, run.completed_at = "timed_out", now
        for log in db.query(models.UpdateExecutionLog).filter(
            models.UpdateExecutionLog.run_id == run.id,
            models.UpdateExecutionLog.execution_status == "pending",
        ):
            log.execution_status = "failed"
            log.error_log = _("The host never reported the result")
            log.completed_at = log.updated_at = now
            # As a reported failure does: left "updating", every later run
            # skipped the update as already_updating until the host's next
            # update scan (lab, 2026-11-17).
            db.query(models.PackageUpdate).filter(
                models.PackageUpdate.host_id == run.host_id,
                models.PackageUpdate.package_name == log.package_name,
                models.PackageUpdate.package_manager == log.package_manager,
                models.PackageUpdate.status == "updating",
            ).update({"status": "failed"}, synchronize_session=False)
        expired += 1
    return expired


def expire_stale_manual(db, now) -> int:
    """A manual "apply updates" whose host never answered (2026-11-19).

    Production: an "update all" whose batch included the agent's own package
    lost the result on seven of nine hosts, and their packages stayed
    "updating" with no end -- unlike an automatic run, a manual one had no
    timeout.  After RUN_TIMEOUT_HOURS its pending log fails with "The host
    never reported the result" and its package is "failed", as an automatic
    run's does.  Returns how many logs it closed."""
    cutoff = now - timedelta(hours=RUN_TIMEOUT_HOURS)
    stale = (
        db.query(models.UpdateExecutionLog)
        .filter(
            models.UpdateExecutionLog.run_id.is_(None),
            models.UpdateExecutionLog.execution_status == "pending",
            models.UpdateExecutionLog.created_at < cutoff,
        )
        .all()
    )
    for log in stale:
        log.execution_status = "failed"
        log.error_log = _("The host never reported the result")
        log.completed_at = log.updated_at = now
        db.query(models.PackageUpdate).filter(
            models.PackageUpdate.host_id == log.host_id,
            models.PackageUpdate.package_name == log.package_name,
            models.PackageUpdate.package_manager == log.package_manager,
            models.PackageUpdate.status == "updating",
        ).update({"status": "failed"}, synchronize_session=False)
    return len(stale)


def _due(db, now):
    return (
        db.query(models.UpgradeProfile)
        .filter(
            models.UpgradeProfile.enabled.is_(True),
            models.UpgradeProfile.auto_apply.is_(True),
            models.UpgradeProfile.held.is_(False),
            models.UpgradeProfile.next_run.isnot(None),
            models.UpgradeProfile.next_run <= now,
        )
        .all()
    )


def tick_database(db, eng, now, summary) -> None:
    from backend.services import (  # pylint: disable=import-outside-toplevel
        auto_update_results,
    )

    summary["timed_out"] += expire_stale_runs(db, now)
    db.commit()
    try:
        auto_update_results.follow_reboots(db, eng, now)
        db.commit()
    except Exception:  # pylint: disable=broad-exception-caught
        # Following reboots must never stop policies from firing.
        db.rollback()
        logger.exception("Automatic updates: following reboots failed")
    if settings_row(db).hold_all:
        summary["held"] = True
        db.commit()
        return
    try:
        from backend.services import (  # pylint: disable=import-outside-toplevel
            auto_update_timing,
        )

        summary["queued"] += auto_update_timing.start_waiting_runs(db, eng, now)
        db.commit()
    except Exception:  # pylint: disable=broad-exception-caught
        db.rollback()
        logger.exception("Automatic updates: starting waiting runs failed")
    from backend.services import (  # pylint: disable=import-outside-toplevel
        auto_update_rollout,
    )

    auto_update_rollout.advance_rollouts(db, eng, now)
    for profile in _due(db, now):
        try:
            fired = fire_profile(db, eng, profile, now)
            profile.last_run, profile.last_status = now, "SUCCESS"
            summary["queued"] += fired["queued"]
        except Exception:  # pylint: disable=broad-exception-caught
            db.rollback()
            logger.exception("Automatic updates: policy %s failed to fire", profile.id)
            profile.last_run, profile.last_status = now, "FAILURE"
        profile.next_run = eng.next_run_from_cron(
            profile.cron, datetime.now(timezone.utc)
        )
        if profile.next_run is not None and profile.next_run.tzinfo is not None:
            profile.next_run = profile.next_run.astimezone(timezone.utc).replace(
                tzinfo=None
            )
        db.commit()


def run_one_tick() -> Dict[str, Any]:
    """One pass over every tenant database.  Never raises."""
    summary: Dict[str, Any] = {"queued": 0, "timed_out": 0, "held": False}
    eng = engine()
    automatic = eng is not None and hasattr(eng, "plan_host_run")
    now = now_naive()
    for label, _tenant, db in iter_host_databases():
        try:
            # Manual updates time out in every edition (Community too).
            summary["timed_out"] += expire_stale_manual(db, now)
            db.commit()
            if automatic:
                tick_database(db, eng, now, summary)
        except Exception:  # pylint: disable=broad-exception-caught
            db.rollback()
            logger.exception("Automatic updates tick failed for database %s", label)
        finally:
            db.close()
    return summary


async def auto_update_tick_service() -> None:
    """Background service: one tick every ``TICK_INTERVAL_SECONDS``."""

    def _report(summary):
        if summary["queued"] or summary["timed_out"]:
            logger.info(
                "Automatic updates: queued=%d timed_out=%d",
                summary["queued"],
                summary["timed_out"],
            )

    await run_periodic(
        "Automatic updates tick",
        run_one_tick,
        TICK_INTERVAL_SECONDS,
        ERROR_BACKOFF_SECONDS,
        on_result=_report,
        logger=logger,
    )
