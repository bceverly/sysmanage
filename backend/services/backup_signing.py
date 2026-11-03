# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Snapshot signing (Pro+ backup_engine, ROADMAP 24.6).

A snapshot is signed by the STORAGE host, never by the host it backs up --
a host that could sign could vouch for a snapshot it altered.  When the
target has a signer (``backup_target.sign_fingerprint``, set by
backup_engine) and the storage host's restate signs (``sign`` in the
policy's storage abilities), a good capture is followed by a ``sign`` run
on the storage host BEFORE ``protect``: restate cannot sign a snapshot that
protect already made immutable.  The run carries ``needs_key``; the storage
host's agent fetches the signer's secret key for that run only
(``backup_key_release``) and removes it when the run ends.

A sign that fails never holds the chain back: protect, seal and prune run
regardless, and the snapshot stays unsigned (restores then need the
operator's explicit acknowledgment, as in Community).

The backed-up hosts get the signer's PUBLIC key with their job files
(``trusted_key``), so restate checks every restore against it and refuses
a bad signature or another key's (exit 4, run status ``untrusted``).
"""

import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.websocket.messages import CommandType

logger = logging.getLogger(__name__)

SIGN = "sign"
_FINGERPRINT_MAX = 64


def target_of(
    db: Session, policy: models.BackupPolicy
) -> Optional[models.BackupTarget]:
    return (
        db.query(models.BackupTarget)
        .filter(models.BackupTarget.id == policy.target_id)
        .first()
    )


def signing_on(target: Optional[models.BackupTarget]) -> bool:
    """The target has a signer: its public key and the secret key's
    reference (the secret itself is in OpenBAO, read by backup_engine)."""
    return bool(
        target is not None
        and getattr(target, "sign_public_key", None)
        and getattr(target, "sign_key_ref", None)
    )


def storage_signs(policy: models.BackupPolicy) -> bool:
    """The policy's storage host reported a restate that signs."""
    try:
        found = json.loads(policy.storage_abilities or "[]")
    except ValueError:
        return False
    return isinstance(found, list) and SIGN in found


def wanted(db: Session, policy: models.BackupPolicy) -> bool:
    """Should this policy's new snapshots be signed?  Signing is Pro+: after a
    lapse it stops quietly rather than failing a sign job after every
    capture, and restores keep checking the signatures already made
    (``trusted_key`` is sent in every edition)."""
    return (
        signing_on(target_of(db, policy))
        and storage_signs(policy)
        and module_loader.get_module("backup_engine") is not None
    )


def queue_sign(
    db: Session, policy: models.BackupPolicy, storage_id: Any, snapshot: str
) -> models.BackupRun:
    """Sign ``snapshot`` on the storage host.  Never the key itself (this
    goes through the queue and the run row): the agent fetches it for this
    run (backup_key_release)."""
    return jobs._queue(  # pylint: disable=protected-access
        db,
        policy,
        storage_id,
        SIGN,
        CommandType.BACKUP_RUN,
        {
            "policy_id": str(policy.id),
            "action": SIGN,
            "snapshot": snapshot,
            "needs_key": True,
        },
        jobs.SYSTEM_ACTOR,
    )


def record_signed(
    db: Session, run: models.BackupRun, policy: models.BackupPolicy, result: Dict
) -> Optional[models.BackupSnapshot]:
    """A good sign run: the snapshot it names is signed, by ``signer``.
    restate's result names it as ``REPO::NAME`` (``signed``)."""
    if run.status != "ok":
        logger.error(
            "Backup policy %s: signing snapshot on storage host %s ended %s (%s); "
            "the snapshot stays unsigned and the chain goes on",
            policy.id,
            run.host_id,
            run.status,
            run.message,
        )
        return None
    name = _snapshot_name(result.get("signed")) or _snapshot_name(
        _run_parameters(run).get("snapshot")
    )
    if not name:
        return None
    row = (
        db.query(models.BackupSnapshot)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.name == name,
        )
        .first()
    )
    if row is None:
        return None
    row.signed = True
    signer = result.get("signer")
    if isinstance(signer, str) and signer:
        row.signer = signer[:_FINGERPRINT_MAX]
    logger.info(
        "Backup snapshot %s of policy %s signed by %s", name, policy.id, row.signer
    )
    return row


def record_listing(
    db: Session, run: models.BackupRun, policy: models.BackupPolicy, result: Dict
) -> None:
    """A storage-side ``signatures`` run (restate ``snapshots`` checked
    against the signer's key): each snapshot it found signed by a trusted
    key is signed.  This puts back what a lost catalog forgot (lab, t14,
    2026-11-03: a deleted policy cascaded the rows; du restored them as
    unsigned).  It only ever adds a signature: a snapshot restate does not
    vouch for keeps what the catalog says, and every restore is checked on
    the host regardless.  Only the storage host runs it -- never take a
    backed-up host's word for its own snapshots."""
    if run.status != "ok":
        logger.error(
            "Backup policy %s: listing signatures on storage host %s ended %s (%s)",
            policy.id,
            run.host_id,
            run.status,
            run.message,
        )
        return
    entries = result.get("snapshots")
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or entry.get("trusted") is not True:
            continue
        name, signer = entry.get("name"), entry.get("signer")
        if not isinstance(name, str) or not isinstance(signer, str) or not signer:
            continue
        row = (
            db.query(models.BackupSnapshot)
            .filter(
                models.BackupSnapshot.policy_id == policy.id,
                models.BackupSnapshot.name == name[:255],
                models.BackupSnapshot.gone_at.is_(None),
            )
            .first()
        )
        if row is not None and not row.signed:
            row.signed = True
            row.signer = signer[:_FINGERPRINT_MAX]
            logger.info(
                "Backup snapshot %s of policy %s: signature by %s found on storage",
                row.name,
                policy.id,
                row.signer,
            )


def _snapshot_name(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value:
        return None
    return value.rsplit("::", 1)[-1][:255]


def _run_parameters(run: models.BackupRun) -> Dict[str, Any]:
    try:
        value = json.loads(run.parameters) if run.parameters else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}
