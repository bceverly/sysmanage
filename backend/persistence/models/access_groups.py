"""
Access groups and registration keys (Phase 8.1).

Two related models that together implement scoped RBAC for host
registration and ongoing access:

    AccessGroup
        Hierarchical tree of organizational scopes (e.g., "DC East",
        "DC East / Web Tier", "DC East / Web Tier / Stage").  Has an
        optional ``parent_id`` referencing another AccessGroup; a NULL
        ``parent_id`` makes it a root group.  A user's effective scope
        is the union of every group they're directly granted plus
        every descendant of those groups.

    RegistrationKey
        A pre-shared secret an agent presents at registration time.
        Optionally tied to an ``AccessGroup`` so the host inherits
        that group's scope.  ``auto_approve=True`` lets the agent
        skip the manual approval gate (admin still receives an audit
        log entry).

The hierarchy is materialized as a self-referencing FK on
``access_groups.parent_id``.  Cycle prevention is enforced at the API
layer (see ``backend/api/access_groups.py::_check_no_cycle``); the DB
schema does NOT prevent a pathological direct admin from creating a
loop, but the migration includes the index needed to detect one
quickly via a recursive CTE.
"""

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# FK targets + ondelete clauses are referenced repeatedly across these
# tables;  pulling them into module-level constants is what SonarQube
# wants and also lets a future schema rename happen in one place.
_FK_USER_ID = "user.id"
_FK_ACCESS_GROUPS_ID = "access_groups.id"
_ON_DELETE_SET_NULL = "SET NULL"


class AccessGroup(Base):
    """A named, hierarchical scope for RBAC.

    Roots have ``parent_id IS NULL``.  Tree depth is unbounded by the
    schema; the API layer caps depth at 10 to keep recursive lookups
    bounded."""

    __tablename__ = "access_groups"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(
        GUID(),
        ForeignKey(_FK_ACCESS_GROUPS_ID, ondelete=_ON_DELETE_SET_NULL),
        nullable=True,
    )
    created_by = Column(GUID(), ForeignKey(_FK_USER_ID, ondelete=_ON_DELETE_SET_NULL))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Self-referencing relationship for hierarchy traversal.
    parent = relationship(
        "AccessGroup", remote_side="AccessGroup.id", back_populates="children"
    )
    children = relationship("AccessGroup", back_populates="parent", cascade="all")
    registration_keys = relationship("RegistrationKey", back_populates="access_group")

    __table_args__ = (
        Index("ix_access_groups_parent_id", "parent_id"),
        Index("ix_access_groups_name", "name"),
    )

    def __repr__(self):
        return f"<AccessGroup(id={self.id}, name='{self.name}', parent_id={self.parent_id})>"

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def generate_registration_key() -> str:
    """Generate a 32-byte URL-safe registration token.  Uses
    ``secrets.token_urlsafe`` so the entropy comes from the OS CSPRNG.
    Output is ~43 ASCII chars; safe to embed in URLs / agent configs."""
    return secrets.token_urlsafe(32)


class RegistrationKey(Base):
    """A pre-shared agent-registration token.

    Agents present this at registration; if it matches a non-revoked
    row, the host is enrolled into the associated ``access_group``
    (if any), and approved automatically when ``auto_approve=True``."""

    __tablename__ = "registration_keys"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)  # operator-facing label
    key = Column(
        String(128), nullable=False, unique=True, default=generate_registration_key
    )
    access_group_id = Column(
        GUID(),
        ForeignKey(_FK_ACCESS_GROUPS_ID, ondelete=_ON_DELETE_SET_NULL),
        nullable=True,
    )
    auto_approve = Column(Boolean, nullable=False, default=False)
    revoked = Column(Boolean, nullable=False, default=False)
    # max_uses unset means the key is good for an unlimited number of uses.
    max_uses = Column(Integer, nullable=True)
    use_count = Column(Integer, nullable=False, default=0)
    # expires_at unset means the key never expires.
    expires_at = Column(DateTime, nullable=True)
    created_by = Column(GUID(), ForeignKey(_FK_USER_ID, ondelete=_ON_DELETE_SET_NULL))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime, nullable=True)

    access_group = relationship("AccessGroup", back_populates="registration_keys")

    __table_args__ = (
        Index("ix_registration_keys_key", "key"),
        Index("ix_registration_keys_access_group_id", "access_group_id"),
        Index("ix_registration_keys_revoked", "revoked"),
    )

    def __repr__(self):
        return f"<RegistrationKey(id={self.id}, name='{self.name}', revoked={self.revoked})>"

    def is_usable(self, now: datetime = None) -> bool:
        """True iff this key can still be used right now.  Combines the
        revoked flag, expiry timestamp, and use-count limit."""
        if self.revoked:
            return False
        check_now = now or datetime.now(timezone.utc)
        if self.expires_at is not None:
            # Compare naive-vs-aware safely:  DB-loaded datetimes are naive
            # UTC by convention here, so strip tzinfo from check_now.
            cmp_now = check_now.replace(tzinfo=None) if check_now.tzinfo else check_now
            cmp_exp = (
                self.expires_at.replace(tzinfo=None)
                if self.expires_at.tzinfo
                else self.expires_at
            )
            if cmp_exp <= cmp_now:
                return False
        if self.max_uses is not None and self.use_count >= self.max_uses:
            return False
        return True

    def to_dict(self, *, include_secret: bool = False) -> dict:
        out = {
            "id": str(self.id),
            "name": self.name,
            "access_group_id": (
                str(self.access_group_id) if self.access_group_id else None
            ),
            "auto_approve": self.auto_approve,
            "revoked": self.revoked,
            "max_uses": self.max_uses,
            "use_count": self.use_count,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used_at": (
                self.last_used_at.isoformat() if self.last_used_at else None
            ),
        }
        if include_secret:
            # Only returned at create time — never on subsequent reads.
            out["key"] = self.key
        return out


class HostAccessGroup(Base):
    """Many-to-many: hosts ↔ access groups.  A host can belong to
    multiple groups (e.g., physical-DC scope AND application-team scope).
    The host's effective access set is the union."""

    __tablename__ = "host_access_groups"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    access_group_id = Column(
        GUID(),
        ForeignKey(_FK_ACCESS_GROUPS_ID, ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index(
            "ix_host_access_groups_host_group",
            "host_id",
            "access_group_id",
            unique=True,
        ),
    )

    def __repr__(self):
        return f"<HostAccessGroup(host_id={self.host_id}, access_group_id={self.access_group_id})>"


class UserAccessGroup(Base):
    """Many-to-many: users ↔ access groups.  A user's effective scope
    is the union of every group they're granted plus every descendant
    of those groups (computed at query time via recursive CTE)."""

    __tablename__ = "user_access_groups"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        GUID(), ForeignKey(_FK_USER_ID, ondelete="CASCADE"), nullable=False
    )
    access_group_id = Column(
        GUID(),
        ForeignKey(_FK_ACCESS_GROUPS_ID, ondelete="CASCADE"),
        nullable=False,
    )
    granted_by = Column(GUID(), ForeignKey(_FK_USER_ID, ondelete=_ON_DELETE_SET_NULL))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index(
            "ix_user_access_groups_user_group",
            "user_id",
            "access_group_id",
            unique=True,
        ),
    )

    def __repr__(self):
        return f"<UserAccessGroup(user_id={self.user_id}, access_group_id={self.access_group_id})>"
