"""
Tests for self-service tenant provisioning orchestration (Phase 13.1).

The Postgres + OpenBAO calls are mocked — these verify the orchestration logic,
identifier safety, idempotent DDL, and the OpenBAO config/role payloads.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.services import tenant_orchestration as orch
from backend.services.tenant_orchestration import OrchestrationError


def test_safe_identifier_normalizes():
    assert orch._safe_identifier("Acme Corp") == "acme_corp"
    assert orch._safe_identifier("a-b.c") == "a_b_c"


def test_safe_identifier_rejects_empty():
    with pytest.raises(OrchestrationError):
        orch._safe_identifier("!!!")


def test_derive_names():
    names = orch.derive_names("Acme")
    assert names == {
        "dbname": "tenant_acme",
        "owner_role": "acme_owner",
        "config_name": "acme",
        "openbao_role": "acme-role",
    }


def test_is_provisioner_configured_false_when_vault_disabled():
    with patch.object(orch.config, "is_vault_enabled", return_value=False):
        assert orch.is_provisioner_configured() is False


_CREDS = {
    "host": "localhost",
    "port": 5432,
    "user": "sysmanage_provisioner",
    "password": "pw",
    "sslmode": "prefer",
}


def test_create_tenant_database_idempotent_creates_both():
    cur = MagicMock()
    # pg_roles miss, then pg_database miss → create both.
    cur.fetchone.side_effect = [None, None]
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur

    with patch.object(
        orch, "_provisioner_credentials", return_value=_CREDS
    ), patch.object(orch, "_connect_provisioner", return_value=conn):
        orch.create_tenant_database("tenant_acme", "acme_owner")

    executed = " ".join(str(c.args[0]) for c in cur.execute.call_args_list)
    assert "CREATE ROLE" in executed
    assert "CREATE DATABASE" in executed
    conn.close.assert_called_once()


def test_create_tenant_database_skips_existing():
    cur = MagicMock()
    cur.fetchone.side_effect = [(1,), (1,)]  # both already exist
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur

    with patch.object(
        orch, "_provisioner_credentials", return_value=_CREDS
    ), patch.object(orch, "_connect_provisioner", return_value=conn):
        orch.create_tenant_database("tenant_acme", "acme_owner")

    executed = " ".join(str(c.args[0]) for c in cur.execute.call_args_list)
    assert "CREATE ROLE" not in executed
    assert "CREATE DATABASE" not in executed


def test_configure_openbao_role_writes_config_and_role():
    svc = MagicMock()
    with patch.object(
        orch, "_provisioner_credentials", return_value=_CREDS
    ), patch.object(
        orch.config, "get_vault_database_mount_path", return_value="database"
    ), patch(
        "backend.services.vault_service.VaultService", return_value=svc
    ):
        orch.configure_openbao_role(
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
    # Connection URL is templated (no plaintext password in the URL).
    config_call = next(
        c
        for c in svc.make_raw_request.call_args_list
        if c.args[1].endswith("/config/acme")
    )
    assert "{{username}}" in config_call.args[2]["connection_url"]
    assert "{{password}}" in config_call.args[2]["connection_url"]
    # Role creation makes dynamic users members of the owner role AND has every
    # session SET ROLE to it, so created objects are owned by the stable owner.
    role_call = next(
        c
        for c in svc.make_raw_request.call_args_list
        if c.args[1].endswith("/roles/acme-role")
    )
    statements = role_call.args[2]["creation_statements"]
    assert 'IN ROLE "acme_owner"' in statements
    assert "SET role TO 'acme_owner'" in statements
    # Vault placeholders survive the f-string escaping.
    assert "{{name}}" in statements and "{{password}}" in statements


def test_auto_provision_refused_when_disabled():
    with patch.object(
        orch.config, "is_self_service_provisioning_enabled", return_value=False
    ):
        with pytest.raises(OrchestrationError):
            orch.auto_provision_tenant("t-1", slug="acme")


def test_deprovision_skips_db_when_not_requested():
    with patch.object(orch, "_teardown_openbao") as bao, patch.object(
        orch, "_drop_tenant_database"
    ) as drop, patch.object(orch, "_delete_registry_records") as registry:
        result = orch.deprovision_tenant("t-1", slug="acme", drop_database=False)
    bao.assert_called_once()
    registry.assert_called_once()
    drop.assert_not_called()
    assert "errors" in result


def test_deprovision_drops_db_when_requested():
    with patch.object(orch, "_teardown_openbao"), patch.object(
        orch, "_drop_tenant_database"
    ) as drop, patch.object(orch, "_delete_registry_records"):
        orch.deprovision_tenant("t-1", slug="acme", drop_database=True)
    drop.assert_called_once()


def test_teardown_openbao_revokes_then_deletes():
    svc = MagicMock()
    result = {"errors": []}
    with patch.object(orch.config, "is_vault_enabled", return_value=True), patch.object(
        orch.config, "get_vault_database_mount_path", return_value="database"
    ), patch("backend.services.vault_service.VaultService", return_value=svc):
        orch._teardown_openbao(orch.derive_names("acme"), result)
    calls = [(c.args[0], c.args[1]) for c in svc.make_raw_request.call_args_list]
    assert ("PUT", "sys/leases/revoke-prefix/database/creds/acme-role") in calls
    assert ("DELETE", "database/roles/acme-role") in calls
    assert ("DELETE", "database/config/acme") in calls
    assert result["openbao_removed"] is True


def test_delete_registry_records_removes_all(db_session):
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
    orch._delete_registry_records(tenant_id, result)

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


def test_auto_provision_happy_path_orchestrates_all_steps():
    with patch.object(
        orch.config, "is_self_service_provisioning_enabled", return_value=True
    ), patch.object(orch, "create_tenant_database") as create_db, patch.object(
        orch, "configure_openbao_role"
    ) as cfg_role, patch.object(
        orch, "_upsert_placement"
    ) as upsert, patch(
        "backend.services.tenant_provisioning.provision_tenant_database",
        return_value="rev123",
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
