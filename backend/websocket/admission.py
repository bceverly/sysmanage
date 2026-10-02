# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Reconnect admission control (Phase 22.2).

WHY
---
Each agent's SYSTEM_INFO (sent on every connect) costs a host upsert, an
audit record and possibly a config push.  After a server restart every agent
reconnects at once -- ten thousand of those in the same minute, each holding
a database connection while the rest wait for theirs.

HOW
---
A token bucket in front of the SYSTEM_INFO handler: ``rate`` registrations a
second, bursts up to ``burst``.  An agent over the rate is not refused -- a
refused WebSocket risks an agent reading it as "this network blocks
WebSockets" -- it is given the next free slot and its registration reply simply
comes that much later.  Slots are handed out in order, so the crowd is spread
evenly instead of retrying in waves.  The wait happens before the handler
opens its database session, so a waiting agent holds no connection.

Per server worker: with N workers the server admits N x ``rate``.  Configured
in ``security.agent_connection_limits`` (``admissions_per_second``,
``admission_burst``).
"""

import asyncio
import time

from backend.utils.verbosity_logger import get_logger

logger = get_logger(__name__)

DEFAULT_RATE = 100.0
DEFAULT_BURST = 200.0
MAX_WAIT_SECONDS = 600.0  # never hold a reply longer than this


class AdmissionGate:
    """Hands out registration slots at a steady rate."""

    def __init__(
        self,
        rate: float = DEFAULT_RATE,
        burst: float = DEFAULT_BURST,
        clock=time.monotonic,
    ):
        self._clock = clock
        self.configure(rate, burst)
        self._tokens = self.burst
        self._refilled_at = clock()
        self._next_slot = 0.0
        self.waited = 0  # registrations that had to wait (observability)

    def configure(self, rate: float, burst: float) -> None:
        self.rate = max(0.1, float(rate))
        self.burst = max(1.0, float(burst))

    def _refill(self, now: float) -> None:
        self._tokens = min(
            self.burst, self._tokens + (now - self._refilled_at) * self.rate
        )
        self._refilled_at = now

    def reserve(self) -> float:
        """Take a slot; return how long to wait for it (0 = go now).

        No await between the check and the update: on one event loop this is
        atomic without a lock."""
        now = self._clock()
        self._refill(now)
        if self._tokens >= 1.0 and self._next_slot <= now:
            self._tokens -= 1.0
            return 0.0
        slot = max(self._next_slot, now) + 1.0 / self.rate
        self._next_slot = slot
        self.waited += 1
        return min(slot - now, MAX_WAIT_SECONDS)

    async def wait_turn(self) -> float:
        """Wait for a slot; returns the seconds waited."""
        wait = self.reserve()
        if wait > 0:
            await asyncio.sleep(wait)
        return wait


def _limits() -> tuple:
    from backend.config import config  # pylint: disable=import-outside-toplevel

    raw = (config.get_config().get("security") or {}).get("agent_connection_limits")
    raw = raw if isinstance(raw, dict) else {}
    try:
        rate = float(raw.get("admissions_per_second", DEFAULT_RATE))
        burst = float(raw.get("admission_burst", DEFAULT_BURST))
    except (TypeError, ValueError):
        rate, burst = DEFAULT_RATE, DEFAULT_BURST
    return rate, burst


_gate = None


def gate() -> AdmissionGate:
    """This worker's gate, configured from sysmanage.yaml on first use."""
    global _gate  # pylint: disable=global-statement
    if _gate is None:
        _gate = AdmissionGate(*_limits())
    return _gate
