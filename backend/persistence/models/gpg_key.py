"""
GPG key management models (GPG Key Management — Slice 1).

Named GPG keys whose armored material lives in the OpenBAO vault (NEVER in the
database or YAML).  Each ``gpg_key`` row holds only metadata plus an
``openbao_secret_id`` reference to the vault path where the material is stored.

Keys can be assigned by name either to a whole host (``target_username`` NULL)
or to a specific user account on that host (``target_username`` set), via
``gpg_key_assignment`` rows.

Tenant-partition tables: table names are UNPREFIXED (no ``registry_``/
``shared_`` prefix), consistent with the prefix guard for the tenant chain.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import backref, relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

HOST_ID_FK = "host.id"
GPG_KEY_ID_FK = "gpg_key.id"

# key_type values
KEY_TYPE_PUBLIC = "public"
KEY_TYPE_PRIVATE = "private"
KEY_TYPE_KEYPAIR = "keypair"
KEY_TYPES = (KEY_TYPE_PUBLIC, KEY_TYPE_PRIVATE, KEY_TYPE_KEYPAIR)

# assignment status values
ASSIGNMENT_PENDING = "pending"
ASSIGNMENT_INSTALLED = "installed"
ASSIGNMENT_REMOVING = "removing"
ASSIGNMENT_REMOVED = "removed"
ASSIGNMENT_FAILED = "failed"
ASSIGNMENT_STATUSES = (
    ASSIGNMENT_PENDING,
    ASSIGNMENT_INSTALLED,
    ASSIGNMENT_REMOVING,
    ASSIGNMENT_REMOVED,
    ASSIGNMENT_FAILED,
)


def _utcnow():
    """Timezone-aware UTC now (sibling models store naive-UTC; keep aware here
    to match tenant models that use ``datetime.now(timezone.utc)`` defaults)."""
    return datetime.now(timezone.utc)


class GpgKey(Base):
    """A named GPG key.  Metadata only — armored material lives in OpenBAO."""

    __tablename__ = "gpg_key"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    fingerprint = Column(String(255), nullable=True, index=True)
    # public | private | keypair
    key_type = Column(String(20), nullable=False)
    has_private = Column(Boolean, nullable=False, default=False)
    comment = Column(Text, nullable=True)
    # Vault path/reference where the armored material is stored (NEVER the
    # material itself).
    openbao_secret_id = Column(String(500), nullable=False)
    # Soft reference to the uploading user.  NO FK: users may live in the
    # registry partition, so a cross-partition FK is not permitted.
    uploaded_by = Column(GUID(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    assignments = relationship(
        "GpgKeyAssignment",
        back_populates="gpg_key",
        passive_deletes=True,
    )

    def __repr__(self):
        return (
            f"<GpgKey(id={self.id}, name='{self.name}', "
            f"key_type='{self.key_type}', has_private={self.has_private})>"
        )


class GpgKeyAssignment(Base):
    """Assignment of a named GPG key to a host, or to a user on that host."""

    __tablename__ = "gpg_key_assignment"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    gpg_key_id = Column(
        GUID(),
        ForeignKey(GPG_KEY_ID_FK, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    host_id = Column(
        GUID(),
        ForeignKey(HOST_ID_FK, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # NULL = host-level assignment; else a specific user account on the host.
    target_username = Column(String(255), nullable=True)
    # pending | installed | removing | removed | failed
    status = Column(String(20), nullable=False, default=ASSIGNMENT_PENDING)
    # Soft reference to the assigning user (may live in the registry partition).
    assigned_by = Column(GUID(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    gpg_key = relationship("GpgKey", back_populates="assignments")
    host = relationship(
        "Host",
        backref=backref("gpg_key_assignments", passive_deletes=True),
    )

    def __repr__(self):
        return (
            f"<GpgKeyAssignment(id={self.id}, gpg_key_id={self.gpg_key_id}, "
            f"host_id={self.host_id}, target_username={self.target_username!r}, "
            f"status='{self.status}')>"
        )
