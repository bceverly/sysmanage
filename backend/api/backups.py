# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Fleet backup with restate (ROADMAP Phase 24, Community scope).

``GET /backups/overview`` -- the target, every approved host's backup
status (``ok``, ``incomplete``, ``overdue``, ``failed``, ``never``,
``not_equipped`` with its reason, ...), coverage, next due, and the restate
versions in use; the target carries its storage side's status and
warnings (``backend.services.backup_storage_status``).  ``GET
/backups/summary`` -- counts, for the dashboard (a target whose storage side
is broken counts once).

``POST /backups/targets``, ``PUT``/``DELETE /backups/targets/{id}`` -- the
one target (Community: a second is 409).  Manage Backups.

``GET /host/{id}/backup`` -- one host's status, policy and snapshots.
``PUT``/``DELETE /host/{id}/backup-policy`` -- its schedule, retention,
check cadence and quiesce.  ``POST /host/{id}/backup-now`` -- a capture now
(or ``estimate``/``snapshots`` on the host, ``check`` on the storage host).  Manage Backups.

``GET /backups/runs`` (``?host_id``, ``limit``, ``offset``), ``GET
/backups/runs/{id}`` and ``GET /host/{id}/backup-snapshots``.

``POST /host/{id}/backup-restore`` -- Restore Files.  Into the agent's
staging directory, or with ``in_place`` over the host's own files (specific
paths only, acknowledged with ``acknowledge_in_place``; the agent picks the
root and spares its own state); ``dry_run`` (the default) only previews.
Snapshots are not signed in Community, so the request must acknowledge that
explicitly (``acknowledge_unsigned``).

Every change is audited.
"""

import json
import posixpath
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api import backups_retention as retention
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_jobs as jobs
from backend.services import backup_storage_status as storage_fs
from backend.services import backup_tick
from backend.services import backup_views as views
from backend.services.audit_service import ActionType, AuditService, EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])

_HOOK_NAME = re.compile(r"^[a-z0-9_-]{1,32}$")
_SNAPSHOT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,254}$")
_DATASET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,254}$")
# What the agent accepts for a btrfs seal path (it checks again).
_SEAL_PATH = re.compile(r"^/[A-Za-z0-9_./-]*$")
# A POSIX account name, as the storage host's agent accepts it.
_ACCOUNT_NAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_RUNNABLE = {
    "capture": "host",
    "estimate": "host",
    "snapshots": "host",
    "check": "storage",
    "repack": "storage",
    "prepare": "storage",
}


class TargetBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    host_mount_point: str = Field(min_length=1, max_length=1024)
    storage_host_id: Optional[str] = None
    storage_path: Optional[str] = Field(default=None, max_length=1024)
    max_concurrent: int = 2
    seal_mode: str = "none"
    zfs_dataset: Optional[str] = Field(default=None, max_length=255)
    btrfs_snapshot_dir: Optional[str] = Field(default=None, max_length=1024)
    # The storage host's backup account every host's export maps to.
    service_account: Optional[str] = Field(default=None, max_length=32)
    # Days the storage host keeps its seals; None = the default (14).
    seal_keep_days: Optional[int] = None
    # GB of restate write cache per host before it is flagged; None = 20.
    cache_budget_gb: Optional[int] = None
    # Percent used at which the target warns, and warns critically.
    space_low_percent: Optional[int] = None
    space_critical_percent: Optional[int] = None


class PolicyBody(BaseModel):
    enabled: bool = True
    interval_hours: int = 24
    window_start_hour: Optional[int] = None
    # A month of daily backups when a caller gives no count (2026-10-29).
    keep_last: int = 30
    # Grandfather-father-son (Pro+ to set): 0 = not used.
    keep_daily: int = 0
    keep_weekly: int = 0
    keep_monthly: int = 0
    keep_yearly: int = 0
    # Pro+ scheduled verification: a full-read check every N days (0 = off).
    verify_interval_days: int = 0
    check_interval_days: int = 7
    quiesce: bool = False
    quiesce_with: List[str] = Field(default_factory=list)
    keep_paths: List[str] = Field(default_factory=list)
    skip_paths: List[str] = Field(default_factory=list)


class RunBody(BaseModel):
    action: str = "capture"


MAX_BULK_HOSTS = 500


class BulkBackupBody(BaseModel):
    host_ids: List[str] = Field(min_length=1, max_length=MAX_BULK_HOSTS)


class RestoreBody(BaseModel):
    snapshot: str = Field(min_length=1, max_length=255)
    include: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)
    dry_run: bool = True
    acknowledge_unsigned: bool = False
    # Over the host's own files rather than into staging (24.9).
    in_place: bool = False
    acknowledge_in_place: bool = False


def _bad(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)


def _require(current_user, role: SecurityRoles) -> None:
    if not current_user.has_role(role):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required") % role.value,
        )


def _uuid_or_404(value: str, message: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=message) from exc


def _host_or_404(db: Session, host_id: str) -> models.Host:
    key = _uuid_or_404(host_id, _("Host not found"))
    host = db.query(models.Host).filter(models.Host.id == key).first()
    if host is None:
        raise HTTPException(status_code=404, detail=_("Host not found"))
    return host


def _host_or_none(db: Session, host_id: str) -> Optional[models.Host]:
    try:
        key = uuid.UUID(str(host_id))
    except ValueError:
        return None
    return db.query(models.Host).filter(models.Host.id == key).first()


def _absolute_path(value: Optional[str], label: str) -> None:
    if value is None:
        return
    if not value.startswith("/") or ".." in value.split("/") or "\x00" in value:
        raise _bad(_("%s must be an absolute path without '..'") % label)


def _in_range(value: Optional[int], low: int, high: int, label: str) -> None:
    if value is not None and not low <= value <= high:
        raise _bad(_("%s is out of range") % label + f" ({low}-{high})")


def _validate_target(db: Session, body: TargetBody) -> Optional[uuid.UUID]:
    _absolute_path(body.host_mount_point, _("Host mount point"))
    _absolute_path(body.storage_path, _("Storage path"))
    _in_range(body.max_concurrent, 1, 50, _("Concurrent backups"))
    _in_range(body.seal_keep_days, 1, 3650, _("Days to keep sealed snapshots"))
    _in_range(body.cache_budget_gb, 1, 10000, _("Write cache budget"))
    _in_range(body.space_low_percent, 50, 99, _("Storage space warning"))
    _in_range(body.space_critical_percent, 51, 100, _("Storage space critical"))
    low = body.space_low_percent or 85
    critical = body.space_critical_percent or 95
    if low >= critical:
        raise _bad(_("The storage space warning must be below the critical level"))
    if body.service_account and not _ACCOUNT_NAME.match(body.service_account):
        raise _bad(_("The backup service account is not a valid account name"))
    if body.seal_mode not in jobs.SEAL_MODES:
        raise _bad(_("Unknown seal mode"))
    if body.seal_mode == "zfs_snapshot" and not body.zfs_dataset:
        raise _bad(_("A ZFS snapshot seal needs the dataset name"))
    if body.zfs_dataset and not _DATASET.match(body.zfs_dataset):
        raise _bad(_("The ZFS dataset name is not valid"))
    if body.seal_mode == "btrfs_snapshot":
        _validate_btrfs(body)
    if not body.storage_host_id:
        return None
    storage = _host_or_404(db, body.storage_host_id)
    if not body.storage_path:
        raise _bad(_("A storage host needs the storage path"))
    return storage.id


def _seal_path_ok(value: str) -> bool:
    return (
        bool(_SEAL_PATH.match(value))
        and value != "/"
        and posixpath.normpath(value) == value
        and not any(part.startswith("-") for part in value.split("/"))
    )


def _validate_btrfs(body: TargetBody) -> None:
    """The subvolume is the storage path; snapshots go outside it."""
    snapshot_dir = body.btrfs_snapshot_dir
    if not snapshot_dir:
        raise _bad(_("A btrfs snapshot seal needs the snapshot directory"))
    if not body.storage_path:
        raise _bad(_("A btrfs snapshot seal needs the storage path"))
    for value, label in (
        (body.storage_path, _("Storage path")),
        (snapshot_dir, _("Snapshot directory")),
    ):
        if not _seal_path_ok(value):
            raise _bad(
                _(
                    "%s must be a plain absolute path (letters, digits, "
                    "'_', '.', '-' and '/'; no trailing '/')"
                )
                % label
            )
    if snapshot_dir == body.storage_path or snapshot_dir.startswith(
        body.storage_path + "/"
    ):
        raise _bad(_("The snapshot directory must be outside the storage path"))


def _validate_policy(body: PolicyBody) -> None:
    _in_range(body.interval_hours, 1, 720, _("Interval (hours)"))
    _in_range(body.window_start_hour, 0, 23, _("Window start hour"))
    _in_range(body.keep_last, 1, 1000, _("Snapshots to keep"))
    _in_range(body.check_interval_days, 1, 90, _("Check interval (days)"))
    if len(body.quiesce_with) > 10 or not all(
        _HOOK_NAME.match(n) for n in body.quiesce_with
    ):
        raise _bad(_("Quiesce hooks must be up to 10 short lowercase names"))
    _validate_path_rules(body.keep_paths + body.skip_paths)


# Each pattern becomes one line of a restate rules file on the host (the
# agent checks again): no control characters, no leading or trailing space,
# no comment marker.
MAX_PATH_RULES = 50
MAX_PATH_RULE = 512


def _validate_path_rules(patterns: List[str]) -> None:
    if len(patterns) > MAX_PATH_RULES:
        raise _bad(_("At most 50 path rules can be set"))
    for pattern in patterns:
        if (
            not pattern
            or len(pattern) > MAX_PATH_RULE
            or pattern != pattern.strip()
            or pattern.startswith("#")
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in pattern)
        ):
            raise _bad(
                _(
                    "Each path rule is one line of up to 512 characters, "
                    "without leading or trailing spaces or a leading #"
                )
            )


def _validate_restore(body: RestoreBody) -> None:
    if not _SNAPSHOT_NAME.match(body.snapshot):
        raise _bad(_("The snapshot name is not valid"))
    if len(body.include) > 50 or len(body.exclude) > 50:
        raise _bad(_("At most 50 paths can be restored at once"))
    for pattern in body.include + body.exclude:
        if not pattern or len(pattern) > 1024 or "\x00" in pattern:
            raise _bad(_("A restore path is empty or too long"))
        if ".." in pattern.split("/"):
            raise _bad(_("A restore path must not contain '..'"))
        if not pattern.startswith(("/", "**/")):
            # restate matches paths as a rules file writes them; "~" or a
            # relative path matches nothing, so a preview would "succeed"
            # with no files (lab 2026-10-25).
            raise _bad(
                _("A restore path must be absolute, such as /home/alice/notes.txt")
            )
    if body.in_place:
        _validate_in_place(body)


_WILDCARDS = set("*?[")


def _validate_in_place(body: RestoreBody) -> None:
    """The agent's own rule (job_builder._in_place_includes), said early:
    name what is replaced -- never the whole host, which is a rebuild."""
    if not body.include:
        raise _bad(
            _("Name the paths to put back; a whole host is not restored in place")
        )
    for pattern in body.include:
        first = pattern.lstrip("/").split("/", 1)[0]
        if not pattern.startswith("/") or not first or _WILDCARDS & set(first):
            raise _bad(
                _("Each path restored in place must be specific, such as /etc/nginx")
            )
    if not body.dry_run and not body.acknowledge_in_place:
        raise HTTPException(
            status_code=409,
            detail=_("Confirm that the host's files at these paths will be replaced"),
        )


def _audit(db, current_user, entity_type, entity_id, name, description, details):
    AuditService.log(
        db=db,
        user_id=current_user.id,
        username=current_user.userid,
        action_type=ActionType.UPDATE,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        entity_name=name,
        description=description,
        details=details,
        commit=False,
    )


def _target_or_404(db: Session, target_id: str) -> models.BackupTarget:
    key = _uuid_or_404(target_id, _("Backup target not found"))
    target = db.query(models.BackupTarget).filter(models.BackupTarget.id == key).first()
    if target is None:
        raise HTTPException(status_code=404, detail=_("Backup target not found"))
    return target


def _apply_target(target: models.BackupTarget, body: TargetBody, storage_id) -> None:
    target.name = body.name.strip()
    target.host_mount_point = body.host_mount_point
    target.storage_host_id = storage_id
    target.storage_path = body.storage_path
    target.max_concurrent = body.max_concurrent
    target.seal_mode = body.seal_mode
    target.zfs_dataset = body.zfs_dataset or None
    target.btrfs_snapshot_dir = body.btrfs_snapshot_dir or None
    target.service_account = body.service_account or None
    target.seal_keep_days = body.seal_keep_days
    target.cache_budget_gb = body.cache_budget_gb
    target.space_low_percent = body.space_low_percent
    target.space_critical_percent = body.space_critical_percent
    target.updated_at = jobs.now()


# --- overview -------------------------------------------------------------


@router.get("/backups/overview")
async def backups_overview(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    return views.overview(db)


@router.get("/backups/summary")
async def backups_summary(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    data = views.overview(db)
    return {
        "configured": data["target"] is not None,
        "counts": data["counts"],
        "attention": views.attention_count(data),
        "target_problem": views.target_problem(data),
        "total": sum(1 for row in data["hosts"] if row["policy"]),
    }


# --- targets --------------------------------------------------------------


@router.post("/backups/targets")
async def create_target(
    body: TargetBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    if jobs.the_target(db) is not None:
        raise HTTPException(
            status_code=409,
            detail=_("This edition supports one backup target; edit the existing one"),
        )
    storage_id = _validate_target(db, body)
    target = models.BackupTarget(created_at=jobs.now(), created_by=current_user.userid)
    _apply_target(target, body, storage_id)
    db.add(target)
    db.flush()
    _audit(
        db,
        current_user,
        EntityType.SETTING,
        target.id,
        target.name,
        "Backup target created",
        body.model_dump(),
    )
    backup_tick.configure_now(db)  # take effect now, not on the next tick
    db.commit()
    return views.target_dict(target, db)


@router.put("/backups/targets/{target_id}")
async def update_target(
    target_id: str,
    body: TargetBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    target = _target_or_404(db, target_id)
    storage_id = _validate_target(db, body)
    moved = (str(target.storage_host_id or ""), target.storage_path) != (
        str(storage_id or ""),
        body.storage_path,
    )
    _apply_target(target, body, storage_id)
    if moved:  # the filesystem report was about the old place
        storage_fs.forget_storage_fs(target)
    # Every host's job files name the mount point; the storage side's, the
    # path and seal.  Re-send both.
    for policy in (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.target_id == target.id)
        .all()
    ):
        policy.config_version += 1
        policy.updated_at = jobs.now()
    _audit(
        db,
        current_user,
        EntityType.SETTING,
        target.id,
        target.name,
        "Backup target changed",
        body.model_dump(),
    )
    backup_tick.configure_now(db)  # take effect now, not on the next tick
    db.commit()
    return views.target_dict(target, db)


@router.delete("/backups/targets/{target_id}")
async def delete_target(
    target_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    target = _target_or_404(db, target_id)
    in_use = (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.target_id == target.id)
        .count()
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=_("Remove the hosts' backup policies before the target"),
        )
    _audit(
        db,
        current_user,
        EntityType.SETTING,
        target.id,
        target.name,
        "Backup target deleted",
        {},
    )
    db.delete(target)
    db.commit()
    return {"deleted": True}


# --- per host -------------------------------------------------------------


def _policy_of(db: Session, host: models.Host) -> Optional[models.BackupPolicy]:
    return (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.host_id == host.id)
        .first()
    )


def _snapshots(db: Session, host: models.Host, include_gone: bool = False):
    query = db.query(models.BackupSnapshot).filter(
        models.BackupSnapshot.host_id == host.id
    )
    if not include_gone:
        query = query.filter(models.BackupSnapshot.gone_at.is_(None))
    return query.order_by(models.BackupSnapshot.created_at.desc()).all()


@router.get("/host/{host_id}/backup")
async def host_backup(host_id: str, db: Session = Depends(get_tenant_db)):
    host = _host_or_404(db, host_id)
    view = views.host_status(db, host)
    target = jobs.the_target(db)
    view["target"] = views.target_dict(target, db) if target else None
    return view


@router.get("/host/{host_id}/backup-snapshots")
async def host_snapshots(
    host_id: str,
    include_gone: bool = False,
    db: Session = Depends(get_tenant_db),
) -> List[Dict[str, Any]]:
    host = _host_or_404(db, host_id)
    return [views.snapshot_dict(s) for s in _snapshots(db, host, include_gone)]


def _apply_policy(policy: models.BackupPolicy, body: PolicyBody) -> None:
    policy.enabled = body.enabled
    policy.interval_hours = body.interval_hours
    policy.window_start_hour = body.window_start_hour
    policy.keep_last = body.keep_last
    policy.check_interval_days = body.check_interval_days
    policy.quiesce = body.quiesce
    policy.quiesce_with = json.dumps(list(body.quiesce_with))
    policy.keep_paths = json.dumps(list(body.keep_paths))
    policy.skip_paths = json.dumps(list(body.skip_paths))
    policy.updated_at = jobs.now()


@router.put("/host/{host_id}/backup-policy")
async def put_policy(
    host_id: str,
    body: PolicyBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    host = _host_or_404(db, host_id)
    _validate_policy(body)
    target = jobs.the_target(db)
    if target is None:
        raise HTTPException(status_code=409, detail=_("Set up the backup target first"))
    policy = _policy_of(db, host)
    gfs = retention.check_gfs_change(  # 402 to change without Pro+
        policy, body, jobs.target_storage_abilities(db, target.id)
    )
    if policy is None:
        policy = models.BackupPolicy(
            host_id=host.id,
            target_id=target.id,
            config_version=1,
            host_acked_version=0,
            storage_acked_version=0,
            created_at=jobs.now(),
            created_by=current_user.userid,
        )
        db.add(policy)
    else:
        policy.config_version += 1
    _apply_policy(policy, body)
    retention.apply_gfs(policy, gfs)
    _audit(
        db,
        current_user,
        EntityType.HOST,
        host.id,
        host.fqdn,
        "Backup policy set",
        body.model_dump(),
    )
    backup_tick.configure_now(db)  # take effect now, not on the next tick
    db.commit()
    return views.policy_dict(policy)


@router.delete("/host/{host_id}/backup-policy")
async def delete_policy(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Stops scheduling; the repository and its snapshots are left alone."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    host = _host_or_404(db, host_id)
    policy = _policy_of(db, host)
    if policy is None:
        raise HTTPException(status_code=404, detail=_("No backup policy"))
    _audit(
        db,
        current_user,
        EntityType.HOST,
        host.id,
        host.fqdn,
        "Backup policy removed",
        {},
    )
    db.delete(policy)
    db.commit()
    return {"deleted": True}


def _ready_policy(db: Session, host: models.Host) -> models.BackupPolicy:
    ready, reason = jobs.equipped(host)
    if not ready:
        raise HTTPException(
            status_code=409,
            detail=_("This host cannot run backups yet (%s)") % reason,
        )
    policy = _policy_of(db, host)
    if policy is None or policy.host_acked_version < 1:
        raise HTTPException(
            status_code=409,
            detail=_("This host's backup is not configured yet"),
        )
    return policy


def _run_host(db: Session, policy, host: models.Host, action: str):
    if _RUNNABLE[action] == "host":
        return host.id
    target = jobs.the_target(db)
    storage = jobs.storage_host(db, target)
    if (
        storage is None
        or not jobs.equipped(storage)[0]
        or not (policy.storage_acked_version)
    ):
        raise HTTPException(
            status_code=409,
            detail=_("The backup storage host is not ready"),
        )
    return storage.id


@router.post("/host/{host_id}/backup-now")
async def backup_now(
    host_id: str,
    body: Optional[RunBody] = None,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    action = (body or RunBody()).action
    if action not in _RUNNABLE:
        raise _bad(_("Unknown backup action"))
    host = _host_or_404(db, host_id)
    policy = _ready_policy(db, host)
    if action == "repack" and jobs.encrypted(policy):
        # Rewriting packs needs the secret key, which the storage host never
        # holds (Pro+ backup_engine: it stays keyless).
        raise HTTPException(
            status_code=409,
            detail=_("An encrypted repository cannot be repacked on the storage host"),
        )
    if jobs.pending(db, policy.id, action):
        raise HTTPException(
            status_code=409, detail=_("That backup job is already queued or running")
        )
    run = jobs.queue_run(
        db, policy, _run_host(db, policy, host, action), action, current_user.userid
    )
    _audit(
        db,
        current_user,
        EntityType.HOST,
        host.id,
        host.fqdn,
        f"Backup {action} requested",
        {"run_id": str(run.id)},
    )
    db.commit()
    return views.run_dict(run)


def _bulk_skip_reason(db: Session, host: Optional[models.Host]) -> Optional[str]:
    """Why a host cannot take a "Back up now" from the bulk action, or None."""
    if host is None:
        return "no_host"
    ready, reason = jobs.equipped(host)
    if not ready:
        return reason or "not_equipped"
    policy = _policy_of(db, host)
    if policy is None:
        return "no_policy"
    if policy.host_acked_version < 1:
        return "not_configured"
    if jobs.pending(db, policy.id, "capture"):
        return "running"
    return None


@router.post("/backups/backup-now")
async def bulk_backup_now(
    body: BulkBackupBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """ "Back up now" for many hosts.  Each ready host's request starts as
    soon as the target has a free slot under its concurrency cap -- at once
    for the first ones, and as running captures finish for the rest -- so a
    fleet-wide click never floods the storage host.  A host that cannot run
    a capture is skipped, with the reason."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    requested, skipped = 0, []
    now = jobs.now()
    for host_id in dict.fromkeys(body.host_ids):  # de-duplicated, in order
        host = _host_or_none(db, host_id)
        reason = _bulk_skip_reason(db, host)
        if reason is not None:
            skipped.append(
                {"host_id": host_id, "fqdn": host.fqdn if host else None,
                 "reason": reason}
            )  # fmt: skip
            continue
        policy = _policy_of(db, host)
        policy.capture_requested_at = policy.capture_requested_at or now
        requested += 1
        _audit(db, current_user, EntityType.HOST, host.id, host.fqdn,
               "Backup capture requested (bulk)", {})  # fmt: skip
    started = backup_tick.start_requested(db, current_user.userid)
    db.commit()
    return {
        "requested": requested,
        "started": started,
        "waiting": max(0, requested - started),
        "skipped": skipped,
    }


@router.post("/host/{host_id}/backup-restore")
async def backup_restore(
    host_id: str,
    body: RestoreBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.RESTORE_FILES)
    host = _host_or_404(db, host_id)
    _validate_restore(body)
    policy = _ready_policy(db, host)
    snapshot = (
        db.query(models.BackupSnapshot)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.name == body.snapshot,
            models.BackupSnapshot.gone_at.is_(None),
        )
        .first()
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail=_("Snapshot not found"))
    where = _readable_repository(snapshot, policy, host)
    if not snapshot.signed and not body.acknowledge_unsigned:
        raise HTTPException(
            status_code=409,
            detail=_("This snapshot is not signed; confirm to restore it anyway"),
        )
    run = jobs.queue_restore(
        db,
        policy,
        host,
        snapshot.name,
        body.include,
        body.dry_run,
        allow_unverified=not snapshot.signed,
        actor=current_user.userid,
        exclude=body.exclude,
        in_place=body.in_place,
        previous=where == jobs.PREVIOUS,
        needs_key=key_needed(where, policy),
    )
    _audit(
        db,
        current_user,
        EntityType.HOST,
        host.id,
        host.fqdn,
        _restore_audit_text(body),
        {
            "run_id": str(run.id),
            "snapshot": snapshot.name,
            "include": body.include,
            "exclude": body.exclude,
            "dry_run": body.dry_run,
            "in_place": body.in_place,
            "unsigned_acknowledged": not snapshot.signed,
        },
    )
    db.commit()
    out = views.run_dict(run)
    out["in_place"] = body.in_place
    out["staging_path"] = None if body.in_place else jobs.staging_dir(run.id)
    return out


def key_needed(where: str, policy: models.BackupPolicy) -> bool:
    """Does reading this repository need the policy's secret key on the host
    (Pro+ backup_engine, 24.6 S4)?  Then the run says ``needs_key`` and the
    agent fetches the key for that run only (``/api/agent/backup-key``).
    HTTP 409 when it cannot be handed over: no backup engine to read it from
    OpenBAO, or a restate on the host that cannot take it (``decrypt_with``)."""
    if not jobs.needs_secret_key(where, policy):
        return False
    if module_loader.get_module("backup_engine") is None:
        raise HTTPException(
            status_code=409,
            detail=_("Encrypted backups need the Professional+ backup engine"),
        )
    if "decrypt" not in jobs.abilities(policy):
        raise HTTPException(
            status_code=409,
            detail=_("This host's restate cannot do this yet; upgrade restate"),
        )
    return True


def _readable_repository(snapshot, policy, host) -> str:
    """The repository a restore or listing reads; HTTP 409 when the policy
    no longer keeps the one that holds the snapshot."""
    where = jobs.snapshot_repository(snapshot, policy, host)
    if where is None:
        raise HTTPException(
            status_code=409,
            detail=_("This snapshot's repository is no longer kept"),
        )
    return where


def _restore_audit_text(body: RestoreBody) -> str:
    if body.in_place:
        return (
            "Backup restore into place previewed"
            if body.dry_run
            else "Backup restore into place requested"
        )
    return (
        "Backup restore preview requested"
        if body.dry_run
        else "Backup restore to staging requested"
    )


# --- runs -----------------------------------------------------------------


@router.get("/backups/runs")
async def list_runs(
    host_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_tenant_db),
    include_cleared: bool = False,
) -> Dict[str, Any]:
    query = db.query(models.BackupRun)
    if host_id:
        host = _host_or_404(db, host_id)
        policy = _policy_of(db, host)
        if policy is None:
            return {"total": 0, "runs": []}
        query = query.filter(models.BackupRun.policy_id == policy.id)
    if action:
        query = query.filter(models.BackupRun.action == action)
    else:  # every folder opened while browsing is a run; keep them off the list
        query = query.filter(models.BackupRun.action != jobs.LIST)
    if not include_cleared:
        query = query.filter(models.BackupRun.dismissed_at.is_(None))
    total = query.count()
    rows = (
        query.order_by(models.BackupRun.queued_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"total": total, "runs": [views.run_dict(r) for r in rows]}


@router.post("/backups/runs/clear")
async def clear_runs(
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Clear the job list: finished runs leave it; queued and running ones
    stay.  Nothing is deleted -- the scheduler and the status read history,
    and the audit log records each run's own changes as well as this."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    now = jobs.now()
    cleared = (
        db.query(models.BackupRun)
        .filter(
            models.BackupRun.status.in_(jobs.FINAL),
            models.BackupRun.dismissed_at.is_(None),
        )
        .update({models.BackupRun.dismissed_at: now}, synchronize_session=False)
    )
    target = jobs.the_target(db)
    _audit(db, current_user, EntityType.SETTING,
           target.id if target else None, target.name if target else "backups",
           "Backup job list cleared", {"runs": cleared})  # fmt: skip
    db.commit()
    return {"cleared": cleared}


@router.get("/backups/runs/{run_id}")
async def get_run(run_id: str, db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    key = _uuid_or_404(run_id, _("Backup run not found"))
    run = db.query(models.BackupRun).filter(models.BackupRun.id == key).first()
    if run is None:
        raise HTTPException(status_code=404, detail=_("Backup run not found"))
    out = views.run_dict(run)
    if run.action == jobs.RESTORE:
        out["in_place"] = bool((out.get("parameters") or {}).get("in_place"))
        out["staging_path"] = None if out["in_place"] else _staging_path(run)
    return out


def _staging_path(run: models.BackupRun) -> str:
    """Where the restore landed, as restate reports it (``restore.root``):
    the agent keeps its staging directory beside its own database, which is
    not always /var/lib/sysmanage-agent (a source checkout keeps it there)."""
    try:
        result = json.loads(run.result) if run.result else {}
    except ValueError:
        result = {}
    restore = result.get("restore") if isinstance(result, dict) else None
    root = restore.get("root") if isinstance(restore, dict) else None
    return (
        root
        if isinstance(root, str) and root.startswith("/")
        else jobs.staging_dir(run.id)
    )
