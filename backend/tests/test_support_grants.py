"""Phase 13.1.E — vendor-support / break-glass time-boxed grants.

``create_support_grant`` mints a SHORT-LIVED grant whose ``expires_at`` is the
sole enforcement: ``has_active_grant`` refuses it once it lapses.  The TTL must
be hard-capped so an operator can't accidentally mint an unbounded backdoor.
"""

import uuid
from datetime import timedelta

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
