"""
Tests for backend/licensing/validator.py module.
Tests license validation functionality.
"""

import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestDecodeBase64Url:
    """Tests for decode_base64url function."""

    def test_decode_simple_string(self):
        """Test decoding a simple base64url string."""
        from backend.licensing.validator import decode_base64url

        # "test" encoded in base64url
        encoded = base64.urlsafe_b64encode(b"test").decode().rstrip("=")
        result = decode_base64url(encoded)

        assert result == b"test"

    def test_decode_with_padding(self):
        """Test decoding adds padding correctly."""
        from backend.licensing.validator import decode_base64url

        # String that needs padding
        encoded = base64.urlsafe_b64encode(b"hello world").decode().rstrip("=")
        result = decode_base64url(encoded)

        assert result == b"hello world"

    def test_decode_with_url_safe_chars(self):
        """Test decoding handles URL-safe characters."""
        from backend.licensing.validator import decode_base64url

        # Standard base64 with + and /
        standard = "ab+cd/ef=="
        # URL-safe version
        url_safe = "ab-cd_ef"

        # Both should decode to same bytes
        from backend.licensing.validator import decode_base64url

        result = decode_base64url(url_safe)
        assert result == base64.b64decode(standard)


class TestHashLicenseKey:
    """Tests for hash_license_key function."""

    def test_hash_returns_hexadecimal(self):
        """Test hash returns hexadecimal string."""
        from backend.licensing.validator import hash_license_key

        result = hash_license_key("test-license-key")

        # SHA-256 produces 64 hex characters
        assert len(result) == 64
        # Should be valid hex
        int(result, 16)

    def test_hash_is_consistent(self):
        """Test hash returns same result for same input."""
        from backend.licensing.validator import hash_license_key

        hash1 = hash_license_key("same-key")
        hash2 = hash_license_key("same-key")

        assert hash1 == hash2

    def test_hash_is_different_for_different_keys(self):
        """Test hash returns different results for different inputs."""
        from backend.licensing.validator import hash_license_key

        hash1 = hash_license_key("key-1")
        hash2 = hash_license_key("key-2")

        assert hash1 != hash2


class TestParseLicenseKey:
    """Tests for parse_license_key function."""

    def test_parse_valid_license_key(self):
        """Test parsing a valid license key structure."""
        from backend.licensing.validator import parse_license_key

        # Create a valid license key format
        header = {"alg": "ES512", "typ": "JWT"}
        payload = {"lic": "test-123", "tier": "professional"}

        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode()
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        signature_b64 = base64.urlsafe_b64encode(b"fake-signature").decode()

        license_key = f"{header_b64}.{payload_b64}.{signature_b64}"

        h, p, s = parse_license_key(license_key)

        assert h["alg"] == "ES512"
        assert p["lic"] == "test-123"

    def test_parse_invalid_format_too_few_parts(self):
        """Test parsing fails with too few parts."""
        from backend.licensing.validator import parse_license_key

        with pytest.raises(ValueError) as exc_info:
            parse_license_key("only.two")

        assert "expected 3 parts" in str(exc_info.value)

    def test_parse_invalid_format_too_many_parts(self):
        """Test parsing fails with too many parts."""
        from backend.licensing.validator import parse_license_key

        with pytest.raises(ValueError) as exc_info:
            parse_license_key("one.two.three.four")

        assert "expected 3 parts" in str(exc_info.value)


class TestLicensePayloadDataclass:
    """Tests for LicensePayload dataclass."""

    def test_license_payload_required_fields(self):
        """Test LicensePayload can be created with required fields."""
        from backend.licensing.features import LicenseTier
        from backend.licensing.validator import LicensePayload

        payload = LicensePayload(
            license_id="test-123",
            tier=LicenseTier.PROFESSIONAL,
            features=["health"],
            modules=["health_engine"],
            expires_at=datetime.now(timezone.utc),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        assert payload.license_id == "test-123"
        assert payload.tier == LicenseTier.PROFESSIONAL
        assert payload.offline_days == 30

    def test_license_payload_optional_fields(self):
        """Test LicensePayload optional fields default to None."""
        from backend.licensing.features import LicenseTier
        from backend.licensing.validator import LicensePayload

        payload = LicensePayload(
            license_id="test-123",
            tier=LicenseTier.PROFESSIONAL,
            features=[],
            modules=[],
            expires_at=datetime.now(timezone.utc),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        assert payload.customer_id is None
        assert payload.customer_name is None
        assert payload.parent_hosts is None
        assert payload.child_hosts is None


class TestValidationResultDataclass:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_valid(self):
        """Test ValidationResult for valid license."""
        from backend.licensing.validator import ValidationResult

        result = ValidationResult(valid=True)

        assert result.valid is True
        assert result.payload is None
        assert result.error is None
        assert result.warning is None

    def test_validation_result_invalid_with_error(self):
        """Test ValidationResult for invalid license with error."""
        from backend.licensing.validator import ValidationResult

        result = ValidationResult(valid=False, error="License expired")

        assert result.valid is False
        assert result.error == "License expired"

    def test_validation_result_valid_with_warning(self):
        """Test ValidationResult for valid license with warning."""
        from backend.licensing.validator import ValidationResult

        result = ValidationResult(valid=True, warning="License expires in 10 days")

        assert result.valid is True
        assert result.warning == "License expires in 10 days"


class TestCheckExpiration:
    """Tests for check_expiration function."""

    def test_check_expiration_not_expired(self):
        """Test check_expiration for non-expired license."""
        from backend.licensing.validator import check_expiration

        expires_at = datetime.now(timezone.utc) + timedelta(days=60)
        is_valid, warning = check_expiration(expires_at)

        assert is_valid is True
        assert warning is None

    def test_check_expiration_expiring_soon(self):
        """Test check_expiration for license expiring within 30 days."""
        from backend.licensing.validator import check_expiration

        expires_at = datetime.now(timezone.utc) + timedelta(days=15)
        is_valid, warning = check_expiration(expires_at)

        assert is_valid is True
        assert warning is not None
        assert "expires in" in warning

    def test_check_expiration_in_grace_period(self):
        """Test check_expiration for license in grace period."""
        from backend.licensing.validator import check_expiration

        expires_at = datetime.now(timezone.utc) - timedelta(days=3)
        is_valid, warning = check_expiration(expires_at)

        assert is_valid is True
        assert warning is not None
        assert "expired" in warning.lower()

    def test_check_expiration_past_grace_period(self):
        """Test check_expiration for license past grace period."""
        from backend.licensing.validator import check_expiration

        expires_at = datetime.now(timezone.utc) - timedelta(days=30)
        is_valid, warning = check_expiration(expires_at)

        assert is_valid is False


class TestValidatePayload:
    """Tests for validate_payload function."""

    def test_validate_payload_valid(self):
        """Test validate_payload with valid payload."""
        from backend.licensing.validator import validate_payload

        payload = {
            "lic": "test-123",
            "tier": "professional",
            "features": ["health"],
            "modules": ["health_engine"],
            "exp": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp()),
        }

        result = validate_payload(payload)

        assert result.license_id == "test-123"
        assert result.tier.value == "professional"

    def test_validate_payload_old_format(self):
        """Test validate_payload with old field names."""
        from backend.licensing.validator import validate_payload

        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        issued = datetime.now(timezone.utc).isoformat()

        payload = {
            "license_id": "test-456",
            "tier": "enterprise",
            "features": [],
            "modules": [],
            "expires_at": expires,
            "issued_at": issued,
        }

        result = validate_payload(payload)

        assert result.license_id == "test-456"
        assert result.tier.value == "enterprise"

    def test_validate_payload_missing_license_id(self):
        """Test validate_payload fails without license_id."""
        from backend.licensing.validator import validate_payload

        payload = {"tier": "professional"}

        with pytest.raises(ValueError) as exc_info:
            validate_payload(payload)

        assert "lic or license_id" in str(exc_info.value)

    def test_validate_payload_missing_tier(self):
        """Test validate_payload fails without tier."""
        from backend.licensing.validator import validate_payload

        payload = {"lic": "test-123"}

        with pytest.raises(ValueError) as exc_info:
            validate_payload(payload)

        assert "tier" in str(exc_info.value)

    def test_validate_payload_invalid_tier(self):
        """Test validate_payload fails with invalid tier."""
        from backend.licensing.validator import validate_payload

        payload = {"lic": "test-123", "tier": "invalid_tier"}

        with pytest.raises(ValueError) as exc_info:
            validate_payload(payload)

        assert "Invalid tier" in str(exc_info.value)


class TestHasFeature:
    """Tests for has_feature function."""

    def test_has_feature_returns_true(self):
        """Test has_feature returns True when feature exists."""
        from backend.licensing.features import FeatureCode, LicenseTier
        from backend.licensing.validator import LicensePayload, has_feature

        payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.PROFESSIONAL,
            features=["health", "vuln"],
            modules=[],
            expires_at=datetime.now(timezone.utc),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        assert has_feature(payload, FeatureCode.HEALTH_ANALYSIS) is True

    def test_has_feature_returns_false(self):
        """Test has_feature returns False when feature doesn't exist."""
        from backend.licensing.features import FeatureCode, LicenseTier
        from backend.licensing.validator import LicensePayload, has_feature

        payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.PROFESSIONAL,
            features=[],
            modules=[],
            expires_at=datetime.now(timezone.utc),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        assert has_feature(payload, FeatureCode.HEALTH_ANALYSIS) is False


class TestHasModule:
    """Tests for has_module function."""

    def test_has_module_returns_true(self):
        """Test has_module returns True when module exists."""
        from backend.licensing.features import LicenseTier, ModuleCode
        from backend.licensing.validator import LicensePayload, has_module

        payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.PROFESSIONAL,
            features=[],
            modules=["health_engine"],
            expires_at=datetime.now(timezone.utc),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        assert has_module(payload, ModuleCode.HEALTH_ENGINE) is True

    def test_has_module_returns_false(self):
        """Test has_module returns False when module doesn't exist."""
        from backend.licensing.features import LicenseTier, ModuleCode
        from backend.licensing.validator import LicensePayload, has_module

        payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.PROFESSIONAL,
            features=[],
            modules=[],
            expires_at=datetime.now(timezone.utc),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        assert has_module(payload, ModuleCode.HEALTH_ENGINE) is False


class TestConstants:
    """Tests for module constants."""

    def test_expiration_grace_days(self):
        """Test EXPIRATION_GRACE_DAYS constant."""
        from backend.licensing.validator import EXPIRATION_GRACE_DAYS

        assert EXPIRATION_GRACE_DAYS == 7
