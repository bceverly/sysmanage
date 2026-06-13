"""
Tests for the registry service layer — Phase 13.1.B.

Covers grant validity (active/expired/suspended-tenant), default-tenant
resolution, and the email-domain allowlist semantics (empty = allow all).
"""

from datetime import datetime, timedelta, timezone

from backend.persistence.models import (
    RegistryTenant,
    RegistryTenantEmailDomain,
    RegistryUser,
    RegistryUserTenantGrant,
)
from backend.services import registry_service


def _naive_future(**kw):
    return (datetime.now(timezone.utc) + timedelta(**kw)).replace(tzinfo=None)


def _naive_past(**kw):
    return (datetime.now(timezone.utc) - timedelta(**kw)).replace(tzinfo=None)


def _user(session, email="u@example.com"):
    user = RegistryUser(email=email)
    session.add(user)
    session.commit()
    return user


def _tenant(session, slug="acme", status="active"):
    tenant = RegistryTenant(name=slug.title(), slug=slug, status=status)
    session.add(tenant)
    session.commit()
    return tenant


def test_normalize_domain():
    assert registry_service.normalize_domain("Bob@Example.COM") == "example.com"
    assert registry_service.normalize_domain("EXAMPLE.com") == "example.com"
    assert registry_service.normalize_domain("  x@y.io ") == "y.io"


def test_has_active_grant_true(db_session):
    user = _user(db_session)
    tenant = _tenant(db_session)
    db_session.add(
        RegistryUserTenantGrant(user_id=user.id, tenant_id=tenant.id, role="admin")
    )
    db_session.commit()
    assert registry_service.has_active_grant(db_session, user.id, tenant.id) is True


def test_expired_grant_is_not_active(db_session):
    user = _user(db_session)
    tenant = _tenant(db_session)
    db_session.add(
        RegistryUserTenantGrant(
            user_id=user.id, tenant_id=tenant.id, expires_at=_naive_past(hours=1)
        )
    )
    db_session.commit()
    assert registry_service.has_active_grant(db_session, user.id, tenant.id) is False


def test_future_expiry_grant_is_active(db_session):
    user = _user(db_session)
    tenant = _tenant(db_session)
    db_session.add(
        RegistryUserTenantGrant(
            user_id=user.id, tenant_id=tenant.id, expires_at=_naive_future(hours=1)
        )
    )
    db_session.commit()
    assert registry_service.has_active_grant(db_session, user.id, tenant.id) is True


def test_grant_to_suspended_tenant_is_not_active(db_session):
    user = _user(db_session)
    tenant = _tenant(db_session, status="suspended")
    db_session.add(RegistryUserTenantGrant(user_id=user.id, tenant_id=tenant.id))
    db_session.commit()
    assert registry_service.has_active_grant(db_session, user.id, tenant.id) is False
    assert registry_service.list_user_grants(db_session, user.id) == []


def test_get_default_tenant_prefers_is_default(db_session):
    user = _user(db_session)
    t1 = _tenant(db_session, slug="one")
    t2 = _tenant(db_session, slug="two")
    db_session.add(RegistryUserTenantGrant(user_id=user.id, tenant_id=t1.id))
    db_session.add(
        RegistryUserTenantGrant(user_id=user.id, tenant_id=t2.id, is_default=True)
    )
    db_session.commit()
    assert registry_service.get_default_tenant_id(db_session, user.id) == t2.id


def test_get_default_tenant_single_grant(db_session):
    user = _user(db_session)
    t1 = _tenant(db_session, slug="solo")
    db_session.add(RegistryUserTenantGrant(user_id=user.id, tenant_id=t1.id))
    db_session.commit()
    assert registry_service.get_default_tenant_id(db_session, user.id) == t1.id


def test_get_default_tenant_ambiguous_returns_none(db_session):
    user = _user(db_session)
    t1 = _tenant(db_session, slug="a")
    t2 = _tenant(db_session, slug="b")
    db_session.add(RegistryUserTenantGrant(user_id=user.id, tenant_id=t1.id))
    db_session.add(RegistryUserTenantGrant(user_id=user.id, tenant_id=t2.id))
    db_session.commit()
    assert registry_service.get_default_tenant_id(db_session, user.id) is None


def test_email_domain_allowlist_empty_allows_all(db_session):
    tenant = _tenant(db_session)
    assert (
        registry_service.is_email_domain_allowed(db_session, tenant.id, "x@any.com")
        is True
    )


def test_email_domain_allowlist_enforced(db_session):
    tenant = _tenant(db_session)
    db_session.add(RegistryTenantEmailDomain(tenant_id=tenant.id, domain="example.com"))
    db_session.commit()
    assert (
        registry_service.is_email_domain_allowed(
            db_session, tenant.id, "ok@example.com"
        )
        is True
    )
    assert (
        registry_service.is_email_domain_allowed(db_session, tenant.id, "no@other.com")
        is False
    )
