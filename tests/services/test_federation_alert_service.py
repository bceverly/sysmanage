# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for federation rollup alerting (Phase 12.1).

Covers the three built-in site conditions (offline / compliance-below /
critical-CVEs), the open-until-resolved lifecycle (one open alert per
site+condition, auto-resolve when the condition clears), acknowledge,
enrolled-only evaluation, listing, and resolved-alert pruning.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.federation import FederationAlert, FederationSite
from backend.services import federation_alert_service as al
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


def _site(session, *, name="site-a", status="enrolled", last_sync_minutes_ago=1):
    last = (
        _naive_utcnow() - timedelta(minutes=last_sync_minutes_ago)
        if last_sync_minutes_ago is not None
        else None
    )
    site = FederationSite(
        id=uuid.uuid4(),
        name=name,
        url="https://site.example",
        status=status,
        sync_interval_seconds=300,
        last_sync_at=last,
        created_at=_naive_utcnow(),
        updated_at=_naive_utcnow(),
    )
    session.add(site)
    session.commit()
    return site


def _open(session, site_id, condition):
    return [
        a for a in al.list_alerts(session, site_id=site_id) if a.condition == condition
    ]


# ----- site_offline ---------------------------------------------------


def test_offline_fires_when_sync_is_stale(session):
    site = _site(session, last_sync_minutes_ago=120)  # 2h, interval 300s*4=20m
    summary = al.evaluate_and_fire(session)
    session.commit()
    assert summary["opened"] == 1
    rows = _open(session, site.id, al.COND_SITE_OFFLINE)
    assert len(rows) == 1
    assert rows[0].severity == "critical"


def test_never_synced_fires_offline(session):
    site = _site(session, last_sync_minutes_ago=None)
    al.evaluate_and_fire(session)
    session.commit()
    assert len(_open(session, site.id, al.COND_SITE_OFFLINE)) == 1


def test_offline_autoresolves_after_fresh_sync(session):
    site = _site(session, last_sync_minutes_ago=120)
    al.evaluate_and_fire(session)
    session.commit()
    # Fresh sync clears the condition.
    site.last_sync_at = _naive_utcnow()
    session.commit()
    summary = al.evaluate_and_fire(session)
    session.commit()
    assert summary["resolved"] == 1
    assert _open(session, site.id, al.COND_SITE_OFFLINE) == []
    # A resolved row still exists in history.
    assert any(a.resolved for a in al.list_alerts(session, include_resolved=True))


def test_one_open_alert_per_condition_refresh_not_duplicate(session):
    site = _site(session, last_sync_minutes_ago=120)
    al.evaluate_and_fire(session)
    session.commit()
    # Second sweep, still offline → refresh, not a new row.
    summary = al.evaluate_and_fire(session)
    session.commit()
    assert summary["opened"] == 0
    assert summary["active"] >= 1
    assert (
        session.query(FederationAlert)
        .filter(
            FederationAlert.site_id == site.id,
            FederationAlert.condition == al.COND_SITE_OFFLINE,
        )
        .count()
        == 1
    )


# ----- compliance_below ----------------------------------------------


def test_compliance_below_fires_and_resolves(session):
    site = _site(session, last_sync_minutes_ago=1)
    rollup_svc.record_compliance_rollup_snapshot(
        session,
        site_id=site.id,
        baseline="cis",
        score_percent=42.0,
        hosts_in_scope=10,
        hosts_compliant=4,
        hosts_noncompliant=6,
    )
    session.commit()
    al.evaluate_and_fire(session)
    session.commit()
    assert len(_open(session, site.id, al.COND_COMPLIANCE_BELOW)) == 1

    # New snapshot above threshold → resolves.
    rollup_svc.record_compliance_rollup_snapshot(
        session,
        site_id=site.id,
        baseline="cis",
        score_percent=95.0,
        hosts_in_scope=10,
        hosts_compliant=10,
        hosts_noncompliant=0,
    )
    session.commit()
    al.evaluate_and_fire(session)
    session.commit()
    assert _open(session, site.id, al.COND_COMPLIANCE_BELOW) == []


def test_compliance_above_threshold_does_not_fire(session):
    site = _site(session, last_sync_minutes_ago=1)
    rollup_svc.record_compliance_rollup_snapshot(
        session,
        site_id=site.id,
        baseline="cis",
        score_percent=99.0,
        hosts_in_scope=5,
        hosts_compliant=5,
        hosts_noncompliant=0,
    )
    session.commit()
    al.evaluate_and_fire(session)
    session.commit()
    assert _open(session, site.id, al.COND_COMPLIANCE_BELOW) == []


# ----- vulnerabilities_high ------------------------------------------


def test_critical_cves_fire(session):
    site = _site(session, last_sync_minutes_ago=1)
    rollup_svc.record_vulnerability_rollup_snapshot(
        session,
        site_id=site.id,
        critical_count=3,
        high_count=5,
        affected_host_count=4,
    )
    session.commit()
    al.evaluate_and_fire(session)
    session.commit()
    rows = _open(session, site.id, al.COND_VULNERABILITIES_HIGH)
    assert len(rows) == 1
    assert rows[0].severity == "critical"


def test_zero_criticals_does_not_fire(session):
    site = _site(session, last_sync_minutes_ago=1)
    rollup_svc.record_vulnerability_rollup_snapshot(
        session, site_id=site.id, critical_count=0, high_count=9
    )
    session.commit()
    al.evaluate_and_fire(session)
    session.commit()
    assert _open(session, site.id, al.COND_VULNERABILITIES_HIGH) == []


# ----- scope / lifecycle ---------------------------------------------


def test_only_enrolled_sites_are_evaluated(session):
    pending = _site(
        session, name="pending", status="pending", last_sync_minutes_ago=999
    )
    suspended = _site(
        session, name="suspended", status="suspended", last_sync_minutes_ago=999
    )
    summary = al.evaluate_and_fire(session)
    session.commit()
    assert summary["opened"] == 0
    assert al.list_alerts(session, site_id=pending.id) == []
    assert al.list_alerts(session, site_id=suspended.id) == []


def test_acknowledge_marks_acked(session):
    site = _site(session, last_sync_minutes_ago=120)
    al.evaluate_and_fire(session)
    session.commit()
    alert = _open(session, site.id, al.COND_SITE_OFFLINE)[0]
    acked = al.acknowledge_alert(session, alert.id)
    session.commit()
    assert acked is not None
    assert acked.acknowledged is True
    assert acked.acknowledged_at is not None


def test_acknowledge_missing_returns_none(session):
    assert al.acknowledge_alert(session, uuid.uuid4()) is None


def test_list_open_only_by_default(session):
    site = _site(session, last_sync_minutes_ago=120)
    al.evaluate_and_fire(session)
    session.commit()
    site.last_sync_at = _naive_utcnow()
    session.commit()
    al.evaluate_and_fire(session)  # resolves it
    session.commit()
    assert al.list_alerts(session) == []  # open-only
    assert len(al.list_alerts(session, include_resolved=True)) == 1


def test_prune_resolved_alerts_respects_age(session):
    site = _site(session, last_sync_minutes_ago=120)
    al.evaluate_and_fire(session)
    session.commit()
    site.last_sync_at = _naive_utcnow()
    session.commit()
    al.evaluate_and_fire(session)  # resolve
    session.commit()
    # Backdate the resolved_at so it's older than the retention window.
    row = al.list_alerts(session, include_resolved=True)[0]
    row.resolved_at = _naive_utcnow() - timedelta(days=60)
    session.commit()
    removed = al.prune_resolved_alerts(session, older_than_days=30)
    session.commit()
    assert removed == 1
    assert al.list_alerts(session, include_resolved=True) == []
