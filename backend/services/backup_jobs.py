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
STORAGE_ACTIONS = ("seal", "prune", "check", "du")
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
    policy: models.BackupPolicy, target: models.BackupTarget, host: models.Host
) -> Dict[str, Any]:
    return {
        "policy_id": str(policy.id),
        "role": "host",
        "target": {"mount_point": target.host_mount_point, "repo_dir": repo_dir(host)},
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


def storage_configuration(
    policy: models.BackupPolicy, target: models.BackupTarget, host: models.Host
) -> Dict[str, Any]:
    """The storage host's jobs for ONE backed-up host's repository."""
    return {
        "policy_id": str(policy.id),
        "role": "storage",
        "target": {"mount_point": target.storage_path, "repo_dir": repo_dir(host)},
        "jobs": {
            "seal": seal_job(target),
            "prune": {"keep_last": policy.keep_last},
            "check": {"read_all": False},
            # After each prune: the repository's size and what each
            # snapshot alone would free (pack lists only; no key needed).
            "du": {},
        },
    }


def seal_job(target: models.BackupTarget) -> Dict[str, Any]:
    """The storage side's seal job: ``{"mode": "none"}``, a ZFS snapshot of
    the dataset, or a read-only btrfs snapshot of the storage path."""
    mode = target.seal_mode or "none"
    if mode == "zfs_snapshot":
        return {"mode": mode, "dataset": target.zfs_dataset}
    if mode == "btrfs_snapshot":
        return {
            "mode": mode,
            "subvolume": target.storage_path,
            "snapshot_dir": target.btrfs_snapshot_dir,
        }
    return {"mode": "none"}


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
    else:
        payload = host_configuration(policy, target, host)
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


def queue_run(
    db: Session,
    policy: models.BackupPolicy,
    run_host_id: Any,
    action: str,
    actor: str = SYSTEM_ACTOR,
) -> models.BackupRun:
    """Run one configured job: a host action on the host, a storage action on
    the storage host.  The caller picks the right host."""
    if action not in HOST_ACTIONS + STORAGE_ACTIONS:
        raise ValueError(f"unknown backup action {action!r}")
    return _queue(
        db,
        policy,
        run_host_id,
        action,
        CommandType.BACKUP_RUN,
        {"policy_id": str(policy.id), "action": action},
        actor,
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
) -> models.BackupRun:
    """Restore into the agent's staging directory -- never over the live tree."""
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
        },
        actor,
    )


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
