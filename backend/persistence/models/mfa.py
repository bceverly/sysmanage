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
        GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, unique=True
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
    updated_by = Column(GUID(), ForeignKey("user.id", ondelete="SET NULL"))

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
