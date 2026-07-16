# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for backend.services.custom_metric_retention.

Covers the OSS custom-metric sample retention prune:
  * old samples are deleted, recent ones kept, and the deleted count returned
  * a non-positive / non-numeric retention window is a safe no-op (never wipes)
  * the background loop coroutine starts and cancels cleanly
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.custom_metric import (
    SAMPLE_STATUS_OK,
    CustomMetric,
    CustomMetricSample,
)
from backend.services.custom_metric_retention import (
    prune_custom_metric_samples,
    run_custom_metric_retention_loop,
)

# custom_metric_sample FKs custom_metric + host; create those tables too so the
# scratch schema is self-consistent (SQLite doesn't enforce FKs by default, but
# building the referenced tables keeps this robust).
_TABLE_NAMES = ["custom_metric", "host", "custom_metric_sample"]


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine,
            tables=[Base.metadata.tables[t] for t in _TABLE_NAMES],
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            yield s
    finally:
        engine.dispose()


def _seed_metric(session):
    metric = CustomMetric(
        id=uuid.uuid4(), name="disk-free", script="echo 42", interpreter="sh"
    )
    session.add(metric)
    session.commit()
    return metric


def _add_sample(session, metric_id, collected_at, value=1.0):
    sample = CustomMetricSample(
        id=uuid.uuid4(),
        custom_metric_id=metric_id,
        host_id=uuid.uuid4(),
        value=value,
        status=SAMPLE_STATUS_OK,
        collected_at=collected_at,
    )
    session.add(sample)
    session.commit()
    return sample


class TestPrune:
    def test_deletes_old_keeps_recent_and_returns_count(self, session):
        metric = _seed_metric(session)
        now = datetime.now(timezone.utc)

        # Three old samples (well past the 90-day window) and two recent ones.
        old_ids = []
        for days in (100, 120, 365):
            s = _add_sample(session, metric.id, now - timedelta(days=days))
            old_ids.append(s.id)
        recent_ids = []
        for days in (1, 89):
            s = _add_sample(session, metric.id, now - timedelta(days=days))
            recent_ids.append(s.id)

        deleted = prune_custom_metric_samples(session, retention_days=90)

        assert deleted == 3
        remaining = {s.id for s in session.query(CustomMetricSample).all()}
        assert remaining == set(recent_ids)
        for old_id in old_ids:
            assert old_id not in remaining

    def test_boundary_recent_sample_kept(self, session):
        metric = _seed_metric(session)
        now = datetime.now(timezone.utc)
        # Just inside the window (30 days, retention 30 -> not strictly older).
        kept = _add_sample(session, metric.id, now - timedelta(days=29, hours=23))
        deleted = prune_custom_metric_samples(session, retention_days=30)
        assert deleted == 0
        assert session.query(CustomMetricSample).count() == 1
        assert session.get(CustomMetricSample, kept.id) is not None

    def test_zero_retention_is_noop(self, session):
        metric = _seed_metric(session)
        now = datetime.now(timezone.utc)
        _add_sample(session, metric.id, now - timedelta(days=1000))
        # A misconfigured 0 must NOT wipe the table.
        assert prune_custom_metric_samples(session, retention_days=0) == 0
        assert session.query(CustomMetricSample).count() == 1

    def test_negative_retention_is_noop(self, session):
        metric = _seed_metric(session)
        now = datetime.now(timezone.utc)
        _add_sample(session, metric.id, now - timedelta(days=1000))
        assert prune_custom_metric_samples(session, retention_days=-5) == 0
        assert session.query(CustomMetricSample).count() == 1

    def test_non_numeric_retention_is_noop(self, session):
        metric = _seed_metric(session)
        now = datetime.now(timezone.utc)
        _add_sample(session, metric.id, now - timedelta(days=1000))
        assert prune_custom_metric_samples(session, retention_days="oops") == 0
        assert session.query(CustomMetricSample).count() == 1

    def test_empty_table_returns_zero(self, session):
        assert prune_custom_metric_samples(session, retention_days=90) == 0


class TestLoop:
    @pytest.mark.asyncio
    async def test_loop_starts_and_cancels_cleanly(self):
        # A long interval so the first pass runs, logs, then parks in sleep;
        # we cancel while it's sleeping and assert clean CancelledError exit.
        task = asyncio.create_task(
            run_custom_metric_retention_loop(interval_seconds=3600)
        )
        # Let the loop reach its first sleep (one pass completes against the
        # collapsed bootstrap DB via iter_host_databases).
        await asyncio.sleep(0.05)
        assert not task.done()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()
