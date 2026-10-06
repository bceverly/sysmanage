# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the Phase 12.2 site-side sync-queue service.

Covers:
  * ``enqueue`` writes rows, validates inputs.
  * Dedup-on-replay: re-enqueueing the same ``dedup_key`` updates
    the existing row rather than appending.
  * FIFO drain ordering on ``peek_batch``.
  * ``mark_sent`` removes; ``mark_failed`` increments + records error.
  * ``queue_depth`` + ``queue_depth_by_payload_type``.
  * ``purge_oldest`` trims correctly.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import json
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.federation import FederationSyncQueue
from backend.services import federation_sync_queue_service as qsvc

FEDERATION_TABLE_NAMES = [
    "federation_sites",
    "federation_host_directory",
    "federation_host_rollup",
    "federation_compliance_rollup",
    "federation_vulnerability_rollup",
    "federation_policies",
    "federation_policy_assignments",
    "federation_dispatched_commands",
    "federation_audit_log",
    "federation_coordinator",
    "federation_sync_queue",
    "federation_received_policies",
    "federation_received_commands",
]


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine, tables=[Base.metadata.tables[t] for t in FEDERATION_TABLE_NAMES]
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            yield s
    finally:
        engine.dispose()


# ---------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------


class TestEnqueue:
    def test_writes_row(self, session):
        row = qsvc.enqueue(
            session,
            payload_type="host_delta",
            payload={"host_id": "abc", "status": "up"},
            dedup_key="abc:status:1",
        )
        session.commit()
        assert row.id is not None
        assert row.payload_type == "host_delta"
        assert json.loads(row.payload_json) == {
            "host_id": "abc",
            "status": "up",
        }
        assert row.attempts == 0
        assert row.dedup_key == "abc:status:1"

    def test_blank_payload_type_raises(self, session):
        with pytest.raises(ValueError):
            qsvc.enqueue(session, payload_type="   ", payload={})

    def test_non_dict_payload_raises(self, session):
        with pytest.raises(ValueError):
            qsvc.enqueue(
                session,
                payload_type="x",
                payload="not a dict",  # type: ignore[arg-type]
            )

    def test_dedup_replaces_existing(self, session):
        qsvc.enqueue(
            session,
            payload_type="host_delta",
            payload={"status": "up"},
            dedup_key="host-1:status",
        )
        qsvc.enqueue(
            session,
            payload_type="host_delta",
            payload={"status": "down"},
            dedup_key="host-1:status",
        )
        session.commit()
        # Only one row in the queue -- the second call replaced the first.
        rows = qsvc.peek_batch(session)
        assert len(rows) == 1
        assert json.loads(rows[0].payload_json) == {"status": "down"}

    def test_dedup_replace_resets_attempts(self, session):
        first = qsvc.enqueue(
            session,
            payload_type="x",
            payload={"a": 1},
            dedup_key="key-1",
        )
        qsvc.mark_failed(session, first.id, error="boom")
        session.commit()
        # Re-enqueue with same key.
        qsvc.enqueue(session, payload_type="x", payload={"a": 2}, dedup_key="key-1")
        session.commit()
        rows = qsvc.peek_batch(session)
        assert len(rows) == 1
        assert rows[0].attempts == 0
        assert rows[0].last_error is None

    def test_no_dedup_appends_each_time(self, session):
        qsvc.enqueue(session, payload_type="x", payload={"a": 1})
        qsvc.enqueue(session, payload_type="x", payload={"a": 2})
        session.commit()
        assert qsvc.queue_depth(session) == 2


# ---------------------------------------------------------------------
# Drain helpers
# ---------------------------------------------------------------------


class TestPeekBatch:
    def test_returns_fifo_order(self, session):
        a = qsvc.enqueue(session, payload_type="x", payload={"n": 1})
        b = qsvc.enqueue(session, payload_type="x", payload={"n": 2})
        c = qsvc.enqueue(session, payload_type="x", payload={"n": 3})
        # peek_batch orders by (created_at, id).  All three rows are
        # inserted in the same instant here, and on a coarse-resolution
        # clock (e.g. Windows) they get an identical created_at -- which
        # makes the id (a random UUID) the tiebreaker and the order
        # non-deterministic.  Stamp strictly-increasing created_at values
        # so the test deterministically exercises the FIFO ordering.
        base = datetime(2026, 1, 1, 0, 0, 0)
        a.created_at = base
        b.created_at = base + timedelta(seconds=1)
        c.created_at = base + timedelta(seconds=2)
        session.commit()
        rows = qsvc.peek_batch(session)
        assert [r.id for r in rows] == [a.id, b.id, c.id]

    def test_limits_results(self, session):
        for _ in range(5):
            qsvc.enqueue(session, payload_type="x", payload={"a": 1})
        session.commit()
        rows = qsvc.peek_batch(session, limit=2)
        assert len(rows) == 2

    def test_limit_zero_raises(self, session):
        with pytest.raises(ValueError):
            qsvc.peek_batch(session, limit=0)

    def test_ready_rows_behind_many_waiting_ones_are_reached(self, session):
        """Phase 22.5: it read the oldest ``limit * 4`` rows and filtered the
        waiting ones in Python, so ready rows behind them starved."""
        base = datetime(2026, 1, 1, 0, 0, 0)
        for n in range(20):  # older, failed, waiting an hour
            row = qsvc.enqueue(session, payload_type="x", payload={"w": n})
            row.created_at = base + timedelta(seconds=n)
            row.attempts = 3
            row.next_attempt_at = datetime(2099, 1, 1)
        ready = qsvc.enqueue(session, payload_type="x", payload={"r": 1})
        ready.created_at = base + timedelta(hours=1)
        session.commit()
        rows = qsvc.peek_batch(session, limit=2, now=datetime(2026, 1, 2))
        assert [r.id for r in rows] == [ready.id]

    def test_waiting_row_becomes_ready_at_its_moment(self, session):
        row = qsvc.enqueue(session, payload_type="x", payload={"a": 1})
        row.attempts = 1
        row.next_attempt_at = datetime(2026, 1, 1, 12, 0, 0)
        session.commit()
        assert qsvc.peek_batch(session, now=datetime(2026, 1, 1, 11, 59, 59)) == []
        assert qsvc.peek_batch(session, now=datetime(2026, 1, 1, 12, 0, 0)) == [row]


class TestQueueDepth:
    def test_returns_zero_when_empty(self, session):
        assert qsvc.queue_depth(session) == 0

    def test_counts_all_rows(self, session):
        for i in range(4):
            qsvc.enqueue(session, payload_type="x", payload={"n": i})
        session.commit()
        assert qsvc.queue_depth(session) == 4


class TestQueueDepthByPayloadType:
    def test_groups_by_type(self, session):
        qsvc.enqueue(session, payload_type="host_delta", payload={})
        qsvc.enqueue(session, payload_type="host_delta", payload={})
        qsvc.enqueue(session, payload_type="host_rollup", payload={})
        session.commit()
        breakdown = qsvc.queue_depth_by_payload_type(session)
        assert breakdown == {"host_delta": 2, "host_rollup": 1}


# ---------------------------------------------------------------------
# Drain write-side
# ---------------------------------------------------------------------


class TestMarkSent:
    def test_removes_row(self, session):
        row = qsvc.enqueue(session, payload_type="x", payload={})
        session.commit()
        qsvc.mark_sent(session, row.id)
        session.commit()
        assert qsvc.queue_depth(session) == 0

    def test_unknown_id_raises(self, session):
        import uuid

        with pytest.raises(qsvc.SyncQueueEntryNotFoundError):
            qsvc.mark_sent(session, uuid.uuid4())


class TestMarkFailed:
    def test_increments_attempts_and_records_error(self, session):
        row = qsvc.enqueue(session, payload_type="x", payload={})
        session.commit()
        qsvc.mark_failed(session, row.id, error="conn refused")
        session.commit()
        refreshed = session.get(FederationSyncQueue, row.id)
        assert refreshed.attempts == 1
        assert refreshed.last_error == "conn refused"
        assert refreshed.last_attempt_at is not None

    def test_repeated_failure_increments(self, session):
        row = qsvc.enqueue(session, payload_type="x", payload={})
        session.commit()
        qsvc.mark_failed(session, row.id, error="boom")
        qsvc.mark_failed(session, row.id, error="boom again")
        session.commit()
        assert session.get(FederationSyncQueue, row.id).attempts == 2

    def test_schedules_the_retry_once(self, session):
        """Phase 22.5: the retry moment is fixed at the failure (jittered
        once), so the entry's readiness does not flicker between ticks."""
        row = qsvc.enqueue(session, payload_type="x", payload={"a": 1})
        session.commit()
        qsvc.mark_failed(session, row.id, error="boom")
        wait = (row.next_attempt_at - row.last_attempt_at).total_seconds()
        assert 8 <= wait <= 12  # 10 s base +/-20% after the first failure
        qsvc.mark_failed(session, row.id, error="boom")
        wait = (row.next_attempt_at - row.last_attempt_at).total_seconds()
        assert 16 <= wait <= 24

    def test_dedup_replace_clears_the_retry_moment(self, session):
        row = qsvc.enqueue(session, payload_type="x", payload={"a": 1}, dedup_key="k")
        session.commit()
        qsvc.mark_failed(session, row.id, error="boom")
        again = qsvc.enqueue(session, payload_type="x", payload={"a": 2}, dedup_key="k")
        assert again.next_attempt_at is None

    def test_blank_error_raises(self, session):
        row = qsvc.enqueue(session, payload_type="x", payload={})
        with pytest.raises(ValueError):
            qsvc.mark_failed(session, row.id, error="")


# ---------------------------------------------------------------------
# Purge
# ---------------------------------------------------------------------


class TestPurgeOldest:
    def test_keeps_newest_n(self, session):
        for i in range(5):
            qsvc.enqueue(session, payload_type="x", payload={"n": i})
            session.commit()  # commit per row so created_at differs

        deleted = qsvc.purge_oldest(session, keep_newest=2)
        session.commit()
        assert deleted >= 3
        assert qsvc.queue_depth(session) <= 2

    def test_keeps_all_when_smaller_than_threshold(self, session):
        for i in range(3):
            qsvc.enqueue(session, payload_type="x", payload={"n": i})
        session.commit()
        deleted = qsvc.purge_oldest(session, keep_newest=10)
        session.commit()
        assert deleted == 0
        assert qsvc.queue_depth(session) == 3

    def test_negative_keep_raises(self, session):
        with pytest.raises(ValueError):
            qsvc.purge_oldest(session, keep_newest=-1)
