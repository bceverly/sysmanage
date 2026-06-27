"""Phase 13.1.E — vendor-support / break-glass time-boxed grants.

``create_support_grant`` mints a SHORT-LIVED grant whose ``expires_at`` is the
sole enforcement: ``has_active_grant`` refuses it once it lapses.  The TTL must
be hard-capped so an operator can't accidentally mint an unbounded backdoor.
"""

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.tenancy import (
    RegistryTenant,
    RegistryUserTenantGrant,
)
from backend.services import registry_service

TENANT = uuid.uuid4()


@pytest.fixture
def session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=eng)
    with sessionmaker(bind=eng)() as s:
        s.add(RegistryTenant(id=TENANT, name="Acme", slug="acme"))
        s.commit()
        yield s
    eng.dispose()


def _user(session, email="vendor@acme.com"):
    u = registry_service.ensure_registry_user(session, email)
    session.commit()
    return u


def test_support_grant_sets_bounded_expiry(session):
    user = _user(session)
    before = registry_service._utcnow()
    grant = registry_service.create_support_grant(session, user.id, TENANT, 4 * 3600)
    session.commit()
    assert grant.role == registry_service.SUPPORT_GRANT_ROLE
    assert grant.expires_at is not None
    # ~4h out (allow a few seconds of slack).
    delta = grant.expires_at - before
    assert (
        timedelta(hours=4) - timedelta(seconds=5)
        <= delta
        <= timedelta(hours=4, seconds=5)
    )


def test_ttl_is_hard_capped(session):
    user = _user(session)
    before = registry_service._utcnow()
    # Ask for a year; must be clamped to the 72h cap.
    grant = registry_service.create_support_grant(
        session, user.id, TENANT, 365 * 24 * 3600
    )
    session.commit()
    delta = grant.expires_at - before
    assert delta <= timedelta(
        seconds=registry_service.SUPPORT_GRANT_MAX_TTL_SECONDS + 5
    )


def test_ttl_floor_is_one_second(session):
    user = _user(session)
    before = registry_service._utcnow()
    grant = registry_service.create_support_grant(session, user.id, TENANT, 0)
    session.commit()
    assert grant.expires_at > before  # never non-positive


def test_refresh_updates_existing_grant_not_duplicate(session):
    user = _user(session)
    g1 = registry_service.create_support_grant(session, user.id, TENANT, 3600)
    g2 = registry_service.create_support_grant(session, user.id, TENANT, 7200)
    session.commit()
    assert g1.id == g2.id
    assert session.query(RegistryUserTenantGrant).count() == 1


def test_live_then_dead_via_expiry(session):
    user = _user(session)
    grant = registry_service.create_support_grant(session, user.id, TENANT, 3600)
    session.commit()
    # Live now.
    assert registry_service.has_active_grant(session, user.id, TENANT) is True
    # Force-expire it in the past; the request-time gate must now refuse it.
    grant.expires_at = registry_service._utcnow() - timedelta(seconds=1)
    session.commit()
    assert registry_service.has_active_grant(session, user.id, TENANT) is False


# --- Phase 13.1.E: OpenBAO lease binding -----------------------------------


def test_bind_support_lease_records_accessor(session):
    user = _user(session)
    grant = registry_service.create_support_grant(session, user.id, TENANT, 3600)
    with patch("backend.services.vault_service.VaultService") as mock_vs:
        mock_vs.return_value.create_support_lease.return_value = "acc-123"
        accessor = registry_service.bind_support_lease(
            grant, 3600, metadata={"email": "vendor@acme.com"}
        )
    session.commit()
    assert accessor == "acc-123"
    assert grant.support_lease_accessor == "acc-123"
    # The TTL + metadata were forwarded to the vault lease.
    _, kwargs = mock_vs.return_value.create_support_lease.call_args
    assert kwargs["ttl_seconds"] == 3600
    assert kwargs["metadata"]["email"] == "vendor@acme.com"


def test_bind_support_lease_noop_when_vault_returns_none(session):
    user = _user(session)
    grant = registry_service.create_support_grant(session, user.id, TENANT, 3600)
    with patch("backend.services.vault_service.VaultService") as mock_vs:
        mock_vs.return_value.create_support_lease.return_value = None
        accessor = registry_service.bind_support_lease(grant, 3600)
    assert accessor is None
    assert grant.support_lease_accessor is None  # expires_at alone enforces


def test_bind_support_lease_swallows_vault_errors(session):
    user = _user(session)
    grant = registry_service.create_support_grant(session, user.id, TENANT, 3600)
    with patch(
        "backend.services.vault_service.VaultService",
        side_effect=RuntimeError("vault down"),
    ):
        accessor = registry_service.bind_support_lease(grant, 3600)
    assert accessor is None
    assert grant.support_lease_accessor is None


def test_revoke_support_grant_expires_immediately(session):
    user = _user(session)
    registry_service.create_support_grant(session, user.id, TENANT, 3600)
    session.commit()
    assert registry_service.has_active_grant(session, user.id, TENANT) is True
    grant = registry_service.revoke_support_grant(session, user.id, TENANT)
    session.commit()
    assert grant is not None
    assert registry_service.has_active_grant(session, user.id, TENANT) is False


def test_revoke_support_grant_revokes_bound_lease(session):
    user = _user(session)
    grant = registry_service.create_support_grant(session, user.id, TENANT, 3600)
    grant.support_lease_accessor = "acc-xyz"
    session.commit()
    with patch("backend.services.vault_service.VaultService") as mock_vs:
        registry_service.revoke_support_grant(session, user.id, TENANT)
        mock_vs.return_value.revoke_support_lease.assert_called_once_with("acc-xyz")
    session.commit()
    assert grant.support_lease_accessor is None


def test_revoke_support_grant_none_when_absent(session):
    user = _user(session)
    assert registry_service.revoke_support_grant(session, user.id, TENANT) is None
