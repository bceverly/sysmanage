"""
Unit tests for Phase 12.10 hardening: the retry policy helpers.

The helpers in ``backend.services.federation_retry_policy`` are
pure functions; no DB.  Tests pin the backoff math + the dead-
letter threshold so a future refactor doesn't accidentally make
retries fire too aggressively against a down coordinator.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring

import random
from datetime import datetime, timedelta, timezone

from backend.services import federation_retry_policy as rp

# ---------------------------------------------------------------------------
# compute_backoff
# ---------------------------------------------------------------------------


class TestComputeBackoff:
    def _rng(self):
        """Seeded RNG so jitter is reproducible in tests."""
        return random.Random(42)

    def test_zero_attempts_returns_zero(self):
        """Never-failed entries fire immediately on next tick."""
        assert rp.compute_backoff(0, rng=self._rng()) == 0.0

    def test_negative_attempts_returns_zero(self):
        # Defensive: callers shouldn't pass negatives, but guard
        # against ``None or 0`` arithmetic landing here.
        assert rp.compute_backoff(-1, rng=self._rng()) == 0.0

    def test_first_failure_waits_about_base_seconds(self):
        # attempt=1 → BASE seconds, +/- 20% jitter.
        wait = rp.compute_backoff(1, rng=self._rng())
        assert rp.BACKOFF_BASE_SECONDS * 0.80 <= wait <= rp.BACKOFF_BASE_SECONDS * 1.20

    def test_second_failure_doubles_first(self):
        # attempt=2 → roughly 2 * BASE.
        wait = rp.compute_backoff(2, rng=self._rng())
        assert (
            (2 * rp.BACKOFF_BASE_SECONDS) * 0.80
            <= wait
            <= (2 * rp.BACKOFF_BASE_SECONDS) * 1.20
        )

    def test_caps_at_max(self):
        # Very high attempt count must not exceed BACKOFF_CAP_SECONDS.
        for n in (10, 20, 100):
            wait = rp.compute_backoff(n, rng=self._rng())
            assert wait <= rp.BACKOFF_CAP_SECONDS * 1.20  # +jitter

    def test_jitter_is_within_fraction(self):
        # Sample 100 calls at attempt=4 and confirm none exceed the
        # +/- jitter envelope around the deterministic value.
        determ = rp.BACKOFF_BASE_SECONDS * (2**3)  # 80s
        for seed in range(100):
            wait = rp.compute_backoff(4, rng=random.Random(seed))
            assert (
                determ * (1 - rp.BACKOFF_JITTER_FRACTION)
                <= wait
                <= determ * (1 + rp.BACKOFF_JITTER_FRACTION)
            )


# ---------------------------------------------------------------------------
# is_ready_for_retry
# ---------------------------------------------------------------------------


class TestIsReadyForRetry:
    def _now(self):
        return datetime(2026, 5, 21, 12, 0, 0)

    def test_never_attempted_is_ready(self):
        assert rp.is_ready_for_retry(None, 0, self._now()) is True

    def test_zero_attempts_is_ready_regardless_of_timestamp(self):
        # A row with attempts=0 has no backoff to honour.
        assert rp.is_ready_for_retry(self._now(), 0, self._now()) is True

    def test_fresh_failure_is_not_ready(self):
        # Just failed → must wait at least ~BASE seconds.
        now = self._now()
        assert rp.is_ready_for_retry(now - timedelta(seconds=1), 1, now) is False

    def test_after_backoff_window_is_ready(self):
        # Well past the cap → ready.
        now = self._now()
        long_ago = now - timedelta(seconds=rp.BACKOFF_CAP_SECONDS * 2)
        assert rp.is_ready_for_retry(long_ago, 5, now) is True

    def test_at_boundary_is_ready(self):
        # last_attempt + computed_backoff <= now (the boundary).
        now = self._now()
        # Use a seeded RNG so jitter doesn't flap the boundary.
        rng = random.Random(0)
        wait = rp.compute_backoff(3, rng=random.Random(0))
        last = now - timedelta(seconds=wait + 0.001)
        assert rp.is_ready_for_retry(last, 3, now, rng=rng) is True


# ---------------------------------------------------------------------------
# is_dead_lettered
# ---------------------------------------------------------------------------


class TestIsDeadLettered:
    def test_below_threshold_not_dead(self):
        for n in range(rp.MAX_ATTEMPTS):
            assert rp.is_dead_lettered(n) is False

    def test_at_threshold_is_dead(self):
        # exactly MAX_ATTEMPTS → dead-letter (we count THIS attempt
        # as the one that exceeds the limit).
        assert rp.is_dead_lettered(rp.MAX_ATTEMPTS) is True

    def test_above_threshold_is_dead(self):
        for n in (rp.MAX_ATTEMPTS + 1, rp.MAX_ATTEMPTS + 100):
            assert rp.is_dead_lettered(n) is True

    def test_max_attempts_is_a_constant(self):
        # Lock the value so a future refactor that bumps it has to
        # come through this test and acknowledge the change.
        assert rp.MAX_ATTEMPTS == 8
