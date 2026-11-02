# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The inbound queue worker thread (Phase 22.2): each thread closes only its
own event loop, so a stop followed at once by a new run never closes the new
thread's running loop ("Cannot close a running event loop", CI 2026-11-02)."""

import asyncio
import threading

import pytest

from backend.websocket.inbound_worker import InboundWorker


async def _answer():
    return threading.current_thread().name


@pytest.mark.asyncio
async def test_a_coroutine_runs_on_the_worker_thread():
    worker = InboundWorker(name="test-inbound")
    try:
        assert await worker.run(_answer()) == "test-inbound"
    finally:
        worker.stop()


@pytest.mark.asyncio
async def test_a_restart_never_closes_the_new_loop():
    worker = InboundWorker(name="test-inbound-restart")
    errors = []
    previous = threading.excepthook
    threading.excepthook = lambda args: errors.append(args.exc_value)
    try:
        for _ in range(20):
            await worker.run(_answer())
            old_thread = worker._thread  # pylint: disable=protected-access
            worker.stop()
            await worker.run(_answer())  # a new thread, a new loop
            old_thread.join(timeout=5)
            new_loop = worker._loop  # pylint: disable=protected-access
            assert new_loop.is_running() and not new_loop.is_closed()
    finally:
        worker.stop()
        threading.excepthook = previous
    assert not errors
    await asyncio.sleep(0)
