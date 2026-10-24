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
import re
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_storage_status as storage_status
from backend.services import backup_tick

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


def _store_nfs_path(policy: Optional[models.BackupPolicy], path: Any) -> None:
    """Where the host mounts its repository, as the storage host reports it.
    A new or changed path re-sends the HOST's job files (bumping the version
    re-sends the storage side's too -- harmless)."""
    if policy is None or path is not None and not isinstance(path, str):
        return
    path = path[:1024] if path and path.startswith("/") else None
    if path != policy.storage_nfs_path:
        policy.storage_nfs_path = path
        policy.config_version += 1


_HOOK_NAME = re.compile(r"^[a-z0-9_-]{1,32}$")


def _store_hooks(policy: Optional[models.BackupPolicy], hooks: Any) -> None:
    """The quiesce hooks the host's restate finds present (older agents and
    restates send none: the dialog then takes names as typed)."""
    if policy is not None and isinstance(hooks, list):
        names = sorted({h for h in hooks if isinstance(h, str) and _HOOK_NAME.match(h)})
        policy.available_hooks = json.dumps(names[:64])


_ABILITIES = ("list", "status", "cache")


def _store_abilities(policy: Optional[models.BackupPolicy], found: Any) -> None:
    """Browse / what changed / write cache: what the host's restate offers."""
    if policy is not None and isinstance(found, list):
        policy.host_abilities = json.dumps(sorted(set(found) & set(_ABILITIES)))


def _store_protects(policy: Optional[models.BackupPolicy], installed: Any) -> None:
    """Did the storage host install the ``protect`` job (its restate has it)?"""
    if policy is not None and isinstance(installed, list):
        policy.storage_protects = "protect" in installed


def _reprotect(db: Session, run: models.BackupRun) -> None:
    """New job files on the storage host -- a restate upgrade among the
    reasons -- may change HOW protect protects (2.1.0.2 moved ZFS on FreeBSD
    from the sticky bit to an NFSv4 ACL), and a capture cannot run against
    the old form.  Protect once now, outside the capture chain."""
    policy = _policy(db, run)
    if policy is not None and policy.storage_protects:
        _storage_next(db, policy, "protect", record={"chain": False})


def _reprepare(db: Session, run: models.BackupRun) -> None:
    """The storage side now knows a new address for this host: a repository
    that was prepared for the old one is prepared again, so its export
    follows the host (never one that was not prepared -- that is the
    administrator's to start)."""
    policy = _policy(db, run)
    address = (_parameters(run).get("target") or {}).get("client_address")
    if policy is None or not address or jobs.pending(db, policy.id, jobs.PREPARE):
        return
    last = (
        db.query(models.BackupRun)
        .filter(
            models.BackupRun.policy_id == policy.id,
            models.BackupRun.action == jobs.PREPARE,
            models.BackupRun.status == "ok",
        )
        .order_by(models.BackupRun.finished_at.desc())
        .first()
    )
    if last is None or _parameters(last).get("client_address") == address:
        return
    logger.info(
        "Backup policy %s: re-preparing storage for the host's new address %s",
        policy.id,
        address,
    )
    jobs.queue_run(db, policy, run.host_id, jobs.PREPARE)


def _refused(db: Session, run: models.BackupRun, code: str) -> None:
    """The agent would not run it.  ``busy`` is retried by the scheduler;
    ``not_configured`` means its job files are gone -- forget the
    acknowledgment so the scheduler sends them again."""
    run.status = "busy" if code == "busy" else "failed"
    run.finished_at = jobs.now()
    run.message = code[:_MESSAGE_LIMIT]
    policy = _policy(db, run)
    if (
        code == "not_configured"
        and policy is not None
        and run.action not in jobs.BROWSE_ACTIONS
    ):
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
        reply = message_data.get("result")
        if _parameters(run).get("role") == "host" and isinstance(reply, dict):
            _store_hooks(_policy(db, run), reply.get("hooks"))
            _store_abilities(_policy(db, run), reply.get("abilities"))
        if _parameters(run).get("role") == "storage":
            if isinstance(reply, dict):
                _store_audit(_policy(db, run), reply.get("storage_audit"))
                _store_nfs_path(_policy(db, run), reply.get("nfs_path"))
                _store_protects(_policy(db, run), reply.get("installed"))
            _reprotect(db, run)
            _reprepare(db, run)
    else:
        run.status = jobs.RUNNING
        run.started_at = run.started_at or jobs.now()
    return True


# --- backup_result --------------------------------------------------------


def _first_error(result: Dict[str, Any]) -> Optional[str]:
    """restate 2.0.0.4+ lists why a run failed in ``errors``; the first is
    the reason (the rest usually follow from it)."""
    errors = result.get("errors")
    if isinstance(errors, list):
        first = next((e for e in errors if isinstance(e, str) and e.strip()), None)
        if first:
            return first
    return None


def snapshot_name(value: str) -> str:
    """The snapshot's own name.  A capture's result names it as
    ``<repository>::<name>``; prune, du and the snapshot listing use the bare
    name, which is also what a restore asks for.  Store the bare name only
    (2026-10-21: the full form made every restore "not a valid snapshot
    name" and kept du's sizes from ever matching)."""
    return value.rsplit("::", 1)[-1]


AUDIT_LEVELS = ("error", "warning", "ok")
MAX_AUDIT_FINDINGS = 64


def _store_audit(policy: Optional[models.BackupPolicy], audit: Any) -> None:
    """Keep the storage host's latest audit of this repository: findings
    ``{code, level, params}``, anything else dropped."""
    if policy is None or not isinstance(audit, list):
        return
    clean = []
    for finding in audit[:MAX_AUDIT_FINDINGS]:
        if (
            isinstance(finding, dict)
            and isinstance(finding.get("code"), str)
            and finding.get("level") in AUDIT_LEVELS
        ):
            params = finding.get("params")
            clean.append(
                {
                    "code": finding["code"][:64],
                    "level": finding["level"],
                    "params": params if isinstance(params, dict) else {},
                }
            )
    policy.storage_audit = json.dumps(clean)
    policy.storage_audit_at = jobs.now()


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
        run.snapshot = snapshot_name(result["snapshot"])[:255]
    message = _first_error(result) or result.get("error") or result.get("message")
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
    db: Session,
    policy: models.BackupPolicy,
    action: str,
    record: Optional[Dict[str, Any]] = None,
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
    return jobs.queue_run(db, policy, storage.id, action, record=record)


def _note_version(
    policy: models.BackupPolicy, field: str, version: Optional[str]
) -> None:
    """Record which restate ran; when it CHANGED, re-send the job files.

    The agent writes job files for the restate it found at configure time --
    a key such as ``create`` only when that restate lists it.  A restate
    upgraded in place keeps those old job files until something re-sends
    them (lab, 2026-10-20: 2.0.0.1 -> 2.0.0.4 never got ``create``), so a
    new version bumps ``config_version`` and the scheduler re-configures.
    """
    if not version:
        return
    known = getattr(policy, field)
    if known and known != version:
        policy.config_version += 1
        logger.info(
            "Backup policy %s: restate changed %s -> %s; re-sending job files",
            policy.id,
            known,
            version,
        )
    setattr(policy, field, version)


def _after_capture(
    db: Session, run: models.BackupRun, policy: models.BackupPolicy, result
) -> None:
    _note_version(policy, "restate_version", run.restate_version)
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
    if policy.storage_protects:
        _storage_next(db, policy, "protect")
        return
    _seal_or_prune(db, policy)


def _seal_or_prune(db: Session, policy: models.BackupPolicy) -> None:
    target = (
        db.query(models.BackupTarget)
        .filter(models.BackupTarget.id == policy.target_id)
        .first()
    )
    sealing = target is not None and (target.seal_mode or "none") != "none"
    _storage_next(db, policy, "seal" if sealing else "prune")


def _after_protect(db: Session, run: models.BackupRun, policy, _result) -> None:
    """Protected (or not): seal and prune follow either way -- an immutable
    snapshot is worth taking even of a repository that is not yet
    append-only -- but a failure is loud: until it is fixed the host can
    still delete its own backups."""
    if run.status != "ok":
        logger.error(
            "Backup policy %s: the storage-side protect ended %s (%s); the "
            "host can still change or remove its finished backups",
            policy.id,
            run.status,
            run.message,
        )
    if _parameters(run).get("chain") is False:
        return  # a re-protect after new job files: no capture to follow up
    _seal_or_prune(db, policy)


def _free_slot(db: Session) -> None:
    """A capture ended: a waiting "Back up now" can take its slot."""
    backup_tick.start_requested(db)


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
    _note_version(policy, "storage_restate_version", run.restate_version)
    pruned = [n for n in result.get("pruned") or [] if isinstance(n, str)]
    _mark_gone(db, policy, pruned)
    if run.status == "ok":
        _storage_next(db, policy, "du")  # what is left, and what each holds


def _after_repack(db: Session, run: models.BackupRun, policy, result) -> None:
    """Packs rewritten (or stopped part-way: the next repack resumes): the
    repository's size changed, so size it again."""
    _note_version(policy, "storage_restate_version", run.restate_version)
    if run.status in ("ok", "incomplete"):
        logger.info(
            "Backup repack for policy %s: %s packs rewritten, %s removed, %s bytes freed",
            policy.id,
            result.get("packs_rewritten"),
            result.get("packs_removed"),
            result.get("bytes_freed"),
        )
        _storage_next(db, policy, "du")


def _after_du(db: Session, run: models.BackupRun, policy, result) -> None:
    """The repository's size on the storage host and, per snapshot, its
    size, what it added, and what dropping it alone would free."""
    if run.status != "ok":
        return
    usage = result.get("du") if isinstance(result.get("du"), dict) else {}
    total = _int(usage.get("bytes"))
    if total is not None:
        policy.repository_bytes = total
    for entry in usage.get("snapshots") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        snapshot = (
            db.query(models.BackupSnapshot)
            .filter(
                models.BackupSnapshot.policy_id == policy.id,
                models.BackupSnapshot.name == entry["name"],
                models.BackupSnapshot.gone_at.is_(None),
            )
            .first()
        )
        if snapshot is None:
            continue
        for field in ("bytes", "new_bytes", "unique_bytes"):
            value = _int(entry.get(field))
            if value is not None:
                setattr(snapshot, field, value)


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
    _note_version(policy, "storage_restate_version", run.restate_version)
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
    "du": _after_du,
    "repack": _after_repack,
    "protect": _after_protect,
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
    if "storage_audit" in payload and str(run.host_id) != str(
        getattr(policy, "host_id", None)
    ):
        _store_audit(policy, payload.get("storage_audit"))
    after = _AFTER.get(run.action)
    if policy is not None and after is not None:
        after(db, run, policy, result)
    if run.action == "capture":
        _free_slot(db)
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
