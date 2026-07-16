# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the Phase 12.1.B federation site service layer.

Covers:
  * Token generation produces high-entropy plaintext + a matching SHA-256 hash.
  * ``create_site`` writes the row, hashes the token, and audit-logs.
  * ``complete_enrollment`` matches by token hash + scrubs the token.
  * State transitions (suspend / resume / remove) enforce the FSM.
  * Audit-log entries are written for every mutating operation.

Each test runs against an in-memory SQLite engine bootstrapped from
the SQLAlchemy ``Base.metadata`` for just the federation tables —
no Alembic, no external state.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import hashlib

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.federation import (
    FederationAuditLog,
    FederationSite,
)
from backend.services import federation_site_service as svc
from tests.federation_crypto import (
    enroll_site,
    make_identity_keypair,
    make_self_signed_cert,
    quick_enroll,
    sign_enrollment_proof,
)

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
    "federation_site_sync_event",
    "federation_coordinator",
    "federation_sync_queue",
    "federation_received_policies",
    "federation_received_commands",
]


@pytest.fixture
def session():
    """Fresh in-memory SQLite + a session.  Each test is hermetic.

    ``engine.dispose()`` is in the ``finally`` so we don't leave
    sqlite3.Connection objects pending GC across the test run —
    pytest's ``ResourceWarning: unclosed database`` plumbing
    surfaces every undisposed engine, and on a 5000-test sweep
    those warnings become the bulk of the output.
    """
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine,
            tables=[Base.metadata.tables[t] for t in FEDERATION_TABLE_NAMES],
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            yield s
    finally:
        engine.dispose()


# ---------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------


class TestEnrollmentTokens:
    def test_token_has_expected_entropy(self):
        plain, _ = svc.generate_enrollment_token()
        # URL-safe base64 of 32 bytes -> ~43 chars (44 with padding stripped).
        assert len(plain) >= 40

    def test_two_calls_produce_distinct_tokens(self):
        a, _ = svc.generate_enrollment_token()
        b, _ = svc.generate_enrollment_token()
        assert a != b

    def test_hash_matches_sha256_of_plaintext(self):
        plain, h = svc.generate_enrollment_token()
        assert h == hashlib.sha256(plain.encode()).hexdigest()


# ---------------------------------------------------------------------
# create_site
# ---------------------------------------------------------------------


class TestCreateSite:
    def test_writes_row_with_pending_status(self, session):
        site, token = svc.create_site(
            session,
            name="Cleveland",
            url="https://sysmanage.cle.example.com",
            actor_userid="admin@x",
        )
        session.commit()

        assert site.id is not None
        assert site.name == "Cleveland"
        assert site.status == svc.STATUS_PENDING
        assert site.enrollment_token_hash == hashlib.sha256(token.encode()).hexdigest()

    def test_audits_enrollment_started(self, session):
        site, _ = svc.create_site(
            session,
            name="Cleveland",
            url="https://sysmanage.cle.example.com",
            actor_userid="admin@x",
        )
        session.commit()
        entries = (
            session.query(FederationAuditLog)
            .filter_by(operation=svc.AUDIT_OP_SITE_ENROLLMENT_STARTED)
            .all()
        )
        assert len(entries) == 1
        assert entries[0].target_site_id == site.id
        assert entries[0].actor_userid == "admin@x"

    def test_duplicate_name_raises(self, session):
        svc.create_site(session, name="Cleveland", url="https://a.x")
        session.commit()
        with pytest.raises(svc.SiteNameConflictError):
            svc.create_site(session, name="Cleveland", url="https://b.x")

    def test_blank_name_raises(self, session):
        with pytest.raises(ValueError):
            svc.create_site(session, name="   ", url="https://a.x")

    def test_blank_url_raises(self, session):
        with pytest.raises(ValueError):
            svc.create_site(session, name="Cleveland", url="")

    def test_optional_fields_persist(self, session):
        site, _ = svc.create_site(
            session,
            name="Cleveland",
            url="https://a.x",
            location_label="Cleveland DC1",
            sync_interval_seconds=120,
            agent_version_min="2.3.0.19",
            geo_latitude=41.4993,
            geo_longitude=-81.6944,
            geo_country_code="US",
        )
        session.commit()
        assert site.location_label == "Cleveland DC1"
        assert site.sync_interval_seconds == 120
        assert site.agent_version_min == "2.3.0.19"
        assert site.geo_country_code == "US"


# ---------------------------------------------------------------------
# complete_enrollment
# ---------------------------------------------------------------------


class TestCompleteEnrollment:
    def test_valid_token_flips_to_enrolled(self, session):
        priv, pub = make_identity_keypair()
        cert = make_self_signed_cert("cle")
        _, token = svc.create_site(
            session,
            name="Cleveland",
            url="https://a.x",
            site_identity_public_key_pem=pub,
        )
        session.commit()
        proof = sign_enrollment_proof(priv, role="site", tls_cert_pem=cert)
        site, bearer, _coord_outbound = svc.complete_enrollment(
            session,
            plaintext_token=token,
            tls_cert_pem=cert,
            identity_proof_b64=proof,
            actor_userid="site@itself",
        )
        session.commit()

        assert site.status == svc.STATUS_ENROLLED
        # Enrollment-token hash is scrubbed so it can't be replayed.
        assert site.enrollment_token_hash is None
        assert site.tls_cert_pem.startswith("-----BEGIN CERTIFICATE-----")
        # Phase 12.6: long-lived sync bearer is minted on completion.
        # Plaintext is returned exactly once; only the hash persists.
        assert bearer  # non-empty plaintext
        assert site.sync_bearer_token_hash is not None
        assert site.sync_bearer_token_hash == svc._hash_token(bearer)
        # Plaintext != hash — confirms we didn't accidentally store
        # the plaintext on the row.
        assert bearer != site.sync_bearer_token_hash

    def test_invalid_token_raises(self, session):
        svc.create_site(session, name="Cleveland", url="https://a.x")
        session.commit()
        with pytest.raises(svc.InvalidEnrollmentTokenError):
            svc.complete_enrollment(
                session,
                plaintext_token="not-the-real-token",
                tls_cert_pem="-----BEGIN CERTIFICATE-----\n...\n",
            )

    def test_empty_token_raises(self, session):
        with pytest.raises(svc.InvalidEnrollmentTokenError):
            svc.complete_enrollment(session, plaintext_token="", tls_cert_pem="x")

    def test_empty_cert_raises(self, session):
        _, token = svc.create_site(session, name="Cleveland", url="https://a.x")
        with pytest.raises(ValueError):
            svc.complete_enrollment(session, plaintext_token=token, tls_cert_pem="")

    def test_already_enrolled_token_cannot_be_reused(self, session):
        priv, pub = make_identity_keypair()
        cert = make_self_signed_cert("cle")
        _, token = svc.create_site(
            session,
            name="Cleveland",
            url="https://a.x",
            site_identity_public_key_pem=pub,
        )
        proof = sign_enrollment_proof(priv, role="site", tls_cert_pem=cert)
        svc.complete_enrollment(
            session, plaintext_token=token, tls_cert_pem=cert, identity_proof_b64=proof
        )
        session.commit()
        # Re-presenting the same token after scrubbing must fail.
        with pytest.raises(svc.InvalidEnrollmentTokenError):
            svc.complete_enrollment(
                session,
                plaintext_token=token,
                tls_cert_pem=cert,
                identity_proof_b64=proof,
            )

    def test_audits_enrollment_completed(self, session):
        site, _bearer, _outbound = enroll_site(
            session, name="Cleveland", url="https://a.x"
        )
        session.commit()
        entries = (
            session.query(FederationAuditLog)
            .filter_by(operation=svc.AUDIT_OP_SITE_ENROLLMENT_COMPLETED)
            .all()
        )
        assert len(entries) == 1
        assert entries[0].target_site_id == site.id


# ---------------------------------------------------------------------
# Lookups + listing
# ---------------------------------------------------------------------


class TestGetters:
    def test_get_site_returns_site(self, session):
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        session.commit()
        assert svc.get_site(session, site.id).id == site.id

    def test_get_site_raises_for_missing(self, session):
        import uuid

        with pytest.raises(svc.SiteNotFoundError):
            svc.get_site(session, uuid.uuid4())

    def test_get_site_accepts_uuid_string(self, session):
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        session.commit()
        # Service should coerce the str representation.
        result = svc.get_site(session, str(site.id))
        assert result.id == site.id

    def test_get_site_by_name_returns_none_for_missing(self, session):
        assert svc.get_site_by_name(session, "nope") is None

    def test_get_site_by_name_returns_none_for_empty(self, session):
        assert svc.get_site_by_name(session, "") is None

    def test_list_excludes_removed_by_default(self, session):
        s_keep, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        s_dead, _ = svc.create_site(session, name="DeadDC", url="https://b.x")
        svc.remove_site(session, s_dead.id)
        session.commit()
        names = {s.name for s in svc.list_sites(session)}
        assert "Cleveland" in names
        assert "DeadDC" not in names

    def test_list_include_removed_returns_all(self, session):
        s_keep, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        s_dead, _ = svc.create_site(session, name="DeadDC", url="https://b.x")
        svc.remove_site(session, s_dead.id)
        session.commit()
        names = {s.name for s in svc.list_sites(session, include_removed=True)}
        assert {"Cleveland", "DeadDC"}.issubset(names)

    def test_list_filtered_by_status(self, session):
        a, _ = svc.create_site(session, name="A", url="https://a.x")
        b, _bearer, _outbound = enroll_site(session, name="B", url="https://b.x")
        session.commit()
        pending = svc.list_sites(session, status=svc.STATUS_PENDING)
        enrolled = svc.list_sites(session, status=svc.STATUS_ENROLLED)
        assert [s.name for s in pending] == ["A"]
        assert [s.name for s in enrolled] == ["B"]


# ---------------------------------------------------------------------
# update_site
# ---------------------------------------------------------------------


class TestUpdateSite:
    def test_updates_allowed_fields(self, session):
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        session.commit()
        svc.update_site(
            session, site.id, location_label="DC1", sync_interval_seconds=600
        )
        session.commit()
        assert site.location_label == "DC1"
        assert site.sync_interval_seconds == 600

    def test_rejects_unknown_field(self, session):
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        session.commit()
        with pytest.raises(ValueError):
            svc.update_site(session, site.id, status="enrolled")

    def test_rejects_token_field(self, session):
        """``enrollment_token_hash`` must not be patchable via update_site
        — it's managed exclusively by ``complete_enrollment``."""
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        with pytest.raises(ValueError):
            svc.update_site(session, site.id, enrollment_token_hash="x")

    def test_rejects_update_on_removed_site(self, session):
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        svc.remove_site(session, site.id)
        session.commit()
        with pytest.raises(svc.InvalidSiteStateError):
            svc.update_site(session, site.id, location_label="X")

    def test_rename_to_existing_name_raises(self, session):
        svc.create_site(session, name="A", url="https://a.x")
        b, _ = svc.create_site(session, name="B", url="https://b.x")
        session.commit()
        with pytest.raises(svc.SiteNameConflictError):
            svc.update_site(session, b.id, name="A")

    def test_no_op_update_does_not_audit(self, session):
        site, _ = svc.create_site(
            session, name="Cleveland", url="https://a.x", location_label="DC1"
        )
        session.commit()
        before = session.query(FederationAuditLog).count()
        svc.update_site(session, site.id, location_label="DC1")  # same value
        session.commit()
        after = session.query(FederationAuditLog).count()
        assert before == after


# ---------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------


class TestStateTransitions:
    def _enrolled(self, session):
        site = quick_enroll(session, name="Cleveland", url="https://a.x")
        session.commit()
        return site

    def test_suspend_enrolled(self, session):
        site = self._enrolled(session)
        svc.suspend_site(session, site.id, actor_userid="admin@x")
        session.commit()
        assert site.status == svc.STATUS_SUSPENDED

    def test_suspend_pending_raises(self, session):
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        session.commit()
        with pytest.raises(svc.InvalidSiteStateError):
            svc.suspend_site(session, site.id)

    def test_resume_suspended(self, session):
        site = self._enrolled(session)
        svc.suspend_site(session, site.id)
        session.commit()
        svc.resume_site(session, site.id)
        session.commit()
        assert site.status == svc.STATUS_ENROLLED

    def test_resume_non_suspended_raises(self, session):
        site = self._enrolled(session)
        with pytest.raises(svc.InvalidSiteStateError):
            svc.resume_site(session, site.id)

    def test_remove_from_any_status(self, session):
        site = self._enrolled(session)
        svc.remove_site(session, site.id)
        session.commit()
        assert site.status == svc.STATUS_REMOVED

    def test_remove_pending_scrubs_token(self, session):
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        assert site.enrollment_token_hash is not None
        svc.remove_site(session, site.id)
        session.commit()
        assert site.status == svc.STATUS_REMOVED
        assert site.enrollment_token_hash is None

    def test_remove_enrolled_scrubs_sync_bearer(self, session):
        # Phase 12.6: removing a site must invalidate its sync bearer
        # so a leaked plaintext token can't keep pushing rollup data
        # after administrative removal.
        site = quick_enroll(session, name="Cleveland", url="https://a.x")
        session.commit()
        assert site.sync_bearer_token_hash is not None
        svc.remove_site(session, site.id)
        session.commit()
        assert site.status == svc.STATUS_REMOVED
        assert site.sync_bearer_token_hash is None

    def test_remove_is_idempotent(self, session):
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        svc.remove_site(session, site.id)
        session.commit()
        before = session.query(FederationAuditLog).count()
        svc.remove_site(session, site.id)  # no-op second time
        session.commit()
        assert session.query(FederationAuditLog).count() == before

    def test_each_transition_audits_once(self, session):
        site = self._enrolled(session)
        before = (
            session.query(FederationAuditLog).filter_by(target_site_id=site.id).count()
        )
        svc.suspend_site(session, site.id)
        svc.resume_site(session, site.id)
        svc.remove_site(session, site.id)
        session.commit()
        after = (
            session.query(FederationAuditLog).filter_by(target_site_id=site.id).count()
        )
        # 3 new audit entries: suspended, resumed, removed.
        assert after - before == 3


# ---------------------------------------------------------------------
# record_sync
# ---------------------------------------------------------------------


class TestRecordSync:
    def test_success_updates_columns(self, session):
        site = quick_enroll(session, name="Cleveland", url="https://a.x")
        session.commit()
        svc.record_sync(session, site.id, success=True, host_count=42)
        session.commit()
        assert site.last_sync_at is not None
        assert site.last_sync_status == "success"
        assert site.host_count == 42

    def test_failure_records_error(self, session):
        site = quick_enroll(session, name="Cleveland", url="https://a.x")
        session.commit()
        svc.record_sync(session, site.id, success=False, error="network_timeout")
        session.commit()
        assert site.last_sync_status == "network_timeout"

    def test_does_not_audit(self, session):
        """Sync events are too frequent to audit-per-row."""
        site = quick_enroll(session, name="Cleveland", url="https://a.x")
        session.commit()
        before = session.query(FederationAuditLog).count()
        svc.record_sync(session, site.id, success=True)
        session.commit()
        assert session.query(FederationAuditLog).count() == before

    def test_missing_site_raises(self, session):
        import uuid

        with pytest.raises(svc.SiteNotFoundError):
            svc.record_sync(session, uuid.uuid4(), success=True)


# ---------------------------------------------------------------------
# Phase 12.1.C: enrollment timestamps, TTL, cancel, regenerate
# ---------------------------------------------------------------------


class TestEnrollmentTimestamps:
    """``create_site`` stamps ``enrollment_token_expires_at``;
    ``complete_enrollment`` stamps ``enrolled_at`` and scrubs the
    expiry along with the hash."""

    def test_create_sets_token_expiry(self, session):
        site, _ = svc.create_site(
            session, name="Cleveland", url="https://a.x", token_ttl_hours=2
        )
        session.commit()
        assert site.enrollment_token_expires_at is not None
        # The expiry should be ~2h in the future; allow ±1 min slop
        # for clock granularity / test runtime.
        from datetime import datetime, timedelta, timezone

        expected = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2)
        delta = abs((site.enrollment_token_expires_at - expected).total_seconds())
        assert delta < 60

    def test_create_uses_default_ttl_when_omitted(self, session):
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        session.commit()
        from datetime import datetime, timedelta, timezone

        expected = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
            hours=svc.DEFAULT_ENROLLMENT_TOKEN_TTL_HOURS
        )
        delta = abs((site.enrollment_token_expires_at - expected).total_seconds())
        assert delta < 60

    def test_create_zero_ttl_raises(self, session):
        with pytest.raises(ValueError):
            svc.create_site(
                session, name="Cleveland", url="https://a.x", token_ttl_hours=0
            )

    def test_complete_stamps_enrolled_at_and_scrubs_expiry(self, session):
        site, _bearer, _outbound = enroll_site(
            session, name="Cleveland", url="https://a.x"
        )
        session.commit()
        assert site.enrolled_at is not None
        assert site.enrollment_token_expires_at is None
        assert site.enrollment_token_hash is None

    def test_expired_token_raises(self, session):
        """A token that matches but is past TTL must raise the
        TTL-specific error so the router can show 'expired, ask admin
        to regenerate' rather than 'unknown token'."""
        from datetime import datetime, timedelta, timezone

        site, token = svc.create_site(session, name="Cleveland", url="https://a.x")
        # Hand-roll an expired token by rewinding the expiry.
        site.enrollment_token_expires_at = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) - timedelta(seconds=10)
        session.commit()
        with pytest.raises(svc.EnrollmentTokenExpiredError):
            svc.complete_enrollment(session, plaintext_token=token, tls_cert_pem="cert")


class TestCancelEnrollment:
    def test_pending_site_cancels(self, session):
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        session.commit()
        svc.cancel_enrollment(session, site.id, actor_userid="admin@x")
        session.commit()
        assert site.status == svc.STATUS_REMOVED
        assert site.enrollment_token_hash is None
        assert site.enrollment_token_expires_at is None

    def test_audits_cancellation(self, session):
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        session.commit()
        svc.cancel_enrollment(session, site.id, actor_userid="admin@x")
        session.commit()
        from backend.persistence.models.federation import (
            FederationAuditLog,  # noqa: PLC0415
        )

        entries = (
            session.query(FederationAuditLog)
            .filter_by(operation=svc.AUDIT_OP_SITE_ENROLLMENT_CANCELLED)
            .all()
        )
        assert len(entries) == 1
        assert entries[0].target_site_id == site.id

    def test_enrolled_site_cannot_be_cancelled(self, session):
        """Cancellation is for *pending* enrollment only — flipping an
        already-enrolled site needs ``remove_site``, not cancel.  This
        is what the operator path expects."""
        site = quick_enroll(session, name="Cleveland", url="https://a.x")
        session.commit()
        with pytest.raises(svc.InvalidSiteStateError):
            svc.cancel_enrollment(session, site.id)


class TestRegenerateEnrollmentToken:
    def test_regenerates_with_new_value(self, session):
        site, original_token = svc.create_site(
            session, name="Cleveland", url="https://a.x"
        )
        session.commit()
        original_hash = site.enrollment_token_hash

        _, new_token = svc.regenerate_enrollment_token(
            session, site.id, actor_userid="admin@x"
        )
        session.commit()

        assert new_token != original_token
        assert site.enrollment_token_hash != original_hash
        # Old plaintext should no longer match.
        with pytest.raises(svc.InvalidEnrollmentTokenError):
            svc.complete_enrollment(
                session, plaintext_token=original_token, tls_cert_pem="c"
            )

    def test_new_token_can_complete_enrollment(self, session):
        priv, pub = make_identity_keypair()
        cert = make_self_signed_cert("cle")
        site, _ = svc.create_site(
            session,
            name="Cleveland",
            url="https://a.x",
            site_identity_public_key_pem=pub,
        )
        session.commit()
        _, new_token = svc.regenerate_enrollment_token(session, site.id)
        session.commit()
        proof = sign_enrollment_proof(priv, role="site", tls_cert_pem=cert)
        svc.complete_enrollment(
            session,
            plaintext_token=new_token,
            tls_cert_pem=cert,
            identity_proof_b64=proof,
        )
        session.commit()
        assert site.status == svc.STATUS_ENROLLED

    def test_regenerate_resets_expiry(self, session):
        from datetime import datetime, timedelta, timezone

        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        # Force the expiry into the past so we can verify regenerate
        # moves it forward.
        site.enrollment_token_expires_at = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) - timedelta(hours=1)
        session.commit()
        svc.regenerate_enrollment_token(session, site.id, token_ttl_hours=3)
        session.commit()
        expected = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=3)
        delta = abs((site.enrollment_token_expires_at - expected).total_seconds())
        assert delta < 60

    def test_audits_token_regeneration(self, session):
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        session.commit()
        svc.regenerate_enrollment_token(session, site.id, actor_userid="admin@x")
        session.commit()
        from backend.persistence.models.federation import (
            FederationAuditLog,  # noqa: PLC0415
        )

        entries = (
            session.query(FederationAuditLog)
            .filter_by(operation=svc.AUDIT_OP_SITE_TOKEN_REGENERATED)
            .all()
        )
        assert len(entries) == 1

    def test_cannot_regenerate_for_enrolled_site(self, session):
        site = quick_enroll(session, name="Cleveland", url="https://a.x")
        session.commit()
        with pytest.raises(svc.InvalidSiteStateError):
            svc.regenerate_enrollment_token(session, site.id)

    def test_zero_ttl_raises(self, session):
        site, _ = svc.create_site(session, name="Cleveland", url="https://a.x")
        with pytest.raises(ValueError):
            svc.regenerate_enrollment_token(session, site.id, token_ttl_hours=0)


# ---------------------------------------------------------------------------
# Phase 12.6: sync bearer token (long-lived site → coordinator auth)
# ---------------------------------------------------------------------------


class TestSyncBearerToken:
    def test_generate_returns_plaintext_and_hash(self):
        plaintext, sha = svc.generate_sync_bearer_token()
        assert plaintext
        assert sha
        assert plaintext != sha
        # Hash must be deterministic for the same plaintext.
        assert svc._hash_token(plaintext) == sha

    def test_lookup_matches_enrolled_site(self, session):
        site, bearer, _coord_outbound = enroll_site(
            session, name="Cleveland", url="https://a.x"
        )
        session.commit()
        resolved = svc.find_site_by_sync_bearer_token(session, bearer)
        assert resolved is not None
        assert resolved.id == site.id

    def test_lookup_returns_none_for_unknown_token(self, session):
        # Set up an enrolled site so the DB isn't trivially empty.
        quick_enroll(session, name="Cleveland", url="https://a.x")
        session.commit()
        assert svc.find_site_by_sync_bearer_token(session, "not-a-real-token") is None

    def test_lookup_returns_none_for_empty_token(self, session):
        assert svc.find_site_by_sync_bearer_token(session, "") is None

    def test_lookup_rejects_suspended_site(self, session):
        # Suspended sites can't push data — only ``status='enrolled'``
        # rows are valid bearer-token holders.
        site, bearer, _coord_outbound = enroll_site(
            session, name="Cleveland", url="https://a.x"
        )
        session.commit()
        svc.suspend_site(session, site.id)
        session.commit()
        assert svc.find_site_by_sync_bearer_token(session, bearer) is None

    def test_lookup_rejects_removed_site(self, session):
        # Removed sites have their bearer hash scrubbed entirely
        # (verified in TestRemoveSite); this confirms the lookup-side
        # gate also short-circuits on status.
        site, bearer, _coord_outbound = enroll_site(
            session, name="Cleveland", url="https://a.x"
        )
        session.commit()
        svc.remove_site(session, site.id)
        session.commit()
        assert svc.find_site_by_sync_bearer_token(session, bearer) is None

    def test_two_sites_get_distinct_bearers(self, session):
        _a, ba, _ = enroll_site(session, name="Alpha", url="https://a.x")
        _b, bb, _ = enroll_site(session, name="Bravo", url="https://b.x")
        session.commit()
        assert ba != bb
        # Each bearer resolves to its own site.
        assert svc.find_site_by_sync_bearer_token(session, ba).name == "Alpha"
        assert svc.find_site_by_sync_bearer_token(session, bb).name == "Bravo"
