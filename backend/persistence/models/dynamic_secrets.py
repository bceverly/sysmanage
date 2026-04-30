"""
Dynamic secret leases (Phase 8.7).

Tracks short-lived credentials issued through the Pro+
``secrets_engine`` against an OpenBAO/Vault dynamic-secrets backend
(database, ssh, etc.).

The actual secret value is NEVER persisted here — it is returned to
the operator at issue time and from then on lives only in OpenBAO
until its TTL expires.  This row is the audit + revocation hook:

  - ``vault_lease_id`` lets us call ``sys/leases/revoke`` on demand;
  - ``expires_at`` lets the UI show a countdown and lets a sweeper
    reconcile rows whose lease has expired in OpenBAO.

A row in state ``EXPIRED`` or ``REVOKED`` is informational only; it
does not constrain re-issuing.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    JSON,
    Integer,
    String,
    Text,
)

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# Lease backend kinds — mirrors OpenBAO secret-engine families.
LEASE_KIND_DATABASE = "database"
LEASE_KIND_SSH = "ssh"
# nosec B105 -- enum literal naming the lease kind, not a credential
LEASE_KIND_TOKEN = "token"  # nosec B105
LEASE_KINDS = (LEASE_KIND_DATABASE, LEASE_KIND_SSH, LEASE_KIND_TOKEN)

# Lease lifecycle states.
LEASE_ACTIVE = "ACTIVE"
LEASE_REVOKED = "REVOKED"
LEASE_EXPIRED = "EXPIRED"
LEASE_FAILED = "FAILED"
LEASE_STATUSES = (LEASE_ACTIVE, LEASE_REVOKED, LEASE_EXPIRED, LEASE_FAILED)


class DynamicSecretLease(Base):
    """One short-lived credential issued via OpenBAO."""

    __tablename__ = "dynamic_secret_lease"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    kind = Column(String(40), nullable=False, index=True)  # one of LEASE_KINDS
    backend_role = Column(String(255), nullable=False)
    # OpenBAO's lease_id — used for revoke + renew.  Nullable because we
    # may have failed the issue call (status=FAILED) without ever
    # getting a lease back.
    vault_lease_id = Column(String(500), nullable=True, index=True)
    # OpenBAO's lease_duration in seconds at issue time;  ``expires_at``
    # is computed as ``issued_at + ttl_seconds``.
    ttl_seconds = Column(Integer, nullable=True)
    issued_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    expires_at = Column(DateTime, nullable=True, index=True)
    revoked_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default=LEASE_ACTIVE, index=True)
    # Free-form metadata about the issued credential — e.g. for SSH
    # leases the issued public key fingerprint, for DB leases the
    # generated username.  NEVER stores the secret value itself.
    secret_metadata = Column(JSON, nullable=True)
    # Audit log: who asked + why (free-form note).
    issued_by = Column(GUID(), ForeignKey("user.id", ondelete="SET NULL"))
    note = Column(Text, nullable=True)

    def __repr__(self):
        return (
            f"<DynamicSecretLease(id={self.id}, kind='{self.kind}', "
            f"role='{self.backend_role}', status='{self.status}')>"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "kind": self.kind,
            "backend_role": self.backend_role,
            "vault_lease_id": self.vault_lease_id,
            "ttl_seconds": self.ttl_seconds,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "status": self.status,
            "secret_metadata": self.secret_metadata or {},
            "note": self.note,
        }
