# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The off-site copy's AWS credentials and AES-256 keys (ROADMAP 27.3).

Both live in OpenBAO under the tenant's own path; the database keeps only
the paths.  They never travel in a job's command (commands sit in the
database-backed message queue): the storage host's agent asks for them over
HTTPS with its own host credentials (``POST /api/agent/offsite-cloud-secret``)
for ONE run, and ``release`` decides, as ``cloud_backup_secrets`` does for
the iCloud password:

* the run exists, belongs to the asking host and is still queued or running;
* it was SENT within ``RELEASE_WINDOW`` and nothing was released for it
  before -- once per run.

An upload or a check gets the copy's current key; a restore gets the key its
streams were made with (a rotated key is kept for as long as anything in the
bucket needs it).  Every release is audited by the caller.

The key id is the agent's (``offsite_cloud/crypto.key_id``): HMAC-SHA256 of
a fixed label under the key, so it names a key without revealing it.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.services import queue_clock

logger = logging.getLogger(__name__)

RELEASE_WINDOW = timedelta(hours=1)
SECRET_TYPE = "backup_offsite"  # nosec B105 - an OpenBAO category name, not a secret
KEY_BYTES = 32
_KEY_ID_LABEL = b"sysmanage-offsite-key-id"
PENDING = ("queued", "running")


class SecretRefused(Exception):
    """Why a run gets no secrets; ``status`` is the HTTP status."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def key_id(key: bytes) -> str:
    return hmac.new(key, _KEY_ID_LABEL, hashlib.sha256).hexdigest()[:16]


def _tenant_scope() -> str:
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


def _store(name: str, text: str, vault=None) -> str:
    stored = _vault(vault).store_secret(
        secret_name=name,
        secret_data=text,
        secret_type=SECRET_TYPE,
        secret_subtype=_tenant_scope(),
    )
    reference = stored.get("vault_path") if isinstance(stored, dict) else None
    if not reference:
        raise SecretRefused(503, _("OpenBAO did not say where it stored the secret"))
    return reference


def _read(reference: Optional[str], vault=None) -> str:
    if not reference:
        raise SecretRefused(409, _("This off-site copy has no secret in OpenBAO"))
    stored = _vault(vault).retrieve_secret(reference)
    content = stored.get("content") if isinstance(stored, dict) else None
    if not isinstance(content, str) or not content:
        raise SecretRefused(503, _("OpenBAO does not hold this off-site copy's secret"))
    return content


def delete(reference: Optional[str], vault=None) -> None:
    """Remove a replaced secret; a failure is logged, never raised."""
    if not reference:
        return
    try:
        _vault(vault).delete_secret(reference)
    except Exception as error:  # pylint: disable=broad-exception-caught
        logger.warning("Could not delete an off-site copy's OpenBAO entry: %s", error)


def store_credentials(
    copy_id: Any, access_key: str, secret_key: str, session_token: Optional[str] = None,
    vault=None,
) -> str:  # fmt: skip
    data = {"access_key": access_key, "secret_key": secret_key}
    if session_token:
        data["session_token"] = session_token
    return _store(f"backup-offsite/{copy_id}/credentials", json.dumps(data), vault)


def read_credentials(reference: Optional[str], vault=None) -> Dict[str, str]:
    try:
        data = json.loads(_read(reference, vault))
    except ValueError as error:
        raise SecretRefused(
            503, _("The off-site credentials in OpenBAO are damaged")
        ) from error
    if (
        not isinstance(data, dict)
        or not data.get("access_key")
        or not data.get("secret_key")
    ):
        raise SecretRefused(503, _("The off-site credentials in OpenBAO are damaged"))
    return data


def new_key(copy_id: Any, vault=None) -> Tuple[str, str]:
    """A fresh AES-256 key, put in OpenBAO: ``(key id, OpenBAO path)``.  The
    key itself never reaches the database."""
    key = os.urandom(KEY_BYTES)
    kid = key_id(key)
    text = base64.b64encode(key).decode("ascii")
    reference = _store(f"backup-offsite/{copy_id}/key-{kid}", text, vault)
    return kid, reference


def read_key(
    reference: Optional[str], expected_id: Optional[str] = None, vault=None
) -> str:
    """The key, base64, checked against its id."""
    text = _read(reference, vault)
    try:
        key = base64.b64decode(text, validate=True)
    except ValueError as error:
        raise SecretRefused(503, _("The off-site key in OpenBAO is damaged")) from error
    if len(key) != KEY_BYTES or (expected_id and key_id(key) != expected_id):
        raise SecretRefused(503, _("The off-site key in OpenBAO is damaged"))
    return text


def current_key(db: Session, copy_id: Any) -> Optional[models.BackupOffsiteKey]:
    return (
        db.query(models.BackupOffsiteKey)
        .filter(models.BackupOffsiteKey.copy_id == copy_id,
                models.BackupOffsiteKey.retired_at.is_(None))  # fmt: skip
        .order_by(models.BackupOffsiteKey.created_at.desc()).first()
    )


def key_row(db: Session, copy_id: Any, kid: str) -> Optional[models.BackupOffsiteKey]:
    return (
        db.query(models.BackupOffsiteKey)
        .filter(models.BackupOffsiteKey.copy_id == copy_id,
                models.BackupOffsiteKey.key_id == kid)  # fmt: skip
        .first()
    )


# --- the release to the storage host ---------------------------------------------


def run_for(db: Session, host_id: str, run_id: Any) -> models.BackupOffsiteRun:
    try:
        key = uuid.UUID(str(run_id))
    except ValueError:
        key = None
    run = db.get(models.BackupOffsiteRun, key) if key else None
    if run is None or str(run.host_id) != str(host_id):
        raise SecretRefused(404, _("No such off-site run for this host"))
    return run


def _check_live(db: Session, run: models.BackupOffsiteRun, now: datetime) -> None:
    if run.status not in PENDING:
        raise SecretRefused(409, _("This off-site run has already ended"))
    if run.secrets_released_at is not None:
        raise SecretRefused(409, _("This off-site run's secrets were already released"))
    started = queue_clock.clock_start(
        queue_clock.delivery(db, run.command_id), run.queued_at
    )
    if started and now - started > RELEASE_WINDOW:
        raise SecretRefused(409, _("This off-site run is too old"))


def release(
    db: Session, host_id: str, run_id: Any, now: Optional[datetime] = None, vault=None
) -> Dict[str, str]:
    """``{"access_key", "secret_key", "key"[, "session_token"]}`` for this
    host's own pending run, once."""
    now = now or datetime.utcnow()
    run = run_for(db, host_id, run_id)
    _check_live(db, run, now)
    copy = db.get(models.BackupOffsiteCopy, run.copy_id)
    if copy is None:
        raise SecretRefused(409, _("This off-site copy was removed"))
    row = key_row(db, copy.id, run.key_id) if run.key_id else current_key(db, copy.id)
    if row is None:
        raise SecretRefused(409, _("The key this run needs is not held"))
    try:
        secrets = dict(read_credentials(copy.credentials_ref, vault))
        secrets["key"] = read_key(row.key_ref, row.key_id, vault)
    except SecretRefused:
        raise
    except Exception as error:  # the vault's own message says why
        logger.exception("Off-site run %s: its OpenBAO entries are unreadable", run.id)
        raise SecretRefused(503, str(error)) from error
    run.secrets_released_at = now
    # Names the host and run only; never what was released.
    # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
    logger.info("Off-site secrets released to host %s for run %s", host_id, run.id)
    return secrets
