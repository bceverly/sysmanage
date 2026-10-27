# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Handing a host its policy's decryption keys for ONE job (Pro+, 24.6 S4).

A restore, snapshot listing or what-changed of an encrypted repository needs
the policy's secret key on the host for that run.  The key lives in OpenBAO;
the Pro+ ``backup_engine`` reads it.  It never travels in the job's command:
commands go through the database-backed message queue, and the run row keeps
its parameters, so a key there would sit in the server's database.  The run
only says ``needs_key``; the agent then fetches the keys over HTTPS with its
own host credentials (``POST /api/agent/backup-key``), and this module decides
whether to hand them over:

* the run exists, belongs to the asking host, is a restore / list / status
  that asked for a key, and is still queued or running;
* it was queued within ``RELEASE_WINDOW``, and its keys were not released
  before (``key_released_at``) -- a key is handed out once per run;
* the policy's repository is encrypted, and backup_engine is loaded.

Every release is audited with the run, the host and the key's fingerprint.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.services import backup_jobs as jobs

logger = logging.getLogger(__name__)

RELEASE_WINDOW = timedelta(hours=1)
KEYED_ACTIONS = (jobs.RESTORE, jobs.LIST, jobs.STATUS)


class KeyRefused(Exception):
    """Why a run's keys are not released; ``status`` is the HTTP status."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _parameters(run: models.BackupRun) -> dict:
    try:
        value = json.loads(run.parameters) if run.parameters else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _run_for(db: Session, host_id: str, run_id: Any) -> models.BackupRun:
    try:
        key = uuid.UUID(str(run_id))
    except ValueError:
        key = None
    run = (
        db.query(models.BackupRun).filter(models.BackupRun.id == key).first()
        if key
        else None
    )
    if run is None or str(run.host_id) != str(host_id):
        # The same answer for "no such run" and "not yours": a host learns
        # nothing about another host's runs.
        raise KeyRefused(404, _("No such backup run for this host"))
    return run


def _check_run(run: models.BackupRun, now: datetime) -> None:
    if run.action not in KEYED_ACTIONS or not _parameters(run).get("needs_key"):
        raise KeyRefused(409, _("This backup run does not need a key"))
    if run.status not in jobs.PENDING:
        raise KeyRefused(409, _("This backup run has already ended"))
    if run.key_released_at is not None:
        raise KeyRefused(409, _("This backup run's key was already released"))
    if run.queued_at and now - run.queued_at > RELEASE_WINDOW:
        raise KeyRefused(409, _("This backup run is too old to release its key"))


def release(
    db: Session, host_id: str, run_id: Any, now: Optional[datetime] = None
) -> List[str]:
    """The armored secret keys for this host's own pending run, once."""
    now = now or jobs.now()
    run = _run_for(db, host_id, run_id)
    _check_run(run, now)
    policy = (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.id == run.policy_id)
        .first()
    )
    if policy is None or not jobs.encrypted(policy):
        raise KeyRefused(409, _("This host's backups are not encrypted"))
    engine = module_loader.get_module("backup_engine")
    if engine is None:
        raise KeyRefused(
            402, _("Encrypted backups need the Professional+ backup engine")
        )
    try:
        keys = engine.secret_keys(policy, db=db)
    except Exception as error:  # the engine's own message says why
        logger.error(
            "Backup key for run %s (host %s, policy %s) could not be read: %s",
            run.id,
            host_id,
            policy.id,
            error,
        )
        raise KeyRefused(503, str(error)) from error
    run.key_released_at = now
    logger.info(
        "Backup key %s released to host %s for run %s (%s)",
        policy.encrypt_fingerprint,
        host_id,
        run.id,
        run.action,
    )
    return keys
