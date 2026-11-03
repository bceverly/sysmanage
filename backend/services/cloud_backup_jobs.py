# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""iCloud Photos to local (ROADMAP 24.12): the jobs and their rules.

Everything runs on the backup target's STORAGE HOST -- the machine that
already holds the fleet's backups -- never on a backed-up host.  Its agent
installs a pinned icloudpd, keeps each account's photos in their own dataset
(or directory) under the storage path, and runs the downloads.

The server sends only what the storage host's agent validates again: the run
id, the storage path, the Apple ID, the library name, the account's directory
name and the counts.  It never sends the Apple ID PASSWORD: that is written
straight to OpenBAO (``store_password``) and the agent fetches it over HTTPS
for one job, when icloudpd asks for it (``cloud_backup_secrets``).  The
two-factor code an operator types reaches the job the same way.
"""

import json
import re
import uuid
from datetime import timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import config_mgmt_dispatch
from backend.services.agent_capability_service import UnsupportedCapabilityError
from backend.websocket.messages import CommandType

ENABLE, CONNECT, DOWNLOAD, RECONCILE, LIBRARIES, REMOVE = (
    "enable",
    "connect",
    "download",
    "reconcile",
    "libraries",
    "remove",
)
ACTIONS = (ENABLE, CONNECT, DOWNLOAD, RECONCILE, LIBRARIES, REMOVE)
# Downloads share the backup target's concurrency cap with captures (24.8).
TRANSFER_ACTIONS = (DOWNLOAD, RECONCILE)
QUEUED, RUNNING, WAITING_CODE = "queued", "running", "waiting_code"
OK, FAILED, NEEDS_SIGN_IN = "ok", "failed", "needs_sign_in"
PENDING = (QUEUED, RUNNING, WAITING_CODE)
FINAL = (OK, FAILED, NEEDS_SIGN_IN)
# Account states shown on the Backups page.
STATE_NEW, STATE_OK, STATE_FAILED = "new", "ok", "failed"
STATE_NEEDS_SIGN_IN = NEEDS_SIGN_IN

# Apple's two-factor sign-in lasts about two months; warn this long before.
SESSION_LIFETIME = timedelta(days=60)
SESSION_WARN_BEFORE = timedelta(days=10)
# A weekly full pass without --until-found catches what an incremental missed.
RECONCILE_EVERY = timedelta(days=7)
DEFAULT_UNTIL_FOUND = 50
# The cloud root's name under the storage path.
CLOUD_ROOT = "cloud-photos"
PROVIDER = "icloud"

_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")
# A library name as icloudpd lists them ("PrimarySync", "SharedSync-<id>").
_LIBRARY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]{0,127}$")
_DIR = re.compile(r"^icloud-[0-9a-f]{8}$")
_CODE = re.compile(r"^\d{6}$")


class CloudBackupRefused(Exception):
    """A request the rules refuse; ``status`` is the HTTP status."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def now():
    return jobs.now()


def valid_apple_id(value: Any) -> str:
    text = str(value or "").strip()
    if not _EMAIL.match(text):
        raise CloudBackupRefused(422, _("An Apple ID is an e-mail address"))
    return text


def valid_library(value: Any) -> str:
    text = str(value or "PrimarySync").strip()
    if not _LIBRARY.match(text):
        raise CloudBackupRefused(422, _("That is not an iCloud library name"))
    return text


def valid_code(value: Any) -> str:
    text = str(value or "").strip().replace(" ", "")
    if not _CODE.match(text):
        raise CloudBackupRefused(422, _("A two-factor code is six digits"))
    return text


def valid_dir(value: str) -> str:
    if not _DIR.match(value or ""):
        raise CloudBackupRefused(422, "bad account directory")
    return value


def dir_name_for(account_id: Any) -> str:
    return "icloud-" + uuid.UUID(str(account_id)).hex[:8]


def airgapped() -> bool:
    """An air-gapped repository appliance has no internet: the feature is
    hidden there (it is the one part of Phase 24 that needs it)."""
    # pylint: disable=import-outside-toplevel
    from backend.services import server_config_service  # noqa: PLC0415

    return server_config_service.get_server_role() == "repository"


def target_and_storage(db: Session):
    """``(target, storage host)``; refused when there is no target or no
    storage host to run on."""
    target = jobs.the_target(db)
    if target is None:
        raise CloudBackupRefused(409, _("Set up the backup target first"))
    host = jobs.storage_host(db, target)
    if host is None or not target.storage_path:
        raise CloudBackupRefused(
            409, _("The backup target has no storage host to run on")
        )
    return target, host


def enable_row(db: Session, target_id: Any) -> Optional[models.CloudBackupEnable]:
    return (
        db.query(models.CloudBackupEnable)
        .filter(models.CloudBackupEnable.target_id == target_id)
        .first()
    )


def enabled(db: Session, target_id: Any) -> bool:
    row = enable_row(db, target_id)
    return row is not None and row.status == OK


def pending(db: Session, account_id: Any = None, target_id: Any = None) -> bool:
    query = db.query(models.CloudBackupRun.id).filter(
        models.CloudBackupRun.status.in_(PENDING)
    )
    if account_id is not None:
        query = query.filter(models.CloudBackupRun.account_id == account_id)
    if target_id is not None:
        query = query.filter(models.CloudBackupRun.target_id == target_id)
    return query.first() is not None


def running_transfers(db: Session, target_id: Any) -> int:
    """Downloads queued or running on the target (they share its cap)."""
    return (
        db.query(models.CloudBackupRun)
        .filter(
            models.CloudBackupRun.target_id == target_id,
            models.CloudBackupRun.action.in_(TRANSFER_ACTIONS),
            models.CloudBackupRun.status.in_(PENDING),
        )
        .count()
    )


def _queue(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session,
    target: models.BackupTarget,
    host: models.Host,
    action: str,
    parameters: Dict[str, Any],
    actor: str,
    account: Optional[models.CloudBackupAccount] = None,
) -> models.CloudBackupRun:
    run_id = uuid.uuid4()
    run = models.CloudBackupRun(
        id=run_id,
        target_id=target.id,
        account_id=account.id if account is not None else None,
        host_id=host.id,
        action=action,
        status=QUEUED,
        queued_at=now(),
        requested_by=actor,
    )
    db.add(run)
    db.flush()
    command = {
        ENABLE: CommandType.CLOUD_BACKUP_ENABLE,
        REMOVE: CommandType.CLOUD_BACKUP_REMOVE,
    }.get(action, CommandType.CLOUD_BACKUP_RUN)
    try:
        run.command_id = config_mgmt_dispatch.queue_command(
            db,
            host.id,
            command,
            {"run_id": str(run_id), "action": action, **parameters},
        )
    except UnsupportedCapabilityError as refused:
        # The storage host's agent cannot run it (yet): too old, an OS
        # icloudpd has no build for, or iCloud backup not enabled there.
        db.delete(run)
        raise CloudBackupRefused(409, str(refused)) from refused
    db.flush()
    return run


def queue_enable(
    db: Session, target: models.BackupTarget, host: models.Host, actor: str
) -> models.CloudBackupRun:
    """ "Enable iCloud backup": install the pinned icloudpd, prepare the
    cloud root under the storage path and the root-only session directory.
    Idempotent on the agent: pressing it again repairs or upgrades."""
    run = _queue(db, target, host, ENABLE, {"storage_path": target.storage_path}, actor)
    row = enable_row(db, target.id) or models.CloudBackupEnable(target_id=target.id)
    row.host_id = host.id
    row.status, row.reason, row.detail = RUNNING, None, None
    row.run_id = run.id
    row.requested_by = actor
    row.requested_at = now()
    row.finished_at = None
    db.add(row)
    return run


def account_parameters(
    account: models.CloudBackupAccount, target: models.BackupTarget, action: str
) -> Dict[str, Any]:
    parameters: Dict[str, Any] = {
        "account_id": str(account.id),
        "apple_id": account.apple_id,
        "library": account.library,
        "dir_name": valid_dir(account.dir_name),
        "storage_path": target.storage_path,
    }
    if action == DOWNLOAD:
        parameters["until_found"] = int(account.until_found or DEFAULT_UNTIL_FOUND)
    if action in (DOWNLOAD, RECONCILE):
        parameters["auto_delete"] = bool(account.auto_delete)
    return parameters


def queue_account_run(
    db: Session,
    account: models.CloudBackupAccount,
    action: str,
    actor: str,
) -> models.CloudBackupRun:
    target, host = target_and_storage(db)
    if action != REMOVE and not enabled(db, target.id):
        raise CloudBackupRefused(
            409, _("Enable iCloud backup on the storage host first")
        )
    if action != REMOVE and pending(db, account_id=account.id):
        raise CloudBackupRefused(
            409, _("A job for this account is already queued or running")
        )
    return _queue(
        db,
        target,
        host,
        action,
        account_parameters(account, target, action),
        actor,
        account,
    )


def parse_json(text: Optional[str]) -> Any:
    try:
        return json.loads(text) if text else None
    except ValueError:
        return None
