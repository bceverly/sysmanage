"""
Tests for certificate management API endpoints.
"""

from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest
from backend.persistence.models import Host


class TestCertificateEndpoints:
    """Test certificate management endpoints."""

    def test_get_server_fingerprint_success(self, client):
        """Test successful server fingerprint retrieval."""
        with patch("backend.api.certificates.certificate_manager") as mock_cert_manager:
            mock_cert_manager.get_server_certificate_fingerprint.return_value = (
                "ABCD1234" * 8
            )

            response = client.get("/certificates/server-fingerprint")

            assert response.status_code == 200
            data = response.json()
            assert "fingerprint" in data
            assert len(data["fingerprint"]) == 64

    def test_get_server_fingerprint_error(self, client):
        """Test server fingerprint retrieval error handling."""
        with patch("backend.api.certificates.certificate_manager") as mock_cert_manager:
            mock_cert_manager.get_server_certificate_fingerprint.side_effect = (
                Exception("Certificate error")
            )

            response = client.get("/certificates/server-fingerprint")

            assert response.status_code == 500
            assert "Failed to get server fingerprint" in response.json()["detail"]

    def test_get_ca_certificate_success(self, client):
        """Test successful CA certificate retrieval."""
        with patch("backend.api.certificates.certificate_manager") as mock_cert_manager:
            mock_cert_data = (
                b"-----BEGIN CERTIFICATE-----\nTEST CA CERT\n-----END CERTIFICATE-----"
            )
            mock_cert_manager.get_ca_certificate.return_value = mock_cert_data

            response = client.get("/certificates/ca-certificate")

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/x-pem-file"
            assert "attachment" in response.headers["content-disposition"]
            assert response.content == mock_cert_data

    def test_get_ca_certificate_error(self, client):
        """Test CA certificate retrieval error handling."""
        with patch("backend.api.certificates.certificate_manager") as mock_cert_manager:
            mock_cert_manager.get_ca_certificate.side_effect = Exception("CA error")

            response = client.get("/certificates/ca-certificate")

            assert response.status_code == 500
            assert "Failed to get CA certificate" in response.json()["detail"]

    def test_get_client_certificate_success(self, client, session, auth_headers):
        """Test successful client certificate retrieval."""
        # Create a test host in the database using raw SQL to avoid model field issues
        from sqlalchemy import text

        session.execute(
            text(
                """
            INSERT INTO host (id, fqdn, active, ipv4, approval_status, last_access, reboot_required)
            VALUES (101, 'success-test.example.com', 1, '192.168.1.100', 'approved', :timestamp, 0)
        """
            ),
            {"timestamp": datetime.now(timezone.utc)},
        )
        session.commit()

        with patch("backend.api.certificates.certificate_manager") as mock_cert_manager:
            mock_cert_pem = (
                b"-----BEGIN CERTIFICATE-----\nCLIENT CERT\n-----END CERTIFICATE-----"
            )
            mock_key_pem = (
                b"-----BEGIN PRIVATE KEY-----\nCLIENT KEY\n-----END PRIVATE KEY-----"
            )
            mock_ca_pem = (
                b"-----BEGIN CERTIFICATE-----\nCA CERT\n-----END CERTIFICATE-----"
            )

            mock_cert_manager.generate_client_certificate.return_value = (
                mock_cert_pem,
                mock_key_pem,
            )
            mock_cert_manager.get_ca_certificate.return_value = mock_ca_pem
            mock_cert_manager.get_server_certificate_fingerprint.return_value = (
                "FINGERPRINT123"
            )

            with patch("backend.api.certificates.x509") as mock_x509:
                mock_cert = MagicMock()
                mock_cert.serial_number = 12345
                mock_x509.load_pem_x509_certificate.return_value = mock_cert

                response = client.get(
                    "/api/certificates/client/101", headers=auth_headers
                )

                assert response.status_code == 200
                data = response.json()
                assert "certificate" in data
                assert "private_key" in data
                assert "ca_certificate" in data
                assert "server_fingerprint" in data

    def test_get_client_certificate_host_not_found(self, client, auth_headers):
        """Test client certificate retrieval when host not found."""
        response = client.get("/api/certificates/client/999", headers=auth_headers)

        assert response.status_code == 404
        assert "Host not found" in response.json()["detail"]

    def test_get_client_certificate_host_not_approved(
        self, client, session, auth_headers
    ):
        """Test client certificate retrieval when host not approved."""
        # Create a test host with pending approval using raw SQL
        from sqlalchemy import text

        session.execute(
            text(
                """
            INSERT INTO host (id, fqdn, active, ipv4, approval_status, last_access, reboot_required)
            VALUES (102, 'pending-test.example.com', 1, '192.168.1.100', 'pending', :timestamp, 0)
        """
            ),
            {"timestamp": datetime.now(timezone.utc)},
        )
        session.commit()

        response = client.get("/api/certificates/client/102", headers=auth_headers)

        assert response.status_code == 403
        assert "Host is not approved" in response.json()["detail"]

    def test_get_client_certificate_requires_auth(self, client):
        """Test that client certificate endpoint requires authentication."""
        response = client.get("/api/certificates/client/123")

        assert response.status_code in [401, 403]

    def test_revoke_client_certificate_success(self, client, session, auth_headers):
        """Test successful client certificate revocation."""
        # Create a test host with existing certificate using raw SQL
        from sqlalchemy import text

        timestamp = datetime.now(timezone.utc)
        session.execute(
            text(
                """
            INSERT INTO host (id, fqdn, active, ipv4, approval_status, client_certificate, certificate_serial, certificate_issued_at, last_access, reboot_required)
            VALUES (103, 'revoke-test.example.com', 1, '192.168.1.100', 'approved', 'existing cert', '12345', :timestamp, :timestamp, 0)
        """
            ),
            {"timestamp": timestamp},
        )
        session.commit()

        response = client.post("/api/certificates/revoke/103", headers=auth_headers)

        assert response.status_code == 200
        assert "Certificate revoked successfully" in response.json()["result"]

        # Query the host to verify changes
        from backend.persistence.models import Host

        host = session.query(Host).filter(Host.id == 103).first()
        assert host is not None
        assert host.client_certificate is None
        assert host.certificate_serial is None
        assert host.certificate_issued_at is None
        assert host.approval_status == "revoked"

    def test_revoke_client_certificate_host_not_found(self, client, auth_headers):
        """Test certificate revocation when host not found."""
        response = client.post("/api/certificates/revoke/999", headers=auth_headers)

        assert response.status_code == 404
        assert "Host not found" in response.json()["detail"]

    def test_revoke_client_certificate_requires_auth(self, client):
        """Test that certificate revocation requires authentication."""
        response = client.post("/api/certificates/revoke/123")

        assert response.status_code in [401, 403]


class TestCertificateEndpointsIntegration:
    """Integration tests for certificate endpoints."""

    def test_certificate_workflow_integration(self, client, session, auth_headers):
        """Test complete certificate workflow integration."""
        # Create a test host using raw SQL to avoid model field issues
        from sqlalchemy import text

        session.execute(
            text(
                """
            INSERT INTO host (id, fqdn, active, ipv4, approval_status, last_access, reboot_required)
            VALUES (104, 'integration-test.example.com', 1, '192.168.1.100', 'approved', :timestamp, 0)
        """
            ),
            {"timestamp": datetime.now(timezone.utc)},
        )
        session.commit()

        with patch("backend.api.certificates.certificate_manager") as mock_cert_manager:
            mock_cert_manager.get_server_certificate_fingerprint.return_value = (
                "TEST_FINGERPRINT_64CHARS" + "0" * 40
            )
            mock_cert_manager.get_ca_certificate.return_value = (
                b"-----BEGIN CERTIFICATE-----\nCA CERT\n-----END CERTIFICATE-----"
            )
            mock_cert_manager.generate_client_certificate.return_value = (
                b"-----BEGIN CERTIFICATE-----\nCLIENT CERT\n-----END CERTIFICATE-----",
                b"-----BEGIN PRIVATE KEY-----\nCLIENT KEY\n-----END PRIVATE KEY-----",
            )

            with patch("backend.api.certificates.x509") as mock_x509:
                mock_cert = MagicMock()
                mock_cert.serial_number = 12345
                mock_x509.load_pem_x509_certificate.return_value = mock_cert

                # 1. Get server fingerprint (unauthenticated)
                fingerprint_response = client.get("/certificates/server-fingerprint")
                assert fingerprint_response.status_code == 200

                # 2. Get CA certificate (unauthenticated)
                ca_response = client.get("/certificates/ca-certificate")
                assert ca_response.status_code == 200

                # 3. Get client certificate (authenticated)
                client_response = client.get(
                    "/api/certificates/client/104", headers=auth_headers
                )
                assert client_response.status_code == 200

                # 4. Revoke certificate (authenticated)
                revoke_response = client.post(
                    "/api/certificates/revoke/104", headers=auth_headers
                )
                assert revoke_response.status_code == 200


class TestCertificateEndpointsError:
    """Test certificate endpoint error conditions."""

    def test_invalid_host_id_format(self, client, auth_headers):
        """Test handling of invalid host ID format."""
        response = client.get("/api/certificates/client/invalid", headers=auth_headers)

        assert response.status_code == 422
