# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Short-lived tombstones for hosts deleted via the child-host cascade path.

The problem this guards against: when an operator deletes a child host
from the WebUI, the server cascade-deletes the linked ``Host`` row at
the same time it dispatches the destroy plan to the parent.  In the
seconds between "cascade deletes the Host row" and "agent inside the
doomed VM is actually killed by virsh destroy", the agent inside the
VM can call ``POST /host/register`` one last time — recreating the
Host row in ``approval_status=pending`` with no parent linkage.  The
VM then dies, the new row never picks up another connection, and the
ghost row sits in the Hosts list forever (heartbeat reaper skips
pending rows by design).

A short-lived in-memory tombstone keyed by (fqdn, ipv4) closes the
race: the register endpoint consults this module and returns success
without creating a row when a recent deletion matches.  The agent
doesn't care about the response — it's about to be destroyed.

Why in-memory and not in the DB:
  * The window is short (default 5 minutes) and the volume is tiny
    (one entry per child-host delete) — a DB table would add a
    write+read on every register call for no benefit.
  * The data is intentionally lost on server restart.  A restart
    is itself a long-enough gap that any in-flight register storms
    have already drained or expired.
  * No cross-instance coordination is needed: the cascade-delete and
    the subsequent /host/register both land on the same server
    process (there's no load-balanced multi-instance deployment
    pattern for the sysmanage backend today).

Public API:
    ``record_recent_child_host_deletion(fqdn, ipv4)``
    ``is_recent_child_host_deletion(fqdn, ipv4)``

Both prune expired entries on call to keep the dict bounded; the
overall structure stays O(N) in the number of currently-live
tombstones, which is bounded by the number of child-host deletes in
the last TTL_SECONDS window.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Five minutes is comfortably longer than the worst-case observed gap
# between Host row cascade-delete and VM destroy completion (sub-second
# in the common case, up to ~30s if the agent inside the VM is mid-
# request when virsh destroy fires).  Picked round and short — long
# enough to win the race, short enough that a legitimate re-enrollment
# after a stale-name cleanup isn't blocked for an annoying duration.
TTL_SECONDS = 300

_LOCK = threading.Lock()
# key: (fqdn_lower, ipv4_or_empty)  value: monotonic timestamp recorded
_TOMBSTONES: dict[tuple[str, str], float] = {}


def _key(fqdn: str, ipv4: Optional[str]) -> tuple[str, str]:
    return (fqdn.lower(), (ipv4 or "").strip())


def _prune_locked(now: float) -> None:
    """Drop expired tombstones.  Caller must hold ``_LOCK``."""
    cutoff = now - TTL_SECONDS
    stale = [k for k, recorded in _TOMBSTONES.items() if recorded < cutoff]
    for k in stale:
        del _TOMBSTONES[k]


def record_recent_child_host_deletion(fqdn: str, ipv4: Optional[str]) -> None:
    """Record that ``(fqdn, ipv4)`` was just cascade-deleted by a
    child-host delete.  Subsequent registrations matching the same key
    within ``TTL_SECONDS`` are short-circuited."""
    if not fqdn:
        return
    now = time.monotonic()
    with _LOCK:
        _prune_locked(now)
        _TOMBSTONES[_key(fqdn, ipv4)] = now
        logger.info(
            "Recorded child-host deletion tombstone for fqdn=%s ipv4=%s "
            "(TTL=%ds, %d live)",
            fqdn,
            ipv4 or "<none>",
            TTL_SECONDS,
            len(_TOMBSTONES),
        )


def is_recent_child_host_deletion(fqdn: str, ipv4: Optional[str]) -> bool:
    """Return True iff ``(fqdn, ipv4)`` matches a tombstone recorded
    within the last ``TTL_SECONDS`` seconds.

    Match precedence:
      1. exact ``(fqdn, ipv4)`` match — used when the doomed agent
         re-registers with the same IP its VM had.
      2. ``fqdn``-only match (any ipv4) — fallback for the (rare) case
         the agent's IP changed between cascade-delete and the final
         register call.
    """
    if not fqdn:
        return False
    now = time.monotonic()
    with _LOCK:
        _prune_locked(now)
        if _key(fqdn, ipv4) in _TOMBSTONES:
            return True
        fqdn_lower = fqdn.lower()
        for fkey in _TOMBSTONES:
            if fkey[0] == fqdn_lower:
                return True
    return False


def _reset_for_tests() -> None:
    """Wipe the in-memory store.  Tests only — not part of the public
    runtime contract."""
    with _LOCK:
        _TOMBSTONES.clear()
