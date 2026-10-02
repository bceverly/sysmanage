# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A worker thread for the inbound queue drain (Phase 22.2 / 22.3).

WHY
---
A profile of the server under a 1,000-agent fleet (the Phase 22 scale
harness): the event loop was 98% busy, and 88% of that time was inside the
database driver -- the loop WAITING on PostgreSQL round trips made by the
synchronous handlers.  The same thread serves every agent WebSocket, so the
inbound drain and the agents took turns on one thread and neither kept up.

The drain's handlers never touch a real WebSocket (queue processing hands them
a ``MockConnection``), so it can run elsewhere: this worker owns a thread with
its own event loop, and the message processor awaits it.  While the worker
waits on the database (the driver releases the GIL), the main loop serves the
agents.  Outbound sending stays on the main loop -- it writes to the real
connections.

SQLAlchemy sessions are not shared between threads: the coroutine handed to
``run`` creates, uses and closes its own session inside the worker.
"""

import asyncio
import threading
from typing import Any, Awaitable

from backend.utils.verbosity_logger import get_logger

logger = get_logger(__name__)


class InboundWorker:
    """One background thread running its own asyncio event loop."""

    def __init__(self, name: str = "sysmanage-inbound"):
        self._name = name
        self._loop = None
        self._thread = None
        self._lock = threading.Lock()

    def _ensure_started(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            ready = threading.Event()

            def run():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                ready.set()
                try:
                    self._loop.run_forever()
                finally:
                    self._loop.close()

            self._thread = threading.Thread(target=run, name=self._name, daemon=True)
            self._thread.start()
            ready.wait()
            logger.info("Inbound queue worker thread started")

    async def run(self, coro: Awaitable[Any]) -> Any:
        """Run ``coro`` on the worker's loop; await its result here."""
        self._ensure_started()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return await asyncio.wrap_future(future)

    def stop(self):
        with self._lock:
            if self._loop is not None and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread = None


inbound_worker = InboundWorker()
