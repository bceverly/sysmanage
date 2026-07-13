"""
Advisory / errata models (Phase 14.1).

Vendor advisories (Ubuntu USN, Red Hat RHSA/RHBA/RHEA, SUSE-SU/openSUSE-SU,
Debian DSA, FreeBSD-SA) are the "patch by advisory" abstraction on top of raw CVE
+ package tracking.  Advisory data is **global reference data** — a USN is
identical for every customer — so the catalog lives ONCE in the **shared**
partition (``shared_*``), exactly like ``shared_vulnerability``.  Only the
*per-host applicability* is tenant-scoped.

Partition split (get this right — it mirrors the CVE precedent verbatim):

* **shared partition** (``shared_*`` prefix, shared alembic chain):
  - ``SharedAdvisory`` — the advisory itself.
  - ``SharedAdvisoryPackage`` — fixed-package rows (intra-shared FK to advisory).
  - ``SharedAdvisoryCve`` — advisory↔CVE links (intra-shared FKs to advisory AND
    ``shared_vulnerability`` — same partition, so real FKs are fine).
  - ``AdvisoryIngestionLog`` / ``AdvisoryRefreshSettings`` — server-global
    ingestion bookkeeping (mirrors the CVE equivalents).

* **tenant partition** (unprefixed, tenant alembic chain):
  - ``HostApplicableAdvisory`` — a host has advisory X applicable to package Y.
    ``advisory_id`` is a **soft** cross-partition reference to
    ``shared_advisory.id`` — NO ForeignKey (the two tables live in different
    partitions/engines under scale-out), matching ``host_vulnerability_finding``.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# Advisory kinds (Security / Bugfix / Enhancement) — drives the UI filter.
ADVISORY_TYPE_SECURITY = "security"
ADVISORY_TYPE_BUGFIX = "bugfix"
ADVISORY_TYPE_ENHANCEMENT = "enhancement"
ADVISORY_TYPES = (
    ADVISORY_TYPE_SECURITY,
    ADVISORY_TYPE_BUGFIX,
    ADVISORY_TYPE_ENHANCEMENT,
)

# Advisory source registry keys (see backend/vulnerability/advisory_sources.py).
ADVISORY_SOURCES = ("ubuntu", "redhat", "suse", "debian", "freebsd")


def _utcnow() -> datetime:
    """Naive-UTC now, matching the shared/CVE timestamp convention."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SharedAdvisory(Base):
    """A vendor advisory (USN / RHSA / SUSE-SU / DSA / FreeBSD-SA)."""

    __tablename__ = "shared_advisory"
    __table_args__ = (
        UniqueConstraint("source", "advisory_id", name="uq_shared_advisory_src_id"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    # Vendor advisory identifier, e.g. "USN-6700-1", "RHSA-2024:1234".
    advisory_id = Column(String(64), nullable=False, index=True)
    source = Column(String(50), nullable=False, index=True)  # ubuntu/redhat/...
    advisory_type = Column(
        String(20), nullable=False, default=ADVISORY_TYPE_SECURITY, index=True
    )  # security | bugfix | enhancement
    severity = Column(String(20), nullable=True, index=True)  # CRITICAL..LOW / None
    title = Column(String(500), nullable=True)
    summary = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    # OS releases the advisory applies to, e.g. ["ubuntu:22.04", "ubuntu:24.04"].
    affected_releases = Column(JSON, nullable=True)
    references = Column(JSON, nullable=True)  # list of URLs
    published_date = Column(DateTime, nullable=True)
    modified_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # Intra-shared relationships (both sides in the shared partition).
    packages = relationship(
        "SharedAdvisoryPackage",
        back_populates="advisory",
        cascade="all, delete-orphan",
    )
    cve_links = relationship(
        "SharedAdvisoryCve",
        back_populates="advisory",
        cascade="all, delete-orphan",
    )

    def to_dict(self, include_packages: bool = False) -> dict:
        data = {
            "id": str(self.id),
            "advisory_id": self.advisory_id,
            "source": self.source,
            "advisory_type": self.advisory_type,
            "severity": self.severity,
            "title": self.title,
            "summary": self.summary,
            "description": self.description,
            "affected_releases": self.affected_releases or [],
            "references": self.references or [],
            "cve_ids": [link.cve_id for link in (self.cve_links or [])],
            "published_date": (
                self.published_date.isoformat() if self.published_date else None
            ),
            "modified_date": (
                self.modified_date.isoformat() if self.modified_date else None
            ),
        }
        if include_packages:
            data["packages"] = [p.to_dict() for p in (self.packages or [])]
        return data

    def __repr__(self):
        return (
            f"<SharedAdvisory(advisory_id='{self.advisory_id}', "
            f"source='{self.source}', type='{self.advisory_type}')>"
        )


class SharedAdvisoryPackage(Base):
    """A package (per OS release) that an advisory fixes, with the fixed version."""

    __tablename__ = "shared_advisory_package"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    advisory_row_id = Column(
        GUID(),
        # Intra-shared FK (both tables live in the shared partition) — kept.
        ForeignKey("shared_advisory.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    package_name = Column(String(255), nullable=False, index=True)
    package_manager = Column(String(50), nullable=False, index=True)  # apt/dnf/...
    # The fixed version differs per OS release, so keep the release alongside it.
    release = Column(String(100), nullable=True, index=True)  # e.g. "ubuntu:22.04"
    fixed_version = Column(String(100), nullable=True)
    source = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    advisory = relationship("SharedAdvisory", back_populates="packages")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "package_name": self.package_name,
            "package_manager": self.package_manager,
            "release": self.release,
            "fixed_version": self.fixed_version,
        }


class SharedAdvisoryCve(Base):
    """An advisory↔CVE link (an advisory addresses one or more CVEs)."""

    __tablename__ = "shared_advisory_cve"
    __table_args__ = (
        UniqueConstraint("advisory_row_id", "cve_id", name="uq_shared_advisory_cve"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    advisory_row_id = Column(
        GUID(),
        ForeignKey("shared_advisory.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Intra-shared FK to the CVE catalog (same partition) — nullable because an
    # advisory may cite a CVE we haven't ingested a vulnerability row for yet.
    vulnerability_id = Column(
        GUID(),
        ForeignKey("shared_vulnerability.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Denormalized CVE id so the link is useful even without a vulnerability row.
    cve_id = Column(String(20), nullable=False, index=True)

    advisory = relationship("SharedAdvisory", back_populates="cve_links")

    def to_dict(self) -> dict:
        return {
            "cve_id": self.cve_id,
            "vulnerability_id": (
                str(self.vulnerability_id) if self.vulnerability_id else None
            ),
        }


class AdvisoryIngestionLog(Base):
    """Server-global advisory ingestion run bookkeeping (mirrors CVE)."""

    __tablename__ = "shared_advisory_ingestion_log"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    source = Column(String(100), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False)  # running | success | failed
    advisories_processed = Column(Integer, nullable=True)
    packages_processed = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)


class AdvisoryRefreshSettings(Base):
    """Server-global advisory refresh config (mirrors CveRefreshSettings)."""

    __tablename__ = "shared_advisory_refresh_settings"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    refresh_interval_hours = Column(Integer, nullable=False, default=24)
    enabled_sources = Column(
        JSON, nullable=False, default=lambda: ["ubuntu", "redhat", "suse", "debian"]
    )
    last_refresh_at = Column(DateTime, nullable=True)
    next_refresh_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class HostApplicableAdvisory(Base):
    """An advisory applicable to a host (tenant partition).

    ``advisory_id`` is a **soft** cross-partition reference to
    ``shared_advisory.id`` — NO ForeignKey (the shared catalog lives in a
    different partition/engine under scale-out).  Callers resolve the advisory
    via the shared session, not an ORM relationship.  Matches
    ``host_vulnerability_finding.vulnerability_id``.
    """

    __tablename__ = "host_applicable_advisory"
    __table_args__ = (
        UniqueConstraint(
            "host_id",
            "advisory_id",
            "package_name",
            name="uq_host_applicable_advisory",
        ),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    # host lives in the tenant partition too → a real intra-partition FK is fine.
    host_id = Column(
        GUID(),
        ForeignKey("host.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SOFT ref to shared_advisory.id (cross-partition) — NO ForeignKey().
    advisory_id = Column(GUID(), nullable=False, index=True)
    # Denormalized advisory fields so the tenant row is useful without a shared
    # join (list/filter without cross-engine lookups).
    advisory_identifier = Column(String(64), nullable=False, index=True)
    source = Column(String(50), nullable=True)
    advisory_type = Column(String(20), nullable=True, index=True)
    severity = Column(String(20), nullable=True, index=True)
    package_name = Column(String(255), nullable=False)
    installed_version = Column(String(100), nullable=True)
    fixed_version = Column(String(100), nullable=True)
    status = Column(
        String(20), nullable=False, default="applicable", index=True
    )  # applicable | resolved
    computed_at = Column(DateTime, nullable=False, default=_utcnow)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "host_id": str(self.host_id),
            "advisory_id": str(self.advisory_id),
            "advisory_identifier": self.advisory_identifier,
            "source": self.source,
            "advisory_type": self.advisory_type,
            "severity": self.severity,
            "package_name": self.package_name,
            "installed_version": self.installed_version,
            "fixed_version": self.fixed_version,
            "status": self.status,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
        }

    def __repr__(self):
        return (
            f"<HostApplicableAdvisory(host_id={self.host_id}, "
            f"advisory='{self.advisory_identifier}', pkg='{self.package_name}')>"
        )
