# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Dispatch correlations kept in the database (2026-11-25).

``proplus_dispatch`` maps a queued plan's message_id to the engine that
must handle its result.  That map was process memory, but the server runs
several workers: the leader dispatches (ticks are singletons) while any
worker may process the agent's command_result.  A result handled elsewhere
found no entry and was dropped -- an air-gap collection run sat in
MIRRORING with its plan long finished (2026-11-25).

So each correlation is also written to ``dispatch_correlation`` in the
database that holds the host's queue, and a worker that does not have it in
memory claims it from there.  Rows are claimed (deleted) when the result is
routed; one never answered is pruned after ``KEEP``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from backend.persistence import models

logger = logging.getLogger(__name__)

# The longest plan (an ISO burn) times out after two hours; a week is ample.
KEEP = timedelta(days=7)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def save(bind, message_id: str, engine: str, primary_id: str, host_id: str) -> None:
    """Record one correlation (and prune stale ones).  Never raises: the
    in-memory map still serves a result handled by this worker."""
    try:
        with Session(bind=bind) as session:
            session.merge(
                models.DispatchCorrelation(
                    message_id=str(message_id),
                    engine=engine,
                    primary_id=str(primary_id),
                    host_id=str(host_id),
                    created_at=_now(),
                )
            )
            session.query(models.DispatchCorrelation).filter(
                models.DispatchCorrelation.created_at < _now() - KEEP
            ).delete(synchronize_session=False)
            session.commit()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("dispatch correlation %s not stored: %s", message_id, exc)


def take(bind, message_id: str) -> Optional[Tuple[str, str, str]]:
    """Claim the correlation for ``message_id``: (engine, primary_id,
    host_id), or None.  Claimed means deleted -- only one worker routes a
    result.  Its own transaction, so the caller's is untouched."""
    try:
        with Session(bind=bind) as session:
            row = session.get(models.DispatchCorrelation, str(message_id))
            if row is None:
                return None
            found = (row.engine, row.primary_id, row.host_id)
            claimed = (
                session.query(models.DispatchCorrelation)
                .filter(models.DispatchCorrelation.message_id == str(message_id))
                .delete(synchronize_session=False)
            )
            session.commit()
            return found if claimed else None
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("dispatch correlation %s not read: %s", message_id, exc)
        return None


def forget(bind, message_id: str) -> None:
    """Drop a correlation this worker routed from memory."""
    try:
        with Session(bind=bind) as session:
            session.query(models.DispatchCorrelation).filter(
                models.DispatchCorrelation.message_id == str(message_id)
            ).delete(synchronize_session=False)
            session.commit()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("dispatch correlation %s not cleared: %s", message_id, exc)
