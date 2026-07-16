# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for the rollup retention sweeper (Phase 12.1 followup).

The three append-only rollup series are bounded by count opportunistically
at ingest (newest ``DEFAULT_ROLLUP_RETENTION`` kept per series) and by the
explicit ``prune_rollups`` sweep (count + optional age).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.federation import (
    FederationHostRollup,
    FederationSite,
    FederationVulnerabilityRollup,
)
from backend.services import federation_rollup_service as rollup_svc


def _naive_utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def session():
    engine = sa.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=sa.pool.StaticPool,
    )
    Base.metadata.create_all(engine)
    sess = sessionmaker(bind=engine)()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


@pytest.fixture
def site(session):
    s = FederationSite(
        id=uuid.uuid4(),
        name="site-a",
        url="https://s.example",
        status="enrolled",
        sync_interval_seconds=300,
        created_at=_naive_utcnow(),
        updated_at=_naive_utcnow(),
    )
    session.add(s)
    session.commit()
    return s


def _host_count(session, site_id):
    return (
        session.query(FederationHostRollup)
        .filter(FederationHostRollup.site_id == site_id)
        .count()
    )


def test_opportunistic_prune_bounds_host_series(session, site):
    keep = rollup_svc.DEFAULT_ROLLUP_RETENTION
    for i in range(keep + 5):
        rollup_svc.record_host_rollup_snapshot(
            session,
            site_id=site.id,
            host_count=i,
            active_count=i,
            snapshot_at=_naive_utcnow() + timedelta(seconds=i),
            update_site_host_count=False,
        )
    session.commit()
    # Bounded at the retention limit despite keep+5 inserts.
    assert _host_count(session, site.id) == keep
    # The newest snapshot survives (highest host_count).
    newest = (
        session.query(FederationHostRollup)
        .filter(FederationHostRollup.site_id == site.id)
        .order_by(FederationHostRollup.snapshot_at.desc())
        .first()
    )
    assert newest.host_count == keep + 4


def test_prune_rollups_count_per_series(session, site):
    for i in range(6):
        rollup_svc.record_vulnerability_rollup_snapshot(
            session,
            site_id=site.id,
            critical_count=i,
            snapshot_at=_naive_utcnow() + timedelta(seconds=i),
        )
    session.commit()
    counts = rollup_svc.prune_rollups(session, keep_per_series=2)
    session.commit()
    assert counts["vulnerability"] == 4
    assert (
        session.query(FederationVulnerabilityRollup)
        .filter(FederationVulnerabilityRollup.site_id == site.id)
        .count()
        == 2
    )


def test_prune_rollups_older_than_days(session, site):
    # One ancient + one fresh host snapshot.
    rollup_svc.record_host_rollup_snapshot(
        session,
        site_id=site.id,
        host_count=1,
        active_count=1,
        snapshot_at=_naive_utcnow() - timedelta(days=120),
        update_site_host_count=False,
    )
    rollup_svc.record_host_rollup_snapshot(
        session,
        site_id=site.id,
        host_count=2,
        active_count=2,
        snapshot_at=_naive_utcnow(),
        update_site_host_count=False,
    )
    session.commit()
    # Generous count keep so only the age cutoff prunes the ancient row.
    counts = rollup_svc.prune_rollups(session, keep_per_series=1000, older_than_days=30)
    session.commit()
    assert counts["host"] == 1
    assert _host_count(session, site.id) == 1


def test_prune_is_idempotent(session, site):
    for i in range(4):
        rollup_svc.record_vulnerability_rollup_snapshot(
            session,
            site_id=site.id,
            critical_count=i,
            snapshot_at=_naive_utcnow() + timedelta(seconds=i),
        )
    session.commit()
    rollup_svc.prune_rollups(session, keep_per_series=2)
    session.commit()
    # Second sweep with the same params removes nothing more.
    counts = rollup_svc.prune_rollups(session, keep_per_series=2)
    session.commit()
    assert counts["vulnerability"] == 0
