"""
Tests for the Phase 12.5 coordinator-side federation secret-lease service:
the request → issue → renew → revoke/expire lifecycle plus the reconcile
loop's work-lists (list_pending / list_expiring / expire_overdue) and the
retention prune.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.federation import (
    FED_LEASE_ACTIVE,
    FED_LEASE_EXPIRED,
    FED_LEASE_FAILED,
    FED_LEASE_REQUESTED,
    FED_LEASE_REVOKED,
    FederationSite,
)
from backend.services import federation_secret_lease_service as lsvc


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                Base.metadata.tables["federation_sites"],
                Base.metadata.tables["federation_secret_lease"],
            ],
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            yield s
    finally:
        engine.dispose()


@pytest.fixture
def site(session):
    s = FederationSite(id=uuid.uuid4(), name="a", url="https://a", status="enrolled")
    session.add(s)
    session.commit()
    return s


def _request(session, site, **kw):
    defaults = dict(
        site_id=site.id,
        host_id="host-1",
        secret_name="db-readonly",
        backend_role="readonly",
        kind="database",
        ttl_seconds=3600,
    )
    defaults.update(kw)
    lease = lsvc.record_requested_lease(session, **defaults)
    session.commit()
    return lease


class TestLifecycle:
    def test_request_starts_in_requested(self, session, site):
        lease = _request(session, site)
        assert lease.status == FED_LEASE_REQUESTED
        assert lease.vault_lease_id is None

    def test_request_dedups_on_correlation_key(self, session, site):
        a = _request(session, site, correlation_key="k1")
        b = lsvc.record_requested_lease(
            session,
            site_id=site.id,
            host_id="host-1",
            secret_name="db-readonly",
            backend_role="readonly",
            kind="database",
            correlation_key="k1",
        )
        assert a.id == b.id

    def test_issue_computes_expiry_from_ttl(self, session, site):
        lease = _request(session, site, ttl_seconds=120)
        lsvc.mark_issued(session, lease.id, vault_lease_id="vault/abc")
        session.commit()
        refreshed = lsvc.get_lease(session, lease.id)
        assert refreshed.status == FED_LEASE_ACTIVE
        assert refreshed.vault_lease_id == "vault/abc"
        assert refreshed.expires_at is not None

    def test_issue_stores_metadata_not_secret(self, session, site):
        lease = _request(session, site)
        lsvc.mark_issued(
            session,
            lease.id,
            vault_lease_id="v",
            secret_metadata={"username": "gen_user_x"},
        )
        session.commit()
        d = lsvc.to_dict(lsvc.get_lease(session, lease.id))
        assert d["secret_metadata"] == {"username": "gen_user_x"}

    def test_failed_is_terminal(self, session, site):
        lease = _request(session, site)
        lsvc.mark_failed(session, lease.id, error="vault down")
        session.commit()
        assert lsvc.get_lease(session, lease.id).status == FED_LEASE_FAILED

    def test_renew_pushes_expiry_out(self, session, site):
        lease = _request(session, site, ttl_seconds=60)
        lsvc.mark_issued(session, lease.id, vault_lease_id="v")
        session.commit()
        before = lsvc.get_lease(session, lease.id).expires_at
        lsvc.mark_renewed(session, lease.id, ttl_seconds=3600)
        session.commit()
        after = lsvc.get_lease(session, lease.id).expires_at
        assert after > before
        assert lsvc.get_lease(session, lease.id).last_renewed_at is not None

    def test_revoke_is_terminal(self, session, site):
        lease = _request(session, site)
        lsvc.mark_issued(session, lease.id, vault_lease_id="v")
        lsvc.mark_revoked(session, lease.id)
        session.commit()
        row = lsvc.get_lease(session, lease.id)
        assert row.status == FED_LEASE_REVOKED
        assert row.revoked_at is not None


class TestReconcileWorklists:
    def test_list_pending_returns_only_requested(self, session, site):
        a = _request(session, site, correlation_key="a")
        b = _request(session, site, correlation_key="b")
        lsvc.mark_issued(session, b.id, vault_lease_id="v")
        session.commit()
        pending = lsvc.list_pending(session)
        assert {p.id for p in pending} == {a.id}

    def test_list_expiring_within_window(self, session, site):
        soon = _request(session, site, correlation_key="soon")
        later = _request(session, site, correlation_key="later")
        lsvc.mark_issued(session, soon.id, vault_lease_id="v", ttl_seconds=30)
        lsvc.mark_issued(session, later.id, vault_lease_id="v", ttl_seconds=100000)
        session.commit()
        expiring = lsvc.list_expiring(session, within_seconds=120)
        assert {e.id for e in expiring} == {soon.id}

    def test_expire_overdue_marks_expired(self, session, site):
        lease = _request(session, site)
        lsvc.mark_issued(session, lease.id, vault_lease_id="v", ttl_seconds=60)
        session.commit()
        row = lsvc.get_lease(session, lease.id)
        row.expires_at = row.expires_at - timedelta(hours=2)  # backdate
        session.commit()
        n = lsvc.expire_overdue(session)
        session.commit()
        assert n == 1
        assert lsvc.get_lease(session, lease.id).status == FED_LEASE_EXPIRED

    def test_renew_revives_freshly_expired(self, session, site):
        lease = _request(session, site)
        lsvc.mark_issued(session, lease.id, vault_lease_id="v", ttl_seconds=60)
        session.commit()
        r = lsvc.get_lease(session, lease.id)
        r.expires_at = r.expires_at - timedelta(hours=2)
        session.commit()
        lsvc.expire_overdue(session)
        session.commit()
        lsvc.mark_renewed(session, lease.id, ttl_seconds=3600)
        session.commit()
        assert lsvc.get_lease(session, lease.id).status == FED_LEASE_ACTIVE


class TestListAndPrune:
    def test_list_filters_by_site_and_status(self, session, site):
        other = FederationSite(
            id=uuid.uuid4(), name="b", url="https://b", status="enrolled"
        )
        session.add(other)
        session.commit()
        _request(session, site, correlation_key="x")
        _request(session, other, correlation_key="y")
        rows = lsvc.list_leases(session, site_id=site.id)
        assert len(rows) == 1
        req = lsvc.list_leases(session, status=FED_LEASE_REQUESTED)
        assert len(req) == 2

    def test_prune_drops_old_terminal_only(self, session, site):
        keep = _request(session, site, correlation_key="keep")  # requested → kept
        old = _request(session, site, correlation_key="old")
        lsvc.mark_revoked(session, old.id)
        session.commit()
        row = lsvc.get_lease(session, old.id)
        row.requested_at = row.requested_at - timedelta(days=60)
        session.commit()
        n = lsvc.prune_terminal(session, older_than_days=14)
        session.commit()
        assert n == 1
        assert lsvc.get_lease(session, keep.id) is not None
        assert lsvc.get_lease(session, old.id) is None
