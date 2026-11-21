# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backup targets (ROADMAP Phase 24; several are 27.3, Enterprise).

``GET /backups/targets`` -- every target in a line, the default first.
``POST /backups/targets``, ``PUT``/``DELETE /backups/targets/{id}`` and
``PUT /backups/targets/{id}/default``, and ``POST
/backups/moves/{id}/cancel`` (a host moving to another target with its
backups, 27.3: stopping a move is never licensed).  Manage Backups.  The first target is
the default; a second needs the Enterprise ``backup_ops_engine`` (402
without it), and so does choosing another default while there are several.
A target in use by a host or tag policy, or the default while others
remain, cannot be deleted.  Every change is audited.
"""

import posixpath
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import (
    _absolute_path,
    _audit,
    _bad,
    _host_or_404,
    _in_range,
    _require,
)
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_jobs as jobs
from backend.services import backup_moves as moves
from backend.services import backup_storage_status as storage_fs
from backend.services import backup_targets as targets
from backend.services import backup_tick
from backend.services import backup_views as views
from backend.services.audit_service import EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])

_DATASET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,254}$")
# What the agent accepts for a btrfs seal path (it checks again).
_SEAL_PATH = re.compile(r"^/[A-Za-z0-9_./-]*$")
# A POSIX account name, as the storage host's agent accepts it.
_ACCOUNT_NAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


class TargetBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # Where the target is -- a site, room or building (27.3).
    location: Optional[str] = Field(default=None, max_length=255)
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


def _apply_target(target: models.BackupTarget, body: TargetBody, storage_id) -> None:
    target.name = body.name.strip()
    target.location = (body.location or "").strip() or None
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


def _target_or_404(db: Session, target_id: str) -> models.BackupTarget:
    return targets.target_or_404(db, target_id)


@router.get("/backups/targets")
def list_targets(db: Session = Depends(get_tenant_db)) -> List[Dict[str, Any]]:
    return targets.brief(db)


@router.post("/backups/targets")
def create_target(
    body: TargetBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    first = jobs.default_target(db) is None
    if not first:  # a second target is Enterprise (27.3)
        targets.engine_or_402()
    storage_id = _validate_target(db, body)
    targets.refuse_clash(db, body)
    target = models.BackupTarget(created_at=jobs.now(), created_by=current_user.userid)
    _apply_target(target, body, storage_id)
    target.is_default = first
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
def update_target(
    target_id: str,
    body: TargetBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    target = _target_or_404(db, target_id)
    storage_id = _validate_target(db, body)
    targets.refuse_clash(db, body, own_id=target.id)
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
def delete_target(
    target_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    target = _target_or_404(db, target_id)
    used = targets.in_use(db, target)
    if used["hosts"]:
        raise HTTPException(
            status_code=409,
            detail=_("Remove the hosts' backup policies before the target"),
        )
    if used["tag_policies"]:
        raise HTTPException(
            status_code=409,
            detail=_("A tag policy sends its hosts to this target; change it first"),
        )
    if target.is_default and len(jobs.targets(db)) > 1:
        raise HTTPException(
            status_code=409,
            detail=_("Make another target the default before deleting this one"),
        )
    if targets.copies_into(db, target):
        raise HTTPException(
            status_code=409,
            detail=_(
                "Another target copies off-site to this one; stop its off-site "
                "copy first"
            ),
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


@router.put("/backups/targets/{target_id}/default")
def set_default_target(
    target_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Where new host policies go.  Enterprise while there are several: a
    lapse must not let hosts be spread by switching the default."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    target = _target_or_404(db, target_id)
    if len(jobs.targets(db)) > 1:
        targets.engine_or_402()
    targets.make_default(db, target)
    _audit(
        db,
        current_user,
        EntityType.SETTING,
        target.id,
        target.name,
        "Backup target made the default",
        {},
    )
    db.commit()
    return views.target_dict(target, db)


class ReplicaBody(BaseModel):
    replica_target_id: Optional[str] = Field(default=None, max_length=64)


@router.put("/backups/targets/{target_id}/replica")
def set_replica_target(
    target_id: str,
    body: ReplicaBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Copy every repository on this target off-site to another target, or
    stop (Enterprise).  Stopping leaves the copies where they are."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    target = _target_or_404(db, target_id)
    replica = targets.set_replica(db, target, body.replica_target_id)
    for policy in (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.target_id == target.id)
        .all()
    ):
        policy.config_version += 1  # the storage host learns where to copy
    _audit(
        db,
        current_user,
        EntityType.SETTING,
        target.id,
        target.name,
        (
            "Backup target off-site copy set"
            if replica
            else "Backup target off-site copy stopped"
        ),
        {"replica_target": replica.name if replica else None},
    )
    backup_tick.configure_now(db)
    db.commit()
    return views.target_dict(target, db)


@router.post("/backups/moves/{move_id}/cancel")
def cancel_move(
    move_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Stop a host's move to another target before it switches: the host
    stays on its target, backing up as before.  Any edition."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    row = moves.move_or_404(db, move_id)
    if row.status not in moves.replicas.MOVING:
        raise HTTPException(
            status_code=409, detail=_("This move is no longer under way")
        )
    policy = db.get(models.BackupPolicy, row.policy_id)
    host = db.get(models.Host, policy.host_id) if policy else None
    moves.cancel(db, row)
    _audit(
        db,
        current_user,
        EntityType.HOST,
        host.id if host else None,
        host.fqdn if host else None,
        "Backup move canceled",
        {"move_id": str(row.id)},
    )
    backup_tick.configure_now(db)
    db.commit()
    return {"canceled": True}


def _move_host(db: Session, row: models.BackupMove) -> Optional[models.Host]:
    policy = db.get(models.BackupPolicy, row.policy_id)
    return db.get(models.Host, policy.host_id) if policy else None


@router.post("/backups/moves/{move_id}/remove-old")
def remove_old_repository(
    move_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Remove a moved host's old repository now rather than at its keep
    date (never while a seal of it still runs).  Any edition."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    row = moves.move_or_404(db, move_id)
    moves.remove_now(db, row, jobs.now())
    host = _move_host(db, row)
    _audit(
        db, current_user, EntityType.HOST, host.id if host else None,
        host.fqdn if host else None, "Backup move: old repository removal requested",
        {"move_id": str(row.id)},
    )  # fmt: skip
    db.commit()
    return {"status": row.status}


@router.post("/backups/moves/{move_id}/keep")
def keep_old_repository(
    move_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Keep a moved host's old repository until someone removes it.  Any
    edition."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    row = moves.move_or_404(db, move_id)
    moves.keep(row)
    host = _move_host(db, row)
    _audit(
        db, current_user, EntityType.HOST, host.id if host else None,
        host.fqdn if host else None, "Backup move: old repository kept",
        {"move_id": str(row.id)},
    )  # fmt: skip
    db.commit()
    return {"status": row.status}
