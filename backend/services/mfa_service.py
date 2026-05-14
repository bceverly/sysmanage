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

import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy.orm import Session

from backend.persistence.models import (
    MfaEmailChallenge,
    MfaSettings,
    SINGLETON_MFA_SETTINGS_ID,
    UserMfaEnrollment,
)
from backend.security import mfa_crypto

logger = logging.getLogger(__name__)

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

    Tries in order:
      1. TOTP (the primary authenticator-app factor)
      2. Backup code (one of the 10 single-use codes from enrollment)
      3. Email-OTP challenge (Phase 10.3 fallback path for users who
         can't reach their authenticator app and have no backup codes
         left)

    Returns ``(ok, method)`` where ``method`` is
    ``"totp"`` / ``"backup_code"`` / ``"email_otp"`` / None.

    On match the enrollment row's ``last_used_at`` + ``last_used_method``
    are updated and the session is left dirty for the caller to commit.
    The email-OTP challenge row's ``consumed_at`` is set in the same
    transaction so a successful code can't be replayed.
    """
    enrollment = get_enrollment(db, user_id)
    if enrollment is None:
        return False, None
    settings = get_settings(db)
    secret = decrypt_secret(enrollment.totp_secret_encrypted)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if verify_totp(secret, code, settings):
        enrollment.last_used_at = now
        enrollment.last_used_method = "totp"
        return True, "totp"
    if consume_backup_code(enrollment, code):
        enrollment.last_used_at = now
        enrollment.last_used_method = "backup_code"
        return True, "backup_code"
    if _consume_email_challenge(db, user_id, code):
        enrollment.last_used_at = now
        enrollment.last_used_method = "email_otp"
        return True, "email_otp"
    return False, None


# ---------------------------------------------------------------------
# Email-OTP fallback (Phase 10.3 follow-up)
# ---------------------------------------------------------------------

# Numeric 6-digit code — same shape as the TOTP output so the user-
# facing input field can stay a single 6-digit box regardless of
# which method delivered the code.  ``secrets.randbelow`` is the
# crypto-strong path; ``zfill`` keeps leading zeros so the rendered
# code always has exactly 6 digits.
_EMAIL_OTP_DIGITS = 6
_EMAIL_OTP_LIFETIME_MINUTES = 10

# Argon2 hasher reused from backup-code path — same cost parameters
# are fine for short-lived codes since the value horizon is 10
# minutes; a separate _EMAIL_CODE_HASHER would add a parameter knob
# without a security argument behind it.
_EMAIL_CODE_HASHER = _BACKUP_CODE_HASHER


def generate_email_otp_code() -> str:
    """Generate a fresh 6-digit OTP for the email-fallback flow.

    Lives in a dedicated function (vs. an inline expression in the
    request path) so tests can monkeypatch it to a known string
    without poking ``secrets``.
    """
    return str(secrets.randbelow(10**_EMAIL_OTP_DIGITS)).zfill(_EMAIL_OTP_DIGITS)


def request_email_otp(
    db: Session,
    user_id,
    user_email: str,
    *,
    ip_address: Optional[str] = None,
    email_send_fn=None,
) -> bool:
    """Issue an email-OTP challenge for ``user_id`` and dispatch it.

    Lifecycle:
      1. Invalidate any unconsumed challenges for this user (so a
         spammed Request endpoint at most rotates the live code
         rather than flooding the inbox).
      2. Generate a 6-digit code, Argon2-hash it, and persist a new
         row with ``expires_at = now + 10 minutes``.
      3. Hand the plaintext code to ``email_send_fn(to, subject, body)``
         for delivery.  Default injection is the OSS
         ``EmailService.send_email`` bound method so tests can
         substitute a recorder.

    Returns True iff the email send succeeded (or the email service
    is disabled — see below).  The challenge row is *always* written
    on success of step 1+2, so a False return means a live challenge
    exists in the DB but the user never received it; the verify path
    will still accept the code if the user has it via another channel.

    The caller is responsible for committing the session.
    """
    # 1. Tombstone any live challenge for this user.  ``mark all
    # outstanding as consumed`` is simpler than DELETE because it
    # preserves the audit row.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    live_challenges = (
        db.query(MfaEmailChallenge)
        .filter(
            MfaEmailChallenge.user_id == user_id,
            MfaEmailChallenge.consumed_at.is_(None),
            MfaEmailChallenge.expires_at > now,
        )
        .all()
    )
    for challenge in live_challenges:
        challenge.consumed_at = now

    # 2. Mint a new code + persist.
    code = generate_email_otp_code()
    challenge = MfaEmailChallenge(
        user_id=user_id,
        code_hash=_EMAIL_CODE_HASHER.hash(code),
        created_at=now,
        expires_at=now + timedelta(minutes=_EMAIL_OTP_LIFETIME_MINUTES),
        consumed_at=None,
        ip_address=ip_address,
    )
    db.add(challenge)
    db.flush()  # surface unique/FK errors before we trigger an email

    # 3. Hand off to the email service.  Late-binding the default
    # send_fn avoids importing EmailService at module-load time
    # (which transitively imports the smtp config; a test env without
    # SMTP wired up shouldn't fail to import this module).
    if email_send_fn is None:
        from backend.services.email_service import EmailService  # noqa: WPS433

        email_send_fn = EmailService().send_email

    subject = "Your SysManage verification code"
    body = (
        f"Your SysManage verification code is: {code}\n\n"
        f"This code expires in {_EMAIL_OTP_LIFETIME_MINUTES} minutes "
        "and can only be used once.\n\n"
        "If you did not request this code, you can ignore this email."
    )
    try:
        sent = bool(
            email_send_fn(to_addresses=[user_email], subject=subject, body=body)
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Don't surface SMTP failure to the caller as an exception —
        # the user-facing endpoint should always return a generic
        # "if your account exists we sent a code" response to avoid
        # user-enumeration leaks.  Log it for ops.
        logger.warning("MFA email send failed for user %s: %s", user_id, exc)
        sent = False
    return sent


def _consume_email_challenge(db: Session, user_id, code: str) -> bool:
    """Internal: check a candidate ``code`` against this user's live
    email-OTP challenges and consume on match.

    Public verify_user_code chains this after TOTP + backup-code
    misses.  Iterates each live challenge (there's usually only one
    after ``request_email_otp`` invalidates older ones) and Argon2-
    compares; the first match wins and the row's ``consumed_at`` is
    set so the code can't be replayed.

    Returns False on any of:
      - no live challenge for this user
      - code is empty / non-string
      - hash mismatch on every live row
    """
    if not code or not isinstance(code, str):
        return False
    candidate = code.strip()
    if not candidate:
        return False
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    live = (
        db.query(MfaEmailChallenge)
        .filter(
            MfaEmailChallenge.user_id == user_id,
            MfaEmailChallenge.consumed_at.is_(None),
            MfaEmailChallenge.expires_at > now,
        )
        .all()
    )
    for challenge in live:
        try:
            _EMAIL_CODE_HASHER.verify(challenge.code_hash, candidate)
        except VerifyMismatchError:
            continue
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("MFA email-OTP hash verify raised unexpectedly: %s", exc)
            continue
        challenge.consumed_at = now
        return True
    return False
