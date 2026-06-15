"""
Tests for the OpenBAO database-secrets credential broker — Phase 13.1.C.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.services import openbao_db_secrets
from backend.services.openbao_db_secrets import DbSecretsError


def test_lease_credentials_parses_response():
    response = {
        "lease_id": "database/creds/acme/abc",
        "lease_duration": 1800,
        "data": {"username": "v-token-acme-xyz", "password": "secret-pw"},
    }
    with patch("backend.services.vault_service.VaultService") as vs, patch.object(
        openbao_db_secrets.config,
        "get_vault_database_mount_path",
        return_value="database",
    ):
        vs.return_value.make_raw_request.return_value = response
        lease = openbao_db_secrets.lease_credentials("acme")
    assert lease.username == "v-token-acme-xyz"
    assert lease.password == "secret-pw"
    assert lease.lease_id == "database/creds/acme/abc"
    assert lease.lease_duration == 1800
    # Verify the right engine path was hit.
    vs.return_value.make_raw_request.assert_called_once_with(
        "GET", "database/creds/acme"
    )


def test_lease_credentials_raises_on_empty():
    with patch("backend.services.vault_service.VaultService") as vs:
        vs.return_value.make_raw_request.return_value = {"data": {}}
        with pytest.raises(DbSecretsError):
            openbao_db_secrets.lease_credentials("acme")


def test_lease_credentials_raises_on_vault_error():
    with patch("backend.services.vault_service.VaultService") as vs:
        vs.return_value.make_raw_request.side_effect = RuntimeError("down")
        with pytest.raises(DbSecretsError):
            openbao_db_secrets.lease_credentials("acme")


def test_renew_lease_returns_duration():
    with patch("backend.services.vault_service.VaultService") as vs:
        vs.return_value.make_raw_request.return_value = {"lease_duration": 900}
        assert openbao_db_secrets.renew_lease("lease-1") == 900


def test_renew_lease_empty_id_returns_zero():
    assert openbao_db_secrets.renew_lease("") == 0


def test_revoke_lease_best_effort():
    with patch("backend.services.vault_service.VaultService") as vs:
        vs.return_value.make_raw_request.return_value = {}
        assert openbao_db_secrets.revoke_lease("lease-1") is True
    assert openbao_db_secrets.revoke_lease("") is False
