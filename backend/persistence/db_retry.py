# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Bounded retry for transient database errors during a PostgreSQL failover.

During the few seconds a primary is being promoted there is no writable primary,
so a connection opened *into that gap* raises ``OperationalError`` /
``InterfaceError``.  ``pool_pre_ping`` (see :data:`backend.persistence.db.
HA_ENGINE_KWARGS`) already reconnects a *dead pooled* socket transparently on
checkout; this helper covers the remaining case — a unit of work that begins
mid-gap — by retrying with bounded exponential backoff until the new primary
accepts connections.

SAFETY — only for IDEMPOTENT / not-yet-committed work.  The wrapped callable
MUST be safe to run again from the start with no partially-applied side effects:
a read, or a self-contained ``with Session() as s: ...; s.commit()`` block that
had not yet committed when it failed.  NEVER wrap a partially-committed
multi-step transaction — a blind replay would double-apply it.  A non-transient
error (bad SQL, constraint violation, ...) is re-raised immediately, never
retried.
"""

import asyncio
import logging
import time
from functools import wraps

from sqlalchemy.exc import InterfaceError, OperationalError

logger = logging.getLogger(__name__)

# Errors that signal a lost/absent connection — transient during a failover —
# as opposed to a query/logic error (IntegrityError, ProgrammingError, ...),
# which must surface immediately rather than be replayed.
TRANSIENT_DB_ERRORS = (OperationalError, InterfaceError)

DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BASE_DELAY = 0.5
DEFAULT_MAX_DELAY = 4.0


def run_with_db_retry(
    func,
    *args,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    **kwargs,
):
    """Call ``func(*args, **kwargs)``, retrying only transient DB errors.

    Backoff is exponential and capped: ``base_delay * 2**(n-1)`` bounded by
    ``max_delay``.  Blocks the calling thread with ``time.sleep`` between tries,
    so use from a sync context or a threadpool — never inline in the event loop.
    Re-raises the last transient error once ``max_attempts`` is exhausted, and
    re-raises any non-transient error on the first occurrence.
    """
    attempt = 0
    while True:
        try:
            return func(*args, **kwargs)
        except TRANSIENT_DB_ERRORS as exc:
            attempt += 1
            if attempt >= max_attempts:
                logger.error(
                    "DB operation failed after %d attempt(s) (transient, likely "
                    "failover window not yet closed): %s",
                    attempt,
                    exc,
                )
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning(
                "Transient DB error (attempt %d/%d) — retrying in %.1fs: %s",
                attempt,
                max_attempts,
                delay,
                exc,
            )
            time.sleep(delay)


async def run_with_db_retry_async(
    func,
    *args,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    **kwargs,
):
    """Async twin of :func:`run_with_db_retry`.

    Awaits ``func(*args, **kwargs)`` and backs off with ``asyncio.sleep`` — so
    it yields the event loop during the promotion gap instead of blocking it.
    Use from an async request/handler boundary wrapping an awaitable idempotent
    unit of work.  Same transient-vs-fatal classification and give-up semantics.
    """
    attempt = 0
    while True:
        try:
            return await func(*args, **kwargs)
        except TRANSIENT_DB_ERRORS as exc:
            attempt += 1
            if attempt >= max_attempts:
                logger.error(
                    "Async DB operation failed after %d attempt(s) (transient, "
                    "likely failover window not yet closed): %s",
                    attempt,
                    exc,
                )
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning(
                "Transient DB error (async attempt %d/%d) — retrying in %.1fs: %s",
                attempt,
                max_attempts,
                delay,
                exc,
            )
            await asyncio.sleep(delay)


def with_db_retry(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
):
    """Decorator form of :func:`run_with_db_retry` for an idempotent callable."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return run_with_db_retry(
                func,
                *args,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                **kwargs,
            )

        return wrapper

    return decorator
