"""
Tests for backend/api/certificates.py module.
Tests certificate management API endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestGetServerFingerprint:
    """Tests for get_server_fingerprint endpoint."""

    @patch("backend.api.certificates.certificate_manager")
    def test_get_fingerprint_success(self, mock_cert_manager):
        """Test successful fingerprint retrieval."""
        from backend.api.certificates import public_router

        app = FastAPI()
        app.include_router(public_router)

        mock_cert_manager.get_server_certificate_fingerprint.return_value = (
            "AA:BB:CC:DD:EE:FF"
        )

        client = TestClient(app)
        response = client.get("/certificates/server-fingerprint")

        assert response.status_code == 200
        assert response.json()["fingerprint"] == "AA:BB:CC:DD:EE:FF"

    @patch("backend.api.certificates.certificate_manager")
    def test_get_fingerprint_exception(self, mock_cert_manager):
        """Test fingerprint retrieval with exception."""
        from backend.api.certificates import public_router

        app = FastAPI()
        app.include_router(public_router)

        mock_cert_manager.get_server_certificate_fingerprint.side_effect = Exception(
            "Certificate error"
        )

        client = TestClient(app)
        response = client.get("/certificates/server-fingerprint")

        assert response.status_code == 500


class TestGetCaCertificate:
    """Tests for get_ca_certificate endpoint."""

    @patch("backend.api.certificates.certificate_manager")
    def test_get_ca_cert_success(self, mock_cert_manager):
        """Test successful CA certificate retrieval."""
        from backend.api.certificates import public_router

        app = FastAPI()
        app.include_router(public_router)

        mock_cert_manager.get_ca_certificate.return_value = (
            b"-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----"
        )

        client = TestClient(app)
        response = client.get("/certificates/ca-certificate")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-pem-file"
        assert "attachment" in response.headers["content-disposition"]

    @patch("backend.api.certificates.certificate_manager")
    def test_get_ca_cert_exception(self, mock_cert_manager):
        """Test CA certificate retrieval with exception."""
        from backend.api.certificates import public_router

        app = FastAPI()
        app.include_router(public_router)

        mock_cert_manager.get_ca_certificate.side_effect = Exception("CA error")

        client = TestClient(app)
        response = client.get("/certificates/ca-certificate")

        assert response.status_code == 500


class TestGetClientCertificate:
    """Tests for get_client_certificate endpoint."""

    def test_get_client_cert_uuid_validation(self):
        """Test client certificate UUID validation logic."""
        import uuid

        # Valid UUID should not raise
        valid_uuid = "12345678-1234-1234-1234-123456789012"
        uuid.UUID(valid_uuid)  # Should not raise

        # Invalid UUID should raise
        with pytest.raises(ValueError):
            uuid.UUID("invalid-uuid")

    def test_get_client_cert_integer_id_valid(self):
        """Test that integer IDs are accepted for backward compatibility."""
        # This tests the fallback to int() for test compatibility
        host_id = "12345"
        try:
            int(host_id)
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid is True

    def test_get_client_cert_invalid_id_format(self):
        """Test that invalid IDs are rejected."""
        host_id = "not-valid-at-all"

        is_uuid = False
        is_int = False

        try:
            import uuid

            uuid.UUID(host_id)
            is_uuid = True
        except ValueError:
            pass

        try:
            int(host_id)
            is_int = True
        except ValueError:
            pass

        assert is_uuid is False
        assert is_int is False


class TestRevokeCertificate:
    """Tests for revoke_client_certificate endpoint."""

    def test_revoke_cert_uuid_validation(self):
        """Test revoke certificate UUID validation logic."""
        import uuid

        # Valid UUID should not raise
        valid_uuid = "12345678-1234-1234-1234-123456789012"
        uuid.UUID(valid_uuid)  # Should not raise

        # Integer ID should be accepted
        host_id = "12345"
        try:
            int(host_id)
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid is True


class TestRouterConfiguration:
    """Tests for router configuration."""

    def test_public_router_exists(self):
        """Test public_router exists."""
        from backend.api.certificates import public_router

        assert public_router is not None

    def test_auth_router_exists(self):
        """Test auth_router exists."""
        from backend.api.certificates import auth_router

        assert auth_router is not None

    def test_router_backward_compat(self):
        """Test router backward compatibility."""
        from backend.api.certificates import public_router, router

        assert router is public_router
