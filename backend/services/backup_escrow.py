# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Break-glass escrow: is every encrypted host's newest key in an export?
(Pro+ backup_engine, ROADMAP 24.6; Bryan, 2026-11-03.)

A break-glass export holds the keys that existed when it was made.  A host
encrypted, or a key rotated, after the last export leaves that export short
of a key newer snapshots need -- and nothing said so until the advisor's
PM-BACKUP-KEY-ESCROW check.  This module is that check's one source of truth,
shared with the Encryption panel, the Backups page banner and the dashboard:

* ``host_state``     per encrypted host: ok / failing (None when not encrypted);
* ``status``         the fleet view: last export, who, sealed to which key,
                     how many encrypted hosts it covers, and whether it is stale
                     (a host or a key -- encryption or signing -- newer than it);
* ``save_escrow_key`` remember the operator's escrow PUBLIC key (exports
                     default to it); only the public half is ever accepted;
* ``remind_after_rotation`` email Manage Backups after a SCHEDULED rotation,
                     when email is configured, and audit it.

History comes from the audit log: the engine writes one
"Backup keys exported (break-glass)" entry per host in an export.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.services import backup_jobs as jobs

logger = logging.getLogger(__name__)

# The audit entry backup_engine writes for each host in a break-glass export.
BREAK_GLASS_AUDIT = "Backup keys exported (break-glass)"
REMINDER_AUDIT = "Backup key escrow reminder sent"
MANAGE_BACKUPS_ROLE = "Manage Backups"


def _naive(when: Optional[datetime]) -> Optional[datetime]:
    if when is not None and when.tzinfo is not None:
        return when.astimezone(timezone.utc).replace(tzinfo=None)
    return when


def _iso(when: Optional[datetime]) -> Optional[str]:
    return when.isoformat() + "Z" if when is not None else None


def backup_engine():
    """backup_engine when loaded; None otherwise (Community)."""
    # pylint: disable=import-outside-toplevel
    from backend.licensing.module_loader import module_loader  # noqa: PLC0415

    return module_loader.get_module("backup_engine")


def newest_key_at(db: Session, policy) -> Optional[datetime]:
    """When the policy's newest encryption key was made."""
    made = (
        db.query(func.max(models.BackupPolicyKey.created_at))
        .filter(models.BackupPolicyKey.policy_id == policy.id)
        .scalar()
    )
    candidates = [
        _naive(t) for t in (made, policy.encrypted_at, policy.encrypt_rotated_at) if t
    ]
    return max(candidates) if candidates else None


def last_export_at(db: Session, host_id: Any) -> Optional[datetime]:
    """When this host's keys were last in a break-glass export."""
    return _naive(
        db.query(func.max(models.AuditLog.timestamp))
        .filter(
            models.AuditLog.entity_id == str(host_id),
            models.AuditLog.description == BREAK_GLASS_AUDIT,
        )
        .scalar()
    )


def host_state(db: Session, host, policy) -> Optional[str]:
    """ok when the host's newest key is in an export made after it; failing
    when there is no export or it predates the key; None when unencrypted."""
    if policy is None or not policy.encrypt_fingerprint:
        return None
    exported = last_export_at(db, host.id)
    if exported is None:
        return "failing"
    since = newest_key_at(db, policy)
    return "ok" if since is None or exported > since else "failing"


def _last_export_row(db: Session) -> Optional[models.AuditLog]:
    return (
        db.query(models.AuditLog)
        .filter(models.AuditLog.description == BREAK_GLASS_AUDIT)
        .order_by(models.AuditLog.timestamp.desc())
        .first()
    )


def _export_dict(row: Optional[models.AuditLog]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    details = row.details if isinstance(row.details, dict) else {}
    return {
        "at": _iso(_naive(row.timestamp)),
        "by": row.username,
        "recipient": details.get("recipient"),
        "reason": details.get("reason"),
    }


def _escrow_key_dict(target) -> Optional[Dict[str, Any]]:
    if target is None or not getattr(target, "escrow_fingerprint", None):
        return None
    return {
        "fingerprint": target.escrow_fingerprint,
        "uid": target.escrow_uid,
        "saved_at": _iso(_naive(target.escrow_saved_at)),
        "saved_by": target.escrow_saved_by,
        "public_key": target.escrow_public_key,
    }


def status(db: Session) -> Dict[str, Any]:
    """The fleet's escrow status.  ``applies`` is False in Community, or with
    nothing encrypted and signing off -- then nothing needs escrow."""
    target = jobs.the_target(db)
    signing_at = _naive(getattr(target, "signing_enabled_at", None))
    rows = (
        db.query(models.BackupPolicy, models.Host)
        .join(models.Host, models.Host.id == models.BackupPolicy.host_id)
        .filter(models.BackupPolicy.encrypt_fingerprint.isnot(None))
        .all()
    )
    applies = backup_engine() is not None and (bool(rows) or signing_at is not None)
    stale_hosts: List[str] = []
    export_host_id: Optional[str] = None  # where the banner's link goes
    for policy, host in rows:
        if host_state(db, host, policy) != "ok":
            stale_hosts.append(host.fqdn)
            export_host_id = export_host_id or str(host.id)
    if export_host_id is None and rows:
        export_host_id = str(rows[0][1].id)
    last = _last_export_row(db)
    last_at = _naive(last.timestamp) if last is not None else None
    signing_stale = signing_at is not None and (last_at is None or last_at < signing_at)
    return {
        "applies": applies,
        "encrypted_hosts": len(rows),
        "covered_hosts": len(rows) - len(stale_hosts),
        "stale_hosts": sorted(stale_hosts),
        "signing_on": signing_at is not None,
        "signing_stale": signing_stale,
        "stale": applies and (last is None or bool(stale_hosts) or signing_stale),
        "last_export": _export_dict(last),
        "escrow_key": _escrow_key_dict(target),
        "export_host_id": export_host_id,
    }


class EscrowKeyRefused(ValueError):
    """The pasted key cannot be the escrow key (said why)."""


def save_escrow_key(db: Session, target, armored: str, who: str) -> Dict[str, Any]:
    """Remember the operator's escrow PUBLIC key on the target.  The engine
    reads it with gpg (one usable public key that can encrypt); a private
    key block is refused before anything else looks at it."""
    if not isinstance(armored, str) or "PRIVATE KEY" in armored:
        raise EscrowKeyRefused(
            _("That is a SECRET key; paste the PUBLIC key (gpg --armor --export)")
        )
    engine = backup_engine()
    if engine is None or not hasattr(engine, "inspect_recipient"):
        raise EscrowKeyRefused(_("The backup engine is not available"))
    try:
        fingerprint, uid = engine.inspect_recipient(armored)
    except Exception as refused:  # BreakGlassRefused / BackupKeyError
        raise EscrowKeyRefused(str(refused)) from refused
    target.escrow_public_key = armored.strip() + "\n"
    target.escrow_fingerprint = fingerprint
    target.escrow_uid = (uid or "")[:255] or None
    target.escrow_saved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    target.escrow_saved_by = (who or "")[:255] or None
    return _escrow_key_dict(target)


def _backup_managers(db: Session) -> List[str]:
    """Active users who hold Manage Backups (or are admins); their user ids
    are their e-mail addresses."""
    holders = (
        db.query(models.User.userid)
        .join(
            models.UserSecurityRole, models.UserSecurityRole.user_id == models.User.id
        )
        .join(
            models.SecurityRole,
            models.SecurityRole.id == models.UserSecurityRole.role_id,
        )
        .filter(models.SecurityRole.name == MANAGE_BACKUPS_ROLE)
        .filter(models.User.active.is_(True))
        .all()
    )
    admins = (
        db.query(models.User.userid)
        .filter(models.User.is_admin.is_(True), models.User.active.is_(True))
        .all()
    )
    found = {row[0] for row in holders + admins if row[0] and "@" in row[0]}
    return sorted(found)


def remind_after_rotation(
    db: Session, rotated: int, tenant_id: Optional[str] = None
) -> bool:
    """A scheduled rotation made new keys an existing export lacks: e-mail
    the backup managers (only when e-mail is configured) and audit it.
    True when an e-mail went out.  Never raises."""
    if rotated <= 0:
        return False
    try:
        # pylint: disable=import-outside-toplevel
        from backend.services.audit_service import (  # noqa: PLC0415
            ActionType,
            AuditService,
            EntityType,
        )
        from backend.services.email_service import email_service  # noqa: PLC0415

        if not email_service.is_enabled():
            return False
        recipients = _backup_managers(db)
        if not recipients:
            return False
        subject = _("Backup keys rotated: make a new break-glass export")
        body = _(
            "SysManage rotated %(count)d backup encryption key(s) on schedule. "
            "A break-glass export made before this rotation does not hold the "
            "new keys, and backups taken from now on need them.\n\n"
            "Open Backups, then a host's Encryption panel, and use "
            '"Break-glass key export" to make a new export. Keep it offline, '
            "and destroy the old one."
        ) % {"count": rotated}
        sent = email_service.send_email(recipients, subject, body, tenant_id=tenant_id)
        AuditService.log(
            db=db,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.SETTING,
            description=REMINDER_AUDIT,
            details={
                "rotated": rotated,
                "recipients": len(recipients),
                "sent": bool(sent),
            },
            commit=False,
        )
        return bool(sent)
    except Exception:  # pylint: disable=broad-except
        logger.exception("Backup key escrow reminder failed")
        return False
