"""
Package compliance profiles (Phase 8.3).

Distinct from the existing ``ComplianceProfile`` (CIS/STIG security
benchmarks).  This is OS-package-level policy: which packages MUST be
installed and which are FORBIDDEN, with optional version constraints.

Three new tables:

  package_profiles
      Named profile (e.g., "production-web-required").

  package_profile_constraints
      Per-profile rules.  ``constraint_type`` is ``REQUIRED`` (package
      must be installed) or ``BLOCKED`` (package must NOT be installed).
      Optional ``version_op`` + ``version`` for version constraints
      (``>=`` 1.2.3, ``=`` 2.0.0, etc.).

  host_package_compliance_status
      Per-(host, profile) latest scan result.  ``violations`` is a
      JSON list of constraint-id + reason rows so the UI can display
      what specifically failed.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# Valid values for PackageProfileConstraint.constraint_type.
CONSTRAINT_REQUIRED = "REQUIRED"
CONSTRAINT_BLOCKED = "BLOCKED"
CONSTRAINT_TYPES = (CONSTRAINT_REQUIRED, CONSTRAINT_BLOCKED)

# Valid values for PackageProfileConstraint.version_op.
VERSION_OPS = ("=", "==", ">=", "<=", ">", "<", "!=", "~=")

# Valid values for HostPackageComplianceStatus.status.
STATUS_COMPLIANT = "COMPLIANT"
STATUS_NON_COMPLIANT = "NON_COMPLIANT"
STATUS_PENDING = "PENDING"  # not yet scanned
STATUS_VALUES = (STATUS_COMPLIANT, STATUS_NON_COMPLIANT, STATUS_PENDING)


class PackageProfile(Base):
    """A named bundle of package-compliance rules."""

    __tablename__ = "package_profiles"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(GUID(), ForeignKey("user.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    constraints = relationship(
        "PackageProfileConstraint",
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    statuses = relationship(
        "HostPackageComplianceStatus",
        back_populates="profile",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<PackageProfile(id={self.id}, name='{self.name}')>"

    def to_dict(self, *, include_constraints: bool = False) -> dict:
        out = {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_constraints:
            out["constraints"] = [c.to_dict() for c in self.constraints]
        return out


class PackageProfileConstraint(Base):
    """One rule inside a PackageProfile."""

    __tablename__ = "package_profile_constraints"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_id = Column(
        GUID(),
        ForeignKey("package_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    package_name = Column(String(255), nullable=False)
    package_manager = Column(String(60), nullable=True)  # NULL = any manager
    constraint_type = Column(String(20), nullable=False, default=CONSTRAINT_REQUIRED)
    version_op = Column(String(4), nullable=True)  # NULL = any version
    version = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    profile = relationship("PackageProfile", back_populates="constraints")

    __table_args__ = (
        Index(
            "ix_package_profile_constraints_profile_id",
            "profile_id",
        ),
        Index(
            "ix_package_profile_constraints_package_name",
            "package_name",
        ),
    )

    def __repr__(self):
        return (
            f"<PackageProfileConstraint(profile_id={self.profile_id}, "
            f"{self.constraint_type} {self.package_name} "
            f"{self.version_op or ''}{self.version or ''})>"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "profile_id": str(self.profile_id),
            "package_name": self.package_name,
            "package_manager": self.package_manager,
            "constraint_type": self.constraint_type,
            "version_op": self.version_op,
            "version": self.version,
        }


class HostPackageComplianceStatus(Base):
    """Latest scan result for one (host, profile) pair."""

    __tablename__ = "host_package_compliance_status"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    profile_id = Column(
        GUID(),
        ForeignKey("package_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(String(20), nullable=False, default=STATUS_PENDING)
    violations = Column(JSON, nullable=True)  # list of {constraint_id, reason}
    last_scan_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    profile = relationship("PackageProfile", back_populates="statuses")

    __table_args__ = (
        Index(
            "ix_host_package_compliance_host_profile",
            "host_id",
            "profile_id",
            unique=True,
        ),
        Index("ix_host_package_compliance_status", "status"),
    )

    def __repr__(self):
        return (
            f"<HostPackageComplianceStatus(host_id={self.host_id}, "
            f"profile_id={self.profile_id}, status={self.status})>"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "host_id": str(self.host_id),
            "profile_id": str(self.profile_id),
            "status": self.status,
            "violations": self.violations or [],
            "last_scan_at": (
                self.last_scan_at.isoformat() if self.last_scan_at else None
            ),
        }
