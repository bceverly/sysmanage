# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Run a coroutine from plain, blocking code -- never on the server's loop.

Route handlers are plain ``def`` (FastAPI runs them in its thread pool) so
their blocking database calls leave the event loop.  A few still have one
coroutine to finish -- a CVE feed refresh, an agent's authentication check --
and ``run_to_completion`` finishes it there, on an event loop of its own.
"""

import asyncio
import concurrent.futures
from typing import Any, Coroutine


def run_to_completion(coroutine: Coroutine[Any, Any, Any]) -> Any:
    """Run ``coroutine`` to completion on an event loop of its own.

    In a thread with no running loop -- FastAPI's pool, where a plain handler
    runs in production -- that is ``asyncio.run``.  Called from inside a
    running loop (a test calling a handler directly), where ``asyncio.run``
    refuses to start, it runs on a fresh loop in a short-lived worker thread
    instead; the caller then waits for it, which only a caller that is
    already on a loop (never the server's request path) pays for.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()
