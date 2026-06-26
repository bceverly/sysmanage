"""
Tests for self-service tenant provisioning orchestration (Pro+ relocation,
Phase 2).

The orchestration logic moved into the licensed engine; the OSS module is a thin
shim that keeps ``OrchestrationError``.  Shim-contract tests (always run) assert
the no-engine behavior; behavioral tests run against the real compiled engine
(skip-tolerant), with Postgres + OpenBAO mocked.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.services import tenant_orchestration as orch
from backend.services.tenant_orchestration import OrchestrationError

_CREDS = {
    "host": "localhost",
    "port": 5432,
    "user": "sysmanage_provisioner",
    "password": "pw",
    "sslmode": "prefer",
}


# ---------------------------------------------------------------------------
# Shim contract (always runs — no engine)
# ---------------------------------------------------------------------------


@pytest.fixture
def _no_engine():
    from backend.multitenancy import seam

    seam.unregister_engine()
    yield
    seam.unregister_engine()


def test_provisioning_requires_engine(_no_engine):
    with pytest.raises(OrchestrationError):
        orch.auto_provision_tenant("t-1", slug="acme")
    with pytest.raises(OrchestrationError):
        orch.deprovision_tenant("t-1", slug="acme")


def test_is_provisioner_configured_false_without_engine(_no_engine):
    assert orch.is_provisioner_configured() is False


# ---------------------------------------------------------------------------
# Behavioral against the real compiled engine (skips if the .so is absent)
# ---------------------------------------------------------------------------


def test_safe_identifier_normalizes(real_engine):
    assert real_engine._safe_identifier("Acme Corp") == "acme_corp"
    assert real_engine._safe_identifier("a-b.c") == "a_b_c"


def test_safe_identifier_rejects_empty(real_engine):
    with pytest.raises(OrchestrationError):
        real_engine._safe_identifier("!!!")


def test_derive_names(real_engine):
    assert real_engine.derive_names("Acme") == {
        "dbname": "tenant_acme",
        "owner_role": "acme_owner",
        "config_name": "acme",
        "openbao_role": "acme-role",
    }


def test_is_provisioner_configured_false_when_vault_disabled(real_engine):
    with patch("backend.config.config.is_vault_enabled", return_value=False):
        assert orch.is_provisioner_configured() is False


def test_create_tenant_database_idempotent_creates_both(real_engine):
    cur = MagicMock()
    cur.fetchone.side_effect = [None, None]  # role miss, db miss → create both
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur

    with patch.object(
        real_engine, "_provisioner_credentials", return_value=_CREDS
    ), patch.object(real_engine, "_connect_provisioner", return_value=conn):
        real_engine.create_tenant_database("tenant_acme", "acme_owner")

    executed = " ".join(str(c.args[0]) for c in cur.execute.call_args_list)
    assert "CREATE ROLE" in executed
    assert "CREATE DATABASE" in executed
    conn.close.assert_called_once()


def test_create_tenant_database_skips_existing(real_engine):
    cur = MagicMock()
    cur.fetchone.side_effect = [(1,), (1,)]  # both already exist
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur

    with patch.object(
        real_engine, "_provisioner_credentials", return_value=_CREDS
    ), patch.object(real_engine, "_connect_provisioner", return_value=conn):
        real_engine.create_tenant_database("tenant_acme", "acme_owner")

    executed = " ".join(str(c.args[0]) for c in cur.execute.call_args_list)
    assert "CREATE ROLE" not in executed
    assert "CREATE DATABASE" not in executed


def test_configure_openbao_role_writes_config_and_role(real_engine):
    svc = MagicMock()
    with patch.object(
        real_engine, "_provisioner_credentials", return_value=_CREDS
    ), patch(
        "backend.config.config.get_vault_database_mount_path", return_value="database"
    ), patch(
        "backend.services.vault_service.VaultService", return_value=svc
    ):
        real_engine.configure_openbao_role(
            config_name="acme",
            role_name="acme-role",
            owner_role="acme_owner",
            dbname="tenant_acme",
            host="localhost",
            port=5432,
        )

    paths = [c.args[1] for c in svc.make_raw_request.call_args_list]
    assert "database/config/acme" in paths
    assert "database/roles/acme-role" in paths
    config_call = next(
        c
        for c in svc.make_raw_request.call_args_list
        if c.args[1].endswith("/config/acme")
    )
    assert "{{username}}" in config_call.args[2]["connection_url"]
    assert "{{password}}" in config_call.args[2]["connection_url"]
    role_call = next(
        c
        for c in svc.make_raw_request.call_args_list
        if c.args[1].endswith("/roles/acme-role")
    )
    statements = role_call.args[2]["creation_statements"]
    assert 'IN ROLE "acme_owner"' in statements
    assert "SET role TO 'acme_owner'" in statements
    assert "{{name}}" in statements and "{{password}}" in statements


def test_auto_provision_refused_when_disabled(real_engine):
    with patch(
        "backend.config.config.is_self_service_provisioning_enabled",
        return_value=False,
    ):
        with pytest.raises(OrchestrationError):
            orch.auto_provision_tenant("t-1", slug="acme")


def test_deprovision_skips_db_when_not_requested(real_engine):
    with patch.object(real_engine, "_teardown_openbao") as bao, patch.object(
        real_engine, "_drop_tenant_database"
    ) as drop, patch.object(real_engine, "_delete_registry_records") as registry:
        result = orch.deprovision_tenant("t-1", slug="acme", drop_database=False)
    bao.assert_called_once()
    registry.assert_called_once()
    drop.assert_not_called()
    assert "errors" in result


def test_deprovision_drops_db_when_requested(real_engine):
    with patch.object(real_engine, "_teardown_openbao"), patch.object(
        real_engine, "_drop_tenant_database"
    ) as drop, patch.object(real_engine, "_delete_registry_records"):
        orch.deprovision_tenant("t-1", slug="acme", drop_database=True)
    drop.assert_called_once()


def test_teardown_openbao_revokes_then_deletes(real_engine):
    svc = MagicMock()
    result = {"errors": []}
    with patch("backend.config.config.is_vault_enabled", return_value=True), patch(
        "backend.config.config.get_vault_database_mount_path", return_value="database"
    ), patch("backend.services.vault_service.VaultService", return_value=svc):
        real_engine._teardown_openbao(real_engine.derive_names("acme"), result)
    calls = [(c.args[0], c.args[1]) for c in svc.make_raw_request.call_args_list]
    assert ("PUT", "sys/leases/revoke-prefix/database/creds/acme-role") in calls
    assert ("DELETE", "database/roles/acme-role") in calls
    assert ("DELETE", "database/config/acme") in calls
    assert result["openbao_removed"] is True


def test_delete_registry_records_removes_all(real_engine, db_session):
    from backend.persistence.models import (
        RegistryTenant,
        RegistryTenantEmailDomain,
        RegistryTenantPlacement,
        RegistryUser,
        RegistryUserTenantGrant,
        TENANT_STATUS_ACTIVE,
    )

    tenant = RegistryTenant(name="Acme", slug="acme-del", status=TENANT_STATUS_ACTIVE)
    user = RegistryUser(email="m@acme.com")
    db_session.add_all([tenant, user])
    db_session.commit()
    db_session.add_all(
        [
            RegistryUserTenantGrant(user_id=user.id, tenant_id=tenant.id, role="admin"),
            RegistryTenantEmailDomain(tenant_id=tenant.id, domain="acme.com"),
            RegistryTenantPlacement(tenant_id=tenant.id, tier="silo"),
        ]
    )
    db_session.commit()
    tenant_id = tenant.id

    result = {"errors": []}
    real_engine._delete_registry_records(tenant_id, result)

    assert result["registry_removed"] is True
    assert (
        db_session.query(RegistryTenant).filter(RegistryTenant.id == tenant_id).first()
        is None
    )
    assert (
        db_session.query(RegistryUserTenantGrant)
        .filter(RegistryUserTenantGrant.tenant_id == tenant_id)
        .count()
        == 0
    )


def test_auto_provision_happy_path_orchestrates_all_steps(real_engine):
    with patch(
        "backend.config.config.is_self_service_provisioning_enabled",
        return_value=True,
    ), patch.object(real_engine, "create_tenant_database") as create_db, patch.object(
        real_engine, "configure_openbao_role"
    ) as cfg_role, patch.object(
        real_engine, "_upsert_placement"
    ) as upsert, patch.object(
        real_engine, "provision_tenant_database", return_value="rev123"
    ) as migrate:
        result = orch.auto_provision_tenant("t-1", slug="Acme", host="db", port=5433)

    create_db.assert_called_once_with("tenant_acme", "acme_owner")
    cfg_role.assert_called_once()
    upsert.assert_called_once()
    migrate.assert_called_once_with("t-1")
    assert result["dbname"] == "tenant_acme"
    assert result["openbao_role"] == "acme-role"
    assert result["revision"] == "rev123"
    assert result["status"] == "provisioned"
