"""
Tests for the per-tenant migration fan-out script (Phase 13.1).
"""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_tenants.py"


def _load():
    spec = importlib.util.spec_from_file_location("migrate_tenants", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_noop_when_multitenancy_disabled():
    mod = _load()
    with patch.object(mod.config, "is_multitenancy_enabled", return_value=False):
        assert mod.main() == 0


def test_placed_tenants_lists_only_placed(db_session):
    from backend.persistence.models import (
        RegistryTenant,
        RegistryTenantPlacement,
        TENANT_STATUS_ACTIVE,
    )

    placed = RegistryTenant(name="Placed", slug="placed", status=TENANT_STATUS_ACTIVE)
    unplaced = RegistryTenant(name="Bare", slug="bare", status=TENANT_STATUS_ACTIVE)
    db_session.add_all([placed, unplaced])
    db_session.commit()
    db_session.add(
        RegistryTenantPlacement(
            tenant_id=placed.id, tier="silo", openbao_role="placed-role"
        )
    )
    db_session.commit()

    mod = _load()
    rows = mod._placed_tenants()
    by_slug = {slug: has_role for (_id, slug, has_role) in rows}
    assert by_slug.get("placed") is True
    assert "bare" not in by_slug  # no placement → not listed


def test_skips_tenant_without_openbao_role(db_session):
    from backend.persistence.models import (
        RegistryTenant,
        RegistryTenantPlacement,
        TENANT_STATUS_ACTIVE,
    )

    tenant = RegistryTenant(name="NoRole", slug="norole", status=TENANT_STATUS_ACTIVE)
    db_session.add(tenant)
    db_session.commit()
    db_session.add(
        RegistryTenantPlacement(tenant_id=tenant.id, tier="silo", openbao_role=None)
    )
    db_session.commit()

    mod = _load()
    with patch.object(mod.config, "is_multitenancy_enabled", return_value=True), patch(
        "backend.services.tenant_provisioning.provision_tenant_database"
    ) as prov:
        rc = mod.main()
    # No role → skipped, never provisioned, and a clean (0) exit.
    prov.assert_not_called()
    assert rc == 0
