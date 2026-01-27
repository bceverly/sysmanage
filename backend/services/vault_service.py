"""
Service for interacting with OpenBAO vault to store and retrieve secrets.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.config import config
from backend.i18n import _

logger = logging.getLogger(__name__)

# Constants for vault paths
VAULT_DATA_PATH = "/data/"


class VaultError(Exception):
    """Exception raised for vault-related errors."""


class VaultService:
    """Service for managing secrets in OpenBAO vault."""

    def __init__(self):
        self.vault_config = config.get_vault_config()
        self.base_url = self.vault_config.get("url", "http://localhost:8200")
        self.token = self.vault_config.get("token", "")
        self.mount_path = self.vault_config.get("mount_path", "secret")
        self.timeout = self.vault_config.get("timeout", 30)
        self.verify_ssl = self.vault_config.get("verify_ssl", True)

        # Configure session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Set default headers
        self.session.headers.update(
            {"X-Vault-Token": self.token, "Content-Type": "application/json"}
        )

    def _make_request(  # NOSONAR
        self, method: str, path: str, data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make a request to the vault API with error handling."""
        if not self.vault_config.get("enabled", False):
            raise VaultError(_("vault.not_enabled", "Vault is not enabled"))

        if not self.token:
            raise VaultError(_("vault.no_token", "Vault token not configured"))

        url = f"{self.base_url}/v1/{path}"

        try:
            if method.upper() == "GET":
                response = self.session.get(
                    url, timeout=self.timeout, verify=self.verify_ssl
                )
            elif method.upper() == "POST":
                response = self.session.post(
                    url, json=data, timeout=self.timeout, verify=self.verify_ssl
                )
            elif method.upper() == "PUT":
                response = self.session.put(
                    url, json=data, timeout=self.timeout, verify=self.verify_ssl
                )
            elif method.upper() == "DELETE":
                response = self.session.delete(
                    url, timeout=self.timeout, verify=self.verify_ssl
                )
            else:
                raise VaultError(f"Unsupported HTTP method: {method}")

            # Check for HTTP errors
            if response.status_code == 404:
                return {}  # Not found is often expected in vault operations
            elif response.status_code == 403:
                raise VaultError(_("vault.permission_denied", "Permission denied"))
            elif response.status_code >= 400:
                error_msg = response.text or f"HTTP {response.status_code}"
                raise VaultError(f"Vault API error: {error_msg}")

            # Parse JSON response
            if response.content:
                return response.json()
            return {}

        except requests.exceptions.ConnectionError as exc:
            raise VaultError(
                _("vault.connection_error", "Cannot connect to vault server")
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise VaultError(_("vault.timeout", "Vault request timed out")) from exc
        except requests.exceptions.RequestException as e:
            raise VaultError(f"Vault request failed: {str(e)}") from e
        except json.JSONDecodeError as exc:
            raise VaultError(
                _("vault.invalid_response", "Invalid response from vault")
            ) from exc

    def store_secret(  # NOSONAR
        self,
        secret_name: str,
        secret_data: str,
        secret_type: str,
        secret_subtype: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Store a secret in the vault and return metadata for database storage.

        Args:
            secret_name: Name of the secret
            secret_data: The actual secret content
            secret_type: Type of secret (e.g., 'ssh_key')
            secret_subtype: For SSH keys: 'public' or 'private'

        Returns:
            Dictionary with vault_path and vault_token for database storage
        """
        # Generate unique path for this secret with proper subpath structure
        secret_id = str(uuid.uuid4())

        # Create subpath based on secret type and visibility
        if secret_type == "ssh_key":  # nosec B105
            # SSH keys: ssh/public, ssh/private, ssh/ca
            base_path = "ssh"
            if secret_subtype in ["public", "private", "ca"]:
                subpath = secret_subtype
            else:
                subpath = "private"  # Default fallback
        elif secret_type == "ssl_certificate":  # nosec B105
            # SSL certificates: pki/root, pki/intermediate, pki/chain, pki/key_file, pki/certificate
            base_path = "pki"
            if secret_subtype in [
                "root",
                "intermediate",
                "chain",
                "key_file",
                "certificate",
            ]:
                subpath = secret_subtype
            else:
                subpath = "certificate"  # Default fallback
        elif secret_type == "database_credentials":  # nosec B105
            # Database credentials: db/postgresql, db/mysql, db/oracle, db/sqlserver, db/sqlite
            base_path = "db"
            if secret_subtype in [
                "postgresql",
                "mysql",
                "oracle",
                "sqlserver",
                "sqlite",
            ]:
                subpath = secret_subtype
            else:
                subpath = "postgresql"  # Default fallback
        elif secret_type == "api_keys":  # nosec B105
            # API keys: api/github, api/salesforce
            base_path = "api"
            if secret_subtype in ["github", "salesforce"]:
                subpath = secret_subtype
            else:
                subpath = "github"  # Default fallback
        elif secret_type == "API Key":  # nosec B105
            # API Keys: api/grafana, api/github, api/salesforce
            base_path = "api"
            if secret_subtype in ["grafana", "github", "salesforce"]:
                subpath = secret_subtype
            else:
                subpath = "default"  # Default fallback
        else:
            # Fallback for unknown types
            base_path = secret_type
            subpath = secret_subtype or "default"

        vault_path = f"{self.mount_path}/data/secrets/{base_path}/{subpath}/{secret_id}"

        # Prepare secret data for vault storage
        vault_data = {
            "data": {
                "name": secret_name,
                "secret_type": secret_type,
                "content": secret_data,
                "secret_subtype": secret_subtype,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        }

        try:
            # Store the secret in vault
            response = self._make_request("PUT", vault_path, vault_data)

            # For KV v2, vault returns version info
            version = None
            if response and "data" in response:
                version = response["data"].get("version")

            return {
                "vault_path": vault_path,
                "vault_token": self.token,  # In production, you'd use a unique token per secret
                "version": version,
            }

        except VaultError:
            raise
        except Exception as e:
            raise VaultError(f"Failed to store secret: {str(e)}") from e

    def retrieve_secret(
        self, vault_path: str, vault_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieve a secret from the vault.

        Args:
            vault_path: Path where the secret is stored
            vault_token: Token to access the secret (optional, uses default if not provided)

        Returns:
            Dictionary containing the secret data
        """
        # Temporarily use the provided token if different
        original_token = None
        if vault_token and vault_token != self.token:
            original_token = self.session.headers.get("X-Vault-Token")
            self.session.headers["X-Vault-Token"] = vault_token

        try:
            response = self._make_request("GET", vault_path)

            if not response or "data" not in response:
                raise VaultError(_("vault.secret_not_found", "Secret not found"))

            # Extract secret data (KV v2 format)
            secret_data = response["data"].get("data", {})
            if not secret_data:
                raise VaultError(
                    _("vault.invalid_secret_format", "Invalid secret format")
                )

            return secret_data

        except VaultError:
            raise
        except Exception as e:
            raise VaultError(f"Failed to retrieve secret: {str(e)}") from e
        finally:
            # Restore original token if it was changed
            if original_token:
                self.session.headers["X-Vault-Token"] = original_token

    def delete_secret(self, vault_path: str, vault_token: Optional[str] = None) -> bool:
        """
        Delete a secret from the vault.

        Args:
            vault_path: Path where the secret is stored
            vault_token: Token to access the secret (optional)

        Returns:
            True if deletion was successful
        """
        # Temporarily use the provided token if different
        original_token = None
        if vault_token and vault_token != self.token:
            original_token = self.session.headers.get("X-Vault-Token")
            self.session.headers["X-Vault-Token"] = vault_token

        try:
            logger.info("Starting vault deletion for path: %s", vault_path)
            # For KV v2, we need to permanently delete (destroy) the secret
            # First, get the current version number
            try:
                response = self._make_request("GET", vault_path)
                current_version = 1  # Default to 1
                if response and "data" in response and "metadata" in response["data"]:
                    current_version = response["data"]["metadata"].get("version", 1)
                elif not response or not response.get("data"):
                    # Secret doesn't exist in vault - consider it already deleted
                    return True
            except Exception:
                current_version = 1  # Fallback to version 1

            # Soft delete first
            delete_path = vault_path.replace(VAULT_DATA_PATH, "/delete/")
            logger.info("Step 1: Soft delete at path: %s", delete_path)
            try:
                self._make_request("DELETE", delete_path)
                logger.info("Soft delete successful")
            except Exception as e:
                # Continue with destroy even if soft delete fails
                logger.warning(
                    "Soft delete failed for path %s: %s", delete_path, str(e)
                )

            # Then permanently destroy it to completely remove from vault
            destroy_path = vault_path.replace(VAULT_DATA_PATH, "/destroy/")
            destroy_data = {"versions": [current_version]}
            logger.info(
                "Step 2: Destroy at path: %s with versions: %s",
                destroy_path,
                destroy_data,
            )
            try:
                self._make_request("PUT", destroy_path, destroy_data)
                logger.info("Destroy successful")
            except Exception as e:
                # If both operations failed because secret doesn't exist, that's ok
                if "not found" in str(e).lower():
                    logger.info("Secret not found during destroy - considering deleted")
                    return True
                logger.error("Destroy failed: %s", str(e))
                raise

            # Finally, delete the metadata to completely remove all traces
            metadata_path = vault_path.replace(VAULT_DATA_PATH, "/metadata/")
            logger.info("Step 3: Metadata delete at path: %s", metadata_path)
            try:
                self._make_request("DELETE", metadata_path)
                logger.info("Metadata delete successful")
            except Exception as e:
                # If metadata delete fails, log but don't fail the whole operation
                # since the data is already destroyed
                logger.warning(
                    "Metadata delete failed for path %s: %s", metadata_path, str(e)
                )

            return True

        except VaultError:
            raise
        except Exception as e:
            raise VaultError(f"Failed to delete secret: {str(e)}") from e
        finally:
            # Restore original token if it was changed
            if original_token:
                self.session.headers["X-Vault-Token"] = original_token

    def test_connection(self) -> Dict[str, Any]:
        """Test the connection to vault and return status information."""
        try:
            response = self._make_request("GET", "sys/health")
            return {"status": "connected", "vault_info": response}
        except VaultError as e:
            return {"status": "error", "error": str(e)}
        except Exception as e:
            return {"status": "error", "error": f"Unexpected error: {str(e)}"}
