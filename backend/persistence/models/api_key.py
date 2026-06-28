"""
API key model — Phase 13.2 (API Completeness).

A long-lived, hashed credential that lets automation/CI authenticate to the
REST API *as a user*, without an interactive login or a refreshable JWT.

Security model (GitHub-PAT style):

  * The plaintext key is shown **exactly once**, at creation.  Only a SHA-256
    digest (``key_hash``) is persisted — a DB compromise never yields a usable
    key, and there is no decrypt path.  SHA-256 (not Argon2) is appropriate
    because the key carries full machine entropy, so it isn't brute-forceable.
  * ``key_prefix`` keeps a short, non-secret leading slice for display/audit
    ("which key is this?") without storing the secret.
  * Lookups are O(1) on the indexed ``key_hash`` — the presented key is hashed
    and matched directly, never scanned.

The key authenticates as ``user_id``'s identity and inherits that user's roles,
so no separate authorization model is needed.  ``tenant_id`` (soft reference to
``registry_tenant.id`` — no FK across the partition boundary) optionally pins
the key to one tenant in multi-tenant deployments; NULL means server-scoped
(the single-tenant default).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class ApiKey(Base):
    """One API key issued to a user for programmatic access."""

    __tablename__ = "api_key"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    # Owning user — the key authenticates AS this identity.  CASCADE so deleting
    # a user automatically tears down their keys.
    user_id = Column(
        GUID(),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(120), nullable=False)
    # Non-secret leading slice of the key, for identification in the UI/audit.
    key_prefix = Column(String(32), nullable=False, index=True)
    # SHA-256 hex digest of the full key (64 chars).  The secret itself is never
    # stored.  Unique + indexed so authentication is a single point lookup.
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    # Optional comma-separated scope list (NULL = full access as the owning
    # user).  Reserved for finer-grained scoping; not enforced yet.
    scopes = Column(Text, nullable=True)
    # Optional tenant pin (soft ref to registry_tenant.id; no cross-partition FK).
    tenant_id = Column(GUID(), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    def is_usable(self, now: datetime = None) -> bool:
        """True when the key may authenticate: active, not revoked, not expired."""
        if not self.is_active or self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            current = now or datetime.now(timezone.utc)
            # Compare naive-vs-aware safely: normalise both to naive UTC.
            expires = self.expires_at
            if expires.tzinfo is not None:
                expires = expires.astimezone(timezone.utc).replace(tzinfo=None)
            if current.tzinfo is not None:
                current = current.astimezone(timezone.utc).replace(tzinfo=None)
            if expires <= current:
                return False
        return True

    def to_dict(self) -> dict:
        """Serialise for API responses — NEVER includes the hash or plaintext."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "name": self.name,
            "key_prefix": self.key_prefix,
            "scopes": self.scopes,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "is_active": bool(self.is_active),
            "created_at": (self.created_at.isoformat() if self.created_at else None),
            "last_used_at": (
                self.last_used_at.isoformat() if self.last_used_at else None
            ),
            "expires_at": (self.expires_at.isoformat() if self.expires_at else None),
            "revoked_at": (self.revoked_at.isoformat() if self.revoked_at else None),
        }
