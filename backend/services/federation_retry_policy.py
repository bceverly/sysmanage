# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Phase 12.10 hardening: retry policy helpers shared by the three
federation queue surfaces (sync_queue / policy_assignments /
dispatched_commands).

The wire-protocol workers (Slice 2 sync drain + Slice 3 policy +
command push) mark entries failed on transport / 4xx / 5xx, but
before this module they retried every entry on every tick — a down
coordinator got hammered, a bad payload chewed CPU in a loop.

This module provides:

  * ``compute_backoff(attempts) -> seconds``  — exponential with
    bounded jitter, capped at ``BACKOFF_CAP_SECONDS``.  Pure
    function; deterministic in tests when ``random.Random`` is
    seeded.
  * ``MAX_ATTEMPTS``  — universal dead-letter threshold.  After
    this many tries, the queue surfaces transition out of the
    worker's view (sync_queue: status='dead' marker on the row;
    assignments: push_status='dead'; commands: never auto-dead-
    lettered — terminal FSM states for commands are operator-
    driven).
  * ``is_ready_for_retry(last_attempt_at, attempts, now) -> bool``
    — convenience wrapper the workers' list queries use to skip
    entries still in their backoff window.

Design notes
============
Backoff uses the standard ``base * 2^attempts + jitter`` shape that
AWS / Kubernetes / Tenacity all converge on.  The constants here
target a "down coordinator for hours, recover gracefully" failure
mode rather than "rapid retry of a transient blip" — the FIRST
retry is delayed at all (no immediate re-fire) because in the
federation wire protocol every failure costs the receiving side a
DB write + audit-log entry.
"""

import random
from datetime import datetime, timedelta
from typing import Optional

# Backoff math.
#
# Schedule (no jitter) — attempt N means "N-th failure has been
# recorded, what's the wait before attempt N+1?":
#
#     attempt=1  → 10s
#     attempt=2  → 20s
#     attempt=3  → 40s
#     attempt=4  → 80s
#     attempt=5  → 160s
#     attempt=6  → 320s
#     attempt=7  → 640s
#     attempt=8  → 1200s (capped)
#     attempt=9+ → 1200s
#
# 20% jitter is added on top to break herd patterns when many
# entries fail at once (e.g., coordinator restart).
BACKOFF_BASE_SECONDS = 10
BACKOFF_CAP_SECONDS = 1200  # 20 min
BACKOFF_JITTER_FRACTION = 0.20

# Universal dead-letter threshold.  After this many consecutive
# failures we stop retrying and leave the row for operator triage.
# Aligns with the 8-attempt point in the schedule above (~37 min
# of cumulative wait, which is enough that a transient outage
# would have recovered).
MAX_ATTEMPTS = 8


def compute_backoff(attempts: int, rng: Optional[random.Random] = None) -> float:
    """Return the wait (seconds) before the next retry given that
    ``attempts`` failures have already been recorded.

    ``attempts <= 0`` returns 0 — a row that has never failed should
    fire immediately on the next tick.  ``attempts >= MAX_ATTEMPTS``
    still returns the capped backoff; the caller is responsible for
    transitioning to dead-letter rather than retrying.
    """
    if attempts <= 0:
        return 0.0
    raw = BACKOFF_BASE_SECONDS * (2 ** (attempts - 1))
    capped = min(raw, BACKOFF_CAP_SECONDS)
    # Jitter is +/- BACKOFF_JITTER_FRACTION of the capped value.
    rng = rng or random
    jitter_span = capped * BACKOFF_JITTER_FRACTION
    jitter = rng.uniform(-jitter_span, jitter_span)
    return max(0.0, capped + jitter)


def is_ready_for_retry(
    last_attempt_at: Optional[datetime],
    attempts: int,
    now: datetime,
    rng: Optional[random.Random] = None,
) -> bool:
    """Worker convenience: is this entry past its backoff window?

    ``last_attempt_at is None`` (never attempted) → True (fire now).
    ``attempts <= 0`` → True (no failures, backoff doesn't apply).
    Otherwise compare ``last_attempt_at + compute_backoff(attempts) <= now``.

    Jitter is recomputed every call, which is fine — backoff is
    advisory; the goal is to space retries, not to commit to a
    specific timestamp.
    """
    if last_attempt_at is None or attempts <= 0:
        return True
    wait = compute_backoff(attempts, rng=rng)
    return last_attempt_at + timedelta(seconds=wait) <= now


def is_dead_lettered(attempts: int) -> bool:
    """``attempts >= MAX_ATTEMPTS`` — caller should transition the
    row out of the worker's view rather than retry."""
    return attempts >= MAX_ATTEMPTS
