"""
Tests for backend/persistence/models/secret.py module.
Tests Secret model structure and methods.
"""

import uuid
from datetime import datetime, timezone

import pytest


class TestSecretModel:
    """Tests for Secret model."""

    def test_secret_table_name(self):
        """Test Secret table name."""
        from backend.persistence.models.secret import Secret

        assert Secret.__tablename__ == "secrets"

    def test_secret_columns_exist(self):
        """Test Secret has expected columns."""
        from backend.persistence.models.secret import Secret

        # Check that expected columns exist
        assert hasattr(Secret, "id")
        assert hasattr(Secret, "name")
        assert hasattr(Secret, "filename")
        assert hasattr(Secret, "secret_type")
        assert hasattr(Secret, "secret_subtype")
        assert hasattr(Secret, "vault_token")
        assert hasattr(Secret, "vault_path")
        assert hasattr(Secret, "created_at")
        assert hasattr(Secret, "updated_at")
        assert hasattr(Secret, "created_by")
        assert hasattr(Secret, "updated_by")


class TestSecretRepr:
    """Tests for Secret __repr__ method."""

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.secret import Secret

        secret = Secret()
        secret.id = uuid.uuid4()
        secret.name = "test-secret"
        secret.secret_type = "ssh_key"

        repr_str = repr(secret)

        assert "Secret" in repr_str
        assert "test-secret" in repr_str
        assert "ssh_key" in repr_str


class TestSecretToDict:
    """Tests for Secret.to_dict method."""

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all non-sensitive fields."""
        from backend.persistence.models.secret import Secret

        secret = Secret()
        secret.id = uuid.uuid4()
        secret.name = "my-secret"
        secret.filename = "id_rsa.pub"
        secret.secret_type = "ssh_key"
        secret.secret_subtype = "public"
        secret.vault_token = "s.token123"
        secret.vault_path = "secret/data/ssh"
        secret.created_at = datetime.now(timezone.utc)
        secret.updated_at = datetime.now(timezone.utc)
        secret.created_by = "admin@example.com"
        secret.updated_by = "admin@example.com"

        result = secret.to_dict()

        assert result["id"] == str(secret.id)
        assert result["name"] == "my-secret"
        assert result["filename"] == "id_rsa.pub"
        assert result["secret_type"] == "ssh_key"
        assert result["secret_subtype"] == "public"
        assert result["created_by"] == "admin@example.com"
        assert result["updated_by"] == "admin@example.com"
        # Should not include vault_token or vault_path
        assert "vault_token" not in result
        assert "vault_path" not in result

    def test_to_dict_with_none_dates(self):
        """Test to_dict handles None dates."""
        from backend.persistence.models.secret import Secret

        secret = Secret()
        secret.id = uuid.uuid4()
        secret.name = "test"
        secret.secret_type = "api_key"
        secret.created_at = None
        secret.updated_at = None
        secret.created_by = "user"
        secret.updated_by = "user"

        result = secret.to_dict()

        assert result["created_at"] is None
        assert result["updated_at"] is None

    def test_to_dict_id_is_string(self):
        """Test to_dict converts UUID to string."""
        from backend.persistence.models.secret import Secret

        secret = Secret()
        secret.id = uuid.uuid4()
        secret.name = "test"
        secret.secret_type = "database_credentials"
        secret.created_by = "user"
        secret.updated_by = "user"

        result = secret.to_dict()

        assert isinstance(result["id"], str)
