# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Which kernels a host has booted, and which are proven (ROADMAP 27.8).

Every heartbeat carries the host's boot time and running kernel.  The first
heartbeat of a boot opens a ``host_kernel_boot`` row; each later one moves
``last_seen_at``.  Once a boot has been up and checking in for
``PROVEN_AFTER`` its kernel is PROVEN: it booted, the agent came up, and it
stayed up.  Installed is never known good.

``protected`` turns that into the kernels a cleanup must keep (Bryan,
2026-11-27: "we need to get at least one clean reboot on the new kernel
before we close the escape hatch on the one we last successfully booted
from" -- Livepatch may be what kept the old one safe):

* the running kernel and the newest installed one (the next boot's);
* the newest proven kernel other than the running one -- the fallback, so
  after a reboot into a new kernel the last good one stays until the new
  one has proven itself, and stays afterwards as the way back;
* at least ``MIN_KERNELS`` in all, newest first.

No cleanup runs while the running kernel itself is not proven (the host
just booted it): there is no known-good kernel to fall back on yet.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.persistence import models

PROVEN_AFTER = timedelta(minutes=15)
# psutil's boot time can drift by a second or two between reads on some
# systems; two reports this close are the same boot.
SAME_BOOT = timedelta(minutes=2)
MIN_KERNELS = 2
KEEP_BOOTS = 50
_TOKEN = re.compile(r"\d+|[^\d]+")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def version_key(release: str) -> Tuple:
    """Sort key: the release's numbers, up to its flavor (as the agent's
    ``kernel_state.version_key``)."""
    parts: List[int] = []
    for token in _TOKEN.findall(release or ""):
        if token.isdigit():
            parts.append(int(token))
        elif parts and any(c.isalpha() for c in token):
            break
    return tuple(parts)


def note(
    db: Session, host, release: Optional[str], now: Optional[datetime] = None
) -> None:
    """Record this heartbeat's boot (``host.boot_time`` already updated)."""
    if not release or not host.boot_time:
        return
    now = now or _now()
    row = _this_boot(history(db, host.id), host.boot_time)
    if row is None:
        row = models.HostKernelBoot(
            host_id=host.id, boot_time=host.boot_time, kernel_release=str(release)[:128],
            first_seen_at=now, last_seen_at=now,
        )  # fmt: skip
        db.add(row)
        _prune(db, host.id)
    row.last_seen_at = now
    if row.proven_at is None and now - row.boot_time >= PROVEN_AFTER:
        row.proven_at = now


def _prune(db: Session, host_id) -> None:
    boots = models.HostKernelBoot
    old = (
        db.query(boots.id).filter(boots.host_id == host_id)
        .order_by(boots.boot_time.desc()).offset(KEEP_BOOTS).all()
    )  # fmt: skip
    if old:
        db.query(boots).filter(boots.id.in_([r.id for r in old])).delete(
            synchronize_session=False
        )


def history(db: Session, host_id) -> List[models.HostKernelBoot]:
    boots = models.HostKernelBoot
    return (
        db.query(boots).filter(boots.host_id == host_id)
        .order_by(boots.boot_time.desc()).all()
    )  # fmt: skip


def _this_boot(boots, boot_time):
    if boot_time is None:
        return None
    return next((b for b in boots if abs(b.boot_time - boot_time) <= SAME_BOOT), None)


def running_kernel(db: Session, host) -> Optional[str]:
    """The kernel the current boot runs, from the boot history."""
    row = _this_boot(history(db, host.id), host.boot_time)
    return row.kernel_release if row else None


def protected(
    db: Session, host, installed: Iterable[str]
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """``(refusal, [{release, reason}])``: why no cleanup may run now (or
    None), and the kernels it must keep, with the reason for each."""
    boots = history(db, host.id)
    current = _this_boot(boots, host.boot_time)
    if current is None:
        return "unknown_running_kernel", []
    if current.proven_at is None:
        return "running_kernel_not_proven", []
    installed = sorted(set(installed or []), key=version_key, reverse=True)
    keep: Dict[str, str] = {current.kernel_release: "running"}
    if installed:
        keep.setdefault(installed[0], "newest")
    proven = sorted({b.kernel_release for b in boots if b.proven_at is not None
                     and b.kernel_release != current.kernel_release},
                    key=version_key, reverse=True)  # fmt: skip
    if proven:
        keep.setdefault(proven[0], "last_proven")
    for release in installed:
        if len(keep) >= MIN_KERNELS:
            break
        keep.setdefault(release, "minimum")
    return None, [{"release": r, "reason": why} for r, why in keep.items()]
