"""
Certificate management for mutual TLS authentication.

This module provides utilities for generating, storing, and managing
certificates for both server and client (agent) authentication.
"""

import hashlib
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple
import ipaddress

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from backend.config.config import get_config


class CertificateManager:
    """Manages X.509 certificates for mTLS authentication."""

    def __init__(self):
        self.config = get_config()
        cert_path = self.config.get("certificates", {}).get(
            "path", "/etc/sysmanage/certs"
        )

        # Use a safe default path for testing
        if "PYTEST_CURRENT_TEST" in os.environ:
            cert_path = tempfile.mkdtemp(prefix="sysmanage_test_certs_")

        self.cert_dir = Path(cert_path)
        self.cert_dir.mkdir(parents=True, exist_ok=True)

        # Certificate paths
        self.server_cert_path = self.cert_dir / "server.crt"
        self.server_key_path = self.cert_dir / "server.key"
        self.ca_cert_path = self.cert_dir / "ca.crt"
        self.ca_key_path = self.cert_dir / "ca.key"

    def generate_private_key(self) -> rsa.RSAPrivateKey:
        """Generate RSA private key."""
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def ensure_ca_certificate(self) -> None:
        """Ensure CA certificate exists, create if not."""
        if self.ca_cert_path.exists() and self.ca_key_path.exists():
            return

        # Generate CA private key
        ca_key = self.generate_private_key()

        # Create CA certificate
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SysManage"),
                x509.NameAttribute(NameOID.COMMON_NAME, "SysManage CA"),
            ]
        )

        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName("localhost"),
                    ]
                ),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    key_cert_sign=True,
                    crl_sign=True,
                    digital_signature=False,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256())
        )

        # Save CA certificate and key
        with open(self.ca_cert_path, "wb") as cert_file:
            cert_file.write(ca_cert.public_bytes(serialization.Encoding.PEM))

        with open(self.ca_key_path, "wb") as key_file:
            key_file.write(
                ca_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        # Set restrictive permissions
        os.chmod(self.ca_key_path, 0o600)
        os.chmod(self.ca_cert_path, 0o644)

    def ensure_server_certificate(self) -> None:
        """Ensure server certificate exists, create if not."""
        if self.server_cert_path.exists() and self.server_key_path.exists():
            return

        self.ensure_ca_certificate()

        # Load CA certificate and key
        with open(self.ca_cert_path, "rb") as cert_file:
            ca_cert = x509.load_pem_x509_certificate(cert_file.read())

        with open(self.ca_key_path, "rb") as key_file:
            ca_key = serialization.load_pem_private_key(key_file.read(), password=None)

        # Generate server private key
        server_key = self.generate_private_key()

        # Create server certificate
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SysManage"),
                x509.NameAttribute(NameOID.COMMON_NAME, "SysManage Server"),
            ]
        )

        # Get server hostname from config
        server_hostname = self.config.get("api", {}).get("host", "localhost")

        server_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName("localhost"),
                        x509.DNSName(server_hostname),
                        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                        x509.IPAddress(ipaddress.IPv6Address("::1")),
                    ]
                ),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    key_cert_sign=False,
                    crl_sign=False,
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage(
                    [
                        x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                    ]
                ),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256())
        )

        # Save server certificate and key
        with open(self.server_cert_path, "wb") as cert_file:
            cert_file.write(server_cert.public_bytes(serialization.Encoding.PEM))

        with open(self.server_key_path, "wb") as key_file:
            key_file.write(
                server_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        # Set restrictive permissions
        os.chmod(self.server_key_path, 0o600)
        os.chmod(self.server_cert_path, 0o644)

    def generate_client_certificate(
        self, hostname: str, host_id: int
    ) -> Tuple[bytes, bytes]:
        """Generate client certificate for agent authentication."""
        self.ensure_ca_certificate()

        # Load CA certificate and key
        with open(self.ca_cert_path, "rb") as cert_file:
            ca_cert = x509.load_pem_x509_certificate(cert_file.read())

        with open(self.ca_key_path, "rb") as key_file:
            ca_key = serialization.load_pem_private_key(key_file.read(), password=None)

        # Generate client private key
        client_key = self.generate_private_key()

        # Create client certificate
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SysManage Agent"),
                x509.NameAttribute(NameOID.COMMON_NAME, hostname),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, str(host_id)),
            ]
        )

        client_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(client_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName(hostname),
                    ]
                ),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    key_cert_sign=False,
                    crl_sign=False,
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage(
                    [
                        x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
                    ]
                ),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256())
        )

        # Return certificate and private key as PEM bytes
        cert_pem = client_cert.public_bytes(serialization.Encoding.PEM)
        key_pem = client_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        return cert_pem, key_pem

    def get_server_certificate_fingerprint(self) -> str:  # pylint: disable=invalid-name
        """Get server certificate SHA256 fingerprint for client pinning."""
        self.ensure_server_certificate()

        with open(self.server_cert_path, "rb") as cert_file:
            cert = x509.load_pem_x509_certificate(cert_file.read())

        fingerprint = hashlib.sha256(
            cert.public_bytes(serialization.Encoding.DER)
        ).hexdigest()
        return fingerprint.upper()

    def get_ca_certificate(self) -> bytes:
        """Get CA certificate in PEM format."""
        self.ensure_ca_certificate()

        with open(self.ca_cert_path, "rb") as cert_file:
            return cert_file.read()

    def validate_client_certificate(self, cert_pem: bytes) -> Optional[Tuple[str, int]]:
        """Validate client certificate and return hostname and host_id if valid."""
        try:
            cert = x509.load_pem_x509_certificate(cert_pem)

            # Ensure CA certificate exists
            self.ensure_ca_certificate()

            # Load CA certificate for validation
            with open(self.ca_cert_path, "rb") as cert_file:
                ca_cert = x509.load_pem_x509_certificate(cert_file.read())

            # Verify certificate was signed by our CA (simplified check - issuer matches CA subject)
            if cert.issuer != ca_cert.subject:
                return None

            # Check if certificate is still valid
            now = datetime.now(timezone.utc)
            if now < cert.not_valid_before_utc or now > cert.not_valid_after_utc:
                return None

            # Extract hostname and host_id from certificate
            hostname = None
            host_id = None

            for attribute in cert.subject:
                if attribute.oid == NameOID.COMMON_NAME:
                    hostname = attribute.value
                elif attribute.oid == NameOID.ORGANIZATIONAL_UNIT_NAME:
                    try:
                        host_id = int(attribute.value)
                    except ValueError:
                        return None

            if hostname and host_id:
                return hostname, host_id

            return None

        except Exception:
            return None


# Global certificate manager instance - lazy initialization
_CERTIFICATE_MANAGER = None  # pylint: disable=invalid-name


def get_certificate_manager():
    """Get the global certificate manager instance."""
    global _CERTIFICATE_MANAGER  # pylint: disable=global-statement
    if _CERTIFICATE_MANAGER is None:
        _CERTIFICATE_MANAGER = CertificateManager()
    return _CERTIFICATE_MANAGER


class _CertificateManagerProxy:
    """Proxy to lazily initialize certificate manager."""

    def __getattr__(self, name):
        return getattr(get_certificate_manager(), name)


# For backwards compatibility
certificate_manager = _CertificateManagerProxy()
