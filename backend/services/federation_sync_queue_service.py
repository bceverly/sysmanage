# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Site-side upstream-sync queue service (Phase 12.2).

Manages the outbox table (``federation_sync_queue``) that buffers
deltas the site needs to push to its coordinator.  The Pro+ site
engine's background worker drains this queue on a configurable
cadence; this OSS service layer owns:

  * Enqueue / dedup-on-replay semantics
  * FIFO drain ordering
  * Per-payload attempt counter + last-error capture
  * Cleanup of successfully-sent payloads

The dedup story is the load-bearing design point.  When the
coordinator goes offline mid-sync, the site keeps enqueueing
deltas.  On reconnect:

  1. Site re-sends every unsent payload in ``federation_sync_queue``
  2. Coordinator dedup-keys on ``(payload_type, dedup_key)`` so a
     payload that was actually delivered just before the network
     dropped isn't double-applied.
  3. Site clears the payload from its queue only after a successful
     ack.

``dedup_key`` is opaque to the site — typically a
``"host_id:field:mtime"`` triple for host-delta payloads, or the
snapshot timestamp for rollup payloads.  Free-form so future
payload types can pick their own dedup shape.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.persistence.models.federation import FederationSyncQueue
from backend.services import federation_retry_policy as retry_policy

# ---------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------


class FederationSyncQueueError(Exception):
    """Base class for sync-queue errors."""


class SyncQueueEntryNotFoundError(FederationSyncQueueError, LookupError):
    """Raised when a queue id doesn't resolve."""


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _ensure_entry(session: Session, entry_id: Any) -> FederationSyncQueue:
    eid = _coerce_uuid(entry_id)
    entry = session.get(FederationSyncQueue, eid)
    if entry is None:
        raise SyncQueueEntryNotFoundError(f"No sync-queue entry with id={eid}")
    return entry


# ---------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------


def enqueue(
    session: Session,
    *,
    payload_type: str,
    payload: Dict[str, Any],
    dedup_key: Optional[str] = None,
) -> FederationSyncQueue:
    """Append one entry to the outbound sync queue.

    If ``dedup_key`` is provided AND a row with the same key already
    exists (regardless of payload_type), the existing row is REPLACED
    rather than a duplicate appended.  This makes "host X changed
    from up to down, then immediately back to up" produce a single
    queued row carrying the latest state — common when an agent
    flaps and the coordinator only cares about the final value.

    Returns the persisted row (caller commits).
    """
    if not payload_type or not payload_type.strip():
        raise ValueError("payload_type is required")
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict (will be JSON-serialised)")

    # Dedup on insert: if there's an existing row with the same key,
    # overwrite its payload + reset its attempt counter.  This is
    # what makes "flap then settle" yield one queued entry, not N.
    if dedup_key:
        existing = (
            session.execute(
                select(FederationSyncQueue).where(
                    FederationSyncQueue.dedup_key == dedup_key
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            existing.payload_type = payload_type.strip()
            existing.payload_json = json.dumps(payload, sort_keys=True)
            existing.attempts = 0
            existing.last_attempt_at = None
            existing.last_error = None
            existing.created_at = _utcnow_naive()
            return existing

    entry = FederationSyncQueue(
        payload_type=payload_type.strip(),
        payload_json=json.dumps(payload, sort_keys=True),
        dedup_key=dedup_key,
    )
    session.add(entry)
    session.flush()
    return entry


# ---------------------------------------------------------------------
# Drain (read-side, for the engine's worker)
# ---------------------------------------------------------------------


def peek_batch(
    session: Session,
    *,
    limit: int = 100,
    now: Optional[datetime] = None,
) -> List[FederationSyncQueue]:
    """Return the next ``limit`` queue rows that are READY for
    transmission, in FIFO order, WITHOUT locking them.

    The site engine's worker calls this to fetch a batch, sends them
    upstream, and then calls :func:`mark_sent` / :func:`mark_failed`
    per row based on the coordinator's response.  Because the worker
    is single-threaded per process, no SELECT-FOR-UPDATE is needed —
    the FIFO ordering keeps correctness simple.

    Phase 12.10 hardening: rows whose ``attempts > 0`` are gated by
    :func:`federation_retry_policy.is_ready_for_retry` — entries
    still in their exponential-backoff window are skipped, so a
    down coordinator doesn't get hammered every tick.  Rows whose
    ``attempts >= MAX_ATTEMPTS`` are dead-lettered (never returned;
    operator must reset the counter via direct DB intervention or
    a re-enqueue).  ``now`` is injectable for deterministic tests.
    """
    if limit <= 0:
        raise ValueError("limit must be > 0")
    if now is None:
        now = _utcnow_naive()
    # Cheap pre-filter at the DB level: never-attempted rows are
    # always ready; dead-lettered rows are never ready.  The fine-
    # grained backoff check happens in Python because the
    # ``compute_backoff`` formula uses runtime jitter.
    candidates = list(
        session.execute(
            select(FederationSyncQueue)
            .where(FederationSyncQueue.attempts < retry_policy.MAX_ATTEMPTS)
            .order_by(FederationSyncQueue.created_at, FederationSyncQueue.id)
            .limit(limit * 4)
        )
        .scalars()
        .all()
    )
    ready: List[FederationSyncQueue] = []
    for entry in candidates:
        if retry_policy.is_ready_for_retry(entry.last_attempt_at, entry.attempts, now):
            ready.append(entry)
            if len(ready) >= limit:
                break
    return ready


def queue_depth(session: Session) -> int:
    """Number of unsent entries.  Drives the operator-facing
    sync-status dashboard tile (``/sync-queue/depth``)."""
    from sqlalchemy import func  # noqa: PLC0415

    # pylint: disable=not-callable
    return int(
        session.scalar(select(func.count()).select_from(FederationSyncQueue)) or 0
    )


def queue_depth_by_payload_type(session: Session) -> Dict[str, int]:
    """Per-payload-type breakdown of unsent entries.

    Useful when a site is far behind and the operator wants to know
    "is this 10k host_deltas or 1 stuck compliance_rollup?".
    """
    from sqlalchemy import func  # noqa: PLC0415

    # pylint: disable=not-callable
    rows = session.execute(
        select(FederationSyncQueue.payload_type, func.count()).group_by(
            FederationSyncQueue.payload_type
        )
    ).all()
    return {row[0]: int(row[1]) for row in rows}


# ---------------------------------------------------------------------
# Drain (write-side)
# ---------------------------------------------------------------------


def mark_sent(session: Session, entry_id: Any) -> None:
    """Remove a queue row that the coordinator acknowledged.

    The sync model is "successful ack => row gone" rather than
    "row stays with a sent_at timestamp".  Keeping the queue
    bounded by ack count (vs ever-growing audit log) matters at
    1M-host scale; the audit trail for what got synced is the
    coordinator's ``federation_audit_log``, not ours.
    """
    entry = _ensure_entry(session, entry_id)
    session.delete(entry)


def mark_failed(
    session: Session,
    entry_id: Any,
    *,
    error: str,
) -> FederationSyncQueue:
    """Record a failed delivery attempt and leave the row in the queue.

    Increments ``attempts``, stamps ``last_attempt_at`` / ``last_error``
    so the next drain cycle picks it up again.  Bounded retry / backoff
    is the worker's responsibility — this service just records facts.
    """
    if not error:
        raise ValueError("error string is required for mark_failed")
    entry = _ensure_entry(session, entry_id)
    entry.attempts += 1
    entry.last_attempt_at = _utcnow_naive()
    entry.last_error = error
    return entry


def purge_oldest(session: Session, *, keep_newest: int) -> int:
    """Drop everything except the newest ``keep_newest`` entries.

    Safety valve for a long offline period: at some point the
    queue's data is too stale to be useful (the coordinator will
    pull a fresh rollup anyway), so the operator can trim with this.

    Returns the number of rows deleted.
    """
    if keep_newest < 0:
        raise ValueError("keep_newest must be >= 0")
    total = queue_depth(session)
    if total <= keep_newest:
        return 0
    # Find the cutoff: the (keep_newest+1)-th newest row's created_at.
    cutoff_row = (
        session.execute(
            select(FederationSyncQueue.created_at)
            .order_by(FederationSyncQueue.created_at.desc())
            .offset(keep_newest)
            .limit(1)
        )
        .scalars()
        .first()
    )
    if cutoff_row is None:
        return 0

    deleted_rows = (
        session.execute(
            select(FederationSyncQueue).where(
                FederationSyncQueue.created_at <= cutoff_row
            )
        )
        .scalars()
        .all()
    )
    deleted_count = 0
    for row in deleted_rows:
        session.delete(row)
        deleted_count += 1
    return deleted_count
