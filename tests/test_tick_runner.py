# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.3: background ticks run off the event loop, start at a random
moment, and re-run at a jittered interval.

They ran their synchronous all-tenant passes on the loop that serves every
agent, all started in the same second as the server (in the reconnect storm),
and fired in step at fixed intervals forever after.
"""

import asyncio
import threading
from unittest.mock import patch

import pytest

from backend.startup import tick_runner


class _Stop(BaseException):  # not caught by the runner's error handling
    pass


async def _run(one_pass, passes=3, interval=60.0, backoff=30.0, on_result=None):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) > passes:
            raise _Stop()

    with patch.object(tick_runner.asyncio, "sleep", fake_sleep):
        with pytest.raises(_Stop):
            await tick_runner.run_periodic("t", one_pass, interval, backoff,
                                           on_result=on_result)  # fmt: skip
    return sleeps


async def test_a_synchronous_pass_runs_off_the_event_loop():
    loop_thread = threading.get_ident()
    threads = []
    await _run(lambda: threads.append(threading.get_ident()))
    assert threads and all(t != loop_thread for t in threads)


async def test_the_first_pass_starts_at_a_random_moment():
    firsts = set()
    for _ in range(20):
        sleeps = await _run(lambda: None, passes=1)
        firsts.add(round(sleeps[0], 3))
        assert 0 <= sleeps[0] <= 60.0  # never more than one interval
    assert len(firsts) > 15


async def test_the_start_splay_is_capped_for_long_intervals():
    sleeps = await _run(lambda: None, passes=1, interval=3600.0)
    assert sleeps[0] <= tick_runner.MAX_START_SPLAY_SECONDS


async def test_intervals_are_jittered_so_ticks_drift_apart():
    sleeps = await _run(lambda: None, passes=30)
    intervals = sleeps[1:]
    assert all(54.0 <= s <= 66.0 for s in intervals)
    assert len(set(intervals)) > 25


async def test_errors_back_off_with_jitter_and_the_loop_survives():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("db blip")
        return "ok"

    results = []
    sleeps = await _run(flaky, passes=2, on_result=results.append)
    assert 27.0 <= sleeps[1] <= 33.0  # the error backoff
    assert results == ["ok"]


async def test_cancellation_propagates():
    def cancelled():
        raise asyncio.CancelledError()

    async def no_wait(_seconds):
        return None

    with patch.object(tick_runner.asyncio, "sleep", no_wait):
        with pytest.raises(asyncio.CancelledError):
            await tick_runner.run_periodic("t", cancelled, 60, 30)


async def test_a_coroutine_pass_is_awaited_on_the_loop():
    seen = []

    async def on_loop():
        seen.append(threading.get_ident())

    await _run(on_loop, passes=1)
    assert seen == [threading.get_ident()]
