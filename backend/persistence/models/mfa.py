# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Multi-Factor Authentication models (Phase 10.3).

Two tables back the MFA feature:

  user_mfa_enrollment
      One row per user that has enrolled.  Stores the encrypted TOTP
      shared secret, the Argon2 hashes of the user's backup codes (so
      they can be checked but not exfiltrated), enrolled_at, and
      last_used_at for audit.  Enrollment is opt-in — absence of a row
      means the user has no second factor.

  mfa_settings
      Singleton row of admin-controlled defaults: TOTP issuer name,
      number of digits, period, backup-code count to issue at enrollment,
      whether MFA is admin-required, and the grace period (in days) for
      newly-created accounts to enrol before being locked out.

MFA is intentionally an OSS feature — every operator should be able to
enable a second factor without paying for Pro+.  The implementation
lives entirely in OSS code paths.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# Sentinel id for the singleton MfaSettings row — same upsert pattern
# used by ReportBranding.  Exactly one config row system-wide.
SINGLETON_MFA_SETTINGS_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")

# Foreign-key target for the ``user`` table's primary key — reused by
# every MFA-side row that references a user.  Centralising the literal
# means the ``user`` table can be renamed in one place if it ever needs
# to be (and SonarQube no longer complains about the duplication).
_USER_FK = "user.id"


class UserMfaEnrollment(Base):
    """Per-user MFA enrollment record.

    A row is inserted at the end of the enrollment flow (after the
    user's first TOTP code is verified) and removed when the user
    disables MFA from their profile page or when an admin force-resets
    them.
    """

    __tablename__ = "user_mfa_enrollment"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        GUID(), ForeignKey(_USER_FK, ondelete="CASCADE"), nullable=False, unique=True
    )
    # Fernet-encrypted TOTP shared secret (base32 plaintext, AES-128
    # encrypted via backend.security.mfa_crypto).  Never returned to
    # the client after enrollment.
    totp_secret_encrypted = Column(Text, nullable=False)
    # JSON list of Argon2 hashes for the unused backup codes.  Hashed
    # values are checked at /verify time; matched entries are removed
    # from the list (one-time use).  Plaintext codes are returned to
    # the user exactly once at enrollment / regeneration time.
    backup_codes_hashed = Column(JSON, nullable=False, default=list)
    # Telemetry — useful in audit logs and for the user-facing "last
    # used your TOTP at HH:MM" display in the profile.
    enrolled_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    last_used_at = Column(DateTime, nullable=True)
    last_used_method = Column(String(20), nullable=True)  # "totp" | "backup_code"

    def __repr__(self):
        return f"<UserMfaEnrollment(user_id={self.user_id})>"

    def remaining_backup_codes(self) -> int:
        """Number of unused backup codes left."""
        codes = self.backup_codes_hashed or []
        return len(codes) if isinstance(codes, list) else 0

    def to_dict(self) -> dict:
        return {
            "enrolled_at": self.enrolled_at.isoformat() if self.enrolled_at else None,
            "last_used_at": (
                self.last_used_at.isoformat() if self.last_used_at else None
            ),
            "last_used_method": self.last_used_method,
            "remaining_backup_codes": self.remaining_backup_codes(),
        }


class MfaEmailChallenge(Base):
    """Short-lived email-OTP challenge — Phase 10.3 email fallback path.

    A row is created when a user requests an email-OTP code (because
    they can't reach their authenticator app) and consumed when they
    submit the matching code at /verify.  Codes are Argon2-hashed so
    the row's plaintext is never recoverable from the DB — same pattern
    as the backup-codes list in ``UserMfaEnrollment``.

    Rows are tombstoned by setting ``consumed_at`` rather than deleted
    so a brief audit trail of when each challenge was used survives;
    a separate housekeeping job can prune expired/consumed rows on a
    schedule.

    The verify path's "is this code still valid?" check is:

        consumed_at IS NULL AND expires_at > UTC-NOW

    There is no rate-limit table — the service-layer ``request_email_otp``
    invalidates any unused challenge before issuing a new one, so a
    spammed Request endpoint at most rotates the live code rather than
    flooding the user's inbox with N codes.
    """

    __tablename__ = "mfa_email_challenge"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        GUID(),
        ForeignKey(_USER_FK, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Argon2 hash of the 6-digit OTP — never stored in plaintext.
    code_hash = Column(Text, nullable=False)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    # Hard expiration; the service sets this to created_at + 10 minutes.
    # Stored (not computed) so the verify path's check is a cheap
    # ``<`` against utcnow rather than a recomputed timedelta.
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
    # Audit only — IP address of the request origin.  String form
    # (length 45) holds an IPv6 literal.
    ip_address = Column(String(45), nullable=True)

    def __repr__(self):
        return (
            f"<MfaEmailChallenge(user_id={self.user_id}, "
            f"expires_at={self.expires_at}, consumed_at={self.consumed_at})>"
        )

    def is_live(self) -> bool:
        """True iff this challenge is still consumable.

        Compares against ``datetime.now(timezone.utc)`` — tz-naive
        columns in the DB are treated as UTC by convention across
        the rest of the persistence layer.
        """
        if self.consumed_at is not None:
            return False
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return self.expires_at > now


class MfaSettings(Base):
    """Singleton row of admin-controlled MFA defaults."""

    __tablename__ = "mfa_settings"

    id = Column(GUID(), primary_key=True, default=lambda: SINGLETON_MFA_SETTINGS_ID)
    issuer_name = Column(String(120), nullable=False, default="SysManage")
    totp_digits = Column(Integer, nullable=False, default=6)
    totp_period_seconds = Column(Integer, nullable=False, default=30)
    # 0 disables backup codes entirely; 10 is the typical default.
    backup_code_count = Column(Integer, nullable=False, default=10)
    # When ``admin_required`` is true and a user passes the grace
    # period without enrolling, the login flow returns 403 instead of
    # a session token until they enrol.
    admin_required = Column(Boolean, nullable=False, default=False)
    grace_period_days = Column(Integer, nullable=False, default=14)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by = Column(GUID(), ForeignKey(_USER_FK, ondelete="SET NULL"))

    def __repr__(self):
        return f"<MfaSettings(issuer={self.issuer_name})>"

    def to_dict(self) -> dict:
        return {
            "issuer_name": self.issuer_name,
            "totp_digits": self.totp_digits,
            "totp_period_seconds": self.totp_period_seconds,
            "backup_code_count": self.backup_code_count,
            "admin_required": self.admin_required,
            "grace_period_days": self.grace_period_days,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
