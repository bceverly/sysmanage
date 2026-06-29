"""Phase 12.5 — federation-aware dynamic-secret rotation + delivery.

Two layers:

  * Pure-OSS primitives — ``dynamic_secrets.renew_lease`` (in-place rotation)
    and the lease-service work-lists (``mark_delivered`` /
    ``list_rotation_candidates``) — with a stubbed Vault.
  * The live controller-engine reconcile pass driven over a real in-memory DB +
    a stubbed Vault + a mocked push transport: a requested lease is issued AND
    delivered to the site; a delivery that fails is rotated + re-delivered on
    the next pass; a lease nearing expiry is rotated before it can lapse.

The reconcile lives in the Pro+ ``federation_controller_engine`` ``.so``; the
engine tests skip automatically when it isn't built.
"""

# pylint: disable=redefined-outer-name,protected-access,import-outside-toplevel

import logging
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence import models  # noqa: F401  # register all models
from backend.persistence.db import Base
from backend.persistence.models.dynamic_secrets import LEASE_ACTIVE, DynamicSecretLease
from backend.persistence.models.federation import (
    FED_LEASE_ACTIVE,
    FED_LEASE_REQUESTED,
    FederationSecretLease,
)
from backend.services import dynamic_secrets as ds_svc
from backend.services import federation_secret_lease_service as lease_svc
from tests.federation_crypto import enroll_site


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def session():
    sa_engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(sa_engine)
        with sessionmaker(bind=sa_engine, expire_on_commit=False)() as s:
            yield s
    finally:
        sa_engine.dispose()


def _stub_vault():
    """Patch VaultService so issue/renew never touch a real OpenBAO."""
    ctx = patch("backend.services.dynamic_secrets.VaultService")
    vs = ctx.start()
    vs.return_value.mount_path = "secret"
    vs.return_value._make_request.return_value = {}
    return ctx


# ---------------------------------------------------------------------------
# OSS primitive: renew_lease (in-place rotation)
# ---------------------------------------------------------------------------


class TestRenewLease:
    def test_rotates_value_and_refreshes_row(self, session):
        ctx = _stub_vault()
        try:
            lease = DynamicSecretLease(
                id=uuid.uuid4(),
                name="db",
                kind="database",
                backend_role="readonly",
                vault_lease_id="dyn/abc",
                ttl_seconds=3600,
                issued_at=_now() - timedelta(hours=1),
                expires_at=_now() - timedelta(minutes=1),  # already lapsed
                status="EXPIRED",
                secret_metadata={"vault_path": "dyn/abc"},
            )
            session.add(lease)
            session.commit()

            result = ds_svc.renew_lease(
                session,
                vault_lease_id="dyn/abc",
                kind="database",
                backend_role="readonly",
                ttl_seconds=3600,
            )
            assert result["secret"]  # a fresh plaintext value
            assert result["ttl_seconds"] == 3600
            session.refresh(lease)
            # Row revived + expiry pushed into the future.
            assert lease.status == LEASE_ACTIVE
            assert lease.expires_at > _now()
        finally:
            ctx.stop()

    def test_works_without_a_local_row(self, session):
        """A federation lease whose local DynamicSecretLease row is absent still
        rotates in Vault (delivery is what matters)."""
        ctx = _stub_vault()
        try:
            result = ds_svc.renew_lease(
                session,
                vault_lease_id="dyn/orphan",
                kind="token",
                backend_role="r",
                ttl_seconds=300,
            )
            assert result["secret"]
        finally:
            ctx.stop()

    def test_bad_kind_raises(self, session):
        with pytest.raises(ds_svc.DynamicSecretError):
            ds_svc.renew_lease(
                session, vault_lease_id="x", kind="bogus", backend_role="r"
            )

    def test_missing_vault_id_raises(self, session):
        with pytest.raises(ds_svc.DynamicSecretError):
            ds_svc.renew_lease(
                session, vault_lease_id="", kind="database", backend_role="r"
            )

    def test_vault_failure_raises(self, session):
        ctx = patch("backend.services.dynamic_secrets.VaultService")
        vs = ctx.start()
        try:
            vs.return_value.mount_path = "secret"
            vs.return_value._make_request.side_effect = ds_svc.VaultError("boom")
            with pytest.raises(ds_svc.DynamicSecretError):
                ds_svc.renew_lease(
                    session,
                    vault_lease_id="dyn/abc",
                    kind="database",
                    backend_role="r",
                    ttl_seconds=300,
                )
        finally:
            ctx.stop()


# ---------------------------------------------------------------------------
# OSS work-lists: mark_delivered + list_rotation_candidates
# ---------------------------------------------------------------------------


def _active_lease(session, *, delivered, expires_in_seconds, vault="dyn/x"):
    row = FederationSecretLease(
        site_id=uuid.uuid4(),
        host_id="h",
        secret_name="s",
        backend_role="r",
        kind="database",
        status=FED_LEASE_ACTIVE,
        vault_lease_id=vault,
        ttl_seconds=3600,
        issued_at=_now(),
        expires_at=_now() + timedelta(seconds=expires_in_seconds),
        delivered_at=_now() if delivered else None,
    )
    session.add(row)
    session.flush()
    return row


class TestRotationWorkLists:
    def test_mark_delivered_stamps_time(self, session):
        row = _active_lease(session, delivered=False, expires_in_seconds=9999)
        lease_svc.mark_delivered(session, row.id)
        session.commit()  # the helper mutates; the caller commits
        session.refresh(row)
        assert row.delivered_at is not None

    def test_candidates_include_expiring_and_undelivered_only(self, session):
        expiring = _active_lease(
            session, delivered=True, expires_in_seconds=30, vault="dyn/exp"
        )
        undelivered = _active_lease(
            session, delivered=False, expires_in_seconds=9999, vault="dyn/und"
        )
        # Healthy: delivered AND far from expiry → not a candidate.
        _active_lease(session, delivered=True, expires_in_seconds=9999, vault="dyn/ok")
        # Never issued (no vault id) → excluded even though undelivered.
        no_vault = _active_lease(
            session, delivered=False, expires_in_seconds=9999, vault=None
        )
        session.commit()

        ids = {
            row.id
            for row in lease_svc.list_rotation_candidates(session, within_seconds=90)
        }
        assert expiring.id in ids
        assert undelivered.id in ids
        assert no_vault.id not in ids
        assert len(ids) == 2


# ---------------------------------------------------------------------------
# Live engine reconcile: issue→deliver, redeliver-on-failure, rotate-on-expiry
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def engine_mod():
    from tests._engine_loader import require_engine

    return require_engine("federation_controller_engine")


@pytest.fixture
def reconcile_env():
    sa_engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(sa_engine)
    Session = sessionmaker(bind=sa_engine, expire_on_commit=False)

    def db_maker():
        sess = Session()
        try:
            yield sess
        finally:
            sess.close()

    try:
        yield Session, db_maker
    finally:
        sa_engine.dispose()


def _http_client(status_code):
    client = AsyncMock()
    resp = AsyncMock()
    resp.status_code = status_code
    resp.text = ""
    client.post.return_value = resp
    return client


def _seed_requested(session_factory):
    """Enroll a deliverable site + record one requested lease; return its id."""
    with session_factory() as sess:
        site, _bearer, _outbound = enroll_site(
            sess, name="s1", url="https://s1.example.com"
        )
        sess.commit()
        lease = lease_svc.record_requested_lease(
            sess,
            site_id=site.id,
            host_id="host-1",
            secret_name="db-readonly",
            backend_role="readonly",
            kind="database",
            ttl_seconds=3600,
            correlation_key="corr-1",
        )
        sess.commit()
        return lease.id


@pytest.mark.asyncio
async def test_reconcile_issues_and_delivers(engine_mod, reconcile_env):
    Session, db_maker = reconcile_env
    lease_id = _seed_requested(Session)
    ctx = _stub_vault()
    try:
        client = _http_client(200)
        summary = await engine_mod._reconcile_secret_leases_once(
            db_maker, client, logging.getLogger("rot-test")
        )
    finally:
        ctx.stop()

    assert summary["issued"] == 1
    assert summary["delivered"] == 1
    assert summary["delivery_failed"] == 0
    # Delivery POSTed to the site's secret-lease inbox.
    assert client.post.await_count == 1
    assert "/site/secret-leases" in client.post.await_args.args[0]
    with Session() as sess:
        lease = lease_svc.get_lease(sess, lease_id)
        assert lease.status == FED_LEASE_ACTIVE
        assert lease.vault_lease_id
        assert lease.delivered_at is not None


@pytest.mark.asyncio
async def test_failed_delivery_is_rotated_and_redelivered(engine_mod, reconcile_env):
    Session, db_maker = reconcile_env
    lease_id = _seed_requested(Session)
    ctx = _stub_vault()
    try:
        # Pass 1: site rejects the push → issued but undelivered.
        bad = await engine_mod._reconcile_secret_leases_once(
            db_maker, _http_client(503), logging.getLogger("rot-test")
        )
        assert bad["issued"] == 1 and bad["delivery_failed"] == 1
        with Session() as sess:
            assert lease_svc.get_lease(sess, lease_id).delivered_at is None

        # Pass 2: site back up → the undelivered lease is rotated + delivered.
        good = await engine_mod._reconcile_secret_leases_once(
            db_maker, _http_client(200), logging.getLogger("rot-test")
        )
    finally:
        ctx.stop()

    assert good["renewed"] >= 1
    assert good["delivered"] >= 1
    with Session() as sess:
        assert lease_svc.get_lease(sess, lease_id).delivered_at is not None


@pytest.mark.asyncio
async def test_reconcile_rotates_lease_near_expiry(engine_mod, reconcile_env):
    Session, db_maker = reconcile_env
    # An already-issued, delivered lease about to expire (inside the 90s window).
    with Session() as sess:
        site, _b, _o = enroll_site(sess, name="s2", url="https://s2.example.com")
        sess.commit()
        lease = FederationSecretLease(
            site_id=site.id,
            host_id="host-2",
            secret_name="db",
            backend_role="readonly",
            kind="database",
            status=FED_LEASE_ACTIVE,
            vault_lease_id="dyn/near",
            ttl_seconds=3600,
            issued_at=_now(),
            expires_at=_now() + timedelta(seconds=30),
            delivered_at=_now(),
            correlation_key="corr-2",
        )
        sess.add(lease)
        sess.commit()
        lease_id = lease.id

    ctx = _stub_vault()
    try:
        summary = await engine_mod._reconcile_secret_leases_once(
            db_maker, _http_client(200), logging.getLogger("rot-test")
        )
    finally:
        ctx.stop()

    assert summary["renewed"] == 1
    assert summary["delivered"] == 1
    with Session() as sess:
        lease = lease_svc.get_lease(sess, lease_id)
        # TTL pushed well past the rotation window → no longer expiring.
        assert lease.expires_at > _now() + timedelta(seconds=120)
        assert lease.last_renewed_at is not None
