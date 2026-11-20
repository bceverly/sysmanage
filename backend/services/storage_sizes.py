# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A storage device's sizes from whatever shape its agent reports.

Every platform's agent has its own keys, and until 2026-11-20 the server read
only some of them, so no host's disk list carried a size:

* BSD and macOS: ``capacity_bytes`` / ``used_bytes`` / ``available_bytes``
  and ``file_system``;
* Windows: ``size`` and ``free_space`` in bytes, and ``file_system``;
* Linux up to agent 3.14.0.x: ``size`` only, as ``lsblk`` prints it
  ("8.7G"), and ``file_system``; later agents add the byte keys above.

The server read ``filesystem`` (no agent sends it) and ``total_size``.  This
reads every shape; a size it cannot read is None, never a guess.
"""

import re
from typing import Any, Dict, Optional

# lsblk's human sizes are binary (K = 1024).
_UNITS = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
_HUMAN = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*([BKMGTP])?(?:i?B)?\s*$", re.IGNORECASE)


def _bytes(value: Any) -> Optional[int]:
    """Whole bytes from an int, a digit string or a human size ("8.7G")."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 else None
    if not isinstance(value, str):
        return None
    match = _HUMAN.match(value)
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    unit = (match.group(2) or "B").upper()
    return int(number * _UNITS[unit])


def _first(device: Dict[str, Any], *keys: str) -> Optional[int]:
    for key in keys:
        found = _bytes(device.get(key))
        if found is not None:
            return found
    return None


def _filesystem(device: Dict[str, Any]) -> Optional[str]:
    for key in ("filesystem", "file_system", "fstype"):
        value = device.get(key)
        if (
            isinstance(value, str)
            and value.strip()
            and value.strip()
            not in (
                "N/A",
                "unknown",
            )
        ):
            return value.strip()[:100]
    return None


def device_sizes(device: Dict[str, Any]) -> Dict[str, Any]:
    """``{"total", "used", "available", "filesystem"}`` for one device; a
    size it cannot read is None."""
    total = _first(device, "capacity_bytes", "total_size", "size")
    available = _first(device, "available_bytes", "available_size", "free_space")
    used = _first(device, "used_bytes", "used_size")
    if used is None and total is not None and available is not None:
        used = max(0, total - available)  # Windows sends size and free space
    return {
        "total": total,
        "used": used,
        "available": available,
        "filesystem": _filesystem(device),
    }
