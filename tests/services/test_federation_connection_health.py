# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the Phase 12.2 site-side uplink connection-health logic in
``federation_coordinator_service``:

  * ``record_sync_attempt`` maintains consecutive-failure count, the
    derived ``connection_state`` (online/degraded/offline), and the
    ``last_successful_sync_at`` / ``next_reconnect_at`` fields.
  * ``should_attempt_sync`` honours the reconnect backoff gate.
  * ``is_autonomous`` reports local-autonomy mode only when enrolled AND
    offline.
  * ``connection_health`` snapshot shape for enrolled / unenrolled sites.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

from datetime import timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.services import federation_coordinator_service as csvc


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine,
            tables=[Base.metadata.tables["federation_coordinator"]],
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            yield s
    finally:
        engine.dispose()


def _enroll(session):
    csvc.start_enrollment(
        session,
        coordinator_url="https://coord.x",
        coordinator_tls_cert_pem="cert",
    )
    csvc.mark_enrolled(
        session,
        site_id="11111111-1111-1111-1111-111111111111",
        site_tls_cert_pem="site-cert",
    )
    session.commit()


class TestRecordSyncAttemptHealth:
    def test_success_sets_online_and_clears_backoff(self, session):
        _enroll(session)
        row = csvc.record_sync_attempt(session, success=True)
        assert row.connection_state == csvc.CONN_ONLINE
        assert row.consecutive_sync_failures == 0
        assert row.last_successful_sync_at is not None
        assert row.next_reconnect_at is None

    def test_first_failure_is_degraded_with_backoff(self, session):
        _enroll(session)
        row = csvc.record_sync_attempt(session, success=False, error="boom")
        assert row.connection_state == csvc.CONN_DEGRADED
        assert row.consecutive_sync_failures == 1
        assert row.last_sync_error == "boom"
        assert row.next_reconnect_at is not None

    def test_offline_after_threshold_failures(self, session):
        _enroll(session)
        for _ in range(csvc.OFFLINE_AFTER_FAILURES):
            csvc.record_sync_attempt(session, success=False, error="down")
        row = csvc.get_coordinator(session)
        assert row.consecutive_sync_failures == csvc.OFFLINE_AFTER_FAILURES
        assert row.connection_state == csvc.CONN_OFFLINE

    def test_success_after_failures_resets_to_online(self, session):
        _enroll(session)
        for _ in range(5):
            csvc.record_sync_attempt(session, success=False, error="down")
        csvc.record_sync_attempt(session, success=True)
        row = csvc.get_coordinator(session)
        assert row.connection_state == csvc.CONN_ONLINE
        assert row.consecutive_sync_failures == 0
        assert row.next_reconnect_at is None

    def test_backoff_grows_then_caps(self, session):
        _enroll(session)
        # Drive enough failures that the raw exponential would exceed the
        # cap, and assert the gate never lands further out than the cap.
        last_gap = 0
        for _ in range(12):
            row = csvc.record_sync_attempt(session, success=False, error="x")
            gap = (row.next_reconnect_at - row.last_sync_at).total_seconds()
            assert gap <= csvc.RECONNECT_BACKOFF_CAP_SECONDS
            last_gap = gap
        assert last_gap == csvc.RECONNECT_BACKOFF_CAP_SECONDS


class TestShouldAttemptSync:
    def test_false_when_not_enrolled(self, session):
        # pending (start only) → not eligible
        csvc.start_enrollment(
            session, coordinator_url="https://c", coordinator_tls_cert_pem="c"
        )
        session.commit()
        assert csvc.should_attempt_sync(session) is False

    def test_true_when_enrolled_no_failures(self, session):
        _enroll(session)
        assert csvc.should_attempt_sync(session) is True

    def test_false_while_backoff_gate_in_future(self, session):
        _enroll(session)
        csvc.record_sync_attempt(session, success=False, error="x")
        session.commit()
        assert csvc.should_attempt_sync(session) is False

    def test_true_once_gate_elapses(self, session):
        _enroll(session)
        row = csvc.record_sync_attempt(session, success=False, error="x")
        # Simulate the gate having already passed.
        row.next_reconnect_at = row.last_sync_at - timedelta(seconds=1)
        session.commit()
        assert csvc.should_attempt_sync(session) is True

    def test_suspended_site_still_polls(self, session):
        _enroll(session)
        csvc.mark_suspended(session)
        session.commit()
        assert csvc.should_attempt_sync(session) is True


class TestAutonomy:
    def test_not_autonomous_when_online(self, session):
        _enroll(session)
        csvc.record_sync_attempt(session, success=True)
        session.commit()
        assert csvc.is_autonomous(session) is False

    def test_autonomous_when_enrolled_and_offline(self, session):
        _enroll(session)
        for _ in range(csvc.OFFLINE_AFTER_FAILURES):
            csvc.record_sync_attempt(session, success=False, error="down")
        session.commit()
        assert csvc.is_autonomous(session) is True

    def test_not_autonomous_when_only_degraded(self, session):
        _enroll(session)
        csvc.record_sync_attempt(session, success=False, error="down")
        session.commit()
        assert csvc.is_autonomous(session) is False


class TestConnectionHealthSnapshot:
    def test_unenrolled_snapshot(self, session):
        snap = csvc.connection_health(session)
        assert snap["state"] == csvc.CONN_UNKNOWN
        assert snap["enrolled"] is False
        assert snap["autonomous"] is False
        assert snap["consecutive_failures"] == 0

    def test_offline_snapshot_marks_autonomous(self, session):
        _enroll(session)
        for _ in range(csvc.OFFLINE_AFTER_FAILURES):
            csvc.record_sync_attempt(session, success=False, error="down")
        session.commit()
        snap = csvc.connection_health(session)
        assert snap["state"] == csvc.CONN_OFFLINE
        assert snap["enrolled"] is True
        assert snap["autonomous"] is True
        assert snap["consecutive_failures"] == csvc.OFFLINE_AFTER_FAILURES
