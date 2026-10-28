# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backup jobs with restate (ROADMAP Phase 24): what is sent, and to whom.

The protocol, shared with the agent:

* ``backup_configure`` -- ``{policy_id, role, target: {mount_point,
  repo_dir}, jobs}``.  ``role`` is ``host`` (the backed-up host:
  ``capture``, ``snapshots``, ``estimate`` -- it NEVER prunes) or
  ``storage`` (the target's storage host, the NAS's own agent: ``seal``,
  ``prune``, ``check``), whose ``mount_point`` is the storage path.  The
  agent writes the root-owned restate job files from these, setting the
  command, repository, result and progress paths itself -- and refuses a
  server that sends any of them.  (Encryption, Pro+ later: the armored
  public key would go at the top level as ``encrypt_key``.)  The policy's
  ``config_version`` is NOT sent; it is kept on the run row, and the
  agent's success acknowledges it.
* ``backup_run`` -- ``{run_id, policy_id, action}``; the agent answers
  ``started`` at once, or refuses (``not_configured``, ``busy``, ...).
* ``backup_restore`` -- ``{run_id, policy_id, snapshot, include, exclude,
  dry_run, allow_unverified}``; always into the agent's staging directory.

The repository size comes from each capture's ``repository_bytes``; a
storage-side ``du`` is a follow-up.

Append-only is the storage host's job, not restate's: a root attacker on the
backed-up host would simply not pass the flag.  So every good capture is
followed, on the storage host, by ``seal`` (a ZFS snapshot, or a read-only
btrfs snapshot of ``storage_path`` into ``btrfs_snapshot_dir``, when the
target has one) and only then ``prune`` -- never a prune on the host itself.

"""

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import config_mgmt_dispatch
from backend.services.agent_capability_service import get_capability_report
from backend.websocket.messages import CommandType

logger = logging.getLogger(__name__)

GROUP = "backup"
SYSTEM_ACTOR = "system:backup-scheduler"

HOST_ACTIONS = ("capture", "snapshots", "estimate")
# ``prepare`` is started by an administrator: the storage host gives the
# repository its own dataset / subvolume and an export to that host only.
STORAGE_ACTIONS = ("seal", "prune", "check", "du", "repack", "prepare", "protect")
PREPARE = "prepare"
# Read-only host jobs started from the UI (restate 2.1.0.4+): browse one
# directory of a snapshot, and what changed since one.
LIST = "list"
STATUS = "status"
BROWSE_ACTIONS = (LIST, STATUS)
# Pro+ scheduled verification: ``check --read-all`` on the backed-up host
# (it holds the keys for one job; the storage host never does).
VERIFY = "verify"
CONFIGURE = "configure"
RESTORE = "restore"

QUEUED, RUNNING = "queued", "running"
PENDING = (QUEUED, RUNNING)
# restate's own status words (its exit codes 0, 1, 3, 2, 4, 5).
FINAL = ("ok", "different", "incomplete", "failed", "untrusted", "busy")
GOOD_CAPTURE = ("ok", "incomplete")
SEAL_MODES = ("none", "zfs_snapshot", "btrfs_snapshot")

# Where the agent stages a restore (the agent's own, never the live tree).
STAGING_ROOT = "/var/lib/sysmanage-agent/restore"

_FQDN_UNSAFE = re.compile(r"[^a-z0-9.-]+")


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def repo_dir(host: models.Host) -> str:
    """``<fqdn>-<first 8 hex of the host id>``: keyed by the id so a renamed
    or reinstalled host keeps its history, readable thanks to the name."""
    fqdn = _FQDN_UNSAFE.sub("-", (host.fqdn or "host").lower()).strip(".-") or "host"
    short = uuid.UUID(str(host.id)).hex[:8]
    return f"{fqdn}-{short}"


def policy_repo_dir(policy: models.BackupPolicy, host: models.Host) -> str:
    """The policy's CURRENT repository directory: its own once encryption has
    started a new repository (Pro+ backup_engine), else ``repo_dir``."""
    return policy.repository_dir or repo_dir(host)


def snapshot_repo_dir(snapshot: models.BackupSnapshot, host: models.Host) -> str:
    """Which repository holds a snapshot (NULL = the default one)."""
    return snapshot.repository_dir or repo_dir(host)


def in_previous_repository(
    snapshot: models.BackupSnapshot, policy: models.BackupPolicy, host: models.Host
) -> bool:
    """The snapshot is in the repository before the current one."""
    return (
        bool(policy.previous_repository_dir)
        and snapshot_repo_dir(snapshot, host) == policy.previous_repository_dir
    )


def encrypted(policy: models.BackupPolicy) -> bool:
    """The CURRENT repository is encrypted (its key is in OpenBAO).  The
    public key is sent whether or not backup_engine is loaded now: an
    encrypted repository refuses a capture without it, so a lapsed licence
    must not stop backups."""
    return bool(policy.encrypt_public_key)


def _previous(policy: models.BackupPolicy, storage) -> Dict[str, Any]:
    """The repository before an encrypted one, for restores from it."""
    if not policy.previous_repository_dir:
        return {}
    previous: Dict[str, Any] = {"repo_dir": policy.previous_repository_dir}
    server = host_address(storage) if storage is not None else None
    if server and policy.previous_nfs_path:
        previous["nfs"] = {"server": server, "path": policy.previous_nfs_path}
    return {"previous": previous}


CURRENT = "current"
PREVIOUS = "previous"


def snapshot_repository(
    snapshot: models.BackupSnapshot, policy: models.BackupPolicy, host: models.Host
) -> Optional[str]:
    """CURRENT, PREVIOUS, or None when no repository the policy keeps holds
    it any more."""
    where = snapshot_repo_dir(snapshot, host)
    if where == policy_repo_dir(policy, host):
        return CURRENT
    if where == policy.previous_repository_dir:
        return PREVIOUS
    return None


def needs_secret_key(where: Optional[str], policy: models.BackupPolicy) -> bool:
    """Reading this repository's indexes needs the secret key (restore,
    browse, what changed): the current one when it is encrypted.  The one
    before an encrypted repository is the plain one it replaced."""
    return where == CURRENT and encrypted(policy)


def current_repository_has_snapshots(db: Session, policy: models.BackupPolicy) -> bool:
    """The policy's CURRENT repository exists: it holds a snapshot."""
    in_current = (
        models.BackupSnapshot.repository_dir.is_(None)
        if policy.repository_dir is None
        else models.BackupSnapshot.repository_dir == policy.repository_dir
    )
    return (
        db.query(models.BackupSnapshot.id)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.gone_at.is_(None),
            in_current,
        )
        .first()
        is not None
    )


def staging_dir(run_id: Any) -> str:
    return f"{STAGING_ROOT}/{run_id}"


def equipped(host: Optional[models.Host]) -> Tuple[bool, Optional[str]]:
    """Can this host's agent run backup jobs?  ``(True, None)``, or False
    with why: the agent's own reason (``missing_tool``, ``tool_outdated``),
    ``agent_outdated`` (it predates backups), or ``no_host``."""
    if host is None:
        return False, "no_host"
    report = get_capability_report(host)
    if not report:
        return False, "agent_outdated"
    unavailable = report.get("unavailable") or {}
    if GROUP in unavailable:
        return False, str(unavailable[GROUP])
    not_applicable = report.get("not_applicable") or {}
    if GROUP in not_applicable:
        return False, str(not_applicable[GROUP])
    if GROUP in (report.get("capabilities") or []):
        return True, None
    return False, "agent_outdated"


def _json_strings(text: Optional[str]) -> List[str]:
    try:
        values = json.loads(text) if text else []
    except ValueError:
        return []
    if not isinstance(values, list):
        return []
    return [str(v) for v in values if isinstance(v, str)]


def quiesce_names(policy: models.BackupPolicy) -> List[str]:
    return _json_strings(policy.quiesce_with)


def path_rules(policy: models.BackupPolicy) -> Dict[str, List[str]]:
    """The operator's ``keep_paths`` / ``skip_paths``, only those set."""
    rules = {
        "keep_paths": _json_strings(policy.keep_paths),
        "skip_paths": _json_strings(policy.skip_paths),
    }
    return {key: value for key, value in rules.items() if value}


def host_configuration(
    policy: models.BackupPolicy,
    target: models.BackupTarget,
    host: models.Host,
    storage: Optional[models.Host] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "policy_id": str(policy.id),
        "role": "host",
        "target": {
            "mount_point": target.host_mount_point,
            "repo_dir": policy_repo_dir(policy, host),
            **nfs_source(policy, storage),
            **_previous(policy, storage),
        },
        "jobs": {
            "capture": {
                "all": False,
                "baseline_content": False,
                "quiesce": bool(policy.quiesce),
                "quiesce_with": quiesce_names(policy),
                **path_rules(policy),
            },
            "snapshots": {},
            "estimate": dict(path_rules(policy)),
        },
    }
    if encrypted(policy):
        # The agent installs it root-owned and adds ``encrypt_to`` to the
        # capture; it never receives the secret key here.
        out["encrypt_key"] = policy.encrypt_public_key
    return out


DEFAULT_SERVICE_ACCOUNT = "restate"


def nfs_source(
    policy: models.BackupPolicy, storage: Optional[models.Host]
) -> Dict[str, Any]:
    """``{"nfs": {"server", "path"}}`` once the storage host has said where
    this host's repository is exported, else ``{}`` (the operator mounts
    it).  The host's agent mounts it only while a job runs."""
    server = host_address(storage) if storage is not None else None
    if not server or not policy.storage_nfs_path:
        return {}
    return {"nfs": {"server": server, "path": policy.storage_nfs_path}}


def host_address(host: models.Host) -> Optional[str]:
    """The backed-up host's address as the storage host sees it, if known."""
    value = (host.ipv4 or "").strip()
    return value or None


def storage_configuration(
    policy: models.BackupPolicy, target: models.BackupTarget, host: models.Host
) -> Dict[str, Any]:
    """The storage host's jobs for ONE backed-up host's repository."""
    return {
        "policy_id": str(policy.id),
        "role": "storage",
        "target": {
            "mount_point": target.storage_path,
            "repo_dir": policy_repo_dir(policy, host),
            # Whom this repository's export may serve, and the account it maps
            # them to: what the storage host's audit checks the export against.
            "client_address": host_address(host),
            "service_account": target.service_account or DEFAULT_SERVICE_ACCOUNT,
        },
        "jobs": {
            "seal": seal_job(target),
            "prune": prune_keep(policy),
            "check": {"read_all": False},
            # After each prune: the repository's size and what each
            # snapshot alone would free (pack lists only; no key needed).
            "du": {},
            # Rewrite old packs as seekable ones (restate 2.0.0.8+; the agent
            # installs it only where restate has it).  Started by hand.
            "repack": {},
            # After each capture: finished packs and snapshots root's and
            # read-only -- hosts append only (restate 2.1.0.1+; installed only
            # where restate has it, which the configure reply says).
            "protect": {},
        },
    }


def seal_job(target: models.BackupTarget) -> Dict[str, Any]:
    """The storage side's seal job: ``{"mode": "none"}``, a ZFS snapshot of
    the dataset, or a read-only btrfs snapshot of the storage path."""
    mode = target.seal_mode or "none"
    keep = seal_keep_days(target)
    if mode == "zfs_snapshot":
        return {"mode": mode, "dataset": target.zfs_dataset, "keep_days": keep}
    if mode == "btrfs_snapshot":
        return {
            "mode": mode,
            "subvolume": target.storage_path,
            "snapshot_dir": target.btrfs_snapshot_dir,
            "keep_days": keep,
        }
    return {"mode": "none"}


DEFAULT_SEAL_KEEP_DAYS = 14
# restate's plaintext write cache on each host of an encrypted repository.
DEFAULT_CACHE_BUDGET_GB = 20


def cache_budget_gb(target: models.BackupTarget) -> int:
    """When a host's write cache counts as over budget (GB)."""
    return getattr(target, "cache_budget_gb", None) or DEFAULT_CACHE_BUDGET_GB


def seal_keep_days(target: models.BackupTarget) -> int:
    """How long the storage host keeps its seals (the newest always stays)."""
    return getattr(target, "seal_keep_days", None) or DEFAULT_SEAL_KEEP_DAYS


def _queue(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session,
    policy: models.BackupPolicy,
    run_host_id: Any,
    action: str,
    command_type: CommandType,
    parameters: Dict[str, Any],
    actor: str,
    record: Optional[Dict[str, Any]] = None,
) -> models.BackupRun:
    """Queue one command; ``record`` is kept on the run but never sent."""
    run_id = uuid.uuid4()
    parameters = {"run_id": str(run_id), **parameters}
    run = models.BackupRun(
        id=run_id,
        policy_id=policy.id,
        host_id=run_host_id,
        action=action,
        status=QUEUED,
        queued_at=now(),
        requested_by=actor,
        parameters=json.dumps({**parameters, **(record or {})}),
    )
    db.add(run)
    db.flush()
    run.command_id = config_mgmt_dispatch.queue_command(
        db, run_host_id, command_type, parameters
    )
    db.flush()
    return run


def queue_configure(
    db: Session,
    policy: models.BackupPolicy,
    target: models.BackupTarget,
    host: models.Host,
    role: str,
    actor: str = SYSTEM_ACTOR,
) -> models.BackupRun:
    """Send the host (or the storage host) this policy's job files."""
    if role == "storage":
        payload = storage_configuration(policy, target, host)
        run_host = target.storage_host_id
        policy.storage_client_address = payload["target"]["client_address"]
    else:
        payload = host_configuration(policy, target, host, storage_host(db, target))
        run_host = host.id
    return _queue(
        db,
        policy,
        run_host,
        CONFIGURE,
        CommandType.BACKUP_CONFIGURE,
        payload,
        actor,
        record={"config_version": policy.config_version},
    )


def queue_run(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session,
    policy: models.BackupPolicy,
    run_host_id: Any,
    action: str,
    actor: str = SYSTEM_ACTOR,
    record: Optional[Dict[str, Any]] = None,
) -> models.BackupRun:
    """Run one configured job: a host action on the host, a storage action on
    the storage host.  The caller picks the right host."""
    if action not in HOST_ACTIONS + STORAGE_ACTIONS:
        raise ValueError(f"unknown backup action {action!r}")
    # A prepare remembers the address its export was made for, so a later
    # address change can re-prepare it (backup_results).
    if action == PREPARE:
        record = dict(record or {}, client_address=policy.storage_client_address)
    return _queue(
        db,
        policy,
        run_host_id,
        action,
        CommandType.BACKUP_RUN,
        {"policy_id": str(policy.id), "action": action},
        actor,
        record=record,
    )


def address_changed(policy: models.BackupPolicy, host: models.Host) -> bool:
    """Has the host's address moved since the storage side was told?  Only
    once the storage side has been told something (never on a first send)."""
    told = policy.storage_client_address
    return (
        policy.storage_acked_version > 0
        and told is not None
        and (told != host_address(host))
    )


def queue_restore(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session,
    policy: models.BackupPolicy,
    host: models.Host,
    snapshot: str,
    include: List[str],
    dry_run: bool,
    allow_unverified: bool,
    actor: str,
    exclude: Optional[List[str]] = None,
    in_place: bool = False,
    previous: bool = False,
    needs_key: bool = False,
) -> models.BackupRun:
    """Restore into the agent's staging directory, or (``in_place``) over the
    host's own files; the agent chooses the root either way."""
    return _queue(
        db,
        policy,
        host.id,
        RESTORE,
        CommandType.BACKUP_RESTORE,
        {
            "policy_id": str(policy.id),
            "snapshot": snapshot,
            "include": list(include),
            "exclude": list(exclude or []),
            "dry_run": bool(dry_run),
            "allow_unverified": bool(allow_unverified),
            "in_place": bool(in_place),
            **({"previous": True} if previous else {}),
            # Never the key itself (this goes through the queue and the run
            # row): the agent fetches it for this run (backup_key_release).
            **({"needs_key": True} if needs_key else {}),
        },
        actor,
    )


def queue_browse(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session,
    policy: models.BackupPolicy,
    host: models.Host,
    action: str,
    snapshot: Optional[str],
    path: Optional[str],
    actor: str,
    previous: bool = False,
    needs_key: bool = False,
) -> models.BackupRun:
    """A snapshot listing or a what-changed check on the host itself
    (``previous``: in the repository before an encrypted one)."""
    if action not in BROWSE_ACTIONS:
        raise ValueError(f"unknown browse action {action!r}")
    params: Dict[str, Any] = {"policy_id": str(policy.id), "action": action}
    if previous:
        params["previous"] = True
    if needs_key:
        params["needs_key"] = True  # fetched by the agent, never sent here
    if snapshot:
        params["snapshot"] = snapshot
    if action == LIST:
        params["path"] = path or "/"
    return _queue(db, policy, host.id, action, CommandType.BACKUP_RUN, params, actor)


def queue_verify(
    db: Session, policy: models.BackupPolicy, host_id: Any, needs_key: bool = False
) -> models.BackupRun:
    """A full-read check of the host's current repository, on the host."""
    params: Dict[str, Any] = {"policy_id": str(policy.id), "action": VERIFY}
    if needs_key:
        params["needs_key"] = True  # fetched by the agent, never sent here
    return _queue(
        db, policy, host_id, VERIFY, CommandType.BACKUP_RUN, params, SYSTEM_ACTOR
    )


# Grandfather-father-son counts a prune keeps beside keep_last (q67).
GFS_KEYS = ("keep_daily", "keep_weekly", "keep_monthly", "keep_yearly")


def prune_keep(policy: models.BackupPolicy) -> Dict[str, int]:
    """The storage-side prune's keep rules: keep_last, plus each
    grandfather-father-son count that is set.  Sent whatever the license:
    a lapsed one must never make a prune delete history the operator chose
    to keep (setting them is what needs Pro+)."""
    keep = {"keep_last": policy.keep_last}
    for key in GFS_KEYS:
        value = getattr(policy, key, None)
        if value:
            keep[key] = int(value)
    return keep


def abilities(policy: models.BackupPolicy) -> List[str]:
    """What the host's restate offers beyond the 2.0 contract."""
    return _json_strings(getattr(policy, "host_abilities", None))


def storage_abilities(policy: models.BackupPolicy) -> List[str]:
    """What the storage host's restate offers for this policy (keep_yearly)."""
    return _json_strings(getattr(policy, "storage_abilities", None))


def pending(db: Session, policy_id: Any, action: str, host_id: Any = None) -> bool:
    """A run of ``action`` for this policy is still queued or running."""
    query = db.query(models.BackupRun.id).filter(
        models.BackupRun.policy_id == policy_id,
        models.BackupRun.action == action,
        models.BackupRun.status.in_(PENDING),
    )
    if host_id is not None:
        query = query.filter(models.BackupRun.host_id == host_id)
    return query.first() is not None


def latest_run(
    db: Session, policy_id: Any, action: str, statuses=None
) -> Optional[models.BackupRun]:
    query = db.query(models.BackupRun).filter(
        models.BackupRun.policy_id == policy_id, models.BackupRun.action == action
    )
    if statuses:
        query = query.filter(models.BackupRun.status.in_(statuses))
    return query.order_by(models.BackupRun.queued_at.desc()).first()


# Finished runs older than this are deleted by the scheduler -- except, for
# each policy, the newest run of each action and outcome, which the status
# column and the storage-side scheduling read.
RUN_RETENTION_DAYS = 30
RUN_RETENTION_BATCH = 5000


def prune_run_history(db: Session, now) -> int:
    """Delete old finished runs, keeping each (policy, action, status)'s
    newest.  Bounded per call; the next tick takes the rest."""
    cutoff = now - timedelta(days=RUN_RETENTION_DAYS)
    newest = (
        db.query(
            models.BackupRun.policy_id,
            models.BackupRun.action,
            models.BackupRun.status,
            func.max(models.BackupRun.queued_at),
        )
        .group_by(
            models.BackupRun.policy_id,
            models.BackupRun.action,
            models.BackupRun.status,
        )
        .all()
    )
    keep = {(str(p), a, s, q) for p, a, s, q in newest}
    old = (
        db.query(models.BackupRun)
        .filter(
            models.BackupRun.status.in_(FINAL),
            models.BackupRun.queued_at < cutoff,
        )
        .order_by(models.BackupRun.queued_at)
        .limit(RUN_RETENTION_BATCH)
        .all()
    )
    removed = 0
    for run in old:
        if (str(run.policy_id), run.action, run.status, run.queued_at) in keep:
            continue
        db.delete(run)
        removed += 1
    # A folder listing is only read once, by the browser that asked: a day
    # is plenty, and there are many of them.
    listings = (
        db.query(models.BackupRun)
        .filter(
            models.BackupRun.action == LIST,
            models.BackupRun.status.in_(FINAL),
            models.BackupRun.queued_at < now - timedelta(days=1),
        )
        .limit(RUN_RETENTION_BATCH)
        .all()
    )
    for run in listings:
        db.delete(run)
        removed += 1
    return removed


def the_target(db: Session) -> Optional[models.BackupTarget]:
    """Community has one target."""
    return (
        db.query(models.BackupTarget).order_by(models.BackupTarget.created_at).first()
    )


def storage_host(db: Session, target: models.BackupTarget) -> Optional[models.Host]:
    if target is None or target.storage_host_id is None:
        return None
    return (
        db.query(models.Host).filter(models.Host.id == target.storage_host_id).first()
    )
