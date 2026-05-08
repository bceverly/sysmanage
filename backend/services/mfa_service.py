"""
Multi-Factor Authentication service.

Stateless helpers for the MFA endpoints + login-flow integration:

* TOTP secret generation (random base32)
* TOTP code verification with a small drift window
* Backup-code generation + Argon2 hashing + constant-time check
* Settings lookup (singleton row, seeded by migration)

Storage rules:

* TOTP secrets are stored Fernet-encrypted via
  ``backend.security.mfa_crypto`` so a leaked DB dump alone can't be
  replayed against the authenticator app.
* Backup codes are stored Argon2-hashed; only the user ever sees the
  plaintext (returned exactly once at enrollment / regeneration time).
"""

import secrets
import string
from typing import List, Optional, Tuple

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy.orm import Session

from backend.persistence.models import (
    MfaSettings,
    SINGLETON_MFA_SETTINGS_ID,
    UserMfaEnrollment,
)
from backend.security import mfa_crypto

# Argon2 hasher for backup codes — separate instance from the password
# hasher so the parameters can drift independently if the password
# hardening profile changes.  Backup codes are 8 chars of crockford
# alphabet so brute force is hard but Argon2 doesn't need to be the
# 1-second profile passwords use.
_BACKUP_CODE_HASHER = PasswordHasher()
_BACKUP_CODE_ALPHABET = string.ascii_uppercase + string.digits  # 36 symbols
_BACKUP_CODE_LENGTH = 8

# pyotp default drift — accept a code within ±1 period (60s either way
# for the standard 30s period).  Mitigates clock skew on the user's
# device without giving an attacker too long to replay a phished code.
_TOTP_VALID_WINDOW = 1


# ---------------------------------------------------------------------
# settings (singleton row)
# ---------------------------------------------------------------------


def get_settings(db: Session) -> MfaSettings:
    """Fetch the singleton MFA settings row, falling back to defaults
    if the migration's seed insert was somehow lost.

    Returns a transient (uncommitted) row in the fallback case so the
    caller's read path doesn't need to special-case ``None``.  Admins
    persisting an update via PUT will trigger a real INSERT.
    """
    row = (
        db.query(MfaSettings)
        .filter(MfaSettings.id == SINGLETON_MFA_SETTINGS_ID)
        .first()
    )
    if row is not None:
        return row
    return MfaSettings(
        id=SINGLETON_MFA_SETTINGS_ID,
        issuer_name="SysManage",
        totp_digits=6,
        totp_period_seconds=30,
        backup_code_count=10,
        admin_required=False,
        grace_period_days=14,
    )


# ---------------------------------------------------------------------
# TOTP secret + provisioning URI
# ---------------------------------------------------------------------


def generate_totp_secret() -> str:
    """Return a fresh random base32 TOTP secret (32 chars / 160 bits)."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, account_name: str, settings: MfaSettings) -> str:
    """Build the ``otpauth://totp/...`` URI for an authenticator app.

    Encoded with the issuer's settings so the user's authenticator
    matches the server's verifier on digit count / period.
    """
    return pyotp.TOTP(
        secret,
        digits=settings.totp_digits,
        interval=settings.totp_period_seconds,
    ).provisioning_uri(name=account_name, issuer_name=settings.issuer_name)


def verify_totp(secret: str, code: str, settings: MfaSettings) -> bool:
    """Constant-time-ish TOTP verify with drift tolerance.

    pyotp's own ``verify`` does the constant-time compare internally;
    we just expose the configured drift window.
    """
    if not code or not code.strip().isdigit():
        return False
    return pyotp.TOTP(
        secret,
        digits=settings.totp_digits,
        interval=settings.totp_period_seconds,
    ).verify(code.strip(), valid_window=_TOTP_VALID_WINDOW)


# ---------------------------------------------------------------------
# Backup codes
# ---------------------------------------------------------------------


def generate_backup_codes(count: int) -> List[str]:
    """Generate ``count`` backup codes — uppercase alphanumeric, length 8.

    Format: ``XXXX-XXXX`` for readability, but the dash is stripped on
    verify so the user can paste either form.  The plaintext list is
    returned exactly once; only the Argon2 hashes are persisted.
    """
    out = []
    for _ in range(max(0, int(count))):
        raw = "".join(
            secrets.choice(_BACKUP_CODE_ALPHABET) for _ in range(_BACKUP_CODE_LENGTH)
        )
        out.append(f"{raw[:4]}-{raw[4:]}")
    return out


def hash_backup_codes(codes: List[str]) -> List[str]:
    """Hash a list of plaintext backup codes for storage."""
    return [_BACKUP_CODE_HASHER.hash(_normalize_backup_code(c)) for c in codes]


def consume_backup_code(enrollment: UserMfaEnrollment, supplied: str) -> bool:
    """Look for ``supplied`` in the enrollment's backup-code list.  On
    match: remove the matched hash from the list (one-time use) and
    return True.  Returns False on miss.

    The caller commits the session — we only mutate the ORM object.
    """
    if not supplied:
        return False
    candidate = _normalize_backup_code(supplied)
    hashes = list(enrollment.backup_codes_hashed or [])
    matched_index: Optional[int] = None
    for idx, hashed in enumerate(hashes):
        try:
            _BACKUP_CODE_HASHER.verify(hashed, candidate)
        except VerifyMismatchError:
            continue
        except (
            Exception
        ):  # pylint: disable=broad-except  # nosec B112 - skip malformed hashes; never accept on error
            continue
        matched_index = idx
        break
    if matched_index is None:
        return False
    del hashes[matched_index]
    enrollment.backup_codes_hashed = hashes
    return True


def _normalize_backup_code(code: str) -> str:
    """Strip whitespace and dashes; uppercase.  Lets users paste in
    ``"abcd-efgh"``, ``"ABCDEFGH"``, or ``" ABCD EFGH "``."""
    return "".join(code.upper().split()).replace("-", "")


# ---------------------------------------------------------------------
# enrollment lookup helpers used by login-flow + endpoints
# ---------------------------------------------------------------------


def get_enrollment(db: Session, user_id) -> Optional[UserMfaEnrollment]:
    """Return the user's MFA enrollment row, or None if not enrolled."""
    return (
        db.query(UserMfaEnrollment).filter(UserMfaEnrollment.user_id == user_id).first()
    )


def is_enrolled(db: Session, user_id) -> bool:
    return get_enrollment(db, user_id) is not None


def encrypt_secret(plaintext: str) -> str:
    """Convenience pass-through to the at-rest encryption helper."""
    return mfa_crypto.encrypt_totp_secret(plaintext)


def decrypt_secret(ciphertext: str) -> str:
    return mfa_crypto.decrypt_totp_secret(ciphertext)


def verify_user_code(db: Session, user_id, code: str) -> Tuple[bool, Optional[str]]:
    """End-to-end verify path used by the login challenge.

    Tries TOTP first; falls back to backup-code consumption if the
    TOTP miss looks like a backup-code shape.  Returns ``(ok, method)``
    where ``method`` is ``"totp"`` / ``"backup_code"`` / None.

    On match the enrollment row's ``last_used_at`` + ``last_used_method``
    are updated and the session is left dirty for the caller to commit.
    """
    enrollment = get_enrollment(db, user_id)
    if enrollment is None:
        return False, None
    settings = get_settings(db)
    secret = decrypt_secret(enrollment.totp_secret_encrypted)
    if verify_totp(secret, code, settings):
        from datetime import datetime, timezone

        enrollment.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
        enrollment.last_used_method = "totp"
        return True, "totp"
    if consume_backup_code(enrollment, code):
        from datetime import datetime, timezone

        enrollment.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
        enrollment.last_used_method = "backup_code"
        return True, "backup_code"
    return False, None
