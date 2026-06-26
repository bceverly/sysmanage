"""
Tests for backend.services.vault_service.

These tests exercise the OpenBAO/Vault HTTP wrapper end-to-end with `requests`
mocked at the session level. The goal is to cover the error branches and the
multiple secret-type code paths that the service supports — those are the bits
that are easy to regress when the secret taxonomy changes.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.services.vault_service import (
    VAULT_DATA_PATH,
    VaultError,
    VaultService,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _vault_config(enabled=True, token="test-token"):
    return {
        "enabled": enabled,
        "url": "http://vault.example:8200",
        "token": token,
        "mount_path": "secret",
        "timeout": 5,
        "verify_ssl": False,
    }


def _make_service(enabled=True, token="test-token"):
    """Build a VaultService with the global config patched."""
    with patch("backend.services.vault_service.config") as mock_config:
        mock_config.get_vault_config.return_value = _vault_config(
            enabled=enabled, token=token
        )
        svc = VaultService()
    # Each test will replace svc.session with a Mock so we don't hit the network.
    svc.session = MagicMock()
    svc.session.headers = {"X-Vault-Token": token, "Content-Type": "application/json"}
    return svc


def _response(status_code=200, json_body=None, content=b'{"ok": true}'):
    """Shape a fake requests.Response object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.text = content.decode() if isinstance(content, bytes) else str(content)
    if json_body is None:
        json_body = {}
    resp.json.return_value = json_body
    return resp


# ---------------------------------------------------------------------------
# _make_request error branches
# ---------------------------------------------------------------------------


class TestMakeRequestErrorBranches:
    def test_disabled_vault_raises(self):
        svc = _make_service(enabled=False)
        # Re-mock config so the runtime call inside _make_request also sees disabled.
        svc.vault_config = _vault_config(enabled=False)
        with pytest.raises(VaultError, match="not enabled|not_enabled"):
            svc._make_request("GET", "secret/data/foo")

    def test_missing_token_raises(self):
        svc = _make_service(token="")
        svc.vault_config = _vault_config(token="")
        with pytest.raises(VaultError, match="token|no_token"):
            svc._make_request("GET", "secret/data/foo")

    def test_404_returns_empty_dict(self):
        svc = _make_service()
        svc.session.get.return_value = _response(status_code=404, content=b"")
        assert svc._make_request("GET", "secret/data/missing") == {}

    def test_403_raises_permission_denied(self):
        svc = _make_service()
        svc.session.get.return_value = _response(status_code=403, content=b"forbidden")
        with pytest.raises(VaultError, match="permission|denied"):
            svc._make_request("GET", "secret/data/foo")

    def test_500_includes_response_text(self):
        svc = _make_service()
        svc.session.get.return_value = _response(
            status_code=500, content=b"server exploded"
        )
        with pytest.raises(VaultError, match="server exploded|500"):
            svc._make_request("GET", "secret/data/foo")

    def test_unsupported_method_raises(self):
        svc = _make_service()
        with pytest.raises(VaultError, match="method"):
            svc._make_request("PATCH", "secret/data/foo")

    def test_connection_error_wrapped(self):
        svc = _make_service()
        svc.session.get.side_effect = requests.exceptions.ConnectionError("boom")
        with pytest.raises(VaultError, match="connect"):
            svc._make_request("GET", "secret/data/foo")

    def test_timeout_wrapped(self):
        svc = _make_service()
        svc.session.get.side_effect = requests.exceptions.Timeout("slow")
        with pytest.raises(VaultError, match="timed out|timeout"):
            svc._make_request("GET", "secret/data/foo")

    def test_generic_request_exception_wrapped(self):
        svc = _make_service()
        svc.session.get.side_effect = requests.exceptions.RequestException("nope")
        with pytest.raises(VaultError, match="request failed|nope"):
            svc._make_request("GET", "secret/data/foo")

    def test_invalid_json_wrapped(self):
        svc = _make_service()
        bad = _response(status_code=200, content=b"<<not-json>>")
        bad.json.side_effect = ValueError("decode")
        # Replace ValueError with json.JSONDecodeError, which is what the
        # service catches; ValueError is its base class so the wrapper is fine.
        svc.session.get.return_value = bad
        # The service catches json.JSONDecodeError specifically; raise that.
        import json as _json

        bad.json.side_effect = _json.JSONDecodeError("x", "y", 0)
        with pytest.raises(VaultError, match="invalid|response"):
            svc._make_request("GET", "secret/data/foo")

    def test_post_dispatches_to_session_post(self):
        svc = _make_service()
        svc.session.post.return_value = _response(json_body={"data": {"version": 7}})
        out = svc._make_request("POST", "secret/data/foo", {"k": "v"})
        assert out == {"data": {"version": 7}}
        svc.session.post.assert_called_once()

    def test_put_dispatches_to_session_put(self):
        svc = _make_service()
        svc.session.put.return_value = _response(json_body={"ok": 1})
        svc._make_request("PUT", "secret/data/foo", {"k": "v"})
        svc.session.put.assert_called_once()

    def test_delete_dispatches_to_session_delete(self):
        svc = _make_service()
        svc.session.delete.return_value = _response(content=b"")
        out = svc._make_request("DELETE", "secret/delete/foo")
        # 200 + empty content yields {} from the early-return branch.
        assert out == {}


# ---------------------------------------------------------------------------
# store_secret path-shaping logic
# ---------------------------------------------------------------------------


class TestStoreSecretPathShaping:
    """The vault path is derived from secret_type + secret_subtype with several
    fallbacks. Each branch matters because it's how the UI later locates the
    secret — bad paths mean orphaned data."""

    @pytest.fixture
    def svc(self):
        s = _make_service()
        s.session.put.return_value = _response(json_body={"data": {"version": 1}})
        return s

    def test_ssh_key_with_known_subtype(self, svc):
        out = svc.store_secret("k", "data", "ssh_key", "public")
        assert "/ssh/public/" in out["vault_path"]
        assert out["version"] == 1

    def test_ssh_key_with_unknown_subtype_falls_back_to_private(self, svc):
        out = svc.store_secret("k", "data", "ssh_key", "weird")
        assert "/ssh/private/" in out["vault_path"]

    def test_ssl_certificate_known_subtype(self, svc):
        out = svc.store_secret("k", "d", "ssl_certificate", "intermediate")
        assert "/pki/intermediate/" in out["vault_path"]

    def test_ssl_certificate_unknown_subtype_defaults_to_certificate(self, svc):
        out = svc.store_secret("k", "d", "ssl_certificate", "bogus")
        assert "/pki/certificate/" in out["vault_path"]

    def test_database_credentials_known_subtype(self, svc):
        out = svc.store_secret("k", "d", "database_credentials", "mysql")
        assert "/db/mysql/" in out["vault_path"]

    def test_database_credentials_unknown_defaults_to_postgresql(self, svc):
        out = svc.store_secret("k", "d", "database_credentials", "ibm_db2")
        assert "/db/postgresql/" in out["vault_path"]

    def test_api_keys_lowercase_known_subtype(self, svc):
        out = svc.store_secret("k", "d", "api_keys", "github")
        assert "/api/github/" in out["vault_path"]

    def test_api_keys_lowercase_unknown_defaults_to_github(self, svc):
        out = svc.store_secret("k", "d", "api_keys", "made_up")
        assert "/api/github/" in out["vault_path"]

    def test_api_key_titlecase_known_subtype(self, svc):
        out = svc.store_secret("k", "d", "API Key", "grafana")
        assert "/api/grafana/" in out["vault_path"]

    def test_api_key_titlecase_unknown_defaults_to_default(self, svc):
        out = svc.store_secret("k", "d", "API Key", "made_up")
        assert "/api/default/" in out["vault_path"]

    def test_unknown_type_falls_through_to_subtype_or_default(self, svc):
        out_with = svc.store_secret("k", "d", "weirdtype", "specific")
        assert "/weirdtype/specific/" in out_with["vault_path"]
        out_without = svc.store_secret("k", "d", "weirdtype", None)
        assert "/weirdtype/default/" in out_without["vault_path"]

    def test_store_secret_propagates_vault_error(self):
        svc = _make_service()
        svc.session.put.return_value = _response(status_code=500, content=b"vault down")
        with pytest.raises(VaultError):
            svc.store_secret("k", "d", "ssh_key", "public")

    def test_store_secret_wraps_unexpected_exception(self):
        svc = _make_service()
        svc.session.put.side_effect = RuntimeError("explode")
        with pytest.raises(VaultError, match="store secret|explode"):
            svc.store_secret("k", "d", "ssh_key", "public")

    def test_store_secret_returns_none_version_when_missing(self):
        svc = _make_service()
        # Vault sometimes returns no "data" — service should not blow up.
        svc.session.put.return_value = _response(json_body={})
        out = svc.store_secret("k", "d", "ssh_key", "public")
        assert out["version"] is None
        assert out["vault_path"].startswith("secret/data/secrets/ssh/")
        assert out["vault_token"] == svc.token


# ---------------------------------------------------------------------------
# retrieve_secret
# ---------------------------------------------------------------------------


class TestRetrieveSecret:
    def test_returns_inner_data(self):
        svc = _make_service()
        svc.session.get.return_value = _response(
            json_body={"data": {"data": {"content": "hunter2"}}}
        )
        assert svc.retrieve_secret("secret/data/foo") == {"content": "hunter2"}

    def test_missing_outer_data_raises(self):
        svc = _make_service()
        # 404 path returns {} which then lacks "data" key.
        svc.session.get.return_value = _response(status_code=404, content=b"")
        with pytest.raises(VaultError, match="not found|not_found"):
            svc.retrieve_secret("secret/data/foo")

    def test_empty_inner_data_raises(self):
        svc = _make_service()
        svc.session.get.return_value = _response(json_body={"data": {"data": {}}})
        with pytest.raises(VaultError, match="invalid|format"):
            svc.retrieve_secret("secret/data/foo")

    def test_swaps_token_and_restores(self):
        svc = _make_service(token="default-tok")
        svc.session.get.return_value = _response(json_body={"data": {"data": {"x": 1}}})
        # Passing a different token should swap the header for the call and
        # restore it afterwards.
        svc.retrieve_secret("secret/data/foo", vault_token="other-tok")
        assert svc.session.headers["X-Vault-Token"] == "default-tok"

    def test_unexpected_exception_wrapped(self):
        svc = _make_service()
        svc.session.get.side_effect = RuntimeError("unexpected")
        with pytest.raises(VaultError, match="retrieve|unexpected"):
            svc.retrieve_secret("secret/data/foo")


# ---------------------------------------------------------------------------
# delete_secret — the multi-step KV v2 destroy dance
# ---------------------------------------------------------------------------


class TestDeleteSecret:
    def _wire_get_for_version(self, svc, version=3):
        svc.session.get.return_value = _response(
            json_body={"data": {"metadata": {"version": version}}}
        )

    def test_happy_path_runs_three_steps(self):
        svc = _make_service()
        self._wire_get_for_version(svc, version=4)
        svc.session.delete.return_value = _response(content=b"")
        svc.session.put.return_value = _response(content=b"")

        path = f"secret{VAULT_DATA_PATH}secrets/ssh/private/abc"
        assert svc.delete_secret(path) is True

        # Two DELETE calls: soft-delete then metadata delete.
        assert svc.session.delete.call_count == 2
        # One PUT call: destroy with the version we discovered.
        svc.session.put.assert_called_once()
        destroy_args, destroy_kwargs = svc.session.put.call_args
        # versions=[4] should have been threaded through.
        assert destroy_kwargs["json"] == {"versions": [4]}

    def test_secret_already_gone_returns_true(self):
        """If the GET for version returns an empty body, the secret was already
        deleted — service should treat that as success."""
        svc = _make_service()
        svc.session.get.return_value = _response(
            status_code=404, content=b""
        )  # _make_request returns {}
        assert svc.delete_secret("secret/data/secrets/ssh/private/x") is True
        # Soft-delete and destroy should NOT have been invoked.
        svc.session.delete.assert_not_called()
        svc.session.put.assert_not_called()

    def test_version_lookup_failure_falls_back_to_v1(self):
        svc = _make_service()
        # Make the GET raise an unexpected error mid-call. The service treats
        # any exception during version detection as "fall back to v1".
        svc.session.get.side_effect = RuntimeError("flaky")
        svc.session.delete.return_value = _response(content=b"")
        svc.session.put.return_value = _response(content=b"")
        assert svc.delete_secret("secret/data/secrets/ssh/private/x") is True
        destroy_args, destroy_kwargs = svc.session.put.call_args
        assert destroy_kwargs["json"] == {"versions": [1]}

    def test_soft_delete_failure_does_not_abort(self):
        svc = _make_service()
        self._wire_get_for_version(svc)
        # First DELETE (soft) blows up; second DELETE (metadata) is fine.
        svc.session.delete.side_effect = [
            requests.exceptions.RequestException("soft fail"),
            _response(content=b""),
        ]
        svc.session.put.return_value = _response(content=b"")
        # Should still return True — soft-delete is best-effort.
        assert svc.delete_secret("secret/data/secrets/ssh/private/x") is True

    def test_destroy_failure_with_not_found_returns_true(self):
        svc = _make_service()
        self._wire_get_for_version(svc)
        svc.session.delete.return_value = _response(content=b"")
        # Destroy responds 404 — service interprets "not found" as already gone.
        svc.session.put.return_value = _response(
            status_code=400, content=b"version not found"
        )
        assert svc.delete_secret("secret/data/secrets/ssh/private/x") is True

    def test_destroy_hard_failure_raises(self):
        svc = _make_service()
        self._wire_get_for_version(svc)
        svc.session.delete.return_value = _response(content=b"")
        svc.session.put.return_value = _response(
            status_code=500, content=b"vault on fire"
        )
        with pytest.raises(VaultError):
            svc.delete_secret("secret/data/secrets/ssh/private/x")

    def test_metadata_delete_failure_is_swallowed(self):
        svc = _make_service()
        self._wire_get_for_version(svc)
        # Soft delete OK, destroy OK, metadata delete fails.
        svc.session.delete.side_effect = [
            _response(content=b""),
            requests.exceptions.RequestException("metadata fail"),
        ]
        svc.session.put.return_value = _response(content=b"")
        # The data is destroyed by step 2 so step 3 failing is non-fatal.
        assert svc.delete_secret("secret/data/secrets/ssh/private/x") is True

    def test_token_swap_is_restored_on_exception(self):
        svc = _make_service(token="primary")
        svc.session.get.side_effect = RuntimeError("blow up")
        svc.session.delete.return_value = _response(content=b"")
        svc.session.put.return_value = _response(content=b"")
        svc.delete_secret("secret/data/secrets/ssh/private/x", vault_token="other")
        # Even though we threw mid-call, the original token must be restored.
        assert svc.session.headers["X-Vault-Token"] == "primary"


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------


class TestConnection:
    def test_connection_ok_returns_connected(self):
        svc = _make_service()
        svc.session.get.return_value = _response(
            json_body={"version": "1.15.0", "initialized": True}
        )
        out = svc.test_connection()
        assert out["status"] == "connected"
        assert out["vault_info"]["version"] == "1.15.0"

    def test_connection_vault_error_returns_error_status(self):
        svc = _make_service(enabled=False)
        svc.vault_config = _vault_config(enabled=False)
        out = svc.test_connection()
        assert out["status"] == "error"
        assert "enabled" in out["error"].lower() or "not_enabled" in out["error"]

    def test_connection_unexpected_exception_returns_error_status(self):
        svc = _make_service()
        # Force the session itself to raise something not derived from
        # RequestException so we exercise the bare ``except Exception`` arm.
        svc.session.get.side_effect = RuntimeError("oops")
        out = svc.test_connection()
        assert out["status"] == "error"
        assert "oops" in out["error"] or "Unexpected" in out["error"]
