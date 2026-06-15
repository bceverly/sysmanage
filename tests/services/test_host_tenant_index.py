"""
Tests for the host→tenant index (Phase 13.1 data plane).
"""

import uuid

from backend.services import host_tenant_index


def _tenant(db_session, slug="idx-co"):
    from backend.persistence.models import RegistryTenant, TENANT_STATUS_ACTIVE

    t = RegistryTenant(name="Idx Co", slug=slug, status=TENANT_STATUS_ACTIVE)
    db_session.add(t)
    db_session.commit()
    return t


def test_bind_and_lookup(db_session):
    tenant = _tenant(db_session)
    host_id = uuid.uuid4()
    assert host_tenant_index.bind_host_to_tenant(host_id, tenant.id) is True
    assert host_tenant_index.tenant_for_host(host_id) == str(tenant.id)


def test_lookup_unknown_returns_none(db_session):
    assert host_tenant_index.tenant_for_host(uuid.uuid4()) is None
    assert host_tenant_index.tenant_for_host(None) is None


def test_rebind_updates_tenant(db_session):
    a = _tenant(db_session, "a-co")
    b = _tenant(db_session, "b-co")
    host_id = uuid.uuid4()
    host_tenant_index.bind_host_to_tenant(host_id, a.id)
    host_tenant_index.bind_host_to_tenant(host_id, b.id)
    assert host_tenant_index.tenant_for_host(host_id) == str(b.id)
    # Still exactly one row for the host.
    from backend.persistence.models import RegistryHostTenant

    assert (
        db_session.query(RegistryHostTenant)
        .filter(RegistryHostTenant.host_id == host_id)
        .count()
        == 1
    )


def test_unbind_removes_binding(db_session):
    tenant = _tenant(db_session)
    host_id = uuid.uuid4()
    host_tenant_index.bind_host_to_tenant(host_id, tenant.id)
    assert host_tenant_index.unbind_host(host_id) is True
    assert host_tenant_index.tenant_for_host(host_id) is None
