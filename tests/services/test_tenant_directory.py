"""
Tests for the tenant directory email→tenant resolver (Phase 13.1).
"""

from unittest.mock import patch

from backend.services import tenant_directory


def _make_tenant(db_session, slug="acme-dir"):
    from backend.persistence.models import RegistryTenant, TENANT_STATUS_ACTIVE

    tenant = RegistryTenant(name="Acme", slug=slug, status=TENANT_STATUS_ACTIVE)
    db_session.add(tenant)
    db_session.commit()
    return tenant


def _add_domain(db_session, tenant_id, domain):
    from backend.persistence.models import RegistryTenantEmailDomain

    db_session.add(RegistryTenantEmailDomain(tenant_id=tenant_id, domain=domain))
    db_session.commit()


def test_none_when_multitenancy_disabled(db_session):
    tenant = _make_tenant(db_session)
    _add_domain(db_session, tenant.id, "acme.com")
    with patch.object(
        tenant_directory.config, "is_multitenancy_enabled", return_value=False
    ):
        assert tenant_directory.resolve_tenant_for_email("user@acme.com") is None


def test_resolves_single_match(db_session):
    tenant = _make_tenant(db_session)
    _add_domain(db_session, tenant.id, "acme.com")
    with patch.object(
        tenant_directory.config, "is_multitenancy_enabled", return_value=True
    ):
        assert tenant_directory.resolve_tenant_for_email("user@acme.com") == str(
            tenant.id
        )


def test_case_insensitive_domain(db_session):
    tenant = _make_tenant(db_session)
    _add_domain(db_session, tenant.id, "acme.com")
    with patch.object(
        tenant_directory.config, "is_multitenancy_enabled", return_value=True
    ):
        assert tenant_directory.resolve_tenant_for_email("User@ACME.COM") == str(
            tenant.id
        )


def test_none_when_no_match(db_session):
    _make_tenant(db_session)
    with patch.object(
        tenant_directory.config, "is_multitenancy_enabled", return_value=True
    ):
        assert tenant_directory.resolve_tenant_for_email("user@nobody.com") is None


def test_none_when_ambiguous(db_session):
    t1 = _make_tenant(db_session, slug="t1-dir")
    t2 = _make_tenant(db_session, slug="t2-dir")
    _add_domain(db_session, t1.id, "shared.com")
    _add_domain(db_session, t2.id, "shared.com")
    with patch.object(
        tenant_directory.config, "is_multitenancy_enabled", return_value=True
    ):
        # Two tenants claim the domain → ambiguous → server scope (None).
        assert tenant_directory.resolve_tenant_for_email("user@shared.com") is None


def test_none_for_malformed_email(db_session):
    with patch.object(
        tenant_directory.config, "is_multitenancy_enabled", return_value=True
    ):
        assert tenant_directory.resolve_tenant_for_email("not-an-email") is None
        assert tenant_directory.resolve_tenant_for_email("") is None
        assert tenant_directory.resolve_tenant_for_email(None) is None


def test_never_raises_without_db():
    # No engine fixture → registry unavailable; must degrade to None.
    with patch.object(
        tenant_directory.config, "is_multitenancy_enabled", return_value=True
    ):
        assert tenant_directory.resolve_tenant_for_email("user@acme.com") is None
