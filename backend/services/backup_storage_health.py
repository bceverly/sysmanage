# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Is the storage host itself fit to hold the backups? (ROADMAP 24.8)

Every repository lives on one machine.  A drive it reports failing, or a
filesystem under the storage path that is filling up, puts every host's
backups at risk, so the target says so -- worst first:

* ``storage_drive_failed`` / ``storage_drive_warning`` -- the storage host's
  drives, arrays or pools by hardware health (sensors and memory are left
  out: a hot CPU does not threaten the backups);
* ``storage_space_critical`` (95% used or more) / ``storage_space_low``
  (85%) -- the filesystem holding the storage path, from the host's disk
  inventory (the mount point that contains the path most specifically).

Read-only: it uses what the storage host already reports.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence import models

STORAGE_KINDS = ("drive", "array", "pool")
SPACE_LOW_PERCENT = 85
SPACE_CRITICAL_PERCENT = 95


def _drives(db: Session, host_id) -> Dict[str, List[str]]:
    rows = (
        db.query(models.HardwareComponent)
        .filter(
            models.HardwareComponent.host_id == host_id,
            models.HardwareComponent.kind.in_(STORAGE_KINDS),
            models.HardwareComponent.state.in_(("failed", "warning")),
        )
        .all()
    )
    out: Dict[str, List[str]] = {"failed": [], "warning": []}
    for row in rows:
        out[row.state].append(row.name or row.ident)
    return {state: sorted(names) for state, names in out.items()}


def _contains(mount: str, path: str) -> bool:
    return path == mount or path.startswith(mount.rstrip("/") + "/")


def _space(db: Session, host_id, path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    best = None
    for device in (
        db.query(models.StorageDevice)
        .filter(models.StorageDevice.host_id == host_id)
        .all()
    ):
        mount = device.mount_point
        if not mount or not device.total_size_bytes or not _contains(mount, path):
            continue
        if best is None or len(mount) > len(best.mount_point):
            best = device
    if best is None:
        return None
    total = best.total_size_bytes
    available = best.available_size_bytes
    if available is None and best.used_size_bytes is not None:
        available = max(0, total - best.used_size_bytes)
    if available is None:
        return None
    used_percent = round(100.0 * (total - available) / total, 1)
    return {
        "mount_point": best.mount_point,
        "total_bytes": total,
        "available_bytes": available,
        "used_percent": used_percent,
    }


def storage_health(
    db: Session, target: models.BackupTarget, storage: Optional[models.Host]
) -> Optional[Dict[str, Any]]:
    """The storage host's drives and the space under the storage path."""
    if storage is None:
        return None
    return {
        "drives": _drives(db, storage.id),
        "space": _space(db, storage.id, target.storage_path),
    }


def health_warnings(health: Optional[Dict[str, Any]]) -> List[str]:
    """Warning codes, worst first; the caller merges them into the target's."""
    if not health:
        return []
    found = []
    drives = health["drives"]
    if drives["failed"]:
        found.append("storage_drive_failed")
    space = health["space"]
    if space and space["used_percent"] >= SPACE_CRITICAL_PERCENT:
        found.append("storage_space_critical")
    if drives["warning"]:
        found.append("storage_drive_warning")
    if space and SPACE_LOW_PERCENT <= space["used_percent"] < SPACE_CRITICAL_PERCENT:
        found.append("storage_space_low")
    return found


# Errors: they count the target once on the dashboard's backups card.
HEALTH_PROBLEMS = ("storage_drive_failed", "storage_space_critical")
