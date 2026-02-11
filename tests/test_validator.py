"""
Tests for backend/licensing/validator.py module.
Tests local license signature validation for Pro+ licenses.
"""

import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.licensing.features import FeatureCode, LicenseTier, ModuleCode


class TestDecodeBase64url:
    """Tests for decode_base64url function."""

    def test_decode_base64url_standard(self):
        """Test decoding standard base64url."""
        from backend.licensing.validator import decode_base64url

        # "hello" in base64url
        encoded = "aGVsbG8"
        result = decode_base64url(encoded)
        assert result == b"hello"

    def test_decode_base64url_with_url_safe_chars(self):
        """Test decoding with URL-safe characters."""
        from backend.licensing.validator import decode_base64url

        # Data containing + and / in standard base64 would be - and _ in base64url
        original = b"test?data&more"
        # Encode using standard base64 then convert to base64url format
        standard = base64.b64encode(original).decode()
        url_safe = standard.replace("+", "-").replace("/", "_").rstrip("=")

        result = decode_base64url(url_safe)
        assert result == original


class TestHashLicenseKey:
    """Tests for hash_license_key function."""

    def test_hash_license_key(self):
        """Test hashing a license key."""
        from backend.licensing.validator import hash_license_key

        result = hash_license_key("test-license-key")

        # Should be SHA-256 hex digest
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_license_key_deterministic(self):
        """Test hash is deterministic."""
        from backend.licensing.validator import hash_license_key

        result1 = hash_license_key("same-key")
        result2 = hash_license_key("same-key")

        assert result1 == result2


class TestParseLicenseKey:
    """Tests for parse_license_key function."""

    def test_parse_license_key_valid(self):
        """Test parsing a valid license key."""
        from backend.licensing.validator import parse_license_key

        header = {"alg": "ES512", "typ": "JWT"}
        payload = {"lic": "test-123", "tier": "professional"}

        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        sig_b64 = base64.urlsafe_b64encode(b"fake-signature").decode().rstrip("=")

        license_key = f"{header_b64}.{payload_b64}.{sig_b64}"

        result_header, result_payload, result_sig = parse_license_key(license_key)

        assert result_header == header
        assert result_payload == payload
        assert result_sig == b"fake-signature"

    def test_parse_license_key_invalid_format(self):
        """Test parsing invalid license key format."""
        from backend.licensing.validator import parse_license_key

        with pytest.raises(ValueError) as exc_info:
            parse_license_key("invalid-key-no-dots")

        assert "expected 3 parts" in str(exc_info.value)

    def test_parse_license_key_invalid_encoding(self):
        """Test parsing license key with invalid encoding."""
        from backend.licensing.validator import parse_license_key

        with pytest.raises(ValueError) as exc_info:
            parse_license_key("!invalid!.base64.encoding")

        assert "Invalid license key encoding" in str(exc_info.value)


class TestValidatePayload:
    """Tests for validate_payload function."""

    def test_validate_payload_valid_new_format(self):
        """Test validating payload with new format (lic, exp)."""
        from backend.licensing.validator import validate_payload

        now = datetime.now(timezone.utc)
        payload = {
            "lic": "license-123",
            "tier": "professional",
            "features": ["feature1"],
            "modules": ["vuln_engine"],
            "exp": int(now.timestamp()) + 3600,
            "iat": int(now.timestamp()),
        }

        result = validate_payload(payload)

        assert result.license_id == "license-123"
        assert result.tier == LicenseTier.PROFESSIONAL
        assert "feature1" in result.features
        assert "vuln_engine" in result.modules

    def test_validate_payload_valid_old_format(self):
        """Test validating payload with old format (license_id, expires_at)."""
        from backend.licensing.validator import validate_payload

        payload = {
            "license_id": "old-license-456",
            "tier": "enterprise",
            "features": [],
            "modules": [],
            "expires_at": "2025-12-31T23:59:59Z",
            "issued_at": "2024-01-01T00:00:00Z",
        }

        result = validate_payload(payload)

        assert result.license_id == "old-license-456"
        assert result.tier == LicenseTier.ENTERPRISE

    def test_validate_payload_missing_license_id(self):
        """Test validating payload missing license ID."""
        from backend.licensing.validator import validate_payload

        payload = {"tier": "professional", "exp": 1234567890}

        with pytest.raises(ValueError) as exc_info:
            validate_payload(payload)

        assert "Missing required field: lic" in str(exc_info.value)

    def test_validate_payload_missing_tier(self):
        """Test validating payload missing tier."""
        from backend.licensing.validator import validate_payload

        payload = {"lic": "test", "exp": 1234567890}

        with pytest.raises(ValueError) as exc_info:
            validate_payload(payload)

        assert "Missing required field: tier" in str(exc_info.value)

    def test_validate_payload_invalid_tier(self):
        """Test validating payload with invalid tier."""
        from backend.licensing.validator import validate_payload

        payload = {"lic": "test", "tier": "invalid_tier", "exp": 1234567890}

        with pytest.raises(ValueError) as exc_info:
            validate_payload(payload)

        assert "Invalid tier" in str(exc_info.value)

    def test_validate_payload_missing_expiration(self):
        """Test validating payload missing expiration."""
        from backend.licensing.validator import validate_payload

        payload = {"lic": "test", "tier": "professional"}

        with pytest.raises(ValueError) as exc_info:
            validate_payload(payload)

        assert "Missing required field: exp" in str(exc_info.value)


class TestCheckExpiration:
    """Tests for check_expiration function."""

    def test_check_expiration_not_expired(self):
        """Test license not expired."""
        from backend.licensing.validator import check_expiration

        future = datetime.now(timezone.utc) + timedelta(days=60)

        is_valid, warning = check_expiration(future)

        assert is_valid is True
        assert warning is None

    def test_check_expiration_expires_soon(self):
        """Test license expiring within 30 days."""
        from backend.licensing.validator import check_expiration

        soon = datetime.now(timezone.utc) + timedelta(days=15)

        is_valid, warning = check_expiration(soon)

        assert is_valid is True
        assert warning is not None
        assert "days" in warning
        assert "expires" in warning.lower()

    def test_check_expiration_in_grace_period(self):
        """Test license in grace period."""
        from backend.licensing.validator import check_expiration

        recently_expired = datetime.now(timezone.utc) - timedelta(days=3)

        is_valid, warning = check_expiration(recently_expired)

        assert is_valid is True
        assert "grace period" in warning

    def test_check_expiration_past_grace_period(self):
        """Test license expired past grace period."""
        from backend.licensing.validator import check_expiration

        long_expired = datetime.now(timezone.utc) - timedelta(days=30)

        is_valid, warning = check_expiration(long_expired)

        assert is_valid is False


class TestVerifySignature:
    """Tests for verify_signature function."""

    @patch("backend.licensing.validator.get_public_key_pem_sync")
    def test_verify_signature_no_public_key(self, mock_get_key):
        """Test signature verification without public key."""
        from backend.licensing.validator import verify_signature

        mock_get_key.return_value = None

        result = verify_signature("a.b.c", {"alg": "ES512"}, b"signature")

        assert result is False

    def test_verify_signature_invalid_pem(self):
        """Test signature verification with invalid PEM key."""
        from backend.licensing.validator import verify_signature

        result = verify_signature(
            "a.b.c", {"alg": "ES512"}, b"signature", public_key_pem="invalid-pem"
        )

        assert result is False


class TestValidateLicense:
    """Tests for validate_license function."""

    @patch("backend.licensing.validator.verify_signature")
    @patch("backend.licensing.validator.check_expiration")
    @patch("backend.licensing.validator.validate_payload")
    @patch("backend.licensing.validator.parse_license_key")
    def test_validate_license_success(
        self, mock_parse, mock_validate, mock_check_exp, mock_verify
    ):
        """Test successful license validation."""
        from backend.licensing.validator import (
            LicensePayload,
            LicenseTier,
            validate_license,
        )

        mock_parse.return_value = ({"alg": "ES512"}, {"lic": "test"}, b"sig")
        mock_verify.return_value = True
        mock_payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.PROFESSIONAL,
            features=[],
            modules=[],
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )
        mock_validate.return_value = mock_payload
        mock_check_exp.return_value = (True, None)

        result = validate_license("test.license.key")

        assert result.valid is True
        assert result.payload is not None

    @patch("backend.licensing.validator.parse_license_key")
    def test_validate_license_invalid_algorithm(self, mock_parse):
        """Test validation with unsupported algorithm."""
        from backend.licensing.validator import validate_license

        mock_parse.return_value = ({"alg": "RS256"}, {}, b"sig")

        result = validate_license("test.license.key")

        assert result.valid is False
        assert "Unsupported algorithm" in result.error

    @patch("backend.licensing.validator.verify_signature")
    @patch("backend.licensing.validator.parse_license_key")
    def test_validate_license_invalid_signature(self, mock_parse, mock_verify):
        """Test validation with invalid signature."""
        from backend.licensing.validator import validate_license

        mock_parse.return_value = ({"alg": "ES512"}, {}, b"sig")
        mock_verify.return_value = False

        result = validate_license("test.license.key")

        assert result.valid is False
        assert "Invalid license signature" in result.error

    def test_validate_license_parse_error(self):
        """Test validation with unparseable license key."""
        from backend.licensing.validator import validate_license

        result = validate_license("invalid")

        assert result.valid is False
        assert "expected 3 parts" in result.error


class TestHasFeature:
    """Tests for has_feature function."""

    def test_has_feature_true(self):
        """Test feature present in payload."""
        from backend.licensing.validator import LicensePayload, LicenseTier, has_feature

        payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.PROFESSIONAL,
            features=["vuln"],
            modules=[],
            expires_at=datetime.now(timezone.utc),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        result = has_feature(payload, FeatureCode.VULNERABILITY_SCANNING)

        assert result is True

    def test_has_feature_false(self):
        """Test feature not present in payload."""
        from backend.licensing.validator import LicensePayload, LicenseTier, has_feature

        payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.PROFESSIONAL,
            features=[],
            modules=[],
            expires_at=datetime.now(timezone.utc),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        result = has_feature(payload, FeatureCode.VULNERABILITY_SCANNING)

        assert result is False


class TestHasModule:
    """Tests for has_module function."""

    def test_has_module_true(self):
        """Test module present in payload."""
        from backend.licensing.validator import LicensePayload, LicenseTier, has_module

        payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.ENTERPRISE,
            features=[],
            modules=["vuln_engine"],
            expires_at=datetime.now(timezone.utc),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        result = has_module(payload, ModuleCode.VULN_ENGINE)

        assert result is True

    def test_has_module_false(self):
        """Test module not present in payload."""
        from backend.licensing.validator import LicensePayload, LicenseTier, has_module

        payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.PROFESSIONAL,
            features=[],
            modules=[],
            expires_at=datetime.now(timezone.utc),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        result = has_module(payload, ModuleCode.VULN_ENGINE)

        assert result is False
