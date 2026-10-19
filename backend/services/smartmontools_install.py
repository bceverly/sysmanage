# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Recommend smartmontools where a host's drives cannot be read (23.1 S6).

The agent reads drive health natively wherever the OS allows it (NVMe on
Linux and FreeBSD, macOS, Windows); SATA / SAS drives on Linux and FreeBSD
need ``smartctl``, and without it the drive is ``unknown`` with the reason
``smartctl_absent`` -- never "healthy".  Those hosts are RECOMMENDED
smartmontools:

* an operator installs it on one host or on every recommended host (OSS;
  the Manage Hardware Health AND Add Package roles -- installing a package
  is never wider than the package page allows);
* with Enterprise fleet bulk operations licensed AND an administrator's consent
  (the ``hardware_health.auto_install_smartmontools`` setting, off until
  someone turns it on, per tenant under multi-tenancy) the server installs
  it itself, as the antivirus auto-deploy does (21.3): retried with backoff
  when the agent reports failure, never given up on, audited.

The install is the generic deployment plan (``packages: ["smartmontools"]``,
the agent picks the package manager) -- except on Debian and Ubuntu, where
the package RECOMMENDS a mail client and that pulls in a mail server
(postfix): a disk-health tool must not put an MTA on every host, so there
it is ``apt-get install -y --no-install-recommends`` through
the plan's commands.  Done means the agent said so
(``record_result``, matched by command id).  The drives turn readable on the
agent's next collection (at most five minutes), which ends the
recommendation.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.config import settings_service
from backend.persistence import models
from backend.services import config_mgmt_dispatch
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.utils.host_spread import host_offset
from backend.websocket.messages import CommandType
from backend.websocket.queue_enums import QueueStatus

logger = logging.getLogger(__name__)

PACKAGE = "smartmontools"
REASON = "smartctl_absent"
SETTING_AUTO = "hardware_health.auto_install_smartmontools"
SYSTEM_ACTOR = "system:smartmontools-auto-install"

STATUS_QUEUED = "queued"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

RETRY_BASE_HOURS = 1
RETRY_MAX_HOURS = 24
RETRY_SPREAD = 0.25
# The agent re-collects every five minutes; a host still without readable
# drives this long after a SUCCESSFUL install (a package that does not ship
# smartctl, a PATH the agent does not see) is tried again, on the backoff.
RECHECK_AFTER_SUCCESS = timedelta(hours=1)
MAX_PUSHES_PER_PASS = 250


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def licensed() -> bool:
    """Automatic install is Enterprise: the server acting across the fleet on
    its own (fleet bulk operations).  Not ``auto_remediation``, which the
    tier table names but no issued license carries."""
    try:
        from backend.licensing.features import FeatureCode  # noqa: PLC0415
        from backend.licensing.license_service import (  # noqa: PLC0415
            license_service,
        )

        return bool(license_service.has_feature(FeatureCode.FLEET_BULK_OPERATIONS))
    except Exception:  # pylint: disable=broad-except
        logger.debug("license check failed; automatic install stays off", exc_info=True)
        return False


def auto_enabled(tenant_id: Optional[str]) -> bool:
    """The administrator's consent, for this tenant (or the server)."""
    if tenant_id:
        value = settings_service.get_tenant_setting(tenant_id, SETTING_AUTO)
    else:
        value = settings_service.get_setting(SETTING_AUTO, default=False)
    return value is True


def set_auto(tenant_id: Optional[str], enabled: bool) -> bool:
    if tenant_id:
        return settings_service.set_tenant_setting(tenant_id, SETTING_AUTO, enabled)
    return settings_service.set_setting(SETTING_AUTO, enabled)


def _needs(reasons_text: Optional[str]) -> bool:
    """The exact check behind the SQL ``LIKE`` pre-filter."""
    try:
        reasons = json.loads(reasons_text) if reasons_text else []
    except ValueError:
        return False
    return isinstance(reasons, list) and any(
        isinstance(r, dict) and r.get("code") == REASON for r in reasons
    )


def recommended_hosts(db: Session) -> List[models.Host]:
    """Approved, active hosts with a drive that only smartctl could read."""
    rows = (
        db.query(models.HardwareComponent.host_id, models.HardwareComponent.reasons)
        .filter(
            models.HardwareComponent.kind == "drive",
            models.HardwareComponent.reasons.like(f"%{REASON}%"),
        )
        .all()
    )
    ids = {host_id for host_id, reasons in rows if _needs(reasons)}
    if not ids:
        return []
    return (
        db.query(models.Host)
        .filter(
            models.Host.id.in_(ids),
            models.Host.approval_status == "approved",
            models.Host.active.is_(True),
        )
        .order_by(models.Host.fqdn)
        .all()
    )


def _record(db: Session, host_id) -> Optional[models.HardwareToolInstall]:
    return (
        db.query(models.HardwareToolInstall)
        .filter(models.HardwareToolInstall.host_id == host_id)
        .first()
    )


def install_view(record: Optional[models.HardwareToolInstall]) -> Optional[Dict]:
    if record is None:
        return None
    return {
        "package": record.package,
        "status": record.status,
        "attempts": record.attempts,
        "requested_by": record.requested_by,
        "requested_at": (
            record.requested_at.isoformat() if record.requested_at else None
        ),
        "finished_at": record.finished_at.isoformat() if record.finished_at else None,
        "last_error": record.last_error,
    }


def installs_by_host(db: Session, host_ids) -> Dict[str, Dict]:
    if not host_ids:
        return {}
    return {
        str(r.host_id): install_view(r)
        for r in db.query(models.HardwareToolInstall).filter(
            models.HardwareToolInstall.host_id.in_(list(host_ids))
        )
    }


_APT_FAMILY = ("ubuntu", "debian", "mint", "pop!_os", "raspbian", "kali")


def build_plan(host: models.Host) -> Dict[str, Any]:
    """The deployment plan that installs smartmontools on ``host``."""
    release = (host.platform_release or "").lower()
    if (host.platform or "").lower() == "linux" and any(
        name in release for name in _APT_FAMILY
    ):
        return {
            "commands": [
                {
                    "argv": ["apt-get", "update", "-q"],
                    "sudo": True,
                    "timeout": 300,
                    # a stale index usually still has the package
                    "ignore_errors": True,
                    "description": "refresh the package index",
                },
                {
                    # NOT ``env DEBIAN_FRONTEND=... apt-get``: the agent runs
                    # a sudo command as ``sudo -n <argv>``, the sudoers
                    # allowlist grants apt-get but not env, so every install
                    # was refused (beast, nextcloud, mail.archive,
                    # 2026-10-19).  smartmontools asks no debconf questions,
                    # and with no terminal apt never prompts.
                    "argv": [
                        "apt-get", "install", "-y", "-q",
                        "--no-install-recommends", PACKAGE,
                    ],  # fmt: skip
                    "sudo": True,
                    "timeout": 600,
                    "description": f"install {PACKAGE} (no mail server)",
                },
            ]
        }
    return {"packages": [PACKAGE]}


def queue_install(db: Session, host: models.Host, actor: str) -> str:
    """Queue the install on ``db`` (the caller commits); the command id."""
    command_id = config_mgmt_dispatch.queue_command(
        db,
        host.id,
        CommandType.APPLY_DEPLOYMENT_PLAN,
        {"plan": build_plan(host)},
    )
    record = _record(db, host.id)
    if record is None:
        record = models.HardwareToolInstall(host_id=host.id, attempts=0)
        db.add(record)
    automatic = actor == SYSTEM_ACTOR
    record.package = PACKAGE
    record.attempts = (record.attempts or 0) + 1 if automatic else 0
    record.status = STATUS_QUEUED
    record.command_id = command_id
    record.requested_by = actor
    record.requested_at = _now()
    record.finished_at = None
    record.last_error = None
    db.flush()
    return command_id


def _plan_errors(message_data: Dict[str, Any]) -> str:
    result = message_data.get("result")
    errors = result.get("errors") if isinstance(result, dict) else None
    if errors:
        return "; ".join(str(e) for e in errors)[:2000]
    return str(message_data.get("error") or "the agent reported failure")[:2000]


def record_result(db: Session, message_data: Dict[str, Any]) -> bool:
    """Record an ``apply_deployment_plan`` result if it answers one of these
    installs; False for any other plan.  The caller commits."""
    command_id = message_data.get("command_id")
    if not command_id:
        return False
    record = (
        db.query(models.HardwareToolInstall)
        .filter(models.HardwareToolInstall.command_id == str(command_id))
        .first()
    )
    if record is None:
        return False
    result = message_data.get("result")
    succeeded = bool(message_data.get("success")) and not (
        isinstance(result, dict) and result.get("success") is False
    )
    record.finished_at = _now()
    record.status = STATUS_SUCCEEDED if succeeded else STATUS_FAILED
    record.last_error = None if succeeded else _plan_errors(message_data)
    logger.info(
        "smartmontools install on host %s: %s%s",
        record.host_id,
        record.status,
        f" ({record.last_error})" if record.last_error else "",
    )
    return True


def retry_delay(attempts: int, host_id: Any = None) -> timedelta:
    """1 h, 2 h, 4 h ... at most a day, spread per host (22.3)."""
    hours = min(RETRY_BASE_HOURS * (2 ** max(0, attempts - 1)), RETRY_MAX_HOURS)
    return timedelta(hours=hours * (1 + RETRY_SPREAD * host_offset(host_id)))


def _due(record: Optional[models.HardwareToolInstall], now: datetime) -> bool:
    """Whether a recommended host gets an automatic push now."""
    if record is None:
        return True
    since = record.finished_at or record.requested_at
    if record.status == STATUS_QUEUED:
        # no answer (offline host, the queue gave up): again after a day
        return record.requested_at <= now - timedelta(hours=RETRY_MAX_HOURS)
    if record.status == STATUS_SUCCEEDED:
        return since <= now - max(
            RECHECK_AFTER_SUCCESS, retry_delay(record.attempts, record.host_id)
        )
    return since <= now - retry_delay(record.attempts, record.host_id)


def _mark_undelivered(db: Session) -> None:
    """Installs the queue gave up delivering are failed attempts."""
    waiting = {
        r.command_id: r
        for r in db.query(models.HardwareToolInstall).filter(
            models.HardwareToolInstall.status == STATUS_QUEUED
        )
        if r.command_id
    }
    if not waiting:
        return
    for message_id, error in (
        db.query(models.MessageQueue.message_id, models.MessageQueue.error_message)
        .filter(models.MessageQueue.message_id.in_(list(waiting)))
        .filter(
            models.MessageQueue.status.in_((QueueStatus.FAILED, QueueStatus.EXPIRED))
        )
    ):
        record = waiting[message_id]
        record.status = STATUS_FAILED
        record.finished_at = _now()
        record.last_error = f"not delivered: {error or 'the queue gave up'}"[:2000]


def reconcile(db: Session, tenant_id: Optional[str], label: str = "") -> int:
    """One automatic pass over one host database: how many installs were
    queued.  Nothing without the license AND the consent.  Caller commits."""
    if not licensed() or not auto_enabled(tenant_id):
        return 0
    _mark_undelivered(db)
    now = _now()
    queued: List[models.Host] = []
    for host in recommended_hosts(db):
        if len(queued) >= MAX_PUSHES_PER_PASS:
            break
        if _due(_record(db, host.id), now):
            queue_install(db, host, SYSTEM_ACTOR)
            queued.append(host)
    if queued:
        logger.info(
            "smartmontools auto-install queued for %d host(s) in %s",
            len(queued),
            label or "bootstrap",
        )
        _audit(db, queued)
    return len(queued)


def _audit(db: Session, hosts: List[models.Host]) -> None:
    """Audit every automatic push in the host database being reconciled --
    audit rows are per tenant -- committed with the pass (the caller
    commits), never failing the pass over it."""
    try:
        for host in hosts:
            AuditService.log(
                commit=False,
                db=db,
                action_type=ActionType.EXECUTE,
                entity_type=EntityType.HOST,
                entity_id=str(host.id),
                entity_name=host.fqdn,
                username=SYSTEM_ACTOR,
                description=f"Automatic {PACKAGE} install queued for host "
                f"{host.fqdn} (drive health unreadable)",
                result=Result.SUCCESS,
                details={"package": PACKAGE},
            )
    except Exception:  # pylint: disable=broad-except
        logger.exception("smartmontools auto-install audit failed")
