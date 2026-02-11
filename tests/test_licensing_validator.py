"""
Tests for backend/licensing/validator.py module.
Tests license validation functions including decode, parse, hash, and expiration checks.
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

        # "hello" in base64url
        encoded = base64.urlsafe_b64encode(b"hello").decode().rstrip("=")
        result = decode_base64url(encoded)
        assert result == b"hello"

    def test_decode_with_padding(self):
        """Test decoding handles missing padding."""
        from backend.licensing.validator import decode_base64url

        # "test" in base64url without padding
        encoded = base64.urlsafe_b64encode(b"test").decode().rstrip("=")
        result = decode_base64url(encoded)
        assert result == b"test"

    def test_decode_url_safe_characters(self):
        """Test decoding handles URL-safe characters."""
        from backend.licensing.validator import decode_base64url

        # Data that would have + and / in standard base64
        data = b"\xfb\xef\xbe"
        encoded = base64.urlsafe_b64encode(data).decode().rstrip("=")
        result = decode_base64url(encoded)
        assert result == data

    def test_decode_json_payload(self):
        """Test decoding a JSON payload."""
        from backend.licensing.validator import decode_base64url

        payload = {"test": "value", "number": 42}
        encoded = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        result = decode_base64url(encoded)
        decoded = json.loads(result)
        assert decoded == payload


class TestHashLicenseKey:
    """Tests for hash_license_key function."""

    def test_hash_returns_string(self):
        """Test that hash_license_key returns a string."""
        from backend.licensing.validator import hash_license_key

        result = hash_license_key("test-license-key")
        assert isinstance(result, str)

    def test_hash_is_hex(self):
        """Test that hash is a valid hex string."""
        from backend.licensing.validator import hash_license_key

        result = hash_license_key("test-license-key")
        # SHA-256 produces 64 hex characters
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_is_deterministic(self):
        """Test that hashing the same key produces the same result."""
        from backend.licensing.validator import hash_license_key

        key = "my-license-key-123"
        result1 = hash_license_key(key)
        result2 = hash_license_key(key)
        assert result1 == result2

    def test_different_keys_produce_different_hashes(self):
        """Test that different keys produce different hashes."""
        from backend.licensing.validator import hash_license_key

        result1 = hash_license_key("key1")
        result2 = hash_license_key("key2")
        assert result1 != result2

    def test_hash_empty_string(self):
        """Test hashing an empty string."""
        from backend.licensing.validator import hash_license_key

        result = hash_license_key("")
        assert isinstance(result, str)
        assert len(result) == 64


class TestParseLicenseKey:
    """Tests for parse_license_key function."""

    def _create_license_key(self, header, payload):
        """Helper to create a mock license key."""
        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        signature_b64 = base64.urlsafe_b64encode(b"fake-signature").decode().rstrip("=")
        return f"{header_b64}.{payload_b64}.{signature_b64}"

    def test_parse_valid_key(self):
        """Test parsing a valid license key structure."""
        from backend.licensing.validator import parse_license_key

        header = {"alg": "ES512", "typ": "JWT"}
        payload = {"lic": "test-123", "tier": "professional"}
        key = self._create_license_key(header, payload)

        parsed_header, parsed_payload, signature = parse_license_key(key)

        assert parsed_header == header
        assert parsed_payload == payload
        assert isinstance(signature, bytes)

    def test_parse_invalid_format_no_dots(self):
        """Test parsing a key without dots raises ValueError."""
        from backend.licensing.validator import parse_license_key

        with pytest.raises(ValueError) as exc_info:
            parse_license_key("invalid-key-without-dots")
        assert "expected 3 parts" in str(exc_info.value)

    def test_parse_invalid_format_too_few_parts(self):
        """Test parsing a key with too few parts raises ValueError."""
        from backend.licensing.validator import parse_license_key

        with pytest.raises(ValueError) as exc_info:
            parse_license_key("part1.part2")
        assert "expected 3 parts" in str(exc_info.value)

    def test_parse_invalid_format_too_many_parts(self):
        """Test parsing a key with too many parts raises ValueError."""
        from backend.licensing.validator import parse_license_key

        with pytest.raises(ValueError) as exc_info:
            parse_license_key("part1.part2.part3.part4")
        assert "expected 3 parts" in str(exc_info.value)

    def test_parse_invalid_base64(self):
        """Test parsing a key with invalid base64 raises ValueError."""
        from backend.licensing.validator import parse_license_key

        with pytest.raises(ValueError) as exc_info:
            parse_license_key("!!!.@@@.###")
        assert "Invalid license key" in str(exc_info.value)

    def test_parse_strips_whitespace(self):
        """Test that parsing strips whitespace from the key."""
        from backend.licensing.validator import parse_license_key

        header = {"alg": "ES512"}
        payload = {"lic": "test"}
        key = self._create_license_key(header, payload)
        key_with_whitespace = f"  {key}  "

        parsed_header, parsed_payload, _ = parse_license_key(key_with_whitespace)

        assert parsed_header == header
        assert parsed_payload == payload


class TestValidatePayload:
    """Tests for validate_payload function."""

    def test_validate_payload_new_format(self):
        """Test validating payload with new format (lic, exp, iat)."""
        from backend.licensing.validator import validate_payload

        now = datetime.now(timezone.utc)
        payload = {
            "lic": "license-123",
            "tier": "professional",
            "exp": int((now + timedelta(days=30)).timestamp()),
            "iat": int(now.timestamp()),
            "features": ["health", "vuln"],
            "modules": ["health_engine"],
        }

        result = validate_payload(payload)

        assert result.license_id == "license-123"
        assert result.tier.value == "professional"
        assert len(result.features) == 2
        assert len(result.modules) == 1

    def test_validate_payload_old_format(self):
        """Test validating payload with old format (license_id, expires_at)."""
        from backend.licensing.validator import validate_payload

        now = datetime.now(timezone.utc)
        payload = {
            "license_id": "license-456",
            "tier": "enterprise",
            "expires_at": (now + timedelta(days=30)).isoformat(),
            "issued_at": now.isoformat(),
            "features": ["health"],
            "modules": [],
        }

        result = validate_payload(payload)

        assert result.license_id == "license-456"
        assert result.tier.value == "enterprise"

    def test_validate_payload_missing_license_id(self):
        """Test that missing license_id raises ValueError."""
        from backend.licensing.validator import validate_payload

        payload = {
            "tier": "professional",
            "exp": int(datetime.now(timezone.utc).timestamp()),
        }

        with pytest.raises(ValueError) as exc_info:
            validate_payload(payload)
        assert "Missing required field" in str(exc_info.value)

    def test_validate_payload_missing_tier(self):
        """Test that missing tier raises ValueError."""
        from backend.licensing.validator import validate_payload

        payload = {
            "lic": "license-123",
            "exp": int(datetime.now(timezone.utc).timestamp()),
        }

        with pytest.raises(ValueError) as exc_info:
            validate_payload(payload)
        assert "Missing required field: tier" in str(exc_info.value)

    def test_validate_payload_invalid_tier(self):
        """Test that invalid tier raises ValueError."""
        from backend.licensing.validator import validate_payload

        payload = {
            "lic": "license-123",
            "tier": "invalid_tier",
            "exp": int(datetime.now(timezone.utc).timestamp()),
        }

        with pytest.raises(ValueError) as exc_info:
            validate_payload(payload)
        assert "Invalid tier" in str(exc_info.value)

    def test_validate_payload_missing_expiration(self):
        """Test that missing expiration raises ValueError."""
        from backend.licensing.validator import validate_payload

        payload = {
            "lic": "license-123",
            "tier": "professional",
        }

        with pytest.raises(ValueError) as exc_info:
            validate_payload(payload)
        assert "Missing required field: exp or expires_at" in str(exc_info.value)

    def test_validate_payload_defaults_offline_days(self):
        """Test that offline_days defaults to 30."""
        from backend.licensing.validator import validate_payload

        now = datetime.now(timezone.utc)
        payload = {
            "lic": "license-123",
            "tier": "professional",
            "exp": int((now + timedelta(days=30)).timestamp()),
        }

        result = validate_payload(payload)

        assert result.offline_days == 30

    def test_validate_payload_custom_offline_days(self):
        """Test that custom offline_days is respected."""
        from backend.licensing.validator import validate_payload

        now = datetime.now(timezone.utc)
        payload = {
            "lic": "license-123",
            "tier": "professional",
            "exp": int((now + timedelta(days=30)).timestamp()),
            "offline_days": 14,
        }

        result = validate_payload(payload)

        assert result.offline_days == 14

    def test_validate_payload_optional_fields(self):
        """Test that optional fields are parsed correctly."""
        from backend.licensing.validator import validate_payload

        now = datetime.now(timezone.utc)
        payload = {
            "lic": "license-123",
            "tier": "enterprise",
            "exp": int((now + timedelta(days=30)).timestamp()),
            "cust": "customer-id",
            "org": "Acme Corp",
            "parent_hosts": 10,
            "child_hosts": 100,
        }

        result = validate_payload(payload)

        assert result.customer_id == "customer-id"
        assert result.customer_name == "Acme Corp"
        assert result.parent_hosts == 10
        assert result.child_hosts == 100

    def test_validate_payload_defaults_issued_at(self):
        """Test that issued_at defaults to now if not provided."""
        from backend.licensing.validator import validate_payload

        now = datetime.now(timezone.utc)
        payload = {
            "lic": "license-123",
            "tier": "professional",
            "exp": int((now + timedelta(days=30)).timestamp()),
        }

        result = validate_payload(payload)

        # issued_at should be approximately now
        assert result.issued_at is not None
        assert abs((result.issued_at - now).total_seconds()) < 5


class TestCheckExpiration:
    """Tests for check_expiration function."""

    def test_not_expired(self):
        """Test license that is not expired."""
        from backend.licensing.validator import check_expiration

        future_date = datetime.now(timezone.utc) + timedelta(days=60)
        is_valid, warning = check_expiration(future_date)

        assert is_valid is True
        assert warning is None

    def test_expiring_soon_warning(self):
        """Test license expiring within 30 days shows warning."""
        from backend.licensing.validator import check_expiration

        future_date = datetime.now(timezone.utc) + timedelta(days=15)
        is_valid, warning = check_expiration(future_date)

        assert is_valid is True
        assert warning is not None
        assert "expires in" in warning

    def test_within_grace_period(self):
        """Test license within grace period is still valid."""
        from backend.licensing.validator import check_expiration

        # Expired 3 days ago (within 7-day grace period)
        past_date = datetime.now(timezone.utc) - timedelta(days=3)
        is_valid, warning = check_expiration(past_date)

        assert is_valid is True
        assert warning is not None
        assert "expired" in warning.lower()
        assert "grace period" in warning.lower()

    def test_past_grace_period(self):
        """Test license past grace period is invalid."""
        from backend.licensing.validator import check_expiration

        # Expired 10 days ago (past 7-day grace period)
        past_date = datetime.now(timezone.utc) - timedelta(days=10)
        is_valid, warning = check_expiration(past_date)

        assert is_valid is False

    def test_naive_datetime_handled(self):
        """Test that naive datetime is handled correctly."""
        from backend.licensing.validator import check_expiration

        # Naive datetime (no timezone)
        future_date = datetime.now() + timedelta(days=60)
        is_valid, warning = check_expiration(future_date)

        assert is_valid is True

    def test_expiring_exactly_at_30_days(self):
        """Test license expiring in exactly 30 days."""
        from backend.licensing.validator import check_expiration

        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        is_valid, warning = check_expiration(future_date)

        assert is_valid is True
        # Should show warning at 30 days
        assert warning is not None


class TestLicensePayload:
    """Tests for LicensePayload dataclass."""

    def test_license_payload_creation(self):
        """Test creating a LicensePayload instance."""
        from backend.licensing.validator import LicensePayload
        from backend.licensing.features import LicenseTier

        now = datetime.now(timezone.utc)
        payload = LicensePayload(
            license_id="test-123",
            tier=LicenseTier.PROFESSIONAL,
            features=["health", "vuln"],
            modules=["health_engine"],
            expires_at=now + timedelta(days=30),
            issued_at=now,
            offline_days=14,
        )

        assert payload.license_id == "test-123"
        assert payload.tier == LicenseTier.PROFESSIONAL
        assert len(payload.features) == 2
        assert len(payload.modules) == 1
        assert payload.offline_days == 14

    def test_license_payload_optional_fields(self):
        """Test LicensePayload optional fields default to None."""
        from backend.licensing.validator import LicensePayload
        from backend.licensing.features import LicenseTier

        now = datetime.now(timezone.utc)
        payload = LicensePayload(
            license_id="test-123",
            tier=LicenseTier.COMMUNITY,
            features=[],
            modules=[],
            expires_at=now,
            issued_at=now,
            offline_days=30,
        )

        assert payload.customer_id is None
        assert payload.customer_name is None
        assert payload.parent_hosts is None
        assert payload.child_hosts is None


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_valid(self):
        """Test creating a valid ValidationResult."""
        from backend.licensing.validator import ValidationResult, LicensePayload
        from backend.licensing.features import LicenseTier

        now = datetime.now(timezone.utc)
        payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.PROFESSIONAL,
            features=[],
            modules=[],
            expires_at=now,
            issued_at=now,
            offline_days=30,
        )

        result = ValidationResult(valid=True, payload=payload)

        assert result.valid is True
        assert result.payload is not None
        assert result.error is None

    def test_validation_result_invalid(self):
        """Test creating an invalid ValidationResult."""
        from backend.licensing.validator import ValidationResult

        result = ValidationResult(valid=False, error="Invalid signature")

        assert result.valid is False
        assert result.payload is None
        assert result.error == "Invalid signature"

    def test_validation_result_with_warning(self):
        """Test ValidationResult with warning."""
        from backend.licensing.validator import ValidationResult

        result = ValidationResult(valid=True, warning="License expires in 5 days")

        assert result.valid is True
        assert result.warning == "License expires in 5 days"


class TestHasFeature:
    """Tests for has_feature function."""

    def test_has_feature_true(self):
        """Test has_feature returns True when feature is present."""
        from backend.licensing.validator import has_feature, LicensePayload
        from backend.licensing.features import LicenseTier, FeatureCode

        now = datetime.now(timezone.utc)
        payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.PROFESSIONAL,
            features=["health", "vuln"],
            modules=[],
            expires_at=now,
            issued_at=now,
            offline_days=30,
        )

        assert has_feature(payload, FeatureCode.HEALTH_ANALYSIS) is True
        assert has_feature(payload, FeatureCode.VULNERABILITY_SCANNING) is True

    def test_has_feature_false(self):
        """Test has_feature returns False when feature is not present."""
        from backend.licensing.validator import has_feature, LicensePayload
        from backend.licensing.features import LicenseTier, FeatureCode

        now = datetime.now(timezone.utc)
        payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.PROFESSIONAL,
            features=["health"],
            modules=[],
            expires_at=now,
            issued_at=now,
            offline_days=30,
        )

        assert has_feature(payload, FeatureCode.VULNERABILITY_SCANNING) is False


class TestHasModule:
    """Tests for has_module function."""

    def test_has_module_true(self):
        """Test has_module returns True when module is present."""
        from backend.licensing.validator import has_module, LicensePayload
        from backend.licensing.features import LicenseTier, ModuleCode

        now = datetime.now(timezone.utc)
        payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.PROFESSIONAL,
            features=[],
            modules=["health_engine", "vuln_engine"],
            expires_at=now,
            issued_at=now,
            offline_days=30,
        )

        assert has_module(payload, ModuleCode.HEALTH_ENGINE) is True
        assert has_module(payload, ModuleCode.VULN_ENGINE) is True

    def test_has_module_false(self):
        """Test has_module returns False when module is not present."""
        from backend.licensing.validator import has_module, LicensePayload
        from backend.licensing.features import LicenseTier, ModuleCode

        now = datetime.now(timezone.utc)
        payload = LicensePayload(
            license_id="test",
            tier=LicenseTier.PROFESSIONAL,
            features=[],
            modules=["health_engine"],
            expires_at=now,
            issued_at=now,
            offline_days=30,
        )

        assert has_module(payload, ModuleCode.VULN_ENGINE) is False


class TestVerifySignature:
    """Tests for verify_signature function."""

    def test_verify_signature_no_public_key(self):
        """Test verify_signature returns False when no public key available."""
        from backend.licensing.validator import verify_signature

        with patch(
            "backend.licensing.validator.get_public_key_pem_sync", return_value=None
        ):
            result = verify_signature("key.parts.sig", {}, b"signature")
            assert result is False

    def test_verify_signature_invalid_key_type(self):
        """Test verify_signature returns False for non-EC public key."""
        from backend.licensing.validator import verify_signature

        # Create a mock RSA key (not EC)
        mock_key = MagicMock()
        mock_key.__class__.__name__ = "RSAPublicKey"

        with patch(
            "backend.licensing.validator.load_pem_public_key", return_value=mock_key
        ):
            result = verify_signature(
                "key.parts.sig",
                {},
                b"signature",
                "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----",
            )
            assert result is False


class TestValidateLicense:
    """Tests for validate_license function."""

    def test_validate_license_invalid_format(self):
        """Test validate_license with invalid format."""
        from backend.licensing.validator import validate_license

        result = validate_license("invalid-key")

        assert result.valid is False
        assert "3 parts" in result.error

    def test_validate_license_unsupported_algorithm(self):
        """Test validate_license with unsupported algorithm."""
        from backend.licensing.validator import validate_license

        # Create a key with RS256 algorithm (unsupported)
        header = {"alg": "RS256", "typ": "JWT"}
        payload = {"lic": "test", "tier": "professional"}
        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        sig_b64 = base64.urlsafe_b64encode(b"sig").decode().rstrip("=")
        key = f"{header_b64}.{payload_b64}.{sig_b64}"

        result = validate_license(key)

        assert result.valid is False
        assert "Unsupported algorithm" in result.error

    def test_validate_license_invalid_signature(self):
        """Test validate_license with invalid signature."""
        from backend.licensing.validator import validate_license

        # Create a key with ES512 algorithm but invalid signature
        header = {"alg": "ES512", "typ": "JWT"}
        now = datetime.now(timezone.utc)
        payload = {
            "lic": "test",
            "tier": "professional",
            "exp": int((now + timedelta(days=30)).timestamp()),
        }
        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        sig_b64 = base64.urlsafe_b64encode(b"invalid-sig").decode().rstrip("=")
        key = f"{header_b64}.{payload_b64}.{sig_b64}"

        # Mock verify_signature to return False
        with patch("backend.licensing.validator.verify_signature", return_value=False):
            result = validate_license(key)

        assert result.valid is False
        assert "Invalid license signature" in result.error

    def test_validate_license_invalid_payload(self):
        """Test validate_license with invalid payload."""
        from backend.licensing.validator import validate_license

        # Create a key with valid signature but invalid payload (missing tier)
        header = {"alg": "ES512", "typ": "JWT"}
        payload = {"lic": "test"}  # Missing tier
        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        sig_b64 = base64.urlsafe_b64encode(b"sig").decode().rstrip("=")
        key = f"{header_b64}.{payload_b64}.{sig_b64}"

        # Mock verify_signature to return True
        with patch("backend.licensing.validator.verify_signature", return_value=True):
            result = validate_license(key)

        assert result.valid is False
        assert "tier" in result.error

    def test_validate_license_expired(self):
        """Test validate_license with expired license."""
        from backend.licensing.validator import validate_license

        # Create a key with expired date (past grace period)
        header = {"alg": "ES512", "typ": "JWT"}
        now = datetime.now(timezone.utc)
        payload = {
            "lic": "test",
            "tier": "professional",
            "exp": int((now - timedelta(days=30)).timestamp()),
            "features": [],
            "modules": [],
        }
        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        sig_b64 = base64.urlsafe_b64encode(b"sig").decode().rstrip("=")
        key = f"{header_b64}.{payload_b64}.{sig_b64}"

        # Mock verify_signature to return True
        with patch("backend.licensing.validator.verify_signature", return_value=True):
            result = validate_license(key)

        assert result.valid is False
        assert "expired" in result.error.lower()

    def test_validate_license_valid(self):
        """Test validate_license with valid license."""
        from backend.licensing.validator import validate_license

        # Create a valid key
        header = {"alg": "ES512", "typ": "JWT"}
        now = datetime.now(timezone.utc)
        payload = {
            "lic": "test-license",
            "tier": "professional",
            "exp": int((now + timedelta(days=30)).timestamp()),
            "features": ["health"],
            "modules": ["health_engine"],
        }
        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        sig_b64 = base64.urlsafe_b64encode(b"sig").decode().rstrip("=")
        key = f"{header_b64}.{payload_b64}.{sig_b64}"

        # Mock verify_signature to return True
        with patch("backend.licensing.validator.verify_signature", return_value=True):
            result = validate_license(key)

        assert result.valid is True
        assert result.payload is not None
        assert result.payload.license_id == "test-license"

    def test_validate_license_with_warning(self):
        """Test validate_license returns warning for expiring license."""
        from backend.licensing.validator import validate_license

        # Create a key expiring in 15 days
        header = {"alg": "ES512", "typ": "JWT"}
        now = datetime.now(timezone.utc)
        payload = {
            "lic": "test-license",
            "tier": "professional",
            "exp": int((now + timedelta(days=15)).timestamp()),
            "features": [],
            "modules": [],
        }
        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        sig_b64 = base64.urlsafe_b64encode(b"sig").decode().rstrip("=")
        key = f"{header_b64}.{payload_b64}.{sig_b64}"

        # Mock verify_signature to return True
        with patch("backend.licensing.validator.verify_signature", return_value=True):
            result = validate_license(key)

        assert result.valid is True
        assert result.warning is not None
        assert "expires in" in result.warning
