"""Block-device enumeration + ISO probing for air-gap import.

An Air-Gap Repository server runs ON the box that physically holds the
collector media, so it can enumerate local block devices with ``lsblk``
and decide whether the operator-selected drive currently holds an
importable ISO.

Two deliberately-shallow heuristics, because the *real* trust decision
happens later during ingest (the signed manifest is verified against
the trusted-collector keyring — a wrong/forged disc simply FAILs):

  * enumeration excludes the OS disk (the one whose tree contains the
    ``/`` mountpoint) so the operator can't pick the system drive.
  * "is this importable media?" = the device carries an ``iso9660`` or
    ``udf`` filesystem.  That's enough to enable the Import button; the
    cryptographic check is the ingest path's job.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess  # nosec B404 - fixed lsblk argv, no shell
from typing import List, Optional

from backend.i18n import _

logger = logging.getLogger(__name__)

_ISO_FSTYPES = {"iso9660", "udf"}


def _as_bool(value) -> bool:
    """lsblk reports rm/ro as JSON booleans on new versions and "0"/"1"
    strings on old ones — coerce both (``bool("0")`` is True, so a naive
    cast is wrong)."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true")


def _run_lsblk() -> Optional[dict]:
    lsblk = shutil.which("lsblk")
    if not lsblk:
        return None
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, no shell, trusted bin
            [
                lsblk,
                "-J",
                "-b",
                "-o",
                "NAME,PATH,TYPE,SIZE,RM,RO,MOUNTPOINT,LABEL,FSTYPE",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("lsblk failed: %s", exc)
        return None
    if proc.returncode != 0:
        logger.warning("lsblk exited %s: %s", proc.returncode, proc.stderr)
        return None
    try:
        return json.loads(proc.stdout)
    except (ValueError, TypeError):
        return None


def _tree_has_root(dev: dict) -> bool:
    """True if this device or any descendant is mounted at ``/``."""
    if dev.get("mountpoint") == "/":
        return True
    for child in dev.get("children") or []:
        if _tree_has_root(child):
            return True
    return False


def list_block_devices() -> List[dict]:
    """Enumerate candidate import devices (OS disk excluded).

    Returns a list of dicts: ``name, path, type, size_bytes, removable,
    label, fstype, mountpoint, is_optical``.  Empty when lsblk is
    unavailable (e.g. non-Linux) — the UI then shows "no devices".
    """
    data = _run_lsblk()
    out: List[dict] = []
    if not data:
        return out
    for dev in data.get("blockdevices", []) or []:
        if _tree_has_root(dev):
            continue  # never offer the OS disk
        size = dev.get("size")
        size_bytes = int(size) if str(size).isdigit() else None
        path = dev.get("path") or ("/dev/" + (dev.get("name") or ""))
        out.append(
            {
                "name": dev.get("name"),
                "path": path,
                "type": dev.get("type"),
                "size_bytes": size_bytes,
                "removable": _as_bool(dev.get("rm")),
                "label": dev.get("label"),
                "fstype": dev.get("fstype"),
                "mountpoint": dev.get("mountpoint"),
                "is_optical": dev.get("type") == "rom",
            }
        )
    return out


def default_device(devices: Optional[List[dict]] = None) -> Optional[str]:
    """Lowest-numbered optical drive's path (e.g. ``/dev/sr0``), else None.

    Opticals sort by name so ``sr0`` wins over ``sr1``; falls back to the
    first removable device, then None.
    """
    devs = devices if devices is not None else list_block_devices()
    opticals = sorted(
        (d for d in devs if d.get("is_optical")), key=lambda d: d.get("name") or ""
    )
    if opticals:
        return opticals[0]["path"]
    removable = sorted(
        (d for d in devs if d.get("removable")), key=lambda d: d.get("name") or ""
    )
    if removable:
        return removable[0]["path"]
    return None


def probe_device(path: str) -> dict:
    """Decide whether ``path`` currently holds importable ISO media.

    ``ready`` is True when the device carries an iso9660/udf filesystem.
    This intentionally does NOT verify the collector signature — that's
    enforced during ingest, where a non-collector disc FAILs at manifest
    verification.  Returns ``{device, ready, reason, label, fstype}``.
    """
    if not path:
        return {"device": path, "ready": False, "reason": _("no device selected")}
    match = next((d for d in list_block_devices() if d.get("path") == path), None)
    if match is None:
        return {
            "device": path,
            "ready": False,
            "reason": _("device not found (was it removed?)"),
        }
    fstype = (match.get("fstype") or "").lower()
    if fstype in _ISO_FSTYPES:
        return {
            "device": path,
            "ready": True,
            "reason": _("ISO filesystem present"),
            "label": match.get("label"),
            "fstype": fstype,
        }
    if match.get("is_optical") and not fstype:
        return {
            "device": path,
            "ready": False,
            "reason": _("drive present but no readable disc inserted"),
        }
    return {
        "device": path,
        "ready": False,
        "reason": _("no ISO filesystem on device (fstype=%s)") % (fstype or "none"),
        "fstype": fstype or None,
    }
