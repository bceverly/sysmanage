"""
Tests for the tenant migration-status detector (Phase 13.1).
"""

from unittest.mock import patch

from backend.services import migration_status


def _tenant(db_session, slug):
    from backend.persistence.models import RegistryTenant, TENANT_STATUS_ACTIVE

    t = RegistryTenant(name=slug.title(), slug=slug, status=TENANT_STATUS_ACTIVE)
    db_session.add(t)
    db_session.commit()
    return t


def _set_version(db_session, tenant_id, revision):
    from backend.persistence.models import RegistryTenantDbVersion

    db_session.add(
        RegistryTenantDbVersion(tenant_id=tenant_id, chain="tenant", revision=revision)
    )
    db_session.commit()


def test_empty_when_multitenancy_disabled(db_session):
    with patch("backend.config.config.is_multitenancy_enabled", return_value=False):
        res = migration_status.pending_tenant_migrations()
    assert res["tenants_pending"] == 0


def test_flags_tenant_behind_head(db_session):
    up = _tenant(db_session, "uptodate")
    behind = _tenant(db_session, "behind")
    never = _tenant(db_session, "never")
    _set_version(db_session, up.id, "HEAD9")
    _set_version(db_session, behind.id, "OLD1")
    # 'never' has no db_version row at all → also pending.

    with patch(
        "backend.config.config.is_multitenancy_enabled", return_value=True
    ), patch.object(migration_status, "_tenant_chain_head", return_value="HEAD9"):
        res = migration_status.pending_tenant_migrations()

    assert res["tenant_head"] == "HEAD9"
    assert res["tenants_pending"] == 2
    assert set(res["tenant_slugs"]) == {"behind", "never"}


def test_no_false_alarm_when_head_unknown(db_session):
    t = _tenant(db_session, "acme")
    _set_version(db_session, t.id, "OLD1")
    with patch(
        "backend.config.config.is_multitenancy_enabled", return_value=True
    ), patch.object(migration_status, "_tenant_chain_head", return_value=None):
        res = migration_status.pending_tenant_migrations()
    # Head couldn't be resolved → don't cry wolf.
    assert res["tenants_pending"] == 0
