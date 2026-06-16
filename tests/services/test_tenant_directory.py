"""
Tests for the tenant directory email→tenant resolver (Pro+ relocation, Phase 2).

The resolver logic moved into the licensed engine; the OSS module is a thin
shim.  No-engine degrades to None (server scope, always run); behavioral tests
run against the real compiled engine (skip-tolerant).
"""

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


# --- shim contract (no engine → server scope) ---


def test_no_engine_returns_none(db_session):
    tenant = _make_tenant(db_session)
    _add_domain(db_session, tenant.id, "acme.com")
    # No engine registered → single-tenant / unlicensed → server scope.
    assert tenant_directory.resolve_tenant_for_email("user@acme.com") is None


# --- behavioral against the real compiled engine ---


def test_resolves_single_match(real_engine, db_session):
    tenant = _make_tenant(db_session)
    _add_domain(db_session, tenant.id, "acme.com")
    assert tenant_directory.resolve_tenant_for_email("user@acme.com") == str(tenant.id)


def test_case_insensitive_domain(real_engine, db_session):
    tenant = _make_tenant(db_session)
    _add_domain(db_session, tenant.id, "acme.com")
    assert tenant_directory.resolve_tenant_for_email("User@ACME.COM") == str(tenant.id)


def test_none_when_no_match(real_engine, db_session):
    _make_tenant(db_session)
    assert tenant_directory.resolve_tenant_for_email("user@nobody.com") is None


def test_none_when_ambiguous(real_engine, db_session):
    t1 = _make_tenant(db_session, slug="t1-dir")
    t2 = _make_tenant(db_session, slug="t2-dir")
    _add_domain(db_session, t1.id, "shared.com")
    _add_domain(db_session, t2.id, "shared.com")
    # Two tenants claim the domain → ambiguous → server scope (None).
    assert tenant_directory.resolve_tenant_for_email("user@shared.com") is None


def test_none_for_malformed_email(real_engine, db_session):
    assert tenant_directory.resolve_tenant_for_email("not-an-email") is None
    assert tenant_directory.resolve_tenant_for_email("") is None
    assert tenant_directory.resolve_tenant_for_email(None) is None
