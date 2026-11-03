# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The Apple ID password and the two-factor code (ROADMAP 24.12).

The PASSWORD goes straight from the add-account form to OpenBAO under the
tenant's own path (``store_password``); the database keeps only that path.
It never travels in a job's command (commands sit in the database-backed
message queue): the storage host's agent asks for it over HTTPS with its own
host credentials (``POST /api/agent/cloud-backup-secret``) at the moment
icloudpd prompts for it, and ``release_password`` decides, the way
``backup_key_release`` does for backup keys:

* the run exists, belongs to the asking host, is an account job that is still
  queued or running;
* it was SENT within ``RELEASE_WINDOW``, and its password was not released
  before (``password_released_at``) -- once per run;

and every release is audited by the caller.

The TWO-FACTOR CODE an operator types in the Backups page is held on the run
(``mfa_code``) only until the waiting job collects it
(``POST /api/agent/cloud-backup-code``); it is cleared the moment it is
handed over, and refused once ``CODE_WINDOW`` has passed.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.services import cloud_backup_jobs as cloud
from backend.services import queue_clock

logger = logging.getLogger(__name__)

RELEASE_WINDOW = timedelta(hours=1)
# How long a job waits for an operator's code before giving up.
CODE_WINDOW = timedelta(minutes=15)
SECRET_TYPE = "cloud_backup"
ACCOUNT_ACTIONS = (cloud.CONNECT, cloud.DOWNLOAD, cloud.RECONCILE, cloud.LIBRARIES)


class SecretRefused(Exception):
    """Why a run gets no password or code; ``status`` is the HTTP status."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _tenant_scope() -> str:
    """The OpenBAO subpath for this tenant (``server`` when the server is not
    multi-tenant): one tenant's passwords never sit in another's."""
    # pylint: disable=import-outside-toplevel
    from backend.persistence.tenant_context import get_active_tenant  # noqa: PLC0415

    tenant = get_active_tenant()
    return str(tenant) if tenant else "server"


def _vault(vault=None):
    if vault is not None:
        return vault
    # pylint: disable=import-outside-toplevel
    from backend.services.vault_service import VaultService  # noqa: PLC0415

    return VaultService()


def store_password(account_id: Any, password: str, vault=None) -> str:
    """Put the Apple ID password in OpenBAO; return its path."""
    if not password:
        raise cloud.CloudBackupRefused(422, _("Enter the Apple ID password"))
    stored = _vault(vault).store_secret(
        secret_name=f"cloud-backup/{account_id}",
        secret_data=password,
        secret_type=SECRET_TYPE,
        secret_subtype=_tenant_scope(),
    )
    reference = stored.get("vault_path") if isinstance(stored, dict) else None
    if not reference:
        raise cloud.CloudBackupRefused(
            503, _("OpenBAO did not say where it stored the password")
        )
    return reference


def delete_password(reference: Optional[str], vault=None) -> None:
    """Remove a password from OpenBAO (account deleted or password replaced).
    A failure is logged, never raised: the account goes either way."""
    if not reference:
        return
    try:
        _vault(vault).delete_secret(reference)
    except Exception as error:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Could not delete a cloud backup account's OpenBAO entry: %s", error
        )


def read_password(reference: Optional[str], vault=None) -> str:
    if not reference:
        raise SecretRefused(409, _("This account has no password in OpenBAO"))
    stored = _vault(vault).retrieve_secret(reference)
    content = stored.get("content") if isinstance(stored, dict) else None
    if not isinstance(content, str) or not content:
        raise SecretRefused(503, _("OpenBAO does not hold this account's password"))
    return content


def run_for(db: Session, host_id: str, run_id: Any) -> models.CloudBackupRun:
    try:
        key = uuid.UUID(str(run_id))
    except ValueError:
        key = None
    run = (
        db.query(models.CloudBackupRun).filter(models.CloudBackupRun.id == key).first()
        if key
        else None
    )
    if run is None or str(run.host_id) != str(host_id):
        # The same answer for "no such run" and "not yours".
        raise SecretRefused(404, _("No such cloud backup run for this host"))
    return run


def _check_live(db: Session, run: models.CloudBackupRun, now: datetime) -> None:
    if run.action not in ACCOUNT_ACTIONS or run.account_id is None:
        raise SecretRefused(409, _("This cloud backup run does not sign in"))
    if run.status not in cloud.PENDING:
        raise SecretRefused(409, _("This cloud backup run has already ended"))
    started = queue_clock.clock_start(
        queue_clock.delivery(db, run.command_id), run.queued_at
    )
    if started and now - started > RELEASE_WINDOW:
        raise SecretRefused(409, _("This cloud backup run is too old"))


def _account(db: Session, run: models.CloudBackupRun) -> models.CloudBackupAccount:
    account = (
        db.query(models.CloudBackupAccount)
        .filter(models.CloudBackupAccount.id == run.account_id)
        .first()
    )
    if account is None:
        raise SecretRefused(409, _("This cloud backup account was deleted"))
    return account


def release_password(
    db: Session, host_id: str, run_id: Any, now: Optional[datetime] = None, vault=None
) -> str:
    """The account's password for this host's own pending run, once."""
    now = now or cloud.now()
    run = run_for(db, host_id, run_id)
    _check_live(db, run, now)
    if run.password_released_at is not None:
        raise SecretRefused(409, _("This run's password was already released"))
    account = _account(db, run)
    try:
        password = read_password(account.password_ref, vault=vault)
    except SecretRefused:
        raise
    except Exception as error:  # the vault's own message says why
        logger.exception("Cloud backup run %s: its OpenBAO entry is unreadable", run.id)
        raise SecretRefused(503, str(error)) from error
    run.password_released_at = now
    logger.info("Cloud backup sign-in released to host %s for run %s", host_id, run.id)
    return password


def submit_code(
    _db: Session, run: models.CloudBackupRun, code: str, now: Optional[datetime] = None
) -> None:
    """An operator's two-factor code for a job that is waiting for one."""
    now = now or cloud.now()
    code = cloud.valid_code(code)
    if run.status != cloud.WAITING_CODE:
        raise cloud.CloudBackupRefused(409, _("This sign-in is not waiting for a code"))
    asked = run.code_requested_at
    if asked is not None and now - asked > CODE_WINDOW:
        raise cloud.CloudBackupRefused(
            409, _("This sign-in waited too long; press Connect again")
        )
    run.mfa_code = code


def release_code(
    db: Session, host_id: str, run_id: Any, now: Optional[datetime] = None
) -> Optional[str]:
    """The operator's code for this host's waiting job, once; ``None`` while
    nobody has typed it yet (the agent asks again)."""
    now = now or cloud.now()
    run = run_for(db, host_id, run_id)
    if run.action != cloud.CONNECT or run.status not in cloud.PENDING:
        raise SecretRefused(409, _("This cloud backup run does not take a code"))
    if run.code_requested_at is None:
        run.code_requested_at = now
        run.status = cloud.WAITING_CODE
    if now - run.code_requested_at > CODE_WINDOW:
        raise SecretRefused(409, _("No two-factor code was entered in time"))
    code = run.mfa_code
    if not code:
        return None
    run.mfa_code = None
    run.code_released_at = now
    run.status = cloud.RUNNING
    return code
