"""
Tests for the multi-tenancy control-plane ("registry") models — Phase 13.1.A.

These verify that the ``registry_*`` tables are created by the shared
``Base.metadata`` (the collapsed/homelab path the whole test suite uses)
and that the core constraints — unique slug/email, the email→tenant grant
mapping, one-placement-per-tenant — hold.
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from backend.persistence.models import (
    RegistryTenant,
    RegistryTenantPlacement,
    RegistryUser,
    RegistryUserTenantGrant,
    TENANT_STATUS_ACTIVE,
    TENANT_TIER_SILO,
)


def _make_tenant(session, slug="acme", name="Acme Inc"):
    tenant = RegistryTenant(name=name, slug=slug, status=TENANT_STATUS_ACTIVE)
    session.add(tenant)
    session.commit()
    return tenant


def test_create_tenant_defaults(db_session):
    tenant = _make_tenant(db_session)
    assert tenant.id is not None
    assert tenant.status == TENANT_STATUS_ACTIVE
    assert tenant.created_at is not None
    assert tenant.updated_at is not None


def test_tenant_slug_is_unique(db_session):
    _make_tenant(db_session, slug="dup")
    with pytest.raises(IntegrityError):
        _make_tenant(db_session, slug="dup", name="Other")
    db_session.rollback()


def test_user_email_is_unique(db_session):
    db_session.add(RegistryUser(email="a@example.com"))
    db_session.commit()
    db_session.add(RegistryUser(email="a@example.com"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_grant_maps_user_to_tenant(db_session):
    tenant = _make_tenant(db_session)
    user = RegistryUser(email="user@example.com")
    db_session.add(user)
    db_session.commit()

    grant = RegistryUserTenantGrant(
        user_id=user.id, tenant_id=tenant.id, role="admin", is_default=True
    )
    db_session.add(grant)
    db_session.commit()

    assert grant.id is not None
    assert grant.is_default is True
    assert grant.expires_at is None  # not a time-boxed grant


def test_grant_user_tenant_pair_is_unique(db_session):
    tenant = _make_tenant(db_session)
    user = RegistryUser(email="user2@example.com")
    db_session.add(user)
    db_session.commit()

    db_session.add(RegistryUserTenantGrant(user_id=user.id, tenant_id=tenant.id))
    db_session.commit()
    db_session.add(RegistryUserTenantGrant(user_id=user.id, tenant_id=tenant.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_placement_holds_coordinates_not_credentials(db_session):
    tenant = _make_tenant(db_session)
    placement = RegistryTenantPlacement(
        tenant_id=tenant.id,
        host="tenant-db.internal",
        port=5432,
        dbname="sysmanage_acme",
        region="us-east-1",
        tier=TENANT_TIER_SILO,
        openbao_role="tenant-acme-db",
    )
    db_session.add(placement)
    db_session.commit()

    # The placement model has no column for a password / secret.
    cols = {c.name for c in RegistryTenantPlacement.__table__.columns}
    assert "password" not in cols
    assert "secret" not in cols
    assert placement.tier == TENANT_TIER_SILO


def test_one_placement_per_tenant(db_session):
    tenant = _make_tenant(db_session)
    db_session.add(RegistryTenantPlacement(tenant_id=tenant.id, dbname="a"))
    db_session.commit()
    db_session.add(RegistryTenantPlacement(tenant_id=tenant.id, dbname="b"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
