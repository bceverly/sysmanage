"""
Tests for certificate management functionality.
"""

import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import NameOID

from backend.security.certificate_manager import CertificateManager


class TestCertificateManager:
    """Test certificate management functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()

        # Mock config to use temporary directory
        self.mock_config = {"certificates": {"path": self.temp_dir}}

    def teardown_method(self):
        """Clean up test environment."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("backend.security.certificate_manager.get_config")
    def test_certificate_manager_initialization(self, mock_get_config):
        """Test certificate manager initialization."""
        mock_get_config.return_value = self.mock_config

        # Mock os.environ to prevent pytest temp dir override
        with patch("backend.security.certificate_manager.os.environ", {}):
            cert_manager = CertificateManager()
            assert cert_manager.cert_dir == Path(self.temp_dir)
            assert cert_manager.cert_dir.exists()

    @patch("backend.security.certificate_manager.get_config")
    def test_generate_private_key(self, mock_get_config):
        """Test private key generation."""
        mock_get_config.return_value = self.mock_config

        cert_manager = CertificateManager()
        private_key = cert_manager.generate_private_key()

        assert private_key.key_size == 2048
        assert private_key.public_key().key_size == 2048

    @patch("backend.security.certificate_manager.get_config")
    def test_ensure_ca_certificate_creates_new(self, mock_get_config):
        """Test CA certificate creation when none exists."""
        mock_get_config.return_value = self.mock_config

        cert_manager = CertificateManager()
        cert_manager.ensure_ca_certificate()

        # Check that CA files were created
        assert cert_manager.ca_cert_path.exists()
        assert cert_manager.ca_key_path.exists()

        # Verify CA certificate properties
        with open(cert_manager.ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())

        assert (
            ca_cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value
            == "SysManage CA"
        )

        # Check that it's a CA certificate
        basic_constraints = ca_cert.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.BASIC_CONSTRAINTS
        )
        assert basic_constraints.value.ca is True

    @patch("backend.security.certificate_manager.get_config")
    def test_ensure_ca_certificate_reuses_existing(self, mock_get_config):
        """Test CA certificate reuse when already exists."""
        mock_get_config.return_value = self.mock_config

        cert_manager = CertificateManager()

        # Create initial CA certificate
        cert_manager.ensure_ca_certificate()
        original_ca_mtime = cert_manager.ca_cert_path.stat().st_mtime

        # Call again - should reuse existing
        cert_manager.ensure_ca_certificate()
        new_ca_mtime = cert_manager.ca_cert_path.stat().st_mtime

        assert original_ca_mtime == new_ca_mtime

    @patch("backend.security.certificate_manager.get_config")
    def test_ensure_server_certificate_creates_new(self, mock_get_config):
        """Test server certificate creation when none exists."""
        mock_get_config.return_value = self.mock_config

        cert_manager = CertificateManager()
        cert_manager.ensure_server_certificate()

        # Check that server files were created
        assert cert_manager.server_cert_path.exists()
        assert cert_manager.server_key_path.exists()
        assert cert_manager.ca_cert_path.exists()  # Should create CA too

        # Verify server certificate properties
        with open(cert_manager.server_cert_path, "rb") as f:
            server_cert = x509.load_pem_x509_certificate(f.read())

        assert (
            server_cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[
                0
            ].value
            == "SysManage Server"
        )

        # Check that it's not a CA certificate
        basic_constraints = server_cert.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.BASIC_CONSTRAINTS
        )
        assert basic_constraints.value.ca is False

        # Check Server Auth extension
        ext_key_usage = server_cert.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.EXTENDED_KEY_USAGE
        )
        assert x509.oid.ExtendedKeyUsageOID.SERVER_AUTH in ext_key_usage.value

    @patch("backend.security.certificate_manager.get_config")
    def test_generate_client_certificate(self, mock_get_config):
        """Test client certificate generation."""
        mock_get_config.return_value = self.mock_config

        cert_manager = CertificateManager()
        hostname = "test-host.example.com"
        host_id = "550e8400-e29b-41d4-a716-446655440001"

        cert_pem, key_pem = cert_manager.generate_client_certificate(hostname, host_id)

        # Verify certificate format
        assert cert_pem.startswith(b"-----BEGIN CERTIFICATE-----")
        assert key_pem.startswith(b"-----BEGIN PRIVATE KEY-----")

        # Load and verify certificate properties
        client_cert = x509.load_pem_x509_certificate(cert_pem)

        # Check subject fields
        common_name = client_cert.subject.get_attributes_for_oid(
            x509.NameOID.COMMON_NAME
        )[0].value
        assert common_name == hostname

        org_unit = client_cert.subject.get_attributes_for_oid(
            x509.NameOID.ORGANIZATIONAL_UNIT_NAME
        )[0].value
        assert org_unit == str(host_id)

        # Check that it's not a CA certificate
        basic_constraints = client_cert.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.BASIC_CONSTRAINTS
        )
        assert basic_constraints.value.ca is False

        # Check Client Auth extension
        ext_key_usage = client_cert.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.EXTENDED_KEY_USAGE
        )
        assert x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH in ext_key_usage.value

    @patch("backend.security.certificate_manager.get_config")
    def test_get_server_certificate_fingerprint(self, mock_get_config):
        """Test server certificate fingerprint calculation."""
        mock_get_config.return_value = self.mock_config

        cert_manager = CertificateManager()
        fingerprint = cert_manager.get_server_certificate_fingerprint()

        # Should be SHA256 fingerprint (64 hex chars, uppercase)
        assert len(fingerprint) == 64
        assert fingerprint.isupper()
        assert all(c in "0123456789ABCDEF" for c in fingerprint)

    @patch("backend.security.certificate_manager.get_config")
    def test_get_ca_certificate(self, mock_get_config):
        """Test CA certificate retrieval."""
        mock_get_config.return_value = self.mock_config

        cert_manager = CertificateManager()
        ca_cert_pem = cert_manager.get_ca_certificate()

        # Should be valid PEM certificate
        assert ca_cert_pem.startswith(b"-----BEGIN CERTIFICATE-----")
        assert ca_cert_pem.endswith(b"-----END CERTIFICATE-----\n")

        # Should be loadable
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem)
        assert (
            ca_cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value
            == "SysManage CA"
        )

    @patch("backend.security.certificate_manager.get_config")
    def test_validate_client_certificate_valid(self, mock_get_config):
        """Test validation of valid client certificate."""
        mock_get_config.return_value = self.mock_config

        # Mock os.environ to prevent pytest temp dir override
        with patch("backend.security.certificate_manager.os.environ", {}):
            cert_manager = CertificateManager()
            hostname = "test-host.example.com"
            host_id = "550e8400-e29b-41d4-a716-446655440001"

            cert_pem, _ = cert_manager.generate_client_certificate(hostname, host_id)
            result = cert_manager.validate_client_certificate(cert_pem)

            assert result is not None
            assert result[0] == hostname
            assert result[1] == host_id

    @patch("backend.security.certificate_manager.get_config")
    def test_validate_client_certificate_expired(self, mock_get_config):
        """Test validation of expired client certificate."""
        mock_get_config.return_value = self.mock_config

        # Mock os.environ to prevent pytest temp dir override
        with patch("backend.security.certificate_manager.os.environ", {}):
            cert_manager = CertificateManager()

            hostname = "test-host.example.com"
            host_id = "550e8400-e29b-41d4-a716-446655440001"

            # Generate certificate normally
            cert_pem, _ = cert_manager.generate_client_certificate(hostname, host_id)

            # Mock datetime to make certificate appear expired during validation
            with patch(
                "backend.security.certificate_manager.datetime"
            ) as mock_datetime:
                # Set current time to far future (make cert appear expired)
                future_time = datetime.now(timezone.utc) + timedelta(days=400)
                mock_datetime.now.return_value = future_time
                mock_datetime.utc = timezone.utc

                result = cert_manager.validate_client_certificate(cert_pem)

                assert result is None

    @patch("backend.security.certificate_manager.get_config")
    def test_validate_client_certificate_invalid(self, mock_get_config):
        """Test validation of invalid certificate."""
        mock_get_config.return_value = self.mock_config

        cert_manager = CertificateManager()

        # Invalid PEM data
        invalid_cert = (
            b"-----BEGIN CERTIFICATE-----\nINVALID DATA\n-----END CERTIFICATE-----"
        )
        result = cert_manager.validate_client_certificate(invalid_cert)

        assert result is None

    @patch("backend.security.certificate_manager.get_config")
    def test_certificate_file_permissions(self, mock_get_config):
        """Test that certificate files have correct permissions."""
        import platform

        mock_get_config.return_value = self.mock_config

        cert_manager = CertificateManager()
        cert_manager.ensure_ca_certificate()
        cert_manager.ensure_server_certificate()

        # Skip detailed permission checks on Windows since it uses a different permission model
        if platform.system() == "Windows":
            # Just verify files exist and are readable
            assert cert_manager.ca_key_path.exists()
            assert cert_manager.server_key_path.exists()
            assert cert_manager.ca_cert_path.exists()
            assert cert_manager.server_cert_path.exists()
        else:
            # CA key should be 0600 (owner read/write only)
            ca_key_perms = oct(cert_manager.ca_key_path.stat().st_mode)[-3:]
            assert ca_key_perms == "600"

            # Server key should be 0600 (owner read/write only)
            server_key_perms = oct(cert_manager.server_key_path.stat().st_mode)[-3:]
            assert server_key_perms == "600"

            # Certificates should be 0644 (world readable)
            ca_cert_perms = oct(cert_manager.ca_cert_path.stat().st_mode)[-3:]
            assert ca_cert_perms == "644"

            server_cert_perms = oct(cert_manager.server_cert_path.stat().st_mode)[-3:]
            assert server_cert_perms == "644"


class TestCertificateManagerError:
    """Test certificate manager error conditions."""

    @patch("backend.security.certificate_manager.get_config")
    def test_certificate_directory_creation_failure(self, mock_get_config):
        """Test handling of certificate directory creation failure."""
        import platform

        # Use platform-appropriate invalid path that should cause directory creation to fail
        if platform.system() == "Windows":
            # Try to create a directory under a system file (this should fail)
            invalid_path = "C:\\Windows\\System32\\kernel32.dll\\invalid_dir"
        else:
            invalid_path = "/dev/null/invalid"

        # Mock the config to return a problematic path
        mock_get_config.return_value = {"certificates": {"path": invalid_path}}

        # Mock os.environ to prevent pytest detection
        with patch("backend.security.certificate_manager.os.environ", {}):
            with pytest.raises(Exception):
                CertificateManager()

    @patch("backend.security.certificate_manager.get_config")
    def test_missing_ca_for_client_cert_generation(self, mock_get_config):
        """Test client certificate generation when CA is missing."""
        temp_dir = tempfile.mkdtemp()
        try:
            mock_get_config.return_value = {"certificates": {"path": temp_dir}}

            cert_manager = CertificateManager()

            # Remove CA files if they exist
            if cert_manager.ca_cert_path.exists():
                cert_manager.ca_cert_path.unlink()
            if cert_manager.ca_key_path.exists():
                cert_manager.ca_key_path.unlink()

            # Should create CA automatically
            cert_pem, key_pem = cert_manager.generate_client_certificate(
                "test-host", 123
            )
            assert cert_pem is not None
            assert key_pem is not None
            assert cert_manager.ca_cert_path.exists()

        finally:
            shutil.rmtree(temp_dir)


class TestCertificateManagerIntegration:
    """Integration tests for certificate manager."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.mock_config = {"certificates": {"path": self.temp_dir}}

    def teardown_method(self):
        """Clean up test environment."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("backend.security.certificate_manager.get_config")
    def test_full_certificate_workflow(self, mock_get_config):
        """Test complete certificate workflow from CA creation to client validation."""
        mock_get_config.return_value = self.mock_config

        # Mock os.environ to prevent pytest temp dir override
        with patch("backend.security.certificate_manager.os.environ", {}):
            cert_manager = CertificateManager()

            # 1. Ensure server certificates
            cert_manager.ensure_server_certificate()
            assert cert_manager.server_cert_path.exists()
            assert cert_manager.ca_cert_path.exists()

            # 2. Get server fingerprint
            fingerprint = cert_manager.get_server_certificate_fingerprint()
            assert len(fingerprint) == 64

            # 3. Generate client certificate
            hostname = "integration-test.example.com"
            host_id = "550e8400-e29b-41d4-a716-446655440002"
            cert_pem, key_pem = cert_manager.generate_client_certificate(
                hostname, host_id
            )

            # 4. Validate client certificate
            result = cert_manager.validate_client_certificate(cert_pem)
            assert result is not None
            assert result[0] == hostname
            assert result[1] == host_id

            # 5. Get CA certificate
            ca_cert_pem = cert_manager.get_ca_certificate()
            assert ca_cert_pem.startswith(b"-----BEGIN CERTIFICATE-----")

            # 6. Verify the client certificate was signed by the CA
            client_cert = x509.load_pem_x509_certificate(cert_pem)
            ca_cert = x509.load_pem_x509_certificate(ca_cert_pem)

            # Check issuer matches CA subject
            assert client_cert.issuer == ca_cert.subject

    @patch("backend.security.certificate_manager.get_config")
    def test_certificate_regeneration_different_serial(self, mock_get_config):
        """Test that regenerated certificates have different serial numbers."""
        mock_get_config.return_value = self.mock_config

        cert_manager = CertificateManager()
        hostname = "serial-test.example.com"
        host_id = 55555

        # Generate first certificate
        cert_pem_1, _ = cert_manager.generate_client_certificate(hostname, host_id)
        client_cert_1 = x509.load_pem_x509_certificate(cert_pem_1)

        # Generate second certificate
        cert_pem_2, _ = cert_manager.generate_client_certificate(hostname, host_id)
        client_cert_2 = x509.load_pem_x509_certificate(cert_pem_2)

        # Serial numbers should be different
        assert client_cert_1.serial_number != client_cert_2.serial_number

    @patch("backend.security.certificate_manager.get_config")
    def test_validate_certificate_invalid_host_id_format(self, mock_get_config):
        """Test certificate validation with non-numeric host_id (line 367-368)."""
        mock_get_config.return_value = self.mock_config

        with patch("backend.security.certificate_manager.os.environ", {}):
            cert_manager = CertificateManager()

            # Create a certificate with non-numeric OU (organizational unit)
            ca_key = cert_manager.generate_private_key()

            # Manually create a CA certificate
            ca_subject = x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, "Test CA"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Org"),
                ]
            )

            ca_cert = (
                x509.CertificateBuilder()
                .subject_name(ca_subject)
                .issuer_name(ca_subject)
                .public_key(ca_key.public_key())
                .serial_number(12345)
                .not_valid_before(datetime.utcnow())
                .not_valid_after(datetime.utcnow() + timedelta(days=365))
                .sign(ca_key, hashes.SHA256())
            )

            client_key = cert_manager.generate_private_key()
            subject = x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, "test-host"),
                    x509.NameAttribute(
                        NameOID.ORGANIZATIONAL_UNIT_NAME, "invalid-host-id"
                    ),  # Non-numeric
                ]
            )

            client_cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(ca_cert.subject)
                .public_key(client_key.public_key())
                .serial_number(12345)
                .not_valid_before(datetime.utcnow())
                .not_valid_after(datetime.utcnow() + timedelta(days=365))
                .sign(ca_key, hashes.SHA256())
            )

            cert_pem = client_cert.public_bytes(serialization.Encoding.PEM)

            # Should return None due to ValueError parsing host_id
            result = cert_manager.validate_client_certificate(cert_pem)
            assert result is None

    @patch("backend.security.certificate_manager.get_config")
    def test_validate_certificate_missing_hostname(self, mock_get_config):
        """Test certificate validation with missing hostname (line 373)."""
        mock_get_config.return_value = self.mock_config

        with patch("backend.security.certificate_manager.os.environ", {}):
            cert_manager = CertificateManager()

            # Create a certificate with only OU but no CN
            ca_key = cert_manager.generate_private_key()

            # Manually create a CA certificate
            ca_subject = x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, "Test CA"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Org"),
                ]
            )

            ca_cert = (
                x509.CertificateBuilder()
                .subject_name(ca_subject)
                .issuer_name(ca_subject)
                .public_key(ca_key.public_key())
                .serial_number(12345)
                .not_valid_before(datetime.utcnow())
                .not_valid_after(datetime.utcnow() + timedelta(days=365))
                .sign(ca_key, hashes.SHA256())
            )

            client_key = cert_manager.generate_private_key()
            subject = x509.Name(
                [
                    x509.NameAttribute(
                        NameOID.ORGANIZATIONAL_UNIT_NAME, "12345"
                    ),  # Only OU, no CN
                ]
            )

            client_cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(ca_cert.subject)
                .public_key(client_key.public_key())
                .serial_number(12345)
                .not_valid_before(datetime.utcnow())
                .not_valid_after(datetime.utcnow() + timedelta(days=365))
                .sign(ca_key, hashes.SHA256())
            )

            cert_pem = client_cert.public_bytes(serialization.Encoding.PEM)

            # Should return None because hostname is missing
            result = cert_manager.validate_client_certificate(cert_pem)
            assert result is None


class TestCertificateManagerPlatformPaths:
    """Test platform-specific certificate paths and error handling."""

    @patch("backend.security.certificate_manager.get_config")
    @patch("backend.security.certificate_manager.os.name", "nt")
    @patch("backend.security.certificate_manager.Path")
    def test_windows_default_cert_path(self, mock_path_class, mock_get_config):
        """Test Windows default certificate path."""
        mock_get_config.return_value = {"certificates": {}}

        # Mock Path to avoid WindowsPath on Linux
        mock_path = MagicMock()
        mock_path_class.return_value = mock_path
        mock_path.mkdir = MagicMock()

        # Mock os.environ to prevent pytest temp dir override
        with patch("backend.security.certificate_manager.os.environ", {}):
            cert_manager = CertificateManager()
            # Should have tried to use Windows path
            mock_path_class.assert_called_with(r"C:\ProgramData\SysManage\certs")

    @patch("backend.security.certificate_manager.get_config")
    @patch("backend.security.certificate_manager.Path.mkdir")
    def test_permission_error_fallback(self, mock_mkdir, mock_get_config):
        """Test fallback path when permission denied on primary cert directory."""
        mock_get_config.return_value = {
            "certificates": {"path": "/etc/sysmanage/certs"}
        }

        # First mkdir call raises PermissionError, second succeeds
        mock_mkdir.side_effect = [PermissionError("Permission denied"), None]

        with patch("backend.security.certificate_manager.os.environ", {}):
            with patch("builtins.print") as mock_print:
                cert_manager = CertificateManager()

                # Should have fallen back to project directory
                assert ".sysmanage-certs" in str(cert_manager.cert_dir)
                # Should have printed warning
                mock_print.assert_called_once()
                assert "Cannot access" in mock_print.call_args[0][0]


class TestCertificateValidationErrors:
    """Test certificate validation error paths."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.mock_config = {"certificates": {"path": self.temp_dir}}

    def teardown_method(self):
        """Clean up test environment."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("backend.security.certificate_manager.get_config")
    def test_validate_certificate_wrong_issuer(self, mock_get_config):
        """Test certificate validation failure when issuer doesn't match CA."""
        mock_get_config.return_value = self.mock_config

        with patch("backend.security.certificate_manager.os.environ", {}):
            cert_manager = CertificateManager()

            # Generate a client certificate normally
            hostname = "test-host.example.com"
            host_id = "550e8400-e29b-41d4-a716-446655440001"
            cert_pem, _ = cert_manager.generate_client_certificate(hostname, host_id)

            # Create a different CA to simulate wrong issuer
            different_ca_key = cert_manager.generate_private_key()

            # Manually create a different CA certificate
            subject = issuer = x509.Name(
                [
                    x509.NameAttribute(x509.NameOID.COMMON_NAME, "Different CA"),
                    x509.NameAttribute(x509.NameOID.ORGANIZATION_NAME, "Different Org"),
                ]
            )

            from cryptography.hazmat.primitives import hashes

            different_ca_cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(different_ca_key.public_key())
                .serial_number(1)
                .not_valid_before(datetime.now(timezone.utc))
                .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
                .add_extension(
                    x509.BasicConstraints(ca=True, path_length=None), critical=True
                )
                .sign(different_ca_key, hashes.SHA256())
            )

            # Overwrite the CA cert file with the different CA
            with open(cert_manager.ca_cert_path, "wb") as f:
                f.write(different_ca_cert.public_bytes(serialization.Encoding.PEM))

            # Validation should fail due to issuer mismatch
            result = cert_manager.validate_client_certificate(cert_pem)
            assert result is None

    @patch("backend.security.certificate_manager.get_config")
    def test_validate_certificate_invalid_host_id(self, mock_get_config):
        """Test certificate validation with invalid host ID in organizational unit."""
        mock_get_config.return_value = self.mock_config

        with patch("backend.security.certificate_manager.os.environ", {}):
            cert_manager = CertificateManager()

            # Mock a certificate with invalid organizational unit (non-numeric host ID)
            hostname = "test-host.example.com"

            # Create certificate manually with invalid host ID
            private_key = cert_manager.generate_private_key()

            subject = x509.Name(
                [
                    x509.NameAttribute(x509.NameOID.COMMON_NAME, hostname),
                    x509.NameAttribute(
                        x509.NameOID.ORGANIZATIONAL_UNIT_NAME, "invalid-host-id"
                    ),  # Non-numeric
                    x509.NameAttribute(x509.NameOID.ORGANIZATION_NAME, "SysManage"),
                ]
            )

            # Get CA cert and key
            cert_manager.ensure_ca_certificate()
            with open(cert_manager.ca_key_path, "rb") as key_file:
                ca_key = serialization.load_pem_private_key(
                    key_file.read(), password=None
                )

            cert_builder = x509.CertificateBuilder()
            cert_builder = cert_builder.subject_name(subject)
            cert_builder = cert_builder.issuer_name(
                subject
            )  # Self-signed for simplicity
            cert_builder = cert_builder.public_key(private_key.public_key())
            cert_builder = cert_builder.serial_number(1)
            cert_builder = cert_builder.not_valid_before(datetime.now(timezone.utc))
            cert_builder = cert_builder.not_valid_after(
                datetime.now(timezone.utc) + timedelta(days=365)
            )

            from cryptography.hazmat.primitives import hashes

            invalid_cert = cert_builder.sign(ca_key, hashes.SHA256())
            cert_pem = invalid_cert.public_bytes(serialization.Encoding.PEM)

            # Validation should fail due to ValueError when parsing host ID
            result = cert_manager.validate_client_certificate(cert_pem)
            assert result is None

    @patch("backend.security.certificate_manager.get_config")
    def test_validate_certificate_missing_fields(self, mock_get_config):
        """Test certificate validation with missing hostname or host_id fields."""
        mock_get_config.return_value = self.mock_config

        with patch("backend.security.certificate_manager.os.environ", {}):
            cert_manager = CertificateManager()
            cert_manager.ensure_ca_certificate()

            # Create certificate with missing organizational unit (host_id)
            private_key = cert_manager.generate_private_key()

            subject = x509.Name(
                [
                    x509.NameAttribute(
                        x509.NameOID.COMMON_NAME, "test-host.example.com"
                    ),
                    # Missing ORGANIZATIONAL_UNIT_NAME (host_id)
                    x509.NameAttribute(x509.NameOID.ORGANIZATION_NAME, "SysManage"),
                ]
            )

            with open(cert_manager.ca_key_path, "rb") as key_file:
                ca_key = serialization.load_pem_private_key(
                    key_file.read(), password=None
                )

            cert_builder = x509.CertificateBuilder()
            cert_builder = cert_builder.subject_name(subject)
            cert_builder = cert_builder.issuer_name(subject)
            cert_builder = cert_builder.public_key(private_key.public_key())
            cert_builder = cert_builder.serial_number(1)
            cert_builder = cert_builder.not_valid_before(datetime.now(timezone.utc))
            cert_builder = cert_builder.not_valid_after(
                datetime.now(timezone.utc) + timedelta(days=365)
            )

            from cryptography.hazmat.primitives import hashes

            invalid_cert = cert_builder.sign(ca_key, hashes.SHA256())
            cert_pem = invalid_cert.public_bytes(serialization.Encoding.PEM)

            # Validation should fail and return None
            result = cert_manager.validate_client_certificate(cert_pem)
            assert result is None
