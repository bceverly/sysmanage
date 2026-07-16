# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the Phase 12.2 coordinator-side additions to
``federation_site_service``:

  * ``record_sync`` appends a ``FederationSiteSyncEvent`` timeline point
    (and can suppress it).
  * ``apply_site_metadata`` caches version / capabilities / connection-state
    onto the registry row.
  * ``list_sync_events`` returns points oldest-first.
  * ``prune_sync_events`` trims by per-site cap and by age.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import json
import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.federation import (
    FederationSite,
    FederationSiteSyncEvent,
)
from backend.services import federation_site_service as ssvc


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                Base.metadata.tables["federation_sites"],
                Base.metadata.tables["federation_site_sync_event"],
                Base.metadata.tables["federation_audit_log"],
            ],
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            yield s
    finally:
        engine.dispose()


def _site(session, name="alpha"):
    site = FederationSite(
        id=uuid.uuid4(), name=name, url="https://s", status="enrolled"
    )
    session.add(site)
    session.commit()
    return site


class TestRecordSyncEvents:
    def test_record_sync_appends_timeline_point(self, session):
        site = _site(session)
        ssvc.record_sync(
            session, site.id, success=True, host_count=7, latency_ms=42, queue_depth=3
        )
        session.commit()
        events = ssvc.list_sync_events(session, site.id)
        assert len(events) == 1
        assert events[0].sync_status == "success"
        assert events[0].latency_ms == 42
        assert events[0].queue_depth == 3
        assert events[0].host_count == 7

    def test_record_sync_can_suppress_event(self, session):
        site = _site(session)
        ssvc.record_sync(session, site.id, success=True, record_event=False)
        session.commit()
        assert ssvc.list_sync_events(session, site.id) == []

    def test_failure_records_error_event(self, session):
        site = _site(session)
        ssvc.record_sync(session, site.id, success=False, error="timeout")
        session.commit()
        events = ssvc.list_sync_events(session, site.id)
        assert events[0].sync_status == "error"

    def test_list_is_oldest_first(self, session):
        site = _site(session)
        for i in range(3):
            ssvc.record_sync(session, site.id, success=True, latency_ms=i)
        session.commit()
        events = ssvc.list_sync_events(session, site.id)
        assert [e.latency_ms for e in events] == [0, 1, 2]


class TestApplyMetadata:
    def test_caches_metadata_fields(self, session):
        site = _site(session)
        ssvc.apply_site_metadata(
            session,
            site.id,
            {
                "sysmanage_version": "2.4.0.0",
                "connection_state": "offline",
                "capabilities": ["federation_site_engine", "secrets_engine"],
                "host_count": 12,
            },
        )
        session.commit()
        refreshed = session.get(FederationSite, site.id)
        assert refreshed.sysmanage_version == "2.4.0.0"
        assert refreshed.connection_state == "offline"
        assert refreshed.host_count == 12
        assert json.loads(refreshed.capabilities_json) == [
            "federation_site_engine",
            "secrets_engine",
        ]
        assert refreshed.last_metadata_at is not None

    def test_ignores_unknown_keys(self, session):
        site = _site(session)
        ssvc.apply_site_metadata(session, site.id, {"some_future_field": "x"})
        session.commit()
        refreshed = session.get(FederationSite, site.id)
        assert refreshed.last_metadata_at is not None


class TestPrune:
    def test_prunes_beyond_per_site_cap(self, session):
        site = _site(session)
        for _ in range(10):
            ssvc.record_sync(session, site.id, success=True, record_event=True)
        session.commit()
        ssvc.prune_sync_events(session, site.id, keep_per_site=4, older_than_days=999)
        session.commit()
        assert len(ssvc.list_sync_events(session, site.id, limit=100)) == 4

    def test_prunes_old_events(self, session):
        site = _site(session)
        ssvc.record_sync(session, site.id, success=True)
        session.commit()
        # Backdate the lone event well past the age cap.
        ev = session.execute(sa.select(FederationSiteSyncEvent)).scalars().first()
        ev.recorded_at = ev.recorded_at - timedelta(days=60)
        session.commit()
        ssvc.prune_sync_events(session, site.id, keep_per_site=500, older_than_days=30)
        session.commit()
        assert ssvc.list_sync_events(session, site.id, limit=100) == []

    def test_per_site_isolation(self, session):
        a = _site(session, "a")
        b = _site(session, "b")
        for _ in range(3):
            ssvc.record_sync(session, a.id, success=True)
        ssvc.record_sync(session, b.id, success=True)
        session.commit()
        ssvc.prune_sync_events(session, a.id, keep_per_site=1, older_than_days=999)
        session.commit()
        assert len(ssvc.list_sync_events(session, a.id)) == 1
        assert len(ssvc.list_sync_events(session, b.id)) == 1
