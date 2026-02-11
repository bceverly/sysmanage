"""
Tests for backend/services/vault_service.py module.
Tests OpenBAO vault service functionality.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestVaultErrorException:
    """Tests for VaultError exception class."""

    def test_vault_error_can_be_raised(self):
        """Test VaultError can be raised with message."""
        from backend.services.vault_service import VaultError

        with pytest.raises(VaultError) as exc_info:
            raise VaultError("Test error message")

        assert str(exc_info.value) == "Test error message"

    def test_vault_error_is_exception(self):
        """Test VaultError inherits from Exception."""
        from backend.services.vault_service import VaultError

        assert issubclass(VaultError, Exception)


class TestVaultServiceInit:
    """Tests for VaultService initialization."""

    @patch("backend.services.vault_service.config")
    def test_init_loads_config(self, mock_config):
        """Test initialization loads vault configuration."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {
            "url": "http://vault.example.com:8200",
            "token": "test-token",
            "mount_path": "kv",
            "timeout": 60,
            "verify_ssl": False,
        }

        service = VaultService()

        assert service.base_url == "http://vault.example.com:8200"
        assert service.token == "test-token"
        assert service.mount_path == "kv"
        assert service.timeout == 60
        assert service.verify_ssl is False

    @patch("backend.services.vault_service.config")
    def test_init_uses_defaults(self, mock_config):
        """Test initialization uses default values when config is empty."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {}

        service = VaultService()

        assert service.base_url == "http://localhost:8200"
        assert service.token == ""
        assert service.mount_path == "secret"
        assert service.timeout == 30
        assert service.verify_ssl is True

    @patch("backend.services.vault_service.config")
    def test_init_sets_up_session(self, mock_config):
        """Test initialization sets up requests session with retry strategy."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"token": "my-token"}

        service = VaultService()

        assert service.session is not None
        assert service.session.headers.get("X-Vault-Token") == "my-token"
        assert service.session.headers.get("Content-Type") == "application/json"


class TestVaultServiceMakeRequest:
    """Tests for VaultService._make_request method."""

    @patch("backend.services.vault_service.config")
    def test_make_request_raises_when_not_enabled(self, mock_config):
        """Test _make_request raises when vault is not enabled."""
        from backend.services.vault_service import VaultError, VaultService

        mock_config.get_vault_config.return_value = {"enabled": False}

        service = VaultService()

        with pytest.raises(VaultError):
            service._make_request("GET", "sys/health")

    @patch("backend.services.vault_service.config")
    def test_make_request_raises_when_no_token(self, mock_config):
        """Test _make_request raises when no token configured."""
        from backend.services.vault_service import VaultError, VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": ""}

        service = VaultService()

        with pytest.raises(VaultError):
            service._make_request("GET", "sys/health")

    @patch("backend.services.vault_service.config")
    def test_make_request_unsupported_method(self, mock_config):
        """Test _make_request raises for unsupported HTTP method."""
        from backend.services.vault_service import VaultError, VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with pytest.raises(VaultError) as exc_info:
            service._make_request("PATCH", "sys/health")

        assert "Unsupported HTTP method" in str(exc_info.value)

    @patch("backend.services.vault_service.config")
    def test_make_request_get_success(self, mock_config):
        """Test _make_request GET returns response data."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data": "test"}'
        mock_response.json.return_value = {"data": "test"}

        with patch.object(service.session, "get", return_value=mock_response):
            result = service._make_request("GET", "sys/health")

        assert result == {"data": "test"}

    @patch("backend.services.vault_service.config")
    def test_make_request_post_success(self, mock_config):
        """Test _make_request POST returns response data."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"result": "ok"}'
        mock_response.json.return_value = {"result": "ok"}

        with patch.object(service.session, "post", return_value=mock_response):
            result = service._make_request("POST", "v1/secret", {"key": "value"})

        assert result == {"result": "ok"}

    @patch("backend.services.vault_service.config")
    def test_make_request_put_success(self, mock_config):
        """Test _make_request PUT returns response data."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"version": 1}'
        mock_response.json.return_value = {"version": 1}

        with patch.object(service.session, "put", return_value=mock_response):
            result = service._make_request("PUT", "v1/secret", {"data": "test"})

        assert result == {"version": 1}

    @patch("backend.services.vault_service.config")
    def test_make_request_delete_success(self, mock_config):
        """Test _make_request DELETE returns empty dict."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b""

        with patch.object(service.session, "delete", return_value=mock_response):
            result = service._make_request("DELETE", "v1/secret")

        assert result == {}

    @patch("backend.services.vault_service.config")
    def test_make_request_404_returns_empty(self, mock_config):
        """Test _make_request returns empty dict for 404."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch.object(service.session, "get", return_value=mock_response):
            result = service._make_request("GET", "v1/nonexistent")

        assert result == {}

    @patch("backend.services.vault_service.config")
    def test_make_request_403_raises_permission_denied(self, mock_config):
        """Test _make_request raises for 403."""
        from backend.services.vault_service import VaultError, VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch.object(service.session, "get", return_value=mock_response):
            with pytest.raises(VaultError):
                service._make_request("GET", "v1/secret")

    @patch("backend.services.vault_service.config")
    def test_make_request_connection_error(self, mock_config):
        """Test _make_request handles connection errors."""
        import requests

        from backend.services.vault_service import VaultError, VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(
            service.session, "get", side_effect=requests.exceptions.ConnectionError()
        ):
            with pytest.raises(VaultError):
                service._make_request("GET", "sys/health")

    @patch("backend.services.vault_service.config")
    def test_make_request_timeout_error(self, mock_config):
        """Test _make_request handles timeout errors."""
        import requests

        from backend.services.vault_service import VaultError, VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(
            service.session, "get", side_effect=requests.exceptions.Timeout()
        ):
            with pytest.raises(VaultError):
                service._make_request("GET", "sys/health")


class TestVaultServiceStoreSecret:
    """Tests for VaultService.store_secret method."""

    @patch("backend.services.vault_service.config")
    def test_store_ssh_key_public(self, mock_config):
        """Test storing a public SSH key."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(service, "_make_request") as mock_request:
            mock_request.return_value = {"data": {"version": 1}}

            result = service.store_secret(
                secret_name="test-key",
                secret_data="ssh-rsa AAAA...",
                secret_type="ssh_key",
                secret_subtype="public",
            )

        assert "vault_path" in result
        assert "ssh/public" in result["vault_path"]
        assert result["version"] == 1

    @patch("backend.services.vault_service.config")
    def test_store_ssh_key_private(self, mock_config):
        """Test storing a private SSH key."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(service, "_make_request") as mock_request:
            mock_request.return_value = {"data": {"version": 1}}

            result = service.store_secret(
                secret_name="test-key",
                secret_data="-----BEGIN RSA PRIVATE KEY-----",
                secret_type="ssh_key",
                secret_subtype="private",
            )

        assert "vault_path" in result
        assert "ssh/private" in result["vault_path"]

    @patch("backend.services.vault_service.config")
    def test_store_ssl_certificate(self, mock_config):
        """Test storing an SSL certificate."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(service, "_make_request") as mock_request:
            mock_request.return_value = {}

            result = service.store_secret(
                secret_name="test-cert",
                secret_data="-----BEGIN CERTIFICATE-----",
                secret_type="ssl_certificate",
                secret_subtype="certificate",
            )

        assert "vault_path" in result
        assert "pki/certificate" in result["vault_path"]

    @patch("backend.services.vault_service.config")
    def test_store_database_credentials(self, mock_config):
        """Test storing database credentials."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(service, "_make_request") as mock_request:
            mock_request.return_value = {}

            result = service.store_secret(
                secret_name="db-creds",
                secret_data='{"user": "admin", "password": "secret"}',
                secret_type="database_credentials",
                secret_subtype="postgresql",
            )

        assert "vault_path" in result
        assert "db/postgresql" in result["vault_path"]

    @patch("backend.services.vault_service.config")
    def test_store_api_key(self, mock_config):
        """Test storing an API key."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(service, "_make_request") as mock_request:
            mock_request.return_value = {}

            result = service.store_secret(
                secret_name="github-token",
                secret_data="ghp_xxx...",
                secret_type="api_keys",
                secret_subtype="github",
            )

        assert "vault_path" in result
        assert "api/github" in result["vault_path"]


class TestVaultServiceRetrieveSecret:
    """Tests for VaultService.retrieve_secret method."""

    @patch("backend.services.vault_service.config")
    def test_retrieve_secret_success(self, mock_config):
        """Test successful secret retrieval."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(service, "_make_request") as mock_request:
            mock_request.return_value = {
                "data": {"data": {"name": "test", "content": "secret_value"}}
            }

            result = service.retrieve_secret("secret/data/test")

        assert result["name"] == "test"
        assert result["content"] == "secret_value"

    @patch("backend.services.vault_service.config")
    def test_retrieve_secret_not_found(self, mock_config):
        """Test secret retrieval when secret not found."""
        from backend.services.vault_service import VaultError, VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(service, "_make_request") as mock_request:
            mock_request.return_value = {}

            with pytest.raises(VaultError):
                service.retrieve_secret("secret/data/nonexistent")

    @patch("backend.services.vault_service.config")
    def test_retrieve_secret_with_custom_token(self, mock_config):
        """Test secret retrieval with custom token."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {
            "enabled": True,
            "token": "default-token",
        }

        service = VaultService()

        with patch.object(service, "_make_request") as mock_request:
            mock_request.return_value = {"data": {"data": {"content": "value"}}}

            service.retrieve_secret("secret/data/test", vault_token="custom-token")

        # Token should be restored after call
        assert service.session.headers.get("X-Vault-Token") == "default-token"


class TestVaultServiceDeleteSecret:
    """Tests for VaultService.delete_secret method."""

    @patch("backend.services.vault_service.config")
    def test_delete_secret_success(self, mock_config):
        """Test successful secret deletion."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(service, "_make_request") as mock_request:
            mock_request.return_value = {"data": {"metadata": {"version": 1}}}

            result = service.delete_secret("secret/data/test")

        assert result is True

    @patch("backend.services.vault_service.config")
    def test_delete_secret_not_found_treated_as_deleted(self, mock_config):
        """Test deletion returns True when secret already doesn't exist."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(service, "_make_request") as mock_request:
            # First GET returns empty (not found)
            mock_request.return_value = {}

            result = service.delete_secret("secret/data/nonexistent")

        assert result is True


class TestVaultServiceTestConnection:
    """Tests for VaultService.test_connection method."""

    @patch("backend.services.vault_service.config")
    def test_connection_success(self, mock_config):
        """Test successful connection test."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(service, "_make_request") as mock_request:
            mock_request.return_value = {"initialized": True, "sealed": False}

            result = service.test_connection()

        assert result["status"] == "connected"
        assert result["vault_info"]["initialized"] is True

    @patch("backend.services.vault_service.config")
    def test_connection_vault_error(self, mock_config):
        """Test connection test with VaultError."""
        from backend.services.vault_service import VaultError, VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(service, "_make_request") as mock_request:
            mock_request.side_effect = VaultError("Connection failed")

            result = service.test_connection()

        assert result["status"] == "error"
        assert "Connection failed" in result["error"]

    @patch("backend.services.vault_service.config")
    def test_connection_unexpected_error(self, mock_config):
        """Test connection test with unexpected error."""
        from backend.services.vault_service import VaultService

        mock_config.get_vault_config.return_value = {"enabled": True, "token": "token"}

        service = VaultService()

        with patch.object(service, "_make_request") as mock_request:
            mock_request.side_effect = RuntimeError("Unexpected")

            result = service.test_connection()

        assert result["status"] == "error"
        assert "Unexpected" in result["error"]


class TestVaultConstants:
    """Tests for vault service constants."""

    def test_vault_data_path_constant(self):
        """Test VAULT_DATA_PATH constant."""
        from backend.services.vault_service import VAULT_DATA_PATH

        assert VAULT_DATA_PATH == "/data/"
