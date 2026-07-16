# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the Phase 12.2 site-metadata reporting service.

  * ``collect_site_metadata`` gathers version / host-count / OS-breakdown /
    capabilities / uplink connection-state.
  * ``enqueue_site_metadata`` is a no-op when unenrolled, and otherwise
    enqueues exactly one (dedup-keyed) ``site_metadata`` payload that
    re-collection REPLACES rather than duplicates.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import json

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.core import Host
from backend.services import federation_coordinator_service as csvc
from backend.services import federation_site_metadata_service as msvc
from backend.services import federation_sync_queue_service as qsvc


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                Base.metadata.tables["federation_coordinator"],
                Base.metadata.tables["federation_sync_queue"],
                Base.metadata.tables["host"],
            ],
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            yield s
    finally:
        engine.dispose()


def _enroll(session):
    csvc.start_enrollment(
        session, coordinator_url="https://c", coordinator_tls_cert_pem="c"
    )
    csvc.mark_enrolled(
        session,
        site_id="22222222-2222-2222-2222-222222222222",
        site_tls_cert_pem="site-cert",
    )
    session.commit()


def _add_hosts(session):
    session.add_all(
        [
            Host(active=True, fqdn="a.example.com", platform="Linux"),
            Host(active=True, fqdn="b.example.com", platform="Linux"),
            Host(active=True, fqdn="c.example.com", platform="Windows"),
            Host(active=False, fqdn="dead.example.com", platform="Linux"),
        ]
    )
    session.commit()


class TestCollect:
    def test_counts_only_active_hosts_with_breakdown(self, session):
        _enroll(session)
        _add_hosts(session)
        meta = msvc.collect_site_metadata(session)
        assert meta["host_count"] == 3  # the inactive one is excluded
        assert meta["os_breakdown"] == {"Linux": 2, "Windows": 1}
        assert "sysmanage_version" in meta
        assert isinstance(meta["capabilities"], list)

    def test_reports_offline_connection_state(self, session):
        _enroll(session)
        for _ in range(csvc.OFFLINE_AFTER_FAILURES):
            csvc.record_sync_attempt(session, success=False, error="down")
        session.commit()
        meta = msvc.collect_site_metadata(session)
        assert meta["connection_state"] == csvc.CONN_OFFLINE
        assert meta["autonomous"] is True


class TestEnqueue:
    def test_noop_when_unenrolled(self, session):
        assert msvc.enqueue_site_metadata(session) is None
        assert qsvc.queue_depth(session) == 0

    def test_enqueues_one_metadata_row(self, session):
        _enroll(session)
        _add_hosts(session)
        entry = msvc.enqueue_site_metadata(session)
        session.commit()
        assert entry is not None
        assert entry.payload_type == msvc.SITE_METADATA_PAYLOAD_TYPE
        assert qsvc.queue_depth(session) == 1
        payload = json.loads(entry.payload_json)
        assert payload["host_count"] == 3

    def test_recollect_replaces_not_duplicates(self, session):
        _enroll(session)
        _add_hosts(session)
        msvc.enqueue_site_metadata(session)
        session.commit()
        # A new host appears, then we re-report.
        session.add(Host(active=True, fqdn="d.example.com", platform="Linux"))
        session.commit()
        entry = msvc.enqueue_site_metadata(session)
        session.commit()
        # Still exactly one pending metadata row, carrying the NEW count.
        assert qsvc.queue_depth(session) == 1
        payload = json.loads(entry.payload_json)
        assert payload["host_count"] == 4
