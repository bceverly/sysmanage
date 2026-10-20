# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backup results (ROADMAP Phase 24): record what restate said, then chain.

Two things come back for every job:

* the ``command_result`` for the queued command (did the agent accept it?) --
  for ``backup_configure`` that IS the answer: success acknowledges the
  policy's ``config_version`` for that role;
* for a run or a restore, later, ``backup_result`` -- restate's own status
  word and result JSON, stored as sent -- and along the way
  ``backup_progress``.

A good capture (``ok`` or ``incomplete``) is followed, on the storage host,
by ``seal`` when the target seals, and ``prune`` only after the seal
succeeded (a failed seal holds the prune back: never delete history that is
not yet immutable).  The repository's size is each capture's
``repository_bytes``.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_storage_status as storage_status

logger = logging.getLogger(__name__)

_MESSAGE_LIMIT = 1000


def _parse_time(value: Any) -> Optional[datetime]:
    """restate writes ``YYYY-MM-DDTHH:MM:SSZ``; store naive UTC."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _run_by_command(db: Session, command_id: Any) -> Optional[models.BackupRun]:
    if not command_id:
        return None
    return (
        db.query(models.BackupRun)
        .filter(models.BackupRun.command_id == str(command_id))
        .first()
    )


def _run_by_id(db: Session, run_id: Any) -> Optional[models.BackupRun]:
    try:
        key = uuid.UUID(str(run_id))
    except (TypeError, ValueError):
        return None
    return db.query(models.BackupRun).filter(models.BackupRun.id == key).first()


def _parameters(run: models.BackupRun) -> Dict[str, Any]:
    try:
        value = json.loads(run.parameters) if run.parameters else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _policy(db: Session, run: models.BackupRun) -> Optional[models.BackupPolicy]:
    return (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.id == run.policy_id)
        .first()
    )


# --- command_result -------------------------------------------------------


def _acknowledge(db: Session, run: models.BackupRun) -> None:
    params = _parameters(run)
    policy = _policy(db, run)
    version = _int(params.get("config_version"))
    if policy is None or version is None:
        return
    if params.get("role") == "storage":
        policy.storage_acked_version = max(policy.storage_acked_version or 0, version)
    else:
        policy.host_acked_version = max(policy.host_acked_version or 0, version)


def _storage_filesystem(db: Session, run: models.BackupRun, reply: Any) -> None:
    """A storage host's configure reply says which filesystem it is on."""
    if _parameters(run).get("role") != "storage":
        return
    target = jobs.the_target(db)
    if target is not None and str(target.storage_host_id) == str(run.host_id):
        storage_status.record_storage_fs(target, reply)


def _refused(db: Session, run: models.BackupRun, code: str) -> None:
    """The agent would not run it.  ``busy`` is retried by the scheduler;
    ``not_configured`` means its job files are gone -- forget the
    acknowledgment so the scheduler sends them again."""
    run.status = "busy" if code == "busy" else "failed"
    run.finished_at = jobs.now()
    run.message = code[:_MESSAGE_LIMIT]
    policy = _policy(db, run)
    if code == "not_configured" and policy is not None:
        if str(run.host_id) == str(policy.host_id):
            policy.host_acked_version = 0
        else:
            policy.storage_acked_version = 0
    logger.warning(
        "Backup %s for policy %s refused by host %s: %s",
        run.action,
        run.policy_id,
        run.host_id,
        code,
    )


def record_command_result(db: Session, message_data: Dict[str, Any]) -> bool:
    """The agent's answer to a queued backup command; False when it answers
    none of ours.  The caller commits."""
    run = _run_by_command(db, message_data.get("command_id"))
    if run is None:
        return False
    error = message_data.get("error")
    success = bool(message_data.get("success")) and not error
    if run.status not in jobs.PENDING:
        return True  # backup_result got here first; it is the authority
    if not success:
        _refused(db, run, str(error or "agent_error"))
        return True
    if run.action == jobs.CONFIGURE:
        run.status = "ok"
        run.finished_at = jobs.now()
        _acknowledge(db, run)
        _storage_filesystem(db, run, message_data.get("result"))
    else:
        run.status = jobs.RUNNING
        run.started_at = run.started_at or jobs.now()
    return True


# --- backup_result --------------------------------------------------------


def _store_outcome(run: models.BackupRun, payload: Dict[str, Any]) -> Dict[str, Any]:
    status = payload.get("status")
    run.status = status if status in jobs.FINAL else "failed"
    run.exit_code = _int(payload.get("exit"))
    result = payload.get("result")
    result = result if isinstance(result, dict) else {}
    run.result = json.dumps(result)
    run.started_at = _parse_time(payload.get("started_at")) or run.started_at
    run.finished_at = _parse_time(payload.get("finished_at")) or jobs.now()
    version = payload.get("restate_version")
    run.restate_version = str(version)[:64] if version else None
    if isinstance(result.get("snapshot"), str):
        run.snapshot = result["snapshot"][:255]
    message = result.get("error") or result.get("message")
    if message:
        run.message = str(message)[:_MESSAGE_LIMIT]
    run.progress = None
    return result


def _upsert_snapshot(
    db: Session, policy: models.BackupPolicy, name: str, fields: Dict[str, Any]
) -> models.BackupSnapshot:
    row = (
        db.query(models.BackupSnapshot)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.name == name,
        )
        .first()
    )
    if row is None:
        row = models.BackupSnapshot(
            policy_id=policy.id, host_id=policy.host_id, name=name, signed=False
        )
        db.add(row)
    for key, value in fields.items():
        if value is not None:
            setattr(row, key, value)
    row.seen_at = jobs.now()
    row.gone_at = None
    db.flush()  # a name listed twice must find this row, not insert again
    return row


def _storage_next(
    db: Session, policy: models.BackupPolicy, action: str
) -> Optional[models.BackupRun]:
    """Queue ``action`` on the target's storage host, when it can run it."""
    target = (
        db.query(models.BackupTarget)
        .filter(models.BackupTarget.id == policy.target_id)
        .first()
    )
    storage = jobs.storage_host(db, target)
    ready, reason = jobs.equipped(storage)
    if not ready:
        logger.warning(
            "Backup policy %s: no storage-side %s (storage host %s: %s); "
            "the repository is not being maintained",
            policy.id,
            action,
            getattr(target, "storage_host_id", None),
            reason,
        )
        return None
    if not policy.storage_acked_version:
        logger.warning(
            "Backup policy %s: storage host %s has no job files yet; %s waits "
            "for the scheduler to configure it",
            policy.id,
            storage.id,
            action,
        )
        return None
    if jobs.pending(db, policy.id, action, storage.id):
        return None
    return jobs.queue_run(db, policy, storage.id, action)


def _after_capture(
    db: Session, run: models.BackupRun, policy: models.BackupPolicy, result
) -> None:
    if run.restate_version:
        policy.restate_version = run.restate_version
    if run.status not in jobs.GOOD_CAPTURE:
        return
    if result.get("created_repository") is True:
        # The host's first capture made its repository (restate ``create``).
        logger.info(
            "Backup capture %s for policy %s created repository %s on host %s",
            run.id,
            policy.id,
            result.get("repository"),
            run.host_id,
        )
    if run.snapshot:
        _upsert_snapshot(
            db,
            policy,
            run.snapshot,
            {
                "created_at": _parse_time(result.get("started_at")) or run.finished_at,
                "bytes": _int(result.get("read_bytes")),
                "new_bytes": _int(result.get("new_bytes")),
                "files": _int(result.get("paths")),
            },
        )
    repository = _int(result.get("repository_bytes"))
    if repository is not None:
        policy.repository_bytes = repository
    target = (
        db.query(models.BackupTarget)
        .filter(models.BackupTarget.id == policy.target_id)
        .first()
    )
    sealing = target is not None and (target.seal_mode or "none") != "none"
    _storage_next(db, policy, "seal" if sealing else "prune")


def _after_seal(db: Session, run: models.BackupRun, policy, _result) -> None:
    if run.status == "ok":
        _storage_next(db, policy, "prune")
        return
    logger.error(
        "Backup policy %s: the storage-side seal ended %s (%s); prune held back "
        "so no history is deleted before it is immutable",
        policy.id,
        run.status,
        run.message,
    )


def _mark_gone(db: Session, policy, names: List[str]) -> None:
    if not names:
        return
    stamp = jobs.now()
    rows = (
        db.query(models.BackupSnapshot)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.name.in_(names),
        )
        .all()
    )
    for row in rows:
        row.gone_at = row.gone_at or stamp


def _after_prune(db: Session, run: models.BackupRun, policy, result) -> None:
    if run.restate_version:
        policy.storage_restate_version = run.restate_version
    pruned = [n for n in result.get("pruned") or [] if isinstance(n, str)]
    _mark_gone(db, policy, pruned)


def _named(entries: Any) -> List[Dict[str, Any]]:
    """Snapshot entries as dicts with a ``name``; bare strings are names."""
    out = []
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, str):
            out.append({"name": entry})
        elif isinstance(entry, dict) and isinstance(entry.get("name"), str):
            out.append(entry)
    return out


def _refresh(
    db: Session, policy, entries: List[Dict[str, Any]], sizes: bool = False
) -> None:
    """The repository holds exactly ``entries``: upsert them, retire the rest."""
    present = set()
    for entry in entries:
        present.add(entry["name"])
        fields = {"created_at": _parse_time(entry.get("time") or entry.get("at"))}
        if sizes:
            fields.update(
                bytes=_int(entry.get("bytes")),
                unique_bytes=_int(entry.get("unique_bytes")),
                new_bytes=_int(entry.get("new_bytes")),
            )
        _upsert_snapshot(db, policy, entry["name"][:255], fields)
    stamp = jobs.now()
    for row in (
        db.query(models.BackupSnapshot)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.gone_at.is_(None),
        )
        .all()
    ):
        if row.name not in present:
            row.gone_at = stamp


def _after_snapshots(db: Session, run: models.BackupRun, policy, result) -> None:
    if run.status == "ok":
        _refresh(db, policy, _named(result.get("snapshots")), sizes=False)


def _after_estimate(_db: Session, run: models.BackupRun, policy, result) -> None:
    if run.status == "ok" and _int(result.get("bytes")) is not None:
        policy.estimate_bytes = _int(result.get("bytes"))


def _after_check(_db: Session, run: models.BackupRun, policy, _result) -> None:
    if run.restate_version:
        policy.storage_restate_version = run.restate_version
    if run.status not in ("ok",):
        logger.error(
            "Backup policy %s: repository check ended %s on host %s",
            policy.id,
            run.status,
            run.host_id,
        )


_AFTER = {
    "capture": _after_capture,
    "seal": _after_seal,
    "prune": _after_prune,
    "snapshots": _after_snapshots,
    "estimate": _after_estimate,
    "check": _after_check,
}


def record_result(
    db: Session, host_id: Any, payload: Dict[str, Any]
) -> Optional[models.BackupRun]:
    """Store one ``backup_result`` and queue what follows it.  None when it
    answers no run of this host's (logged).  The caller commits."""
    run = _run_by_id(db, payload.get("run_id"))
    if run is None or str(run.host_id) != str(host_id):
        logger.warning(
            "backup_result from host %s for unknown run %s (action %s) ignored",
            host_id,
            payload.get("run_id"),
            payload.get("action"),
        )
        return None
    if run.status not in jobs.PENDING:
        logger.info("backup_result for finished run %s ignored (repeat)", run.id)
        return run
    result = _store_outcome(run, payload)
    policy = _policy(db, run)
    after = _AFTER.get(run.action)
    if policy is not None and after is not None:
        after(db, run, policy, result)
    if run.status in ("failed", "untrusted"):
        logger.error(
            "Backup %s for policy %s ended %s (exit %s): %s",
            run.action,
            run.policy_id,
            run.status,
            run.exit_code,
            run.message,
        )
    return run


def record_progress(
    db: Session, host_id: Any, payload: Dict[str, Any]
) -> Optional[models.BackupRun]:
    """Keep the latest progress line on its run.  The caller commits."""
    run = _run_by_id(db, payload.get("run_id"))
    if run is None or str(run.host_id) != str(host_id):
        return None
    if run.status not in jobs.PENDING:
        return run
    progress = payload.get("progress")
    source = progress if isinstance(progress, dict) else payload
    keep = {
        key: source.get(key)
        for key in (
            "phase",
            "paths",
            "read_bytes",
            "new_bytes",
            "total_bytes",
            "hook",
            "at",
        )
    }
    keep["action"] = payload.get("action")
    run.progress = json.dumps(keep)
    run.status = jobs.RUNNING
    run.started_at = run.started_at or jobs.now()
    return run
