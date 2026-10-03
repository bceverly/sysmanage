# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Keep hosts equipped with antivirus without anyone clicking Deploy (21.3).

A malware scan runs on the host's own ClamAV, so a host without it is a blind
spot.  With ``malware_engine`` licensed, the malware tick calls ``reconcile``
for every host database and, for each approved, active host whose OS has an
antivirus default, queues the same deploy plan the Deploy button sends:

* once per ``av_plan_builder.PLAN_VERSION`` -- so a corrected plan reaches
  hosts that already run the old one -- and
* again when the agent reports that plan FAILED.

Done means the agent said the plan succeeded (``record_result``, matched by
the command id), not that the host reports ClamAV: on 2026-09-30 an agent
without BSD service control installed ClamAV, failed to start anything, and
"installed" made the host look finished.  A failed plan is retried with
backoff (``RETRY_BASE_HOURS``, doubling, at most ``RETRY_MAX_HOURS``) and
never given up on -- an agent update is often what makes the next try work.
A plan the queue gave up DELIVERING (no acknowledgment after its retries --
x13s, 2026-09-30, sent into a connection that never handed it over) counts
as a failed attempt too, so it is retried on the same backoff instead of
waiting a day.  A plan with no answer at all (host offline, old agent) is
re-sent after ``RETRY_MAX_HOURS``.
"""

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session, sessionmaker

from backend.persistence import db as persistence_db
from backend.persistence import models
from backend.services import av_plan_builder
from backend.utils.host_spread import host_offset
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import CommandType, Message, MessageType
from backend.websocket.queue_enums import QueueDirection, QueueStatus
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)

RETRY_BASE_HOURS = 1
RETRY_MAX_HOURS = 24
LOUD_AFTER_ATTEMPTS = 3
# Phase 22.3: a fleet-wide push goes out in WAVES.  A PLAN_VERSION bump made
# every host due at once and one tick queued them all -- every agent then
# downloading and installing antivirus in the same minute.  At most this many
# plans per database per pass (the malware tick runs every 5 minutes, so
# 3,000 an hour); the rest stay due for the next passes.
MAX_PUSHES_PER_PASS = 250
# Each host's retry waits up to this much longer than the base delay, by a
# fixed offset from its id, so hosts that failed together do not retry
# together (fixed per host, so a host's due time does not move tick to tick).
RETRY_SPREAD = 0.25

STATUS_QUEUED = "queued"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
# An operator removed or disabled antivirus on this host: auto-deploy leaves
# it alone -- even across plan versions -- until someone deploys or enables
# it again.  Without this, the next PLAN_VERSION bump would silently put back
# what an operator had taken off on purpose.
STATUS_OPTED_OUT = "opted_out"
SYSTEM_ACTOR = "system:antivirus-auto-deploy"

_queue_ops = QueueOperations()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def host_info_for_planner(host: Any) -> Dict[str, Any]:
    """Pack a Host's OS fields into the dict the AV plan builder expects."""
    return {
        # Spreads a scheduled scan's time per host (Phase 22.3).
        "host_id": str(host.id),
        "platform": host.platform,
        "platform_release": host.platform_release,
        "platform_version": host.platform_version,
        # Homebrew's prefix differs on Apple silicon (/opt/homebrew).
        "machine_architecture": getattr(host, "machine_architecture", None),
    }


def os_name_for_defaults(host: Any) -> Optional[str]:
    """The ``antivirus_default.os_name`` a host matches: the leading word of
    its release ("Ubuntu 25.04" -> "Ubuntu"), or its platform when the release
    is only a number (OpenBSD "7.7") or a macOS codename."""
    if host.platform == "macOS":
        return "macOS"
    raw = host.platform_release or host.platform
    if raw and not re.match(r"^[A-Za-z]", raw):
        raw = host.platform or raw
    if not raw:
        return None
    match = re.match(r"^([A-Za-z]+)", raw)
    return match.group(1) if match else raw


def queue_deploy(session: Session, host: Any, package: str) -> str:
    """Queue the deploy plan for ``host`` on ``session`` (not committed) and
    return its command id: ONE id for the envelope and the queue row, because
    the agent echoes the envelope's id back as ``command_id``."""
    plan = av_plan_builder.build_deploy_plan(host_info_for_planner(host), package)
    command_id = str(uuid.uuid4())
    message = Message(
        message_id=command_id,
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.APPLY_DEPLOYMENT_PLAN,
            "parameters": {"plan": plan},
        },
    )
    _queue_ops.enqueue_message(
        message_type="command",
        message_id=command_id,
        message_data=message.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=session,
    )
    return command_id


def _record_for(session: Session, host_id: Any):
    return (
        session.query(models.AntivirusAutoDeploy)
        .filter(models.AntivirusAutoDeploy.host_id == host_id)
        .first()
    )


def operator_opt_out(session: Session, host_id: Any, action: str, by: str) -> None:
    """Record that an operator removed/disabled antivirus on ``host_id`` (the
    caller commits).  Auto-deploy will not touch the host again until
    ``operator_opt_in``."""
    record = _record_for(session, host_id)
    if record is None:
        record = models.AntivirusAutoDeploy(
            host_id=host_id, antivirus_package="", attempts=0
        )
        session.add(record)
    record.plan_version = av_plan_builder.PLAN_VERSION
    record.requested_at = record.finished_at = _utcnow()
    record.status = STATUS_OPTED_OUT
    record.command_id = None
    record.last_error = f"{action} by {by}"[:2000]


def operator_opt_in(session: Session, host_id: Any) -> None:
    """An operator deployed/enabled antivirus on ``host_id``: auto-deploy may
    manage it again (the caller commits)."""
    record = _record_for(session, host_id)
    if record is not None and record.status == STATUS_OPTED_OUT:
        session.delete(record)


def retry_delay(attempts: int, host_id: Any = None) -> timedelta:
    """1 h, 2 h, 4 h ... at most a day, after ``attempts`` failed pushes --
    plus a fixed per-host share of ``RETRY_SPREAD`` (Phase 22.3)."""
    hours = min(RETRY_BASE_HOURS * (2 ** max(0, attempts - 1)), RETRY_MAX_HOURS)
    return timedelta(hours=hours * (1 + RETRY_SPREAD * host_offset(host_id)))


def _due(record, now: datetime) -> bool:
    """Whether a host needs a push now."""
    if record is not None and record.status == STATUS_OPTED_OUT:
        return False
    if record is None or record.plan_version < av_plan_builder.PLAN_VERSION:
        return True
    if record.status == STATUS_SUCCEEDED:
        return False
    if record.status == STATUS_FAILED:
        return (record.finished_at or record.requested_at) <= now - retry_delay(
            record.attempts, record.host_id
        )
    # Queued with no answer yet (offline host, or an agent too old to say).
    return record.requested_at <= now - timedelta(hours=RETRY_MAX_HOURS)


def _record_push(session, record, host_id, package, now, command_id):
    if record is None or record.plan_version < av_plan_builder.PLAN_VERSION:
        attempts = 1
    else:
        attempts = record.attempts + 1
    if record is None:
        record = models.AntivirusAutoDeploy(host_id=host_id)
        session.add(record)
    record.antivirus_package = package
    record.plan_version = av_plan_builder.PLAN_VERSION
    record.attempts = attempts
    record.requested_at = now
    record.status = STATUS_QUEUED
    record.command_id = command_id
    record.last_error = None
    record.finished_at = None
    return attempts


def _mark_undelivered(session: Session, records, label: str) -> None:
    """Plans the queue gave up delivering are failed attempts, not waits."""
    waiting = {
        r.command_id: r for r in records if r.status == STATUS_QUEUED and r.command_id
    }
    if not waiting:
        return
    rows = (
        session.query(models.MessageQueue.message_id, models.MessageQueue.error_message)
        .filter(models.MessageQueue.message_id.in_(list(waiting)))
        .filter(
            models.MessageQueue.status.in_((QueueStatus.FAILED, QueueStatus.EXPIRED))
        )
        .all()
    )
    for message_id, error in rows:
        record = waiting[message_id]
        record.status = STATUS_FAILED
        record.finished_at = _utcnow()
        record.last_error = f"not delivered: {error or 'the queue gave up'}"[:2000]
        logger.info(
            "Antivirus auto-deploy: plan v%d for host %s in %s was never delivered "
            "(%s); next try in %s",
            record.plan_version,
            record.host_id,
            label or "bootstrap",
            record.last_error,
            retry_delay(record.attempts, record.host_id),
        )


def _plan_errors(message_data: Dict[str, Any]) -> str:
    """The agent's own words for what went wrong, bounded."""
    result = message_data.get("result")
    errors = result.get("errors") if isinstance(result, dict) else None
    if errors:
        text = "; ".join(str(e) for e in errors)
    else:
        text = str(message_data.get("error") or "the agent reported failure")
    return text[:2000]


def record_result(session: Session, message_data: Dict[str, Any]) -> bool:
    """Record an ``apply_deployment_plan`` result if it answers an automatic
    deploy.  Returns False for any other plan (e.g. the Deploy button's), so
    the caller's normal handling runs.  The caller commits."""
    command_id = message_data.get("command_id")
    if not command_id:
        return False
    record = (
        session.query(models.AntivirusAutoDeploy)
        .filter(models.AntivirusAutoDeploy.command_id == str(command_id))
        .first()
    )
    if record is None:
        return False
    result = message_data.get("result")
    succeeded = bool(message_data.get("success")) and not (
        isinstance(result, dict) and result.get("success") is False
    )
    record.finished_at = _utcnow()
    if succeeded:
        record.status = STATUS_SUCCEEDED
        record.last_error = None
        logger.info(
            "Antivirus auto-deploy: plan v%d succeeded on host %s",
            record.plan_version,
            record.host_id,
        )
        return True
    record.status = STATUS_FAILED
    record.last_error = _plan_errors(message_data)
    log = logger.warning if record.attempts >= LOUD_AFTER_ATTEMPTS else logger.info
    log(
        "Antivirus auto-deploy: plan v%d FAILED on host %s (attempt %d; next try "
        "in %s): %s",
        record.plan_version,
        record.host_id,
        record.attempts,
        retry_delay(record.attempts, record.host_id),
        record.last_error,
    )
    return True


def _summarize(label: str, summary: Dict[str, Any]) -> None:
    """Log what a pass decided for one database, but only when it differs
    from the previous pass there: a host skipped for a reason (no default for
    its OS, not approved, offline) must be visible, not silent -- and not
    repeated every five minutes."""
    key = label or "bootstrap"
    shown = {k: v for k, v in summary.items() if k != "queued"}
    if _LAST_SUMMARY.get(key) == shown and not summary.get("queued"):
        return
    _LAST_SUMMARY[key] = shown
    logger.info("Antivirus auto-deploy in %s: %s", key, summary)


_LAST_SUMMARY: Dict[str, Dict[str, Any]] = {}


def _classify(host, defaults, records, now):
    """``(reason, package)``: why ``host`` is skipped, or ``("due", pkg)``."""
    if host.approval_status != "approved":
        return "not_approved", None
    if not host.active:
        return "inactive", None
    package = defaults.get(os_name_for_defaults(host) or "")
    if not package:
        return "no_default", None
    record = records.get(host.id)
    if record is not None and record.status == STATUS_OPTED_OUT:
        return "opted_out", None
    if _due(record, now):
        return "due", package
    if record.status == STATUS_SUCCEEDED:
        return "current", None
    if record.status == STATUS_FAILED:
        return "waiting_retry", None
    return "waiting_result", None


def reconcile(session: Session, label: str = "") -> Dict[str, Any]:
    """Queue deploy plans for this host database's hosts that need one.
    The caller commits.  Returns (and logs, when it changes) a summary."""
    now = _utcnow()
    defaults = {
        d.os_name: d.antivirus_package
        for d in session.query(models.AntivirusDefault).all()
        if d.antivirus_package
    }
    records = {r.host_id: r for r in session.query(models.AntivirusAutoDeploy).all()}
    _mark_undelivered(session, records.values(), label)
    summary: Dict[str, Any] = {"hosts": 0, "queued": 0, "defaults": len(defaults)}
    no_default = set()
    pushed = []
    for host in session.query(models.Host).all():
        summary["hosts"] += 1
        reason, package = _classify(host, defaults, records, now)
        if reason == "due" and len(pushed) >= MAX_PUSHES_PER_PASS:
            reason = "next_wave"  # still due: a later pass takes it
        if reason == "no_default":
            no_default.add(os_name_for_defaults(host) or "?")
        if reason != "due":
            summary[reason] = summary.get(reason, 0) + 1
            continue
        record = records.get(host.id)
        try:
            command_id = queue_deploy(session, host, package)
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "Antivirus auto-deploy could not queue a plan for host %s (%s) in %s",
                host.fqdn,
                host.id,
                label or "bootstrap",
            )
            summary["queue_failed"] = summary.get("queue_failed", 0) + 1
            continue
        attempts = _record_push(session, record, host.id, package, now, command_id)
        pushed.append((host, package, attempts))
    summary["queued"] = len(pushed)
    if no_default:
        summary["no_default_for"] = sorted(no_default)
    if pushed:
        _audit(pushed)
    _summarize(label, summary)
    return summary


def _audit(pushed) -> None:
    """Audit every automatic push on the main engine (where the audit trail
    lives), never failing the reconcile over it."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=persistence_db.get_engine()
    )
    try:
        with session_local() as audit_session:
            for host, package, attempts in pushed:
                AuditService.log(
                    commit=False,  # one commit for the whole wave (22.3)
                    db=audit_session,
                    action_type=ActionType.EXECUTE,
                    entity_type=EntityType.HOST,
                    entity_id=str(host.id),
                    entity_name=host.fqdn,
                    username=SYSTEM_ACTOR,
                    description=f"Automatic antivirus deployment queued for host {host.fqdn}",
                    result=Result.SUCCESS,
                    details={
                        "antivirus_package": package,
                        "plan_version": av_plan_builder.PLAN_VERSION,
                        "attempt": attempts,
                    },
                )
            audit_session.commit()
    except Exception:  # pylint: disable=broad-except
        logger.exception("Antivirus auto-deploy audit failed")
