# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.3: air-gapped repositories on the default cron do not all
collect from the upstream mirrors at 03:00 sharp."""

import uuid
from datetime import datetime, timedelta, timezone

from backend.services import airgap_schedule_tick as tick

BASE = datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc)


class _Cron:
    def next_run_from_cron(self, _cron, _now):
        return BASE


def test_schedules_spread_over_the_window():
    runs = {
        tick.splayed_next_run(_Cron(), "0 3 * * *", uuid.uuid4(), BASE)
        for _ in range(50)
    }
    assert len(runs) > 40
    assert all(BASE <= r < BASE + timedelta(minutes=tick.SPLAY_MINUTES) for r in runs)


def test_a_schedules_time_is_stable():
    key = uuid.uuid4()
    assert tick.splayed_next_run(_Cron(), "c", key, BASE) == tick.splayed_next_run(
        _Cron(), "c", key, BASE
    )


def test_no_cron_occurrence_stays_none():
    class _Never:
        def next_run_from_cron(self, _cron, _now):
            return None

    assert tick.splayed_next_run(_Never(), "c", uuid.uuid4(), BASE) is None
