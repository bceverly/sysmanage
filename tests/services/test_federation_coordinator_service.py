"""
Tests for the Phase 12.2 site-side coordinator-connection service.

Covers:
  * Singleton row is auto-created on first mutating call.
  * ``start_enrollment`` validates input + persists URL/cert/interval.
  * Enrollment FSM (pending → enrolled → suspended → enrolled → removed).
  * Cannot switch coordinators mid-enrollment; ``clear_enrollment`` is the path.
  * ``record_sync_attempt`` populates last_sync_* without state changes.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.federation import (
    SINGLETON_FEDERATION_COORDINATOR_ID,
)
from backend.services import federation_coordinator_service as csvc

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
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables[t] for t in FEDERATION_TABLE_NAMES]
    )
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as s:
        yield s


# ---------------------------------------------------------------------
# Read-side helpers
# ---------------------------------------------------------------------


class TestGetCoordinator:
    def test_returns_none_when_absent(self, session):
        assert csvc.get_coordinator(session) is None

    def test_returns_singleton_after_start(self, session):
        csvc.start_enrollment(
            session,
            coordinator_url="https://coord.x",
            coordinator_tls_cert_pem="cert-data",
        )
        session.commit()
        row = csvc.get_coordinator(session)
        assert row is not None
        assert row.id == SINGLETON_FEDERATION_COORDINATOR_ID

    def test_is_enrolled_false_when_pending(self, session):
        csvc.start_enrollment(
            session,
            coordinator_url="https://coord.x",
            coordinator_tls_cert_pem="cert",
        )
        session.commit()
        assert csvc.is_enrolled(session) is False

    def test_is_enrolled_true_after_handshake(self, session):
        csvc.start_enrollment(
            session,
            coordinator_url="https://coord.x",
            coordinator_tls_cert_pem="cert",
        )
        csvc.mark_enrolled(session, site_id=uuid.uuid4(), site_tls_cert_pem="site-cert")
        session.commit()
        assert csvc.is_enrolled(session) is True


# ---------------------------------------------------------------------
# start_enrollment
# ---------------------------------------------------------------------


class TestStartEnrollment:
    def test_persists_inputs(self, session):
        csvc.start_enrollment(
            session,
            coordinator_url="https://coord.x",
            coordinator_tls_cert_pem="cert",
            sync_interval_seconds=600,
        )
        session.commit()
        row = csvc.get_coordinator(session)
        assert row.coordinator_url == "https://coord.x"
        assert row.coordinator_tls_cert_pem == "cert"
        assert row.sync_interval_seconds == 600
        assert row.enrollment_status == csvc.STATUS_PENDING

    def test_blank_url_raises(self, session):
        with pytest.raises(ValueError):
            csvc.start_enrollment(
                session,
                coordinator_url="   ",
                coordinator_tls_cert_pem="cert",
            )

    def test_blank_cert_raises(self, session):
        with pytest.raises(ValueError):
            csvc.start_enrollment(
                session,
                coordinator_url="https://coord.x",
                coordinator_tls_cert_pem="",
            )

    def test_zero_interval_raises(self, session):
        with pytest.raises(ValueError):
            csvc.start_enrollment(
                session,
                coordinator_url="https://coord.x",
                coordinator_tls_cert_pem="cert",
                sync_interval_seconds=0,
            )

    def test_re_start_with_same_url_refreshes_cert(self, session):
        """An operator re-running enrollment with the same coordinator
        URL just freshens the cert — no FSM bounce."""
        csvc.start_enrollment(
            session,
            coordinator_url="https://coord.x",
            coordinator_tls_cert_pem="cert-v1",
        )
        csvc.mark_enrolled(session, site_id=uuid.uuid4(), site_tls_cert_pem="site-cert")
        session.commit()
        csvc.start_enrollment(
            session,
            coordinator_url="https://coord.x",
            coordinator_tls_cert_pem="cert-v2",
        )
        session.commit()
        row = csvc.get_coordinator(session)
        assert row.coordinator_tls_cert_pem == "cert-v2"
        # FSM didn't bounce back to pending.
        assert row.enrollment_status == csvc.STATUS_ENROLLED

    def test_switch_coordinator_while_enrolled_raises(self, session):
        csvc.start_enrollment(
            session,
            coordinator_url="https://coord-a.x",
            coordinator_tls_cert_pem="cert",
        )
        csvc.mark_enrolled(session, site_id=uuid.uuid4(), site_tls_cert_pem="site-cert")
        session.commit()
        with pytest.raises(csvc.InvalidCoordinatorStateError):
            csvc.start_enrollment(
                session,
                coordinator_url="https://coord-b.x",
                coordinator_tls_cert_pem="cert",
            )


# ---------------------------------------------------------------------
# Enrollment lifecycle
# ---------------------------------------------------------------------


class TestEnrollmentLifecycle:
    def _pending(self, session):
        csvc.start_enrollment(
            session,
            coordinator_url="https://coord.x",
            coordinator_tls_cert_pem="cert",
        )
        session.commit()

    def test_pending_to_enrolled(self, session):
        self._pending(session)
        sid = uuid.uuid4()
        csvc.mark_enrolled(session, site_id=sid, site_tls_cert_pem="sc")
        session.commit()
        row = csvc.get_coordinator(session)
        assert row.enrollment_status == csvc.STATUS_ENROLLED
        assert row.site_id == sid
        assert row.site_tls_cert_pem == "sc"
        assert row.enrolled_at is not None

    def test_blank_site_cert_raises(self, session):
        self._pending(session)
        with pytest.raises(ValueError):
            csvc.mark_enrolled(session, site_id=uuid.uuid4(), site_tls_cert_pem="")

    def test_enrolled_to_suspended(self, session):
        self._pending(session)
        csvc.mark_enrolled(session, site_id=uuid.uuid4(), site_tls_cert_pem="sc")
        csvc.mark_suspended(session)
        session.commit()
        assert csvc.get_coordinator(session).enrollment_status == csvc.STATUS_SUSPENDED

    def test_suspend_when_not_enrolled_raises(self, session):
        self._pending(session)
        with pytest.raises(csvc.InvalidCoordinatorStateError):
            csvc.mark_suspended(session)

    def test_suspended_can_resume_via_mark_enrolled(self, session):
        self._pending(session)
        csvc.mark_enrolled(session, site_id=uuid.uuid4(), site_tls_cert_pem="sc")
        csvc.mark_suspended(session)
        csvc.mark_enrolled(session, site_id=uuid.uuid4(), site_tls_cert_pem="sc")
        session.commit()
        assert csvc.get_coordinator(session).enrollment_status == csvc.STATUS_ENROLLED

    def test_mark_removed_is_terminal(self, session):
        self._pending(session)
        csvc.mark_enrolled(session, site_id=uuid.uuid4(), site_tls_cert_pem="sc")
        csvc.mark_removed(session)
        session.commit()
        row = csvc.get_coordinator(session)
        assert row.enrollment_status == csvc.STATUS_REMOVED

    def test_clear_enrollment_resets_to_pending(self, session):
        self._pending(session)
        csvc.mark_enrolled(session, site_id=uuid.uuid4(), site_tls_cert_pem="sc")
        csvc.mark_removed(session)
        session.commit()
        csvc.clear_enrollment(session)
        session.commit()
        row = csvc.get_coordinator(session)
        assert row.enrollment_status == csvc.STATUS_PENDING
        assert row.coordinator_url is None
        assert row.coordinator_tls_cert_pem is None
        assert row.site_id is None
        assert row.site_tls_cert_pem is None
        assert row.enrolled_at is None


# ---------------------------------------------------------------------
# Sync attempt recording
# ---------------------------------------------------------------------


class TestRecordSyncAttempt:
    def test_success_recorded(self, session):
        csvc.start_enrollment(
            session,
            coordinator_url="https://coord.x",
            coordinator_tls_cert_pem="c",
        )
        csvc.mark_enrolled(session, site_id=uuid.uuid4(), site_tls_cert_pem="sc")
        csvc.record_sync_attempt(session, success=True)
        session.commit()
        row = csvc.get_coordinator(session)
        assert row.last_sync_at is not None
        assert row.last_sync_status == "success"
        assert row.last_sync_error is None

    def test_failure_recorded(self, session):
        csvc.start_enrollment(
            session,
            coordinator_url="https://coord.x",
            coordinator_tls_cert_pem="c",
        )
        csvc.record_sync_attempt(session, success=False, error="conn refused")
        session.commit()
        row = csvc.get_coordinator(session)
        assert row.last_sync_status == "conn refused"
        assert row.last_sync_error == "conn refused"

    def test_does_not_change_enrollment_status(self, session):
        csvc.start_enrollment(
            session,
            coordinator_url="https://coord.x",
            coordinator_tls_cert_pem="c",
        )
        csvc.record_sync_attempt(session, success=False, error="anything")
        session.commit()
        assert csvc.get_coordinator(session).enrollment_status == csvc.STATUS_PENDING
