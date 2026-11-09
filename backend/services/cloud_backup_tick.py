# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""iCloud Photos to local: the schedule (ROADMAP 24.12, Community).

Called by the backup tick (``backup_tick.reconcile``) every five minutes, in
every host database, once iCloud backup is enabled on the target's storage
host:

1. close cloud runs no result will ever answer, loudly: one that reported
   progress and then fell silent for three hours (a full download of a large
   library runs for days, reporting as it goes), else one sent twelve hours
   ago with no word;
2. start each enabled account's download when it is due -- ``interval_hours``
   after its last good one (an hour after a failure), inside its UTC window
   when it has one -- or when "Run now" asked for one.  The first download
   and then one a week is a FULL pass (``reconcile``, no ``--until-found``);
   the others stop after ``until_found`` photos already present.  They share
   the backup target's ``max_concurrent`` with the fleet's captures;
3. an account that needs sign-in is never started on schedule (it would
   only fail again); the Backups page says so;
3a. when Apple refuses to serve a download (HTTP 503: it limits how fast one
   account downloads), the download is tried again by itself -- schedule on
   or off -- after a cooldown that doubles, 1 h, 2 h, 4 h, 8 h, then 12 h.
   After ``APPLE_MAX_TRIES`` refusals in a row an account with its schedule
   off stops trying (the page says so); one with a schedule keeps trying
   every 12 hours.  Nothing is lost: the next run skips what is present;
4. warn before Apple's two-factor sign-in runs out (about two months): once
   per session, in the log, and by e-mail to the cloud backup managers when
   e-mail is configured.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.services import cloud_backup_jobs as cloud
from backend.services import queue_clock

logger = logging.getLogger(__name__)

STUCK_AFTER = timedelta(hours=12)
# A first full download of a large library can take days: a run that still
# reports progress is not stuck; one silent this long is.
SILENT_AFTER = timedelta(hours=3)
FAILED_RETRY = timedelta(hours=1)
WINDOW_HOURS = 6
SESSION_AUDIT = "iCloud sign-in expiry warning"
APPLE_BUSY = "apple_busy"
# What icloudpd prints when Apple answers 503 (pyicloud_ipd/utils.py); an
# agent older than the "apple_busy" reason reports it as "tool_failed".
# What icloudpd logs when Apple cuts a download off: a refusal (503), or the
# connection to iCloud lost partway (2026-11-06, 13:52 UTC: production's
# reconcile stopped in June 2015 and exited 0).  Either way the rest of the
# library is fetched after the cooldown.
APPLE_BUSY_MARKERS = (
    "Apple iCloud is temporary refusing to serve icloudpd",
    "Cannot connect to Apple iCloud service",
)


# icloudpd's log line: time, level, message.
_LOG_PREFIX = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:,\d+)? +[A-Z]+ +")


def apple_stopped(detail) -> bool:
    """A line whose MESSAGE is one of the markers: the run was stopped.  A
    message that only contains one is about one file -- icloudpd 1.33.0 logs
    "Could not connect to iCloud to download X: Cannot connect to Apple
    iCloud service", skips that file and carries on."""
    for line in (detail or "").splitlines():
        if _LOG_PREFIX.sub("", line.strip()).startswith(APPLE_BUSY_MARKERS):
            return True
    return False


APPLE_COOLDOWNS = tuple(timedelta(hours=h) for h in (1, 2, 4, 8, 12))
APPLE_MAX_TRIES = 10
COOLING_DOWN = "cooling_down"
MANAGE_CLOUD_BACKUPS_ROLE = "Manage Cloud Backups"


def _last_heard(run: models.CloudBackupRun) -> Optional[datetime]:
    """When the run last reported progress, if it has."""
    progress = cloud.parse_json(run.progress) or {}
    try:
        return datetime.fromisoformat(progress["at"]) if progress.get("at") else None
    except (TypeError, ValueError):
        return None


def _stuck(run: models.CloudBackupRun, sent, now: datetime) -> bool:
    heard = _last_heard(run)
    if heard is not None:  # it reports: stuck once it falls silent
        return now - heard > SILENT_AFTER
    waited = run.code_requested_at
    if waited is not None and now - waited > STUCK_AFTER:
        return True
    started = queue_clock.clock_start(sent.get(str(run.command_id)), run.queued_at)
    return started is not None and now - started > STUCK_AFTER


def fail_stuck(db: Session, now: datetime) -> int:
    """Close cloud runs no result will ever answer."""
    candidates = (
        db.query(models.CloudBackupRun)
        .filter(models.CloudBackupRun.status.in_(cloud.PENDING))
        .all()
    )
    if not candidates:
        return 0
    sent = queue_clock.deliveries(db, [run.command_id for run in candidates])
    closed = 0
    for run in candidates:
        if not _stuck(run, sent, now):
            continue
        run.status = cloud.FAILED
        run.finished_at = now
        run.mfa_code = None
        run.message = "no result: the storage host stopped reporting this run"
        if run.action == cloud.ENABLE:
            row = cloud.enable_row(db, run.target_id)
            if row is not None and row.run_id == run.id:
                row.status, row.reason, row.finished_at = cloud.FAILED, "no_result", now
        logger.error(
            "Cloud backup %s run %s (account %s) on host %s stopped reporting; "
            "marked failed",
            run.action, run.id, run.account_id, run.host_id,
        )  # fmt: skip
        closed += 1
    return closed


def _last(db: Session, account_id, statuses) -> Optional[models.CloudBackupRun]:
    return (
        db.query(models.CloudBackupRun)
        .filter(
            models.CloudBackupRun.account_id == account_id,
            models.CloudBackupRun.action.in_(cloud.TRANSFER_ACTIONS),
            models.CloudBackupRun.status.in_(statuses),
        )
        .order_by(models.CloudBackupRun.queued_at.desc())
        .first()
    )


def _apple_busy(run: models.CloudBackupRun) -> bool:
    return (cloud.parse_json(run.result) or {}).get("reason") == APPLE_BUSY


def apple_refusals(db: Session, account_id) -> List[models.CloudBackupRun]:
    """The account's latest downloads Apple refused, newest first, back to
    the last one that ended any other way."""
    recent = (
        db.query(models.CloudBackupRun)
        .filter(
            models.CloudBackupRun.account_id == account_id,
            models.CloudBackupRun.action.in_(cloud.TRANSFER_ACTIONS),
            models.CloudBackupRun.status.in_(cloud.FINAL),
        )
        .order_by(models.CloudBackupRun.queued_at.desc())
        .limit(APPLE_MAX_TRIES)
        .all()
    )
    refused = []
    for run in recent:
        if not _apple_busy(run):
            break
        refused.append(run)
    return refused


def apple_retry_at(db: Session, account: models.CloudBackupAccount):
    """When the download Apple refused is tried again, or None when it is not
    waiting on Apple (or has stopped trying: schedule off, too many tries)."""
    refused = apple_refusals(db, account.id)
    if not refused or (len(refused) >= APPLE_MAX_TRIES and not account.enabled):
        return None
    cooldown = APPLE_COOLDOWNS[min(len(refused), len(APPLE_COOLDOWNS)) - 1]
    last = refused[0]
    return (last.finished_at or last.queued_at) + cooldown


def in_window(account: models.CloudBackupAccount, now: datetime) -> bool:
    if account.window_start_hour is None:
        return True
    return (now.hour - account.window_start_hour) % 24 < WINDOW_HOURS


def due(db: Session, account: models.CloudBackupAccount, now: datetime) -> bool:
    """Whether the account's scheduled download may start now."""
    if account.run_requested_at is not None:
        return True
    if account.state == cloud.STATE_NEEDS_SIGN_IN:
        return False
    if account.session_created_at is None:
        return False  # never signed in: "Connect" first
    if not in_window(account, now):
        return False
    retry = apple_retry_at(db, account)
    if retry is not None:  # Apple refused the last one: finish it, schedule or not
        return now >= retry
    if not account.enabled:
        return False
    last = _last(db, account.id, cloud.FINAL)
    if last is None:
        return True
    if last.status != cloud.OK:
        return now >= (last.finished_at or last.queued_at) + FAILED_RETRY
    ended = last.finished_at or last.queued_at
    return now >= ended + timedelta(hours=max(1, account.interval_hours or 24))


def transfer_action(account: models.CloudBackupAccount, now: datetime) -> str:
    """A full pass first and once a week; incremental between them."""
    if account.last_full_at is None or now - account.last_full_at >= (
        cloud.RECONCILE_EVERY
    ):
        return cloud.RECONCILE
    return cloud.DOWNLOAD


def _captures(db: Session, target_id) -> int:
    return (
        db.query(models.BackupRun)
        .join(models.BackupPolicy, models.BackupPolicy.id == models.BackupRun.policy_id)
        .filter(
            models.BackupPolicy.target_id == target_id,
            models.BackupRun.action == "capture",
            models.BackupRun.status.in_(("queued", "running")),
        )
        .count()
    )


def _accounts(db: Session, target_id) -> List[models.CloudBackupAccount]:
    return (
        db.query(models.CloudBackupAccount)
        .filter(models.CloudBackupAccount.target_id == target_id)
        .order_by(models.CloudBackupAccount.created_at)
        .all()
    )


def start_due(db: Session, target, _host, now: datetime) -> int:
    """Queue the downloads that are due, within the target's free slots."""
    free = max(1, target.max_concurrent or 1) - _captures(db, target.id)
    free -= cloud.running_transfers(db, target.id)
    started = 0
    for account in _accounts(db, target.id):
        if started >= free:
            break
        if cloud.pending(db, account_id=account.id) or not due(db, account, now):
            continue
        actor = account.created_by or "system"
        if account.run_requested_at is not None:
            actor = "run now"
        try:
            cloud.queue_account_run(db, account, transfer_action(account, now), actor)
        except cloud.CloudBackupRefused as refused:
            logger.warning(
                "Cloud backup for account %s not started: %s", account.id, refused
            )
            continue
        finally:
            account.run_requested_at = None
        started += 1
    return started


def expires_at(account: models.CloudBackupAccount) -> Optional[datetime]:
    if account.session_created_at is None:
        return None
    return account.session_created_at + cloud.SESSION_LIFETIME


def expiring(account: models.CloudBackupAccount, now: datetime) -> bool:
    ends = expires_at(account)
    return ends is not None and now >= ends - cloud.SESSION_WARN_BEFORE


def _managers(db: Session) -> List[str]:
    """Active users who hold Manage Cloud Backups, and admins (their user ids
    are their e-mail addresses)."""
    holders = (
        db.query(models.User.userid)
        .join(
            models.UserSecurityRole, models.UserSecurityRole.user_id == models.User.id
        )
        .join(
            models.SecurityRole,
            models.SecurityRole.id == models.UserSecurityRole.role_id,
        )
        .filter(models.SecurityRole.name == MANAGE_CLOUD_BACKUPS_ROLE)
        .filter(models.User.active.is_(True))
        .all()
    )
    admins = (
        db.query(models.User.userid)
        .filter(models.User.is_admin.is_(True), models.User.active.is_(True))
        .all()
    )
    return sorted({row[0] for row in holders + admins if row[0] and "@" in row[0]})


def _email(db: Session, account: models.CloudBackupAccount) -> bool:
    """E-mail the warning when e-mail is configured; True when sent."""
    try:
        # pylint: disable=import-outside-toplevel
        from backend.persistence.tenant_context import (
            get_active_tenant,
        )  # noqa: PLC0415
        from backend.services.email_service import email_service  # noqa: PLC0415

        if not email_service.is_enabled():
            return False
        recipients = _managers(db)
        if not recipients:
            return False
        ends = expires_at(account)
        subject = _("iCloud sign-in ends soon: sign in again")
        body = _(
            "The iCloud sign-in for %(account)s ends around %(date)s. After "
            "that, SysManage cannot download its photos until someone signs "
            "in again.\n\nOpen Backups, then Cloud backup, and press Connect "
            "on this account. You will need the Apple ID's two-factor code."
        ) % {"account": account.display_name, "date": ends.strftime("%Y-%m-%d")}
        tenant = get_active_tenant()
        return bool(
            email_service.send_email(
                recipients, subject, body, tenant_id=str(tenant) if tenant else None
            )
        )
    except Exception:  # pylint: disable=broad-except
        logger.exception("iCloud sign-in warning e-mail failed")
        return False


def warn_expiring(db: Session, target_id, now: datetime) -> int:
    """Warn once per sign-in before it runs out; how many were warned."""
    warned = 0
    for account in _accounts(db, target_id):
        if not expiring(account, now) or account.session_warned_at is not None:
            continue
        account.session_warned_at = now
        sent = _email(db, account)
        logger.warning(
            "iCloud sign-in for cloud backup account %s ends around %s "
            "(e-mailed: %s)",
            account.id, expires_at(account), sent,
        )  # fmt: skip
        # pylint: disable=import-outside-toplevel
        from backend.services.audit_service import (  # noqa: PLC0415
            ActionType,
            AuditService,
            EntityType,
        )

        AuditService.log(
            db=db,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.SETTING,
            entity_id=str(account.id),
            entity_name=account.display_name,
            description=SESSION_AUDIT,
            details={"expires_at": expires_at(account).isoformat(), "emailed": sent},
            commit=False,
        )
        warned += 1
    return warned


def _eligible(host) -> bool:
    return host is not None and host.approval_status == "approved" and bool(host.active)


def reconcile(db: Session, target, now: datetime) -> int:
    """One database's cloud pass; how many jobs were queued.  Never raises
    into the backup tick: a cloud failure must not stop the fleet's backups."""
    try:
        fail_stuck(db, now)
        # The air-gap check last: it reads the server's settings in a session
        # of its own, needed only once iCloud backup is on.
        if target is None or not cloud.enabled(db, target.id) or cloud.airgapped():
            return 0
        warn_expiring(db, target.id, now)
        host = (
            db.query(models.Host)
            .filter(models.Host.id == target.storage_host_id)
            .first()
        )
        if not _eligible(host):
            return 0
        return start_due(db, target, host, now)
    except Exception:  # pylint: disable=broad-except
        logger.exception("Cloud backup scheduling failed")
        return 0
