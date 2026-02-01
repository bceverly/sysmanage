"""
Local license signature validation for Pro+ licenses.

Validates license keys using the embedded ECDSA P-521 public key.
License keys are JWT-like tokens with a header, payload, and signature.
"""

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from backend.licensing.features import FeatureCode, LicenseTier, ModuleCode
from backend.licensing.public_key import get_public_key_pem_sync
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.licensing.validator")

# Grace period in days for expired licenses
EXPIRATION_GRACE_DAYS = 7


@dataclass
class LicensePayload:
    """Decoded license payload data."""

    license_id: str
    tier: LicenseTier
    features: List[str]
    modules: List[str]
    expires_at: datetime
    issued_at: datetime
    offline_days: int
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    parent_hosts: Optional[int] = None
    child_hosts: Optional[int] = None
    grace_seconds: Optional[int] = None
    revocation_check_url: Optional[str] = None
    revocation_nonce: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of license validation."""

    valid: bool
    payload: Optional[LicensePayload] = None
    error: Optional[str] = None
    warning: Optional[str] = None


def decode_base64url(data: str) -> bytes:
    """Decode base64url-encoded data."""
    # Add padding if needed
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    # Replace URL-safe characters
    data = data.replace("-", "+").replace("_", "/")
    return base64.b64decode(data)


def hash_license_key(license_key: str) -> str:
    """
    Create a SHA-256 hash of the license key for storage.

    Args:
        license_key: The raw license key

    Returns:
        Hexadecimal hash string
    """
    return hashlib.sha256(license_key.encode("utf-8")).hexdigest()


def parse_license_key(license_key: str) -> Tuple[dict, dict, bytes]:
    """
    Parse a license key into its components.

    License keys are structured as: header.payload.signature
    where each part is base64url-encoded.

    Args:
        license_key: The license key string

    Returns:
        Tuple of (header_dict, payload_dict, signature_bytes)

    Raises:
        ValueError: If the license key format is invalid
    """
    parts = license_key.strip().split(".")
    if len(parts) != 3:
        raise ValueError(
            "Invalid license key format: expected 3 parts separated by dots"
        )

    try:
        header_json = decode_base64url(parts[0])
        payload_json = decode_base64url(parts[1])
        signature = decode_base64url(parts[2])

        header = json.loads(header_json)
        payload = json.loads(payload_json)

        return header, payload, signature
    except ValueError as e:
        raise ValueError(f"Invalid license key encoding: {e}") from e


def verify_signature(
    license_key: str, header: dict, signature: bytes, public_key_pem: str = None
) -> bool:
    """
    Verify the license signature using the public key.

    Args:
        license_key: The full license key string
        header: The decoded header dictionary
        signature: The raw signature bytes
        public_key_pem: Optional PEM-encoded public key (uses cached if not provided)

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Load the public key
        if public_key_pem is None:
            public_key_pem = get_public_key_pem_sync()
        if public_key_pem is None:
            logger.error("No public key available for signature verification")
            return False
        public_key = load_pem_public_key(public_key_pem.encode("utf-8"))

        # Verify it's an EC key
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            logger.error("Public key is not an EC key")
            return False

        # Get the signed data (header.payload)
        parts = license_key.split(".")
        signed_data = f"{parts[0]}.{parts[1]}".encode("utf-8")

        # Verify the signature
        try:
            public_key.verify(signature, signed_data, ec.ECDSA(hashes.SHA512()))
            return True
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False

    except Exception as e:
        logger.error("Error during signature verification: %s", e)
        return False


def validate_payload(payload: dict) -> LicensePayload:
    """
    Validate and parse the license payload.

    Supports both old format (license_id, expires_at) and new format (lic, exp).

    Args:
        payload: The decoded payload dictionary

    Returns:
        LicensePayload dataclass

    Raises:
        ValueError: If required fields are missing or invalid
    """
    # Support both old and new field names
    license_id = payload.get("lic") or payload.get("license_id")
    tier_str = payload.get("tier")
    features = payload.get("features", [])
    modules = payload.get("modules", [])

    # Check required fields
    if not license_id:
        raise ValueError("Missing required field: lic or license_id")
    if not tier_str:
        raise ValueError("Missing required field: tier")

    try:
        tier = LicenseTier(tier_str)
    except ValueError as exc:
        raise ValueError(f"Invalid tier: {tier_str}") from exc

    # Parse expiration - support Unix timestamp (exp) or ISO string (expires_at)
    try:
        if "exp" in payload:
            expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        elif "expires_at" in payload:
            expires_at = datetime.fromisoformat(
                payload["expires_at"].replace("Z", "+00:00")
            )
        else:
            raise ValueError("Missing required field: exp or expires_at")
    except (ValueError, TypeError, OSError) as e:
        raise ValueError(f"Invalid expiration date: {e}") from e

    # Parse issued at - support Unix timestamp (iat) or ISO string (issued_at)
    try:
        if "iat" in payload:
            issued_at = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        elif "issued_at" in payload:
            issued_at = datetime.fromisoformat(
                payload["issued_at"].replace("Z", "+00:00")
            )
        else:
            issued_at = datetime.now(timezone.utc)  # Default to now if not provided
    except (ValueError, TypeError, OSError) as e:
        raise ValueError(f"Invalid issue date: {e}") from e

    return LicensePayload(
        license_id=license_id,
        tier=tier,
        features=features,
        modules=modules,
        expires_at=expires_at,
        issued_at=issued_at,
        offline_days=payload.get("offline_days", 30),
        customer_id=payload.get("cust") or payload.get("customer_id"),
        customer_name=payload.get("org") or payload.get("customer_name"),
        parent_hosts=payload.get("parent_hosts"),
        child_hosts=payload.get("child_hosts"),
        grace_seconds=payload.get("grace"),
        revocation_check_url=payload.get("rev_check"),
        revocation_nonce=payload.get("rev_nonce"),
    )


def check_expiration(expires_at: datetime) -> Tuple[bool, Optional[str]]:
    """
    Check if the license has expired.

    Args:
        expires_at: The license expiration datetime

    Returns:
        Tuple of (is_valid, warning_message)
        is_valid is False if past grace period
        warning is set if within grace period
    """
    now = datetime.now(timezone.utc)
    expires_utc = (
        expires_at.replace(tzinfo=timezone.utc)
        if expires_at.tzinfo is None
        else expires_at
    )

    if now < expires_utc:
        # Not expired
        days_remaining = (expires_utc - now).days
        if days_remaining <= 30:
            return True, f"License expires in {days_remaining} days"
        return True, None

    # Check grace period
    days_expired = (now - expires_utc).days
    if days_expired <= EXPIRATION_GRACE_DAYS:
        return (
            True,
            f"License expired {days_expired} days ago (grace period ends in {EXPIRATION_GRACE_DAYS - days_expired} days)",
        )

    return False, None


def validate_license(license_key: str, public_key_pem: str = None) -> ValidationResult:
    """
    Validate a Pro+ license key.

    This performs local validation only:
    1. Parse the license key structure
    2. Verify the ECDSA signature
    3. Validate the payload fields
    4. Check expiration with grace period

    Args:
        license_key: The license key string
        public_key_pem: Optional PEM-encoded public key (uses cached if not provided)

    Returns:
        ValidationResult with valid flag, payload (if valid), and any errors/warnings
    """
    try:
        # Parse the license key
        header, payload_dict, signature = parse_license_key(license_key)

        # Verify algorithm in header
        if header.get("alg") != "ES512":
            return ValidationResult(
                valid=False, error=f"Unsupported algorithm: {header.get('alg')}"
            )

        # Verify signature
        if not verify_signature(license_key, header, signature, public_key_pem):
            return ValidationResult(valid=False, error="Invalid license signature")

        # Validate payload
        try:
            payload = validate_payload(payload_dict)
        except ValueError as e:
            return ValidationResult(valid=False, error=str(e))

        # Check expiration
        is_valid, warning = check_expiration(payload.expires_at)
        if not is_valid:
            return ValidationResult(
                valid=False,
                payload=payload,
                error="License has expired beyond the grace period",
            )

        logger.info(
            "License validated successfully: id=%s, tier=%s, expires=%s",
            payload.license_id,
            payload.tier.value,
            payload.expires_at.isoformat(),
        )

        return ValidationResult(valid=True, payload=payload, warning=warning)

    except ValueError as e:
        logger.warning("License validation failed: %s", e)
        return ValidationResult(valid=False, error=str(e))
    except Exception as e:
        logger.error("Unexpected error during license validation: %s", e)
        return ValidationResult(valid=False, error=f"Validation error: {e}")


def has_feature(payload: LicensePayload, feature: FeatureCode) -> bool:
    """
    Check if a license payload includes a specific feature.

    Args:
        payload: The validated license payload
        feature: The feature to check for

    Returns:
        True if the feature is included in the license
    """
    return feature.value in payload.features


def has_module(payload: LicensePayload, module: ModuleCode) -> bool:
    """
    Check if a license payload includes a specific module.

    Args:
        payload: The validated license payload
        module: The module to check for

    Returns:
        True if the module is included in the license
    """
    return module.value in payload.modules
