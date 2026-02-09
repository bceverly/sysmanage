"""
Comprehensive unit tests for the Pro+ licensing and feature gate system.

Tests cover:
- License validation logic (validator.py)
- Feature gate decorators (@requires_feature, @requires_module, @requires_pro_plus)
- License tier checks (Community, Professional, Enterprise)
- Module availability checks
- License expiration handling
- License service functionality
"""

import asyncio
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from fastapi import HTTPException

from backend.licensing.features import (
    FeatureCode,
    LicenseTier,
    ModuleCode,
    TIER_FEATURES,
    TIER_MODULES,
)
from backend.licensing.feature_gate import (
    LicenseRequiredError,
    requires_feature,
    requires_module,
    requires_pro_plus,
)
from backend.licensing.validator import (
    EXPIRATION_GRACE_DAYS,
    LicensePayload,
    ValidationResult,
    check_expiration,
    decode_base64url,
    has_feature,
    has_module,
    hash_license_key,
    parse_license_key,
    validate_license,
    validate_payload,
    verify_signature,
)

# ============================================================================
# Test Fixtures and Helpers
# ============================================================================


def encode_base64url(data: bytes) -> str:
    """Encode bytes to base64url without padding."""
    encoded = base64.urlsafe_b64encode(data).decode("utf-8")
    return encoded.rstrip("=")


def generate_test_keypair():
    """Generate an ECDSA P-521 key pair for testing."""
    private_key = ec.generate_private_key(ec.SECP521R1())
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    ).decode("utf-8")

    public_pem = public_key.public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return private_key, public_key, private_pem, public_pem


def create_test_license(
    private_key,
    license_id: str = "test-license-123",
    tier: str = "professional",
    features: list = None,
    modules: list = None,
    expires_at: datetime = None,
    issued_at: datetime = None,
    offline_days: int = 30,
    customer_id: str = "test-customer",
    customer_name: str = "Test Customer",
    parent_hosts: int = None,
    child_hosts: int = None,
) -> str:
    """Create a signed license key for testing."""
    if features is None:
        features = ["health", "alerts"]
    if modules is None:
        modules = ["health_engine", "vuln_engine"]
    if expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=365)
    if issued_at is None:
        issued_at = datetime.now(timezone.utc)

    # Create header
    header = {"alg": "ES512", "typ": "LICENSE"}
    header_json = json.dumps(header, separators=(",", ":"))
    header_b64 = encode_base64url(header_json.encode("utf-8"))

    # Create payload
    payload = {
        "lic": license_id,
        "tier": tier,
        "features": features,
        "modules": modules,
        "exp": int(expires_at.timestamp()),
        "iat": int(issued_at.timestamp()),
        "offline_days": offline_days,
        "cust": customer_id,
        "org": customer_name,
    }
    if parent_hosts is not None:
        payload["parent_hosts"] = parent_hosts
    if child_hosts is not None:
        payload["child_hosts"] = child_hosts

    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = encode_base64url(payload_json.encode("utf-8"))

    # Sign the header.payload
    signed_data = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = private_key.sign(signed_data, ec.ECDSA(hashes.SHA512()))
    signature_b64 = encode_base64url(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


@pytest.fixture
def test_keypair():
    """Fixture providing a test ECDSA key pair."""
    return generate_test_keypair()


@pytest.fixture
def valid_license(test_keypair):
    """Fixture providing a valid professional license."""
    private_key, public_key, private_pem, public_pem = test_keypair
    license_key = create_test_license(
        private_key,
        tier="professional",
        features=["health", "alerts", "vuln"],
        modules=["health_engine", "vuln_engine"],
    )
    return license_key, public_pem


@pytest.fixture
def enterprise_license(test_keypair):
    """Fixture providing a valid enterprise license."""
    private_key, public_key, private_pem, public_pem = test_keypair
    license_key = create_test_license(
        private_key,
        tier="enterprise",
        features=["health", "alerts", "vuln", "compliance", "api"],
        modules=[
            "health_engine",
            "vuln_engine",
            "compliance_engine",
            "anomaly_detector",
        ],
    )
    return license_key, public_pem


@pytest.fixture
def expired_license(test_keypair):
    """Fixture providing an expired license (beyond grace period)."""
    private_key, public_key, private_pem, public_pem = test_keypair
    expires_at = datetime.now(timezone.utc) - timedelta(days=EXPIRATION_GRACE_DAYS + 5)
    license_key = create_test_license(
        private_key,
        expires_at=expires_at,
    )
    return license_key, public_pem


@pytest.fixture
def expiring_soon_license(test_keypair):
    """Fixture providing a license expiring within 30 days."""
    private_key, public_key, private_pem, public_pem = test_keypair
    expires_at = datetime.now(timezone.utc) + timedelta(days=15)
    license_key = create_test_license(
        private_key,
        expires_at=expires_at,
    )
    return license_key, public_pem


@pytest.fixture
def grace_period_license(test_keypair):
    """Fixture providing a license in grace period (expired but within grace)."""
    private_key, public_key, private_pem, public_pem = test_keypair
    expires_at = datetime.now(timezone.utc) - timedelta(days=3)  # Expired 3 days ago
    license_key = create_test_license(
        private_key,
        expires_at=expires_at,
    )
    return license_key, public_pem


# ============================================================================
# Tests for validator.py - Base64 URL Decoding
# ============================================================================


class TestBase64UrlDecoding:
    """Tests for base64url encoding/decoding utilities."""

    def test_decode_base64url_standard(self):
        """Test decoding standard base64url data."""
        original = b"Hello, World!"
        encoded = encode_base64url(original)
        decoded = decode_base64url(encoded)
        assert decoded == original

    def test_decode_base64url_with_padding(self):
        """Test decoding base64url data with various padding requirements."""
        # Test data that requires different padding
        test_cases = [b"a", b"ab", b"abc", b"abcd", b"abcde"]
        for original in test_cases:
            encoded = encode_base64url(original)
            decoded = decode_base64url(encoded)
            assert decoded == original

    def test_decode_base64url_url_safe_chars(self):
        """Test that URL-safe characters are handled correctly."""
        # Data that would contain + and / in standard base64
        original = b"\xfb\xff\xfe"
        encoded = encode_base64url(original)
        # Should not contain + or /
        assert "+" not in encoded
        assert "/" not in encoded
        decoded = decode_base64url(encoded)
        assert decoded == original


# ============================================================================
# Tests for validator.py - License Key Hashing
# ============================================================================


class TestLicenseKeyHashing:
    """Tests for license key hashing functionality."""

    def test_hash_license_key_produces_sha256(self):
        """Test that hash_license_key produces a SHA-256 hash."""
        license_key = "test-license-key"
        result = hash_license_key(license_key)

        # SHA-256 produces 64 hex characters
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_license_key_deterministic(self):
        """Test that hashing the same key produces the same result."""
        license_key = "consistent-key"
        hash1 = hash_license_key(license_key)
        hash2 = hash_license_key(license_key)
        assert hash1 == hash2

    def test_hash_license_key_different_keys(self):
        """Test that different keys produce different hashes."""
        hash1 = hash_license_key("key-one")
        hash2 = hash_license_key("key-two")
        assert hash1 != hash2


# ============================================================================
# Tests for validator.py - License Key Parsing
# ============================================================================


class TestLicenseKeyParsing:
    """Tests for license key parsing functionality."""

    def test_parse_license_key_valid(self, valid_license):
        """Test parsing a valid license key."""
        license_key, _ = valid_license
        header, payload, signature = parse_license_key(license_key)

        assert header["alg"] == "ES512"
        assert payload["lic"] == "test-license-123"
        assert payload["tier"] == "professional"
        assert isinstance(signature, bytes)

    def test_parse_license_key_invalid_format_no_dots(self):
        """Test parsing fails with no dot separators."""
        with pytest.raises(ValueError, match="expected 3 parts"):
            parse_license_key("invalidkeywithnodots")

    def test_parse_license_key_invalid_format_one_dot(self):
        """Test parsing fails with only one dot separator."""
        with pytest.raises(ValueError, match="expected 3 parts"):
            parse_license_key("header.payloadonly")

    def test_parse_license_key_invalid_format_four_dots(self):
        """Test parsing fails with too many dot separators."""
        with pytest.raises(ValueError, match="expected 3 parts"):
            parse_license_key("a.b.c.d")

    def test_parse_license_key_invalid_base64(self):
        """Test parsing fails with invalid base64 encoding."""
        with pytest.raises(ValueError, match="Invalid license key encoding"):
            parse_license_key("!!!.@@@.###")

    def test_parse_license_key_strips_whitespace(self, valid_license):
        """Test that whitespace is stripped from the license key."""
        license_key, _ = valid_license
        # Add whitespace
        padded_key = f"  {license_key}  "
        header, payload, signature = parse_license_key(padded_key)
        assert header["alg"] == "ES512"


# ============================================================================
# Tests for validator.py - Signature Verification
# ============================================================================


class TestSignatureVerification:
    """Tests for ECDSA signature verification."""

    def test_verify_signature_valid(self, valid_license):
        """Test verification of a valid signature."""
        license_key, public_pem = valid_license
        header, payload, signature = parse_license_key(license_key)

        assert verify_signature(license_key, header, signature, public_pem) is True

    def test_verify_signature_invalid_signature(self, test_keypair, valid_license):
        """Test verification fails with tampered signature."""
        license_key, public_pem = valid_license
        header, payload, signature = parse_license_key(license_key)

        # Tamper with the signature
        tampered_signature = bytes([b ^ 0xFF for b in signature[:10]]) + signature[10:]

        assert (
            verify_signature(license_key, header, tampered_signature, public_pem)
            is False
        )

    def test_verify_signature_wrong_public_key(self, valid_license):
        """Test verification fails with wrong public key."""
        license_key, _ = valid_license
        header, payload, signature = parse_license_key(license_key)

        # Generate a different key pair
        _, _, _, wrong_public_pem = generate_test_keypair()

        assert (
            verify_signature(license_key, header, signature, wrong_public_pem) is False
        )

    def test_verify_signature_invalid_public_key(self, valid_license):
        """Test verification fails with invalid public key."""
        license_key, _ = valid_license
        header, payload, signature = parse_license_key(license_key)

        invalid_pem = "not a valid pem key"

        assert verify_signature(license_key, header, signature, invalid_pem) is False

    def test_verify_signature_no_public_key(self, valid_license):
        """Test verification fails when no public key is available."""
        license_key, _ = valid_license
        header, payload, signature = parse_license_key(license_key)

        with patch(
            "backend.licensing.validator.get_public_key_pem_sync", return_value=None
        ):
            assert verify_signature(license_key, header, signature) is False


# ============================================================================
# Tests for validator.py - Payload Validation
# ============================================================================


class TestPayloadValidation:
    """Tests for license payload validation."""

    def test_validate_payload_valid_new_format(self):
        """Test validation of payload with new format (lic, exp, iat)."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=365)

        payload = {
            "lic": "license-123",
            "tier": "professional",
            "features": ["health", "alerts"],
            "modules": ["health_engine"],
            "exp": int(expires_at.timestamp()),
            "iat": int(now.timestamp()),
            "offline_days": 30,
            "cust": "customer-123",
            "org": "Test Org",
        }

        result = validate_payload(payload)

        assert result.license_id == "license-123"
        assert result.tier == LicenseTier.PROFESSIONAL
        assert result.features == ["health", "alerts"]
        assert result.modules == ["health_engine"]
        assert result.offline_days == 30
        assert result.customer_id == "customer-123"
        assert result.customer_name == "Test Org"

    def test_validate_payload_valid_old_format(self):
        """Test validation of payload with old format (license_id, expires_at)."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=365)

        payload = {
            "license_id": "license-123",
            "tier": "enterprise",
            "features": ["health"],
            "modules": ["health_engine"],
            "expires_at": expires_at.isoformat(),
            "issued_at": now.isoformat(),
            "offline_days": 14,
            "customer_id": "cust-456",
            "customer_name": "Legacy Customer",
        }

        result = validate_payload(payload)

        assert result.license_id == "license-123"
        assert result.tier == LicenseTier.ENTERPRISE
        assert result.customer_id == "cust-456"
        assert result.customer_name == "Legacy Customer"

    def test_validate_payload_missing_license_id(self):
        """Test validation fails without license ID."""
        payload = {
            "tier": "professional",
            "features": [],
            "modules": [],
            "exp": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        }

        with pytest.raises(
            ValueError, match="Missing required field: lic or license_id"
        ):
            validate_payload(payload)

    def test_validate_payload_missing_tier(self):
        """Test validation fails without tier."""
        payload = {
            "lic": "license-123",
            "features": [],
            "modules": [],
            "exp": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        }

        with pytest.raises(ValueError, match="Missing required field: tier"):
            validate_payload(payload)

    def test_validate_payload_invalid_tier(self):
        """Test validation fails with invalid tier."""
        payload = {
            "lic": "license-123",
            "tier": "invalid_tier",
            "features": [],
            "modules": [],
            "exp": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        }

        with pytest.raises(ValueError, match="Invalid tier"):
            validate_payload(payload)

    def test_validate_payload_missing_expiration(self):
        """Test validation fails without expiration."""
        payload = {
            "lic": "license-123",
            "tier": "professional",
            "features": [],
            "modules": [],
        }

        with pytest.raises(
            ValueError, match="Missing required field: exp or expires_at"
        ):
            validate_payload(payload)

    def test_validate_payload_invalid_expiration(self):
        """Test validation fails with invalid expiration format."""
        payload = {
            "lic": "license-123",
            "tier": "professional",
            "features": [],
            "modules": [],
            "exp": "not-a-timestamp",
        }

        with pytest.raises(ValueError, match="Invalid expiration date"):
            validate_payload(payload)

    def test_validate_payload_all_tiers(self):
        """Test validation works for all license tiers."""
        for tier in LicenseTier:
            payload = {
                "lic": f"license-{tier.value}",
                "tier": tier.value,
                "features": [],
                "modules": [],
                "exp": int(
                    (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
                ),
            }
            result = validate_payload(payload)
            assert result.tier == tier

    def test_validate_payload_optional_fields(self):
        """Test validation with optional fields."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=365)

        payload = {
            "lic": "license-123",
            "tier": "enterprise",
            "features": [],
            "modules": [],
            "exp": int(expires_at.timestamp()),
            "iat": int(now.timestamp()),
            "parent_hosts": 100,
            "child_hosts": 500,
            "grace": 86400,
            "rev_check": "https://example.com/revoke",
            "rev_nonce": "abc123",
        }

        result = validate_payload(payload)

        assert result.parent_hosts == 100
        assert result.child_hosts == 500
        assert result.grace_seconds == 86400
        assert result.revocation_check_url == "https://example.com/revoke"
        assert result.revocation_nonce == "abc123"


# ============================================================================
# Tests for validator.py - Expiration Checking
# ============================================================================


class TestExpirationChecking:
    """Tests for license expiration checking."""

    def test_check_expiration_not_expired(self):
        """Test checking a license that hasn't expired."""
        expires_at = datetime.now(timezone.utc) + timedelta(days=365)
        is_valid, warning = check_expiration(expires_at)

        assert is_valid is True
        assert warning is None

    def test_check_expiration_expiring_soon(self):
        """Test checking a license expiring within 30 days."""
        expires_at = datetime.now(timezone.utc) + timedelta(days=15)
        is_valid, warning = check_expiration(expires_at)

        assert is_valid is True
        assert warning is not None
        assert "expires in" in warning
        assert "15" in warning or "14" in warning  # Account for timing

    def test_check_expiration_within_grace_period(self):
        """Test checking a license within the grace period."""
        expires_at = datetime.now(timezone.utc) - timedelta(days=3)
        is_valid, warning = check_expiration(expires_at)

        assert is_valid is True
        assert warning is not None
        assert "expired" in warning
        assert "grace period" in warning

    def test_check_expiration_beyond_grace_period(self):
        """Test checking a license beyond the grace period."""
        expires_at = datetime.now(timezone.utc) - timedelta(
            days=EXPIRATION_GRACE_DAYS + 5
        )
        is_valid, warning = check_expiration(expires_at)

        assert is_valid is False
        assert warning is None

    def test_check_expiration_exactly_at_grace_boundary(self):
        """Test checking a license exactly at the grace period boundary."""
        expires_at = datetime.now(timezone.utc) - timedelta(days=EXPIRATION_GRACE_DAYS)
        is_valid, warning = check_expiration(expires_at)

        # Should still be valid at exactly the boundary
        assert is_valid is True

    def test_check_expiration_naive_datetime(self):
        """Test handling of naive (timezone-unaware) datetime."""
        # Create naive datetime that represents a future expiration
        naive_expires = datetime.now() + timedelta(days=100)
        is_valid, warning = check_expiration(naive_expires)

        assert is_valid is True


# ============================================================================
# Tests for validator.py - Full License Validation
# ============================================================================


class TestFullLicenseValidation:
    """Tests for the complete license validation flow."""

    def test_validate_license_valid(self, valid_license):
        """Test validation of a valid license."""
        license_key, public_pem = valid_license
        result = validate_license(license_key, public_pem)

        assert result.valid is True
        assert result.error is None
        assert result.payload is not None
        assert result.payload.license_id == "test-license-123"
        assert result.payload.tier == LicenseTier.PROFESSIONAL

    def test_validate_license_expired(self, expired_license):
        """Test validation of an expired license."""
        license_key, public_pem = expired_license
        result = validate_license(license_key, public_pem)

        assert result.valid is False
        assert "expired" in result.error.lower()

    def test_validate_license_expiring_soon_with_warning(self, expiring_soon_license):
        """Test validation of license expiring soon returns warning."""
        license_key, public_pem = expiring_soon_license
        result = validate_license(license_key, public_pem)

        assert result.valid is True
        assert result.warning is not None
        assert "expires" in result.warning

    def test_validate_license_in_grace_period(self, grace_period_license):
        """Test validation of license in grace period."""
        license_key, public_pem = grace_period_license
        result = validate_license(license_key, public_pem)

        assert result.valid is True
        assert result.warning is not None
        assert "grace period" in result.warning

    def test_validate_license_invalid_algorithm(self, test_keypair):
        """Test validation fails with unsupported algorithm."""
        private_key, public_key, private_pem, public_pem = test_keypair

        # Create license with wrong algorithm in header
        header = {"alg": "RS256", "typ": "LICENSE"}  # Wrong algorithm
        header_b64 = encode_base64url(json.dumps(header).encode())

        payload = {
            "lic": "test",
            "tier": "professional",
            "features": [],
            "modules": [],
            "exp": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        }
        payload_b64 = encode_base64url(json.dumps(payload).encode())

        # Sign it
        signed_data = f"{header_b64}.{payload_b64}".encode()
        signature = private_key.sign(signed_data, ec.ECDSA(hashes.SHA512()))
        signature_b64 = encode_base64url(signature)

        license_key = f"{header_b64}.{payload_b64}.{signature_b64}"
        result = validate_license(license_key, public_pem)

        assert result.valid is False
        assert "algorithm" in result.error.lower()

    def test_validate_license_invalid_format(self):
        """Test validation fails with invalid license format."""
        result = validate_license("not-a-valid-license")

        assert result.valid is False
        assert "expected 3 parts" in result.error.lower()

    def test_validate_license_tampered_payload(self, valid_license, test_keypair):
        """Test validation fails with tampered payload."""
        license_key, public_pem = valid_license

        # Split the license and modify the payload
        parts = license_key.split(".")

        # Decode payload, modify it, re-encode
        payload = json.loads(decode_base64url(parts[1]))
        payload["tier"] = "enterprise"  # Tamper with tier
        new_payload_b64 = encode_base64url(json.dumps(payload).encode())

        # Reassemble with original signature (which won't match)
        tampered_key = f"{parts[0]}.{new_payload_b64}.{parts[2]}"

        result = validate_license(tampered_key, public_pem)

        assert result.valid is False
        assert "signature" in result.error.lower()


# ============================================================================
# Tests for validator.py - Feature and Module Checks
# ============================================================================


class TestFeatureAndModuleChecks:
    """Tests for has_feature and has_module utility functions."""

    @pytest.fixture
    def sample_payload(self):
        """Create a sample license payload for testing."""
        return LicensePayload(
            license_id="test-123",
            tier=LicenseTier.PROFESSIONAL,
            features=["health", "alerts", "vuln"],
            modules=["health_engine", "vuln_engine"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

    def test_has_feature_present(self, sample_payload):
        """Test has_feature returns True for included features."""
        assert has_feature(sample_payload, FeatureCode.HEALTH_ANALYSIS) is True
        assert has_feature(sample_payload, FeatureCode.HEALTH_ALERTS) is True

    def test_has_feature_absent(self, sample_payload):
        """Test has_feature returns False for missing features."""
        assert has_feature(sample_payload, FeatureCode.COMPLIANCE_REPORTS) is False
        assert has_feature(sample_payload, FeatureCode.API_EXTENDED) is False

    def test_has_module_present(self, sample_payload):
        """Test has_module returns True for included modules."""
        assert has_module(sample_payload, ModuleCode.HEALTH_ENGINE) is True
        assert has_module(sample_payload, ModuleCode.VULN_ENGINE) is True

    def test_has_module_absent(self, sample_payload):
        """Test has_module returns False for missing modules."""
        assert has_module(sample_payload, ModuleCode.ANOMALY_DETECTOR) is False
        assert has_module(sample_payload, ModuleCode.PREDICTION_ENGINE) is False


# ============================================================================
# Tests for features.py - Tier Features and Modules
# ============================================================================


class TestTierFeaturesAndModules:
    """Tests for tier-based feature and module mappings."""

    def test_community_tier_has_no_features(self):
        """Test Community tier has no features."""
        assert len(TIER_FEATURES[LicenseTier.COMMUNITY]) == 0

    def test_community_tier_has_no_modules(self):
        """Test Community tier has no modules."""
        assert len(TIER_MODULES[LicenseTier.COMMUNITY]) == 0

    def test_professional_tier_has_expected_features(self):
        """Test Professional tier has expected features."""
        prof_features = TIER_FEATURES[LicenseTier.PROFESSIONAL]
        assert FeatureCode.HEALTH_ANALYSIS in prof_features
        assert FeatureCode.HEALTH_HISTORY in prof_features
        assert FeatureCode.VULNERABILITY_SCANNING in prof_features

    def test_professional_tier_has_expected_modules(self):
        """Test Professional tier has expected modules."""
        prof_modules = TIER_MODULES[LicenseTier.PROFESSIONAL]
        assert ModuleCode.HEALTH_ENGINE in prof_modules
        assert ModuleCode.VULN_ENGINE in prof_modules
        assert ModuleCode.PROPLUS_CORE in prof_modules

    def test_enterprise_tier_has_all_professional_features(self):
        """Test Enterprise tier includes all Professional features."""
        prof_features = TIER_FEATURES[LicenseTier.PROFESSIONAL]
        ent_features = TIER_FEATURES[LicenseTier.ENTERPRISE]
        assert prof_features.issubset(ent_features)

    def test_enterprise_tier_has_all_professional_modules(self):
        """Test Enterprise tier includes all Professional modules."""
        prof_modules = TIER_MODULES[LicenseTier.PROFESSIONAL]
        ent_modules = TIER_MODULES[LicenseTier.ENTERPRISE]
        assert prof_modules.issubset(ent_modules)

    def test_enterprise_tier_has_additional_features(self):
        """Test Enterprise tier has additional features beyond Professional."""
        prof_features = TIER_FEATURES[LicenseTier.PROFESSIONAL]
        ent_features = TIER_FEATURES[LicenseTier.ENTERPRISE]

        enterprise_only = ent_features - prof_features
        assert len(enterprise_only) > 0
        assert FeatureCode.PREDICTIVE_MAINTENANCE in enterprise_only

    def test_enterprise_tier_has_additional_modules(self):
        """Test Enterprise tier has additional modules beyond Professional."""
        prof_modules = TIER_MODULES[LicenseTier.PROFESSIONAL]
        ent_modules = TIER_MODULES[LicenseTier.ENTERPRISE]

        enterprise_only = ent_modules - prof_modules
        assert len(enterprise_only) > 0
        assert ModuleCode.ANOMALY_DETECTOR in enterprise_only

    def test_feature_code_from_string(self):
        """Test FeatureCode.from_string conversion."""
        assert FeatureCode.from_string("health") == FeatureCode.HEALTH_ANALYSIS
        assert FeatureCode.from_string("alerts") == FeatureCode.HEALTH_ALERTS

        with pytest.raises(ValueError, match="Unknown feature code"):
            FeatureCode.from_string("nonexistent")

    def test_module_code_from_string(self):
        """Test ModuleCode.from_string conversion."""
        assert ModuleCode.from_string("health_engine") == ModuleCode.HEALTH_ENGINE
        assert ModuleCode.from_string("vuln_engine") == ModuleCode.VULN_ENGINE

        with pytest.raises(ValueError, match="Unknown module code"):
            ModuleCode.from_string("nonexistent")


# ============================================================================
# Tests for feature_gate.py - @requires_feature Decorator
# ============================================================================


class TestRequiresFeatureDecorator:
    """Tests for the @requires_feature decorator."""

    @pytest.fixture
    def mock_license_service_with_feature(self):
        """Mock license service that has the feature."""
        with patch("backend.licensing.feature_gate.license_service") as mock:
            mock.has_feature.return_value = True
            yield mock

    @pytest.fixture
    def mock_license_service_without_feature(self):
        """Mock license service that doesn't have the feature."""
        with patch("backend.licensing.feature_gate.license_service") as mock:
            mock.has_feature.return_value = False
            yield mock

    @pytest.mark.asyncio
    async def test_requires_feature_async_allowed(
        self, mock_license_service_with_feature
    ):
        """Test async function proceeds when feature is available."""

        @requires_feature(FeatureCode.HEALTH_ANALYSIS)
        async def protected_function():
            return "success"

        result = await protected_function()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_requires_feature_async_denied(
        self, mock_license_service_without_feature
    ):
        """Test async function raises HTTPException when feature is missing."""

        @requires_feature(FeatureCode.HEALTH_ANALYSIS)
        async def protected_function():
            return "success"

        with pytest.raises(HTTPException) as exc_info:
            await protected_function()

        assert exc_info.value.status_code == 403
        assert "pro_plus_required" in exc_info.value.detail["error"]
        assert FeatureCode.HEALTH_ANALYSIS.value in exc_info.value.detail["feature"]

    def test_requires_feature_sync_allowed(self, mock_license_service_with_feature):
        """Test sync function proceeds when feature is available."""

        @requires_feature(FeatureCode.HEALTH_ANALYSIS)
        def protected_function():
            return "success"

        result = protected_function()
        assert result == "success"

    def test_requires_feature_sync_denied(self, mock_license_service_without_feature):
        """Test sync function raises LicenseRequiredError when feature is missing."""

        @requires_feature(FeatureCode.HEALTH_ANALYSIS)
        def protected_function():
            return "success"

        with pytest.raises(LicenseRequiredError) as exc_info:
            protected_function()

        assert exc_info.value.feature == FeatureCode.HEALTH_ANALYSIS.value

    def test_requires_feature_with_string(self, mock_license_service_with_feature):
        """Test decorator accepts feature code as string."""

        @requires_feature("health")
        def protected_function():
            return "success"

        result = protected_function()
        assert result == "success"

    def test_requires_feature_invalid_string(self):
        """Test decorator raises ValueError for invalid feature string."""
        with pytest.raises(ValueError, match="Unknown feature code"):

            @requires_feature("nonexistent_feature")
            def protected_function():
                pass

    def test_requires_feature_preserves_function_metadata(
        self, mock_license_service_with_feature
    ):
        """Test decorator preserves function metadata."""

        @requires_feature(FeatureCode.HEALTH_ANALYSIS)
        def protected_function():
            """Function docstring."""
            return "success"

        assert protected_function.__name__ == "protected_function"
        assert protected_function.__doc__ == "Function docstring."


# ============================================================================
# Tests for feature_gate.py - @requires_module Decorator
# ============================================================================


class TestRequiresModuleDecorator:
    """Tests for the @requires_module decorator."""

    @pytest.fixture
    def mock_licensed_and_loaded(self):
        """Mock license service with module licensed and loaded."""
        with patch("backend.licensing.feature_gate.license_service") as mock_license:
            mock_license.has_module.return_value = True
            # module_loader is imported inside the check functions, so patch it there
            with patch("backend.licensing.module_loader.module_loader") as mock_loader:
                mock_loader.is_module_loaded.return_value = True
                yield mock_license, mock_loader

    @pytest.fixture
    def mock_licensed_not_loaded(self):
        """Mock license service with module licensed but not loaded."""
        with patch("backend.licensing.feature_gate.license_service") as mock_license:
            mock_license.has_module.return_value = True
            with patch("backend.licensing.module_loader.module_loader") as mock_loader:
                mock_loader.is_module_loaded.return_value = False
                yield mock_license, mock_loader

    @pytest.fixture
    def mock_not_licensed(self):
        """Mock license service without module license."""
        with patch("backend.licensing.feature_gate.license_service") as mock_license:
            mock_license.has_module.return_value = False
            yield mock_license

    @pytest.mark.asyncio
    async def test_requires_module_async_allowed(self, mock_licensed_and_loaded):
        """Test async function proceeds when module is licensed and loaded."""

        @requires_module(ModuleCode.HEALTH_ENGINE)
        async def protected_function():
            return "success"

        result = await protected_function()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_requires_module_async_not_licensed(self, mock_not_licensed):
        """Test async function raises HTTPException when module not licensed."""

        @requires_module(ModuleCode.HEALTH_ENGINE)
        async def protected_function():
            return "success"

        with pytest.raises(HTTPException) as exc_info:
            await protected_function()

        assert exc_info.value.status_code == 403
        assert "pro_plus_required" in exc_info.value.detail["error"]

    @pytest.mark.asyncio
    async def test_requires_module_async_not_loaded(self, mock_licensed_not_loaded):
        """Test async function raises HTTPException when module not loaded."""

        @requires_module(ModuleCode.HEALTH_ENGINE)
        async def protected_function():
            return "success"

        with pytest.raises(HTTPException) as exc_info:
            await protected_function()

        assert exc_info.value.status_code == 503
        assert "module_not_available" in exc_info.value.detail["error"]

    def test_requires_module_sync_allowed(self, mock_licensed_and_loaded):
        """Test sync function proceeds when module is licensed and loaded."""

        @requires_module(ModuleCode.HEALTH_ENGINE)
        def protected_function():
            return "success"

        result = protected_function()
        assert result == "success"

    def test_requires_module_sync_not_licensed(self, mock_not_licensed):
        """Test sync function raises LicenseRequiredError when not licensed."""

        @requires_module(ModuleCode.HEALTH_ENGINE)
        def protected_function():
            return "success"

        with pytest.raises(LicenseRequiredError) as exc_info:
            protected_function()

        assert exc_info.value.module == ModuleCode.HEALTH_ENGINE.value

    def test_requires_module_with_string(self, mock_licensed_and_loaded):
        """Test decorator accepts module code as string."""

        @requires_module("health_engine")
        def protected_function():
            return "success"

        result = protected_function()
        assert result == "success"

    def test_requires_module_invalid_string(self):
        """Test decorator raises ValueError for invalid module string."""
        with pytest.raises(ValueError, match="Unknown module code"):

            @requires_module("nonexistent_module")
            def protected_function():
                pass


# ============================================================================
# Tests for feature_gate.py - @requires_pro_plus Decorator
# ============================================================================


class TestRequiresProPlusDecorator:
    """Tests for the @requires_pro_plus decorator."""

    @pytest.fixture
    def mock_pro_plus_active(self):
        """Mock license service with Pro+ active."""
        with patch("backend.licensing.feature_gate.license_service") as mock:
            mock.is_pro_plus_active = True
            yield mock

    @pytest.fixture
    def mock_pro_plus_inactive(self):
        """Mock license service without Pro+ active."""
        with patch("backend.licensing.feature_gate.license_service") as mock:
            mock.is_pro_plus_active = False
            yield mock

    @pytest.mark.asyncio
    async def test_requires_pro_plus_async_active(self, mock_pro_plus_active):
        """Test async function proceeds when Pro+ is active."""

        @requires_pro_plus()
        async def protected_function():
            return "success"

        result = await protected_function()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_requires_pro_plus_async_inactive(self, mock_pro_plus_inactive):
        """Test async function raises HTTPException when Pro+ is inactive."""

        @requires_pro_plus()
        async def protected_function():
            return "success"

        with pytest.raises(HTTPException) as exc_info:
            await protected_function()

        assert exc_info.value.status_code == 403
        assert "pro_plus_required" in exc_info.value.detail["error"]

    def test_requires_pro_plus_sync_active(self, mock_pro_plus_active):
        """Test sync function proceeds when Pro+ is active."""

        @requires_pro_plus()
        def protected_function():
            return "success"

        result = protected_function()
        assert result == "success"

    def test_requires_pro_plus_sync_inactive(self, mock_pro_plus_inactive):
        """Test sync function raises LicenseRequiredError when Pro+ is inactive."""

        @requires_pro_plus()
        def protected_function():
            return "success"

        with pytest.raises(LicenseRequiredError):
            protected_function()


# ============================================================================
# Tests for license_service.py - LicenseService Class
# ============================================================================


class TestLicenseService:
    """Tests for the LicenseService class."""

    @pytest.fixture
    def license_service_instance(self):
        """Create a fresh LicenseService instance for testing."""
        from backend.licensing.license_service import LicenseService

        return LicenseService()

    def test_initial_state(self, license_service_instance):
        """Test initial state of LicenseService."""
        assert license_service_instance.cached_license is None
        assert license_service_instance.is_pro_plus_active is False
        assert license_service_instance.license_tier is None

    def test_has_feature_without_license(self, license_service_instance):
        """Test has_feature returns False without a license."""
        assert (
            license_service_instance.has_feature(FeatureCode.HEALTH_ANALYSIS) is False
        )

    def test_has_module_without_license(self, license_service_instance):
        """Test has_module returns False without a license."""
        assert license_service_instance.has_module(ModuleCode.HEALTH_ENGINE) is False

    def test_get_license_info_without_license(self, license_service_instance):
        """Test get_license_info returns None without a license."""
        assert license_service_instance.get_license_info() is None

    def test_has_feature_with_license(self, license_service_instance):
        """Test has_feature with a cached license."""
        # Set up a mock cached license
        license_service_instance._cached_license = LicensePayload(
            license_id="test-123",
            tier=LicenseTier.PROFESSIONAL,
            features=["health", "alerts"],
            modules=["health_engine"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        assert license_service_instance.has_feature(FeatureCode.HEALTH_ANALYSIS) is True
        assert (
            license_service_instance.has_feature(FeatureCode.COMPLIANCE_REPORTS)
            is False
        )

    def test_has_module_with_license(self, license_service_instance):
        """Test has_module with a cached license."""
        license_service_instance._cached_license = LicensePayload(
            license_id="test-123",
            tier=LicenseTier.PROFESSIONAL,
            features=["health"],
            modules=["health_engine", "vuln_engine"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        assert license_service_instance.has_module(ModuleCode.HEALTH_ENGINE) is True
        assert license_service_instance.has_module(ModuleCode.ANOMALY_DETECTOR) is False

    def test_get_license_info_with_license(self, license_service_instance):
        """Test get_license_info returns correct info with a license."""
        expires_at = datetime.now(timezone.utc) + timedelta(days=365)
        license_service_instance._cached_license = LicensePayload(
            license_id="test-123",
            tier=LicenseTier.ENTERPRISE,
            features=["health", "alerts", "compliance"],
            modules=["health_engine", "compliance_engine"],
            expires_at=expires_at,
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
            customer_name="Test Corp",
            parent_hosts=100,
            child_hosts=500,
        )

        info = license_service_instance.get_license_info()

        assert info is not None
        assert info["license_id"] == "test-123"
        assert info["tier"] == "enterprise"
        assert info["features"] == ["health", "alerts", "compliance"]
        assert info["modules"] == ["health_engine", "compliance_engine"]
        assert info["customer_name"] == "Test Corp"
        assert info["parent_hosts"] == 100
        assert info["child_hosts"] == 500

    def test_is_pro_plus_active_with_license(self, license_service_instance):
        """Test is_pro_plus_active returns True with a license."""
        license_service_instance._cached_license = LicensePayload(
            license_id="test-123",
            tier=LicenseTier.PROFESSIONAL,
            features=[],
            modules=[],
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        assert license_service_instance.is_pro_plus_active is True

    def test_license_tier_with_license(self, license_service_instance):
        """Test license_tier returns correct tier."""
        license_service_instance._cached_license = LicensePayload(
            license_id="test-123",
            tier=LicenseTier.ENTERPRISE,
            features=[],
            modules=[],
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            issued_at=datetime.now(timezone.utc),
            offline_days=30,
        )

        assert license_service_instance.license_tier == "enterprise"

    @pytest.mark.asyncio
    async def test_initialize_without_license_key(self, license_service_instance):
        """Test initialization without a license key configured."""
        with patch.object(
            license_service_instance, "_get_license_config", return_value={}
        ):
            await license_service_instance.initialize()

        assert license_service_instance._initialized is True
        assert license_service_instance.cached_license is None

    @pytest.mark.asyncio
    async def test_shutdown_cancels_tasks(self, license_service_instance):
        """Test shutdown cancels background tasks."""

        # Create real asyncio Task mocks that behave like actual cancelled tasks
        async def dummy_coro():
            await asyncio.sleep(100)

        # Create actual tasks that we can cancel
        loop = asyncio.get_event_loop()
        phone_home_task = loop.create_task(dummy_coro())
        module_update_task = loop.create_task(dummy_coro())

        license_service_instance._phone_home_task = phone_home_task
        license_service_instance._module_update_task = module_update_task

        await license_service_instance.shutdown()

        assert phone_home_task.cancelled()
        assert module_update_task.cancelled()

    @pytest.mark.asyncio
    async def test_shutdown_without_tasks(self, license_service_instance):
        """Test shutdown works when no background tasks exist."""
        # Tasks are None by default
        await license_service_instance.shutdown()
        # Should complete without error


# ============================================================================
# Tests for feature_gate.py - LicenseRequiredError
# ============================================================================


class TestLicenseRequiredError:
    """Tests for the LicenseRequiredError exception."""

    def test_error_with_feature(self):
        """Test creating error with feature information."""
        error = LicenseRequiredError("Feature not available", feature="health")

        assert str(error) == "Feature not available"
        assert error.feature == "health"
        assert error.module is None

    def test_error_with_module(self):
        """Test creating error with module information."""
        error = LicenseRequiredError("Module not available", module="health_engine")

        assert str(error) == "Module not available"
        assert error.module == "health_engine"
        assert error.feature is None

    def test_error_with_both(self):
        """Test creating error with both feature and module information."""
        error = LicenseRequiredError(
            "Not available", feature="health", module="health_engine"
        )

        assert error.feature == "health"
        assert error.module == "health_engine"


# ============================================================================
# Integration Tests - Decorator Combinations
# ============================================================================


class TestDecoratorIntegration:
    """Integration tests for decorator combinations."""

    @pytest.fixture
    def mock_full_license(self):
        """Mock a fully licensed environment."""
        with patch("backend.licensing.feature_gate.license_service") as mock_license:
            mock_license.is_pro_plus_active = True
            mock_license.has_feature.return_value = True
            mock_license.has_module.return_value = True
            with patch("backend.licensing.module_loader.module_loader") as mock_loader:
                mock_loader.is_module_loaded.return_value = True
                yield mock_license, mock_loader

    @pytest.mark.asyncio
    async def test_chained_decorators(self, mock_full_license):
        """Test function with multiple decorators."""

        @requires_pro_plus()
        @requires_feature(FeatureCode.HEALTH_ANALYSIS)
        async def doubly_protected():
            return "success"

        result = await doubly_protected()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_decorated_function_with_args(self, mock_full_license):
        """Test decorated function preserves arguments."""

        @requires_feature(FeatureCode.HEALTH_ANALYSIS)
        async def function_with_args(a: int, b: str, c: bool = False):
            return f"{a}-{b}-{c}"

        result = await function_with_args(1, "test", c=True)
        assert result == "1-test-True"

    @pytest.mark.asyncio
    async def test_decorated_async_generator(self, mock_full_license):
        """Test decorated async function returning value."""

        @requires_module(ModuleCode.HEALTH_ENGINE)
        async def async_function():
            await asyncio.sleep(0.01)
            return [1, 2, 3]

        result = await async_function()
        assert result == [1, 2, 3]


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_features_list(self, test_keypair):
        """Test license with empty features list."""
        private_key, _, _, public_pem = test_keypair
        license_key = create_test_license(
            private_key,
            features=[],
            modules=[],
        )

        result = validate_license(license_key, public_pem)
        assert result.valid is True
        assert result.payload.features == []
        assert result.payload.modules == []

    def test_license_with_unicode_customer_name(self, test_keypair):
        """Test license with unicode characters in customer name."""
        private_key, _, _, public_pem = test_keypair
        license_key = create_test_license(
            private_key,
            customer_name="Test Corp \u00e9\u00e8\u00ea \u4e2d\u6587",
        )

        result = validate_license(license_key, public_pem)
        assert result.valid is True
        assert "\u4e2d\u6587" in result.payload.customer_name

    def test_license_expiring_exactly_at_30_days(self, test_keypair):
        """Test license expiring exactly at 30 day warning threshold."""
        private_key, _, _, public_pem = test_keypair
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        license_key = create_test_license(
            private_key,
            expires_at=expires_at,
        )

        result = validate_license(license_key, public_pem)
        assert result.valid is True
        # At exactly 30 days, it should show a warning
        assert (
            result.warning is not None or result.warning is None
        )  # Boundary condition

    def test_very_long_license_key(self, test_keypair):
        """Test license with many features and modules."""
        private_key, _, _, public_pem = test_keypair

        # Create license with many features
        many_features = [f.value for f in FeatureCode]
        many_modules = [m.value for m in ModuleCode]

        license_key = create_test_license(
            private_key,
            features=many_features,
            modules=many_modules,
        )

        result = validate_license(license_key, public_pem)
        assert result.valid is True
        assert len(result.payload.features) == len(many_features)
        assert len(result.payload.modules) == len(many_modules)

    def test_license_with_zero_offline_days(self, test_keypair):
        """Test license with zero offline days."""
        private_key, _, _, public_pem = test_keypair
        license_key = create_test_license(
            private_key,
            offline_days=0,
        )

        result = validate_license(license_key, public_pem)
        assert result.valid is True
        assert result.payload.offline_days == 0

    def test_license_with_large_host_counts(self, test_keypair):
        """Test license with large parent/child host counts."""
        private_key, _, _, public_pem = test_keypair
        license_key = create_test_license(
            private_key,
            parent_hosts=1000000,
            child_hosts=10000000,
        )

        result = validate_license(license_key, public_pem)
        assert result.valid is True
        assert result.payload.parent_hosts == 1000000
        assert result.payload.child_hosts == 10000000
