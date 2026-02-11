"""
Tests for backend/persistence/models/host_certificate.py module.
Tests HostCertificate model structure and methods.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest


class TestHostCertificateModel:
    """Tests for HostCertificate model."""

    def test_host_certificate_table_name(self):
        """Test HostCertificate table name."""
        from backend.persistence.models.host_certificate import HostCertificate

        assert HostCertificate.__tablename__ == "host_certificates"

    def test_host_certificate_columns_exist(self):
        """Test HostCertificate has expected columns."""
        from backend.persistence.models.host_certificate import HostCertificate

        assert hasattr(HostCertificate, "id")
        assert hasattr(HostCertificate, "host_id")
        assert hasattr(HostCertificate, "file_path")
        assert hasattr(HostCertificate, "certificate_name")
        assert hasattr(HostCertificate, "subject")
        assert hasattr(HostCertificate, "issuer")
        assert hasattr(HostCertificate, "not_before")
        assert hasattr(HostCertificate, "not_after")
        assert hasattr(HostCertificate, "serial_number")
        assert hasattr(HostCertificate, "fingerprint_sha256")
        assert hasattr(HostCertificate, "is_ca")
        assert hasattr(HostCertificate, "key_usage")
        assert hasattr(HostCertificate, "collected_at")
        assert hasattr(HostCertificate, "created_at")
        assert hasattr(HostCertificate, "updated_at")


class TestHostCertificateRepr:
    """Tests for HostCertificate __repr__ method."""

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.host_certificate import HostCertificate

        cert = HostCertificate()
        cert.id = uuid.uuid4()
        cert.host_id = uuid.uuid4()
        cert.file_path = "/etc/ssl/certs/server.crt"
        cert.not_after = datetime(2025, 12, 31, tzinfo=timezone.utc)

        repr_str = repr(cert)

        assert "HostCertificate" in repr_str
        assert "/etc/ssl/certs/server.crt" in repr_str


class TestHostCertificateToDict:
    """Tests for HostCertificate.to_dict method."""

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all fields."""
        from backend.persistence.models.host_certificate import HostCertificate

        cert = HostCertificate()
        cert.id = uuid.uuid4()
        cert.host_id = uuid.uuid4()
        cert.file_path = "/etc/ssl/server.crt"
        cert.certificate_name = "server.crt"
        cert.subject = "CN=example.com, O=Test Org"
        cert.issuer = "CN=Test CA"
        cert.not_before = datetime.now(timezone.utc)
        cert.not_after = datetime.now(timezone.utc) + timedelta(days=365)
        cert.serial_number = "ABC123"
        cert.fingerprint_sha256 = "deadbeef" * 8
        cert.is_ca = False
        cert.key_usage = "Digital Signature"
        cert.collected_at = datetime.now(timezone.utc)
        cert.created_at = datetime.now(timezone.utc)
        cert.updated_at = datetime.now(timezone.utc)

        result = cert.to_dict()

        assert result["id"] == str(cert.id)
        assert result["host_id"] == str(cert.host_id)
        assert result["file_path"] == "/etc/ssl/server.crt"
        assert result["certificate_name"] == "server.crt"
        assert result["subject"] == "CN=example.com, O=Test Org"
        assert result["issuer"] == "CN=Test CA"
        assert result["serial_number"] == "ABC123"
        assert result["is_ca"] is False
        assert result["key_usage"] == "Digital Signature"

    def test_to_dict_with_none_dates(self):
        """Test to_dict handles None date values."""
        from backend.persistence.models.host_certificate import HostCertificate

        cert = HostCertificate()
        cert.id = uuid.uuid4()
        cert.host_id = uuid.uuid4()
        cert.file_path = "/etc/ssl/test.crt"
        cert.not_before = None
        cert.not_after = None
        cert.collected_at = None
        cert.created_at = None
        cert.updated_at = None

        result = cert.to_dict()

        assert result["not_before"] is None
        assert result["not_after"] is None
        assert result["collected_at"] is None
        assert result["created_at"] is None
        assert result["updated_at"] is None


class TestHostCertificateIsExpired:
    """Tests for HostCertificate.is_expired property."""

    def test_is_expired_true_when_past_expiry(self):
        """Test is_expired returns True when certificate has expired."""
        from backend.persistence.models.host_certificate import HostCertificate

        cert = HostCertificate()
        cert.not_after = datetime.now(timezone.utc) - timedelta(days=1)

        assert cert.is_expired is True

    def test_is_expired_false_when_before_expiry(self):
        """Test is_expired returns False when certificate is still valid."""
        from backend.persistence.models.host_certificate import HostCertificate

        cert = HostCertificate()
        cert.not_after = datetime.now(timezone.utc) + timedelta(days=365)

        assert cert.is_expired is False

    def test_is_expired_false_when_no_expiry_date(self):
        """Test is_expired returns False when no expiry date set."""
        from backend.persistence.models.host_certificate import HostCertificate

        cert = HostCertificate()
        cert.not_after = None

        assert cert.is_expired is False


class TestHostCertificateDaysUntilExpiry:
    """Tests for HostCertificate.days_until_expiry property."""

    def test_days_until_expiry_positive(self):
        """Test days_until_expiry returns positive for future expiry."""
        from backend.persistence.models.host_certificate import HostCertificate

        cert = HostCertificate()
        cert.not_after = datetime.now(timezone.utc) + timedelta(days=30)

        days = cert.days_until_expiry
        assert days >= 29  # May be 29 or 30 depending on time of day

    def test_days_until_expiry_negative_when_expired(self):
        """Test days_until_expiry returns negative for expired cert."""
        from backend.persistence.models.host_certificate import HostCertificate

        cert = HostCertificate()
        cert.not_after = datetime.now(timezone.utc) - timedelta(days=10)

        days = cert.days_until_expiry
        assert days < 0

    def test_days_until_expiry_zero_when_no_date(self):
        """Test days_until_expiry returns 0 when no expiry date."""
        from backend.persistence.models.host_certificate import HostCertificate

        cert = HostCertificate()
        cert.not_after = None

        assert cert.days_until_expiry == 0


class TestHostCertificateCommonName:
    """Tests for HostCertificate.common_name property."""

    def test_common_name_extracts_cn(self):
        """Test common_name extracts CN from subject."""
        from backend.persistence.models.host_certificate import HostCertificate

        cert = HostCertificate()
        cert.subject = "CN=www.example.com, O=Example Inc, C=US"

        assert cert.common_name == "www.example.com"

    def test_common_name_with_cn_at_end(self):
        """Test common_name when CN is at end of subject."""
        from backend.persistence.models.host_certificate import HostCertificate

        cert = HostCertificate()
        cert.subject = "O=Example Inc, CN=mail.example.com"

        assert cert.common_name == "mail.example.com"

    def test_common_name_empty_when_no_cn(self):
        """Test common_name returns empty when no CN in subject."""
        from backend.persistence.models.host_certificate import HostCertificate

        cert = HostCertificate()
        cert.subject = "O=Example Inc, C=US"

        assert cert.common_name == ""

    def test_common_name_empty_when_no_subject(self):
        """Test common_name returns empty when no subject."""
        from backend.persistence.models.host_certificate import HostCertificate

        cert = HostCertificate()
        cert.subject = None

        assert cert.common_name == ""
