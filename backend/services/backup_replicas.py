# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Off-site copies (ROADMAP 27.3; setting one up is Enterprise).

A target may name another target as its off-site copy.  Each host's
repository on it is a ``backup_replica`` row, and two storage hosts keep it:

* **The source storage host copies.**  After each host's nightly chain
  (capture, protect, seal, prune, du) it copies every snapshot the copy lacks,
  oldest first, with ``restate copy`` into the off-site repository through
  restate-proxy, using a token it made itself (only the SHA-256 reaches the
  server).  The grant is ``append``: the source site can add to the copy but
  never delete from it -- the immutable copy.  An encrypted repository's
  packs go as they are; nothing is decrypted.
* **The off-site storage host keeps the copy.**  It is told about the copy as
  one more repository it stores, under the row's id: it prepares it (a plain
  ``restate init``, owned by the proxy's account), protects, seals, prunes
  (the SOURCE policy's retention and legal holds, Bryan 2026-11-20) and sizes
  it.  A snapshot the off-site prune dropped is never copied again, or the
  two prunes would fight.

Off-site runs are stored as ``off_<action>`` so the source's own storage
scheduling, which reads its latest prune and check, never sees them; the
agent is sent the plain action.  After a license lapse copying goes on --
only setting a copy up, or changing it, needs the license.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_proxy as proxy
from backend.services import backup_proxy_cert
from backend.websocket.messages import CommandType

logger = logging.getLogger(__name__)

CLIENT_PREFIX = "replica-"
# The backed-up host's own client on the copy's proxy: read only (27.3).
READ_PREFIX = "offsite-"
# What a backed-up host's agent reports once it reads its off-site copy.
READ_ABILITY = "offsite_read"
COPY = "copy"
# What the source storage agent reports once it can copy into a repository
# behind restate-proxy (and takes ``replicas`` in its configure).
ABILITY = "replica_copy"
# Stored run actions are at most 16 characters (backup_run.action): the
# lab found "replica_configure" refused by PostgreSQL, 2026-11-20.
PREFIX = "off_"
# The off-site storage host's chain once copies are in.
_CHAIN = ("protect", "seal", "prune", "du")
_ACTIONS = ("prepare",) + _CHAIN + ("check",)
# Snapshot names the off-site prune dropped, remembered so they are never
# copied again (the newest this many).
PRUNED_KEEP = 500
# A copy that has not moved for this long is started again by the tick.
RETRY_HOURS = 6


def client(replica: models.BackupReplica) -> str:
    return CLIENT_PREFIX + str(replica.id)


def read_client(replica: models.BackupReplica) -> str:
    return READ_PREFIX + str(replica.id)


def run_action(action: str) -> str:
    """The stored name of an off-site run."""
    return PREFIX + action


def replica_target(
    db: Session, target: Optional[models.BackupTarget]
) -> Optional[models.BackupTarget]:
    """The target ``target`` copies off-site to, or None."""
    if target is None or not getattr(target, "replica_target_id", None):
        return None
    return db.get(models.BackupTarget, target.replica_target_id)


def _names(text: Optional[str]) -> List[str]:
    try:
        value = json.loads(text or "[]")
    except ValueError:
        return []
    return [n for n in value if isinstance(n, str)] if isinstance(value, list) else []


def rows(db: Session, policy: models.BackupPolicy) -> List[models.BackupReplica]:
    return (
        db.query(models.BackupReplica)
        .filter(models.BackupReplica.policy_id == policy.id)
        .all()
    )


# A move with its backups (backup_moves) copies the way an off-site copy
# does, while it is copying or being checked.
MOVING = ("copying", "verifying")


def is_move(row: Any) -> bool:
    return isinstance(row, models.BackupMove)


def moving(db: Session, policy: models.BackupPolicy) -> List[models.BackupMove]:
    return (
        db.query(models.BackupMove)
        .filter(
            models.BackupMove.policy_id == policy.id,
            models.BackupMove.status.in_(MOVING),
        )
        .all()
    )


def copy_rows(db: Session, policy: models.BackupPolicy) -> List[Any]:
    """Every repository the policy's storage host copies into: its off-site
    copies and the target it is moving to."""
    return [*rows(db, policy), *moving(db, policy)]


def ensure(
    db: Session,
    policy: models.BackupPolicy,
    target: models.BackupTarget,
    host: models.Host,
) -> Optional[models.BackupReplica]:
    """The policy's off-site row for its target's copy (made when missing);
    rows for any other target are dropped -- the copy itself stays where it
    is on that storage host, as a stopped copy."""
    wanted = replica_target(db, target)
    found = None
    for row in rows(db, policy):
        if wanted is not None and str(row.target_id) == str(wanted.id):
            found = row
        else:
            db.delete(row)
    if wanted is None or found is not None:
        return found
    stamp = jobs.now()
    found = models.BackupReplica(
        policy_id=policy.id,
        target_id=wanted.id,
        repo_dir=jobs.policy_repo_dir(policy, host),
        config_version=1,
        created_at=stamp,
        updated_at=stamp,
    )
    db.add(found)
    db.flush()
    return found


def target_clients(db: Session, target: models.BackupTarget) -> List[str]:
    """The proxy clients copies into ``target`` use, so the target's storage
    host keeps their grants when it is told about its own hosts."""
    found = (
        db.query(models.BackupReplica.id)
        .filter(models.BackupReplica.target_id == target.id)
        .all()
    )
    moves = (
        db.query(models.BackupMove.id)
        .filter(
            models.BackupMove.target_id == target.id,
            models.BackupMove.status.in_(MOVING),
        )
        .all()
    )
    return sorted(
        [
            prefix + str(row_id)
            for (row_id,) in found
            for prefix in (CLIENT_PREFIX, READ_PREFIX)
        ]
        + [CLIENT_PREFIX + str(row_id) for (row_id,) in moves]
    )


# --- the source storage host --------------------------------------------


def source_block(db: Session, policy: models.BackupPolicy) -> Dict[str, Any]:
    """``{"replicas": [...]}`` for the source storage side's configure: where
    each copy goes and how to trust its proxy.  Only to a storage agent that
    can copy (an older one takes no such key)."""
    if ABILITY not in jobs.storage_abilities(policy):
        return {}
    out = []
    for row in copy_rows(db, policy):
        holder = db.get(models.BackupTarget, row.target_id)
        if not proxy.uses_proxy(holder):
            continue
        entry = {"id": str(row.id), "url": f"{proxy.base_url(holder)}/v1/{client(row)}"}
        trust = proxy.trust(holder)
        if trust.get("ca"):
            entry["ca"] = trust["ca"]
        if trust.get("pin_sha256"):
            entry["pin_sha256"] = trust["pin_sha256"]
        out.append(entry)
    return {"replicas": out}


def _entry(holder: models.BackupTarget, client_name: str) -> Dict[str, Any]:
    entry = {"url": f"{proxy.base_url(holder)}/v1/{client_name}"}
    trust = proxy.trust(holder)
    for key in ("ca", "pin_sha256"):
        if trust.get(key):
            entry[key] = trust[key]
    return entry


def host_block(db: Session, policy: models.BackupPolicy) -> Dict[str, Any]:
    """``{"offsite": [...]}`` for the backed-up host's configure: where its
    off-site copies are, so it can restore from one while its own site's
    storage is down.  Only to an agent that reads them (an older one takes
    no such key)."""
    if READ_ABILITY not in jobs.abilities(policy):
        return {}
    out = []
    for row in rows(db, policy):
        holder = db.get(models.BackupTarget, row.target_id)
        if proxy.uses_proxy(holder):
            out.append({"id": str(row.id), **_entry(holder, read_client(row))})
    return {"offsite": out}


def store_read_tokens(
    db: Session, policy: Optional[models.BackupPolicy], reply: Any
) -> bool:
    """The backed-up host's read tokens (hashes) for its off-site copies;
    True when an off-site storage host must be told."""
    tokens = reply.get("offsite_tokens") if isinstance(reply, dict) else None
    if policy is None or not isinstance(tokens, dict):
        return False
    changed = False
    for row in rows(db, policy):
        digest = tokens.get(str(row.id))
        if not proxy.is_sha256(digest) or digest == row.read_token_sha256:
            continue
        row.read_token_sha256_old = row.read_token_sha256
        row.read_token_sha256 = digest
        row.config_version += 1
        row.updated_at = jobs.now()
        changed = True
    return changed


def store_tokens(
    db: Session, policy: Optional[models.BackupPolicy], reply: Any
) -> bool:
    """The source storage host's copy tokens (their hashes): a new one goes
    to the off-site grant, the one before it kept until that is confirmed.
    True when an off-site storage host must be told."""
    tokens = reply.get("copy_tokens") if isinstance(reply, dict) else None
    if policy is None or not isinstance(tokens, dict):
        return False
    changed = False
    for row in copy_rows(db, policy):
        digest = tokens.get(str(row.id))
        if not proxy.is_sha256(digest) or digest == row.token_sha256:
            continue
        row.token_sha256_old = row.token_sha256
        row.token_sha256 = digest
        row.config_version += 1
        row.updated_at = jobs.now()
        changed = True
    return changed


# --- the off-site storage host ------------------------------------------


def _holds_ok(row: models.BackupReplica, keep: Dict[str, Any]) -> bool:
    """A prune that names held snapshots goes only where restate keeps them."""
    return not keep.get("keep_snapshot") or "keep_snapshot" in _names(
        getattr(row, "abilities", None)
    )


def configuration(
    db: Session,
    row: models.BackupReplica,
    policy: models.BackupPolicy,
    holder: models.BackupTarget,
) -> Dict[str, Any]:
    """The off-site storage host's jobs for one copy, as a repository of its
    own (``policy_id`` is the row's id): no export, no key -- the copy
    arrives through the proxy encrypted or not, as it was made."""
    source = jobs.storage_host(db, db.get(models.BackupTarget, policy.target_id))
    keep = jobs.prune_keep(policy)
    work: Dict[str, Any] = {"check": {"read_all": False}, "du": {}, "protect": {}}
    if not is_move(row):
        # A move's copy is the host's own repository-to-be: nothing is pruned
        # or sealed there until the switch, when its own jobs take over.
        work["seal"] = jobs.seal_job(holder)
        if _holds_ok(row, keep):
            work["prune"] = keep
    hashes = [h for h in (row.token_sha256, row.token_sha256_old) if h]
    grants = []
    if hashes:
        grants.append(
            {"client": client(row), "token_sha256": hashes, "operations": ["append"]}
        )
    readers = [
        h
        for h in (
            getattr(row, "read_token_sha256", None),
            getattr(row, "read_token_sha256_old", None),
        )
        if h
    ]
    if readers:
        # The backed-up host restores from its own copy: read, never more.
        grants.append(
            {
                "client": read_client(row),
                "token_sha256": readers,
                "operations": ["read"],
            }
        )
    block: Dict[str, Any] = {
        "target_id": str(holder.id),
        "enabled": True,
        "grants": grants,
        "clients": proxy.target_clients(db, holder),
        "export": False,
    }

    cert = backup_proxy_cert.storage_block(holder)
    if cert is not None:
        block["cert"] = cert
    return {
        "policy_id": str(row.id),
        "role": "storage",
        "target": {
            "mount_point": holder.storage_path,
            "repo_dir": row.repo_dir,
            "client_address": jobs.host_address(source) if source else None,
            "service_account": holder.service_account or jobs.DEFAULT_SERVICE_ACCOUNT,
            "proxy": block,
        },
        "jobs": work,
    }


def _pending(db: Session, row: models.BackupReplica, action: str, host_id) -> bool:
    return jobs.pending(db, row.policy_id, action, host_id)


def _queue(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session,
    row: models.BackupReplica,
    host_id: Any,
    action: str,
    command: CommandType,
    parameters: Dict[str, Any],
    record: Optional[Dict[str, Any]] = None,
) -> models.BackupRun:
    policy = db.get(models.BackupPolicy, row.policy_id)
    return jobs.queue_command(
        db, policy, host_id, action, command, parameters,
        record={"replica_id": str(row.id), **(record or {})},
    )  # fmt: skip


def queue_configure(
    db: Session, row: models.BackupReplica
) -> Optional[models.BackupRun]:
    holder = db.get(models.BackupTarget, row.target_id)
    policy = db.get(models.BackupPolicy, row.policy_id)
    if holder is None or policy is None or not holder.storage_host_id:
        return None
    action = run_action(jobs.CONFIGURE)
    if _pending(db, row, action, holder.storage_host_id):
        return None
    return _queue(
        db, row, holder.storage_host_id, action, CommandType.BACKUP_CONFIGURE,
        configuration(db, row, policy, holder),
        record={"config_version": row.config_version},
    )  # fmt: skip


def queue_offsite(
    db: Session, row: models.BackupReplica, action: str
) -> Optional[models.BackupRun]:
    """One off-site storage action on the copy (prepare, protect, seal,
    prune, du, check)."""
    holder = db.get(models.BackupTarget, row.target_id)
    if holder is None or not holder.storage_host_id or action not in _ACTIONS:
        return None
    stored = run_action(action)
    if _pending(db, row, stored, holder.storage_host_id):
        return None
    return _queue(
        db, row, holder.storage_host_id, stored, CommandType.BACKUP_RUN,
        {"policy_id": str(row.id), "action": action},
    )  # fmt: skip


def queue_copy(
    db: Session, row: models.BackupReplica, snapshot: str
) -> Optional[models.BackupRun]:
    """Copy one snapshot from the source storage host into the copy."""
    policy = db.get(models.BackupPolicy, row.policy_id)
    target = db.get(models.BackupTarget, policy.target_id) if policy else None
    if target is None or not target.storage_host_id:
        return None
    if _pending(db, row, COPY, target.storage_host_id):
        return None
    return _queue(
        db, row, target.storage_host_id, COPY, CommandType.BACKUP_RUN,
        {"policy_id": str(policy.id), "action": COPY,
         "replica_id": str(row.id), "snapshot": snapshot},
        record={"snapshot": snapshot},
    )  # fmt: skip


# --- what to copy, and what follows -------------------------------------


def needed(db: Session, row: models.BackupReplica) -> List[str]:
    """The snapshots to copy, oldest first: each the source still holds that
    the copy lacks, except one the off-site prune dropped."""
    live = (
        db.query(models.BackupSnapshot.name)
        .filter(
            models.BackupSnapshot.policy_id == row.policy_id,
            models.BackupSnapshot.gone_at.is_(None),
        )
        .all()
    )
    skip = set(_names(row.snapshots)) | set(_names(row.pruned))
    return sorted({name for (name,) in live if name and name not in skip})


def ready(row: models.BackupReplica) -> bool:
    """The copy can take snapshots: its grant names the source's token and
    the off-site repository is made."""
    return (
        bool(row.token_sha256)
        and bool(row.prepared_at)
        and bool(row.acked_version and row.acked_version >= row.config_version)
    )


def _busy(db: Session, row: models.BackupReplica) -> bool:
    db.flush()  # the run being answered is no longer pending
    found = (
        db.query(models.BackupRun.id)
        .filter(
            models.BackupRun.policy_id == row.policy_id,
            models.BackupRun.action.in_(
                [COPY] + [run_action(a) for a in _ACTIONS + (jobs.CONFIGURE,)]
            ),
            models.BackupRun.status.in_(jobs.PENDING),
        )
        .first()
    )
    return found is not None


def advance(db: Session, row: models.BackupReplica, copied: bool = False) -> None:
    """The next step for one copy: the oldest snapshot it lacks, else -- when
    this round copied something -- the off-site chain."""
    if not ready(row) or _busy(db, row):
        return
    if is_move(row) and row.status != MOVING[0]:
        return
    todo = needed(db, row)
    if todo:
        queue_copy(db, row, todo[0])
    elif copied and not is_move(row):  # a move is checked next (backup_moves)
        queue_offsite(db, row, _CHAIN[0])


def after_source_chain(db: Session, policy: models.BackupPolicy) -> None:
    """The source repository's nightly chain ended (its du): copy off-site."""
    for row in rows(db, policy):
        advance(db, row)


def _row(db: Session, run: models.BackupRun) -> Optional[models.BackupReplica]:
    try:
        params = json.loads(run.parameters or "{}")
    except ValueError:
        return None
    replica_id = params.get("replica_id") if isinstance(params, dict) else None
    if not replica_id:
        return None
    key = jobs.as_uuid(replica_id)
    return (
        db.query(models.BackupReplica).filter(models.BackupReplica.id == key).first()
        or db.query(models.BackupMove).filter(models.BackupMove.id == key).first()
    )


def row_of(db: Session, run: models.BackupRun) -> Any:
    """The off-site copy or the move a copying run is for, or None."""
    return _row(db, run)


def names(text: Optional[str]) -> List[str]:
    return _names(text)


def is_offsite_audit(db: Session, replica_id: Any, host_id: Any) -> bool:
    """A storage audit the off-site storage host sent for a copy it keeps
    (it audits every repository it stores, under the id it was given)."""
    key = jobs.as_uuid(replica_id)
    row = db.get(models.BackupReplica, key) or db.get(models.BackupMove, key)
    holder = db.get(models.BackupTarget, row.target_id) if row else None
    return holder is not None and str(holder.storage_host_id) == str(host_id)


def is_replica_run(run: models.BackupRun) -> bool:
    return run.action == COPY or (run.action or "").startswith(PREFIX)


def configured(db: Session, run: models.BackupRun, reply: Any) -> None:
    """The off-site storage host took the copy's job files."""
    row = _row(db, run)
    run.status = "ok"
    run.finished_at = jobs.now()
    if row is None:
        return
    try:
        version = int(json.loads(run.parameters or "{}").get("config_version"))
    except (TypeError, ValueError):
        version = None
    if version is not None:
        row.acked_version = max(row.acked_version or 0, version)
    if isinstance(reply, dict) and isinstance(reply.get("abilities"), list):
        row.abilities = json.dumps(sorted(a for a in reply["abilities"]
                                          if isinstance(a, str)))  # fmt: skip

    holder = db.get(models.BackupTarget, row.target_id)
    if holder is not None and backup_proxy_cert.store_csr_for(db, holder, reply):
        row.config_version += 1
    if row.acked_version >= row.config_version:
        row.token_sha256_old = None  # the grant holds the new ones now
        if not is_move(row):
            row.read_token_sha256_old = None
    if not row.prepared_at:
        queue_offsite(db, row, "prepare")
    row.updated_at = jobs.now()


def refused(db: Session, run: models.BackupRun, code: str) -> None:
    """An off-site run the agent would not start: forget the acknowledgment
    when its job files are gone, so the tick sends them again."""
    row = _row(db, run)
    run.status = "busy" if code == "busy" else "failed"
    run.finished_at = jobs.now()
    run.message = code[:1000]
    if row is None:
        return
    if code == "not_configured":
        if run.action == COPY:
            policy = db.get(models.BackupPolicy, row.policy_id)
            if policy is not None:
                policy.config_version += 1  # the source must learn the copy
        else:
            row.acked_version = 0
    if run.action == COPY:
        row.last_copy_at = jobs.now()
        row.last_copy_status = run.status
        row.last_copy_error = run.message
    logger.warning("Off-site %s for copy %s refused by host %s: %s",
                   run.action, getattr(row, "id", None), run.host_id, code)  # fmt: skip


def record_copy(row: Any, run: models.BackupRun, result: Dict[str, Any]) -> bool:
    """Note one copy run's end on its row; True when it copied."""
    row.last_copy_at = jobs.now()
    row.last_copy_status = run.status
    row.last_copy_error = (run.message or None) if run.status != "ok" else None
    if run.status != "ok":
        logger.error("Copy of %s into %s ended %s: %s",
                     _record(run).get("snapshot"), row.id, run.status,
                     run.message)  # fmt: skip
        return False
    copy = result.get("copy") if isinstance(result.get("copy"), dict) else {}
    name = copy.get("snapshot") or _record(run).get("snapshot")
    if isinstance(name, str):
        row.snapshots = json.dumps(sorted(set(_names(row.snapshots)) | {name}))
    return True


def _after_copy(db: Session, row, run, result) -> None:
    if record_copy(row, run, result):
        advance(db, row, copied=True)


def _record(run: models.BackupRun) -> Dict[str, Any]:
    try:
        value = json.loads(run.parameters or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _after_prune(_db: Session, row, run, result) -> None:
    dropped = [n for n in result.get("pruned") or [] if isinstance(n, str)]
    if dropped:
        row.pruned = json.dumps(
            sorted(set(_names(row.pruned)) | set(dropped))[-PRUNED_KEEP:]
        )
        row.snapshots = json.dumps(sorted(set(_names(row.snapshots)) - set(dropped)))
    if run.status == "ok":
        queue_offsite(_db, row, "du")


def record_du(row: Any, run: models.BackupRun, result: Dict[str, Any]) -> None:
    """What a du of the copy listed: its snapshots and size."""
    _after_du(None, row, run, result)


def _after_du(_db: Session, row, run, result) -> None:
    if run.status != "ok":
        return
    usage = result.get("du") if isinstance(result.get("du"), dict) else {}
    entries = [e for e in usage.get("snapshots") or [] if isinstance(e, dict)]
    names = sorted(e["name"] for e in entries if isinstance(e.get("name"), str))
    if isinstance(usage.get("snapshots"), list):
        row.snapshots = json.dumps(names)
        row.newest_snapshot = names[-1] if names else None
        row.newest_at = _stamp(names[-1]) if names else None
    if isinstance(usage.get("bytes"), int):
        row.repository_bytes = usage["bytes"]


def _stamp(name: str) -> Optional[datetime]:
    try:
        return datetime.strptime(name[:16], "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None


def _after_chain_step(db: Session, row, run, _result) -> None:
    """protect -> seal (when the copy's target seals) -> prune -> du; a failed
    seal holds the prune back, as on the source."""
    action = run.action[len(PREFIX) :]
    if action == "prepare":
        if run.status == "ok":
            row.prepared_at = jobs.now()
            advance(db, row)
        return
    if action == "protect":
        holder = db.get(models.BackupTarget, row.target_id)
        sealing = holder is not None and (holder.seal_mode or "none") != "none"
        nxt = "seal" if sealing else "prune"
    elif action == "seal":
        if run.status != "ok":
            logger.error("Off-site seal for copy %s ended %s; prune held back",
                         row.id, run.status)  # fmt: skip
            return
        nxt = "prune"
    else:
        return
    if nxt == "prune" and "prune" not in _installed(db, row):
        nxt = "du"  # held snapshots this restate cannot keep: never prune
    queue_offsite(db, row, nxt)


def _installed(db: Session, row: models.BackupReplica) -> List[str]:
    policy = db.get(models.BackupPolicy, row.policy_id)
    keep = jobs.prune_keep(policy) if policy else {}
    return ["prune"] if _holds_ok(row, keep) else []


_AFTER = {
    COPY: _after_copy,
    run_action("prune"): _after_prune,
    run_action("du"): _after_du,
    run_action("prepare"): _after_chain_step,
    run_action("protect"): _after_chain_step,
    run_action("seal"): _after_chain_step,
}


def after(db: Session, run: models.BackupRun, result: Dict[str, Any]) -> None:
    """What follows one off-site run's result."""
    row = _row(db, run)
    handler = _AFTER.get(run.action)
    if row is None or handler is None:
        return
    handler(db, row, run, result)
    row.updated_at = jobs.now()


# --- the scheduler ------------------------------------------------------


def _every_copy(db: Session) -> List[Any]:
    return [
        *db.query(models.BackupReplica).all(),
        *db.query(models.BackupMove).filter(models.BackupMove.status.in_(MOVING)),
    ]


def configure_pending(db: Session) -> None:
    """Send each copy's changed job files to its storage host -- once its
    grant can name the source's token."""
    for row in _every_copy(db):
        if row.token_sha256 and (row.acked_version or 0) < row.config_version:
            queue_configure(db, row)


def tick(db: Session, now: datetime) -> None:
    """Send changed off-site job files, and start a copy that has stalled
    (a failure, or a copy set up since the last nightly chain)."""
    configure_pending(db)
    for row in _every_copy(db):
        last = row.last_copy_at
        if last is None or (now - last).total_seconds() >= RETRY_HOURS * 3600:
            advance(db, row)


# --- what the Backups page shows -----------------------------------------


def view(
    db: Session, policy: models.BackupPolicy, now: datetime
) -> List[Dict[str, Any]]:
    """Each off-site copy of one host: where, how far behind, how big."""
    out = []
    for row in rows(db, policy):
        holder = db.get(models.BackupTarget, row.target_id)
        lag = None
        if row.newest_at is not None:
            lag = round(max(0.0, (now - row.newest_at).total_seconds()) / 3600, 1)
        out.append({
            "id": str(row.id),
            "target_id": str(row.target_id),
            "target": holder.name if holder else None,
            "newest_snapshot": row.newest_snapshot,
            "lag_hours": lag,
            "behind": len(needed(db, row)),
            "bytes": row.repository_bytes,
            "ready": ready(row),
            # A restore can come from it: the host's read token is in its
            # grant (27.3); and which snapshots it holds.
            "readable": readable_now(row, policy),
            "snapshots": _names(row.snapshots),
            "last_copy_at": row.last_copy_at.isoformat() if row.last_copy_at else None,
            "last_copy_status": row.last_copy_status,
            "last_copy_error": row.last_copy_error,
        })  # fmt: skip
    return out


# --- restoring from the copy ---------------------------------------------

_UNREADABLE = {
    "no_copy": lambda: _("This host has no off-site copy"),
    "not_ready": lambda: _(
        "The off-site copy cannot be read yet: its storage host has not been "
        "told this host's read token"
    ),
    "not_there": lambda: _("That snapshot is not in the off-site copy"),
    "agent": lambda: _(
        "This host's agent cannot read its off-site copy yet; upgrade the agent"
    ),
}


def readable_now(row: models.BackupReplica, policy: models.BackupPolicy) -> bool:
    return (
        READ_ABILITY in jobs.abilities(policy)
        and bool(row.read_token_sha256)
        and bool(row.acked_version)
        and row.acked_version >= row.config_version
    )


def readable(
    db: Session, policy: models.BackupPolicy, snapshot: Optional[str] = None
) -> models.BackupReplica:
    """The off-site copy a restore or browse reads (HTTP 409 with the
    reason when it cannot): one whose grant names the host's read token,
    holding ``snapshot``.  Its own site's storage is not asked at all."""
    found = [row for row in rows(db, policy) if row.acked_version]
    if not found:
        raise HTTPException(status_code=409, detail=_UNREADABLE["no_copy"]())
    if READ_ABILITY not in jobs.abilities(policy):
        raise HTTPException(status_code=409, detail=_UNREADABLE["agent"]())
    granted = [
        row
        for row in found
        if row.read_token_sha256 and row.acked_version >= row.config_version
    ]
    if not granted:
        raise HTTPException(status_code=409, detail=_UNREADABLE["not_ready"]())
    for row in granted:
        if snapshot is None or snapshot in _names(row.snapshots):
            return row
    raise HTTPException(status_code=409, detail=_UNREADABLE["not_there"]())


def repository_of(
    row: models.BackupReplica, policy: models.BackupPolicy, host: models.Host
) -> str:
    """Which of the policy's repositories the copy is of: the current one
    (encrypted when the policy is, so its key is fetched as for any
    restore), else the one before it, which is plain."""
    if row.repo_dir == jobs.policy_repo_dir(policy, host):
        return jobs.CURRENT
    return jobs.PREVIOUS
