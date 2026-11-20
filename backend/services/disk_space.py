# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A host's fullest local filesystem, and when it is nearly full.

Production, 2026-11-20: functionallyparanoid.com's root sat at 96-99 % for
days.  The server had the number -- the agent's ``host.disk_used_percent_max``
host metric -- but kept it only as graph history (and only with the
observability engine), so nothing said a word until an update of 37
packages ran out of room part-way and left dpkg half-configured.

Two sources, whichever came last wins:

* the host's disk list (``storage_device``): which mount, how full, how much
  is left -- from agents that report sizes (BSD, macOS, Windows, and Linux
  from agent 3.15);
* the ``host_metrics`` message: the fullest local disk's percentage only
  (every agent since 21.5), so older Linux agents are warned on too.

It is kept on the host whatever the license: a full disk is a safety
matter, not a feature.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services.storage_sizes import device_sizes

# At this much used, a host's disk is "nearly full".
WARN_PERCENT = 90.0
# How many nearly full hosts the dashboard names (the rest are counted).
NAMED = 20
METRIC_KEY = "host.disk_used_percent_max"

# Filesystems that are full by design or cannot be filled by the host.
_NOT_FILLABLE = {
    "squashfs",
    "iso9660",
    "udf",
    "tmpfs",
    "devtmpfs",
    "overlay",
    "efivarfs",
    "proc",
    "sysfs",
    "cgroup",
    "cgroup2",
    "nfs",
    "nfs4",
    "cifs",
    "smbfs",
    "fuse.sshfs",
}
_NOT_FILLABLE_MOUNTS = ("/snap/", "/proc", "/sys", "/dev", "/run")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fillable(device: Dict[str, Any], sizes: Dict[str, Any]) -> bool:
    mount = device.get("mount_point") or ""
    if not isinstance(mount, str) or not mount.startswith(("/", "C:", "c:")):
        return False  # Windows drive letters count; unmounted devices do not
    if mount.startswith(_NOT_FILLABLE_MOUNTS) or mount == "/boot/efi":
        return False
    if (sizes["filesystem"] or "").lower() in _NOT_FILLABLE:
        return False
    if str(device.get("type") or device.get("device_type") or "") in ("loop", "rom"):
        return False
    return bool(sizes["total"]) and sizes["available"] is not None


def fullest(devices: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """``{"mount", "percent", "available"}`` of the fullest filesystem the
    host could fill, or None when no device reports its free space."""
    best = None
    for device in devices:
        if not isinstance(device, dict) or device.get("error"):
            continue
        sizes = device_sizes(device)
        if not _fillable(device, sizes):
            continue
        used = sizes["total"] - sizes["available"]
        percent = round(100.0 * used / sizes["total"], 1)
        if best is None or percent > best["percent"]:
            best = {
                "mount": str(device.get("mount_point"))[:255],
                "percent": percent,
                "available": sizes["available"],
            }
    return best


def record_from_storage(session: Session, host: Any, devices: List[Any]) -> bool:
    """The disk list arrived: keep its fullest filesystem.  False when no
    device carries its free space (an older Linux agent) -- the host
    metrics then speak for it."""
    found = fullest(devices or [])
    if host is None or found is None:
        return False
    host.disk_used_percent = found["percent"]
    host.disk_fullest_mount = found["mount"]
    host.disk_available_bytes = found["available"]
    host.disk_checked_at = _now()
    return True


def record_from_metrics(session: Session, host_id: Any, payload: Any) -> bool:
    """The host metrics arrived: keep the fullest disk's percentage.  The
    mount and free space are left as the disk list last said, unless that
    is older than this and disagrees -- then they are cleared, never stale."""
    metrics = (payload or {}).get("metrics") if isinstance(payload, dict) else None
    value = (metrics or {}).get(METRIC_KEY)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    host = session.get(models.Host, host_id) if host_id is not None else None
    if host is None:
        return False
    percent = round(float(value), 1)
    if host.disk_used_percent is None or abs(host.disk_used_percent - percent) > 1.0:
        host.disk_fullest_mount = None
        host.disk_available_bytes = None
    host.disk_used_percent = percent
    host.disk_checked_at = _now()
    return True


def _number(value: Any) -> Optional[float]:
    """A stored number, or None (unknown) for anything else."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def nearly_full(host: Any) -> bool:
    percent = _number(getattr(host, "disk_used_percent", None))
    return percent is not None and percent >= WARN_PERCENT


def view(host: Any) -> Dict[str, Any]:
    """What the host's page and the dashboard show."""
    checked = getattr(host, "disk_checked_at", None)
    mount = getattr(host, "disk_fullest_mount", None)
    available = _number(getattr(host, "disk_available_bytes", None))
    return {
        "disk_used_percent": _number(getattr(host, "disk_used_percent", None)),
        "disk_fullest_mount": mount if isinstance(mount, str) else None,
        "disk_available_bytes": int(available) if available is not None else None,
        "disk_checked_at": (
            checked.isoformat() if isinstance(checked, datetime) else None
        ),
        "disk_nearly_full": nearly_full(host),
    }


def summary(session: Session) -> Dict[str, Any]:
    """Approved hosts with a nearly full disk: counted, the fullest named."""
    host = models.Host
    flagged = (host.approval_status == "approved") & (
        host.disk_used_percent >= WARN_PERCENT
    )
    count = session.query(func.count(host.id)).filter(flagged).scalar()
    rows = (
        session.query(host)
        .filter(flagged)
        .order_by(host.disk_used_percent.desc(), host.fqdn)
        .limit(NAMED)
        .all()
    )
    return {
        "disk_nearly_full": int(count or 0),
        "disk_hosts": [
            {"id": str(row.id), "fqdn": row.fqdn, **view(row)} for row in rows
        ],
    }
