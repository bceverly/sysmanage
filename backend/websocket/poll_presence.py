# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Which hosts are reachable over the HTTP poll transport right now.

The outbound processor delivers over WebSocket and marks a message FAILED when
the host has no socket.  A host on the HTTP fallback never has one, so without
this every command to it was failed within seconds -- before its next poll
could collect it -- and a polling agent received nothing at all (found
2026-09-29: four BSD/macOS test hosts, every command "Failed to send message
to agent").  The processor asks here first and leaves the message PENDING for
the poll to pick up.

In-process on purpose: it only has to outlive one poll interval (5s, at most
25s with a long poll), and a server restart makes the agent reconnect anyway.
Under a multi-instance deployment (Phase 31, HA/DR) this must move to shared state.
"""

import threading
import time
from typing import Dict

# Longer than the slowest poll cadence (25s long poll + the 30s error backoff)
# so a single slow or failed poll does not flip the host back to "unreachable".
POLL_PRESENCE_SECONDS = 60.0

_lock = threading.Lock()
_last_poll: Dict[str, float] = {}


def touch(host_id) -> None:
    """Record that ``host_id`` just completed an authenticated poll."""
    with _lock:
        _last_poll[str(host_id)] = time.monotonic()


def recently_polled(host_id, now: float = None) -> bool:
    """Has ``host_id`` polled within ``POLL_PRESENCE_SECONDS``?"""
    with _lock:
        seen = _last_poll.get(str(host_id))
    if seen is None:
        return False
    return ((now if now is not None else time.monotonic()) - seen) < (
        POLL_PRESENCE_SECONDS
    )


def forget(host_id) -> None:
    """Drop a host (tests, or a host that was deleted)."""
    with _lock:
        _last_poll.pop(str(host_id), None)
