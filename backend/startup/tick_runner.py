# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Run a background tick: off the event loop, started at a random moment,
re-run at a jittered interval (Phase 22.3).

WHY
---
Every tick (advisor, malware, query packs, file watch, config assignments,
air-gap schedules, discovery, retention, ...) ran its synchronous all-tenant
pass directly on the event loop -- the loop that also serves every connected
agent -- and they all started in the same second as the server, i.e. in the
middle of the reconnect storm, then kept firing in step at fixed intervals.

HOW
---
* The pass runs on a worker thread (``asyncio.to_thread``; context variables
  such as the active tenant are copied), so the loop keeps serving agents.
  A pass that is a coroutine (it needs the loop) is awaited as before.
* The first pass waits a random moment, up to ``MAX_START_SPLAY_SECONDS`` and
  never more than one interval, so a restart does not start them all at once.
* Every wait -- interval and error backoff -- varies by +/-``SPREAD``, so
  ticks that started together drift apart instead of staying in phase.
"""

import asyncio
import inspect
import logging
import random

MAX_START_SPLAY_SECONDS = 120.0
SPREAD = 0.1


def _jittered(seconds: float) -> float:
    return seconds * random.uniform(
        1 - SPREAD, 1 + SPREAD
    )  # nosec B311 - spreading load


def start_splay(interval: float) -> float:
    """A random first wait: at most one interval, at most two minutes."""
    return random.uniform(0, min(MAX_START_SPLAY_SECONDS, interval))  # nosec B311


async def run_periodic(  # pylint: disable=too-many-arguments
    name: str,
    one_pass,
    interval: float,
    error_backoff: float,
    *,
    on_result=None,
    logger=None,
) -> None:
    """Run ``one_pass`` every ``interval`` seconds until cancelled.

    ``on_result`` (called on the loop) receives each pass's return value, for
    the tick's own summary logging.  Errors are logged and retried after a
    jittered ``error_backoff``; cancellation propagates."""
    log = logger or logging.getLogger(__name__)
    log.info("Starting %s (interval=%ds)", name, interval)
    await asyncio.sleep(start_splay(interval))
    while True:
        try:
            if inspect.iscoroutinefunction(one_pass):
                result = await one_pass()
            else:
                result = await asyncio.to_thread(one_pass)
                if inspect.isawaitable(result):  # a callable that returned a coroutine
                    result = await result
            if on_result is not None:
                on_result(result)
            await asyncio.sleep(_jittered(interval))
        except asyncio.CancelledError:
            log.info("%s cancelled -- exiting loop", name)
            raise
        except Exception:  # pylint: disable=broad-except
            log.exception("%s error -- sleeping then retrying", name)
            await asyncio.sleep(_jittered(error_backoff))
