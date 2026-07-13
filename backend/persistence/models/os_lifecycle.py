"""
OS lifecycle / release-upgrade models (Phase 14.3).

Two concerns:

* **EOL / support-lifecycle tracking** — when does each OS release go end-of-life?
  That's **global reference data** (Ubuntu 22.04's EOL date is the same for every
  customer), so the lifecycle registry lives ONCE in the **shared** partition
  (``shared_os_lifecycle``), exactly like the CVE + advisory catalogs.  "Approaching
  EOL" per host and the fleet EOL report are *computed* by joining this registry
  against each tenant's host inventory — no per-host EOL rows are stored.

* **Release-upgrade orchestration** — an operator-driven, schedulable,
  maintenance-window-aware distro upgrade job (``do-release-upgrade`` / dnf
  system-upgrade / zypper dup / freebsd-update).  Jobs are per-host operational
  state → **tenant** partition (``release_upgrade_job``).
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

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# Distro release-upgrade methods (validated at the API / engine layer).
UPGRADE_METHOD_UBUNTU = "do-release-upgrade"
UPGRADE_METHOD_DNF = "dnf-system-upgrade"
UPGRADE_METHOD_ZYPPER = "zypper-dup"
UPGRADE_METHOD_FREEBSD = "freebsd-update"
UPGRADE_METHODS = (
    UPGRADE_METHOD_UBUNTU,
    UPGRADE_METHOD_DNF,
    UPGRADE_METHOD_ZYPPER,
    UPGRADE_METHOD_FREEBSD,
)

# Release-upgrade job lifecycle.
JOB_PENDING = "pending"
JOB_SCHEDULED = "scheduled"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
JOB_ROLLED_BACK = "rolled_back"
JOB_STATUSES = (
    JOB_PENDING,
    JOB_SCHEDULED,
    JOB_RUNNING,
    JOB_SUCCEEDED,
    JOB_FAILED,
    JOB_ROLLED_BACK,
)


def _utcnow() -> datetime:
    """Naive-UTC now, matching the shared/tenant timestamp convention."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SharedOsLifecycle(Base):
    """Support-lifecycle / EOL data for one OS release (shared partition).

    Global reference data (endoflife.date-style): identical for every tenant, so
    stored once.  Per-host "approaching EOL" is computed by joining this against
    ``host`` — no per-host rows are persisted.
    """

    __tablename__ = "shared_os_lifecycle"
    __table_args__ = (
        UniqueConstraint("os_name", "os_version", name="uq_shared_os_lifecycle"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    os_name = Column(String(100), nullable=False, index=True)  # ubuntu/debian/rhel...
    os_version = Column(String(50), nullable=False, index=True)  # "22.04", "12", "9"
    codename = Column(String(100), nullable=True)  # jammy, bookworm, ...
    release_date = Column(DateTime, nullable=True)
    support_end = Column(DateTime, nullable=True)  # active/standard support end
    eol_date = Column(DateTime, nullable=True, index=True)  # end of life
    extended_support_end = Column(DateTime, nullable=True)  # ESM / ELS
    lts = Column(Boolean, nullable=False, default=False)
    latest_release = Column(String(50), nullable=True)  # latest patch version
    upgrade_to = Column(String(50), nullable=True)  # recommended next version
    link = Column(String(500), nullable=True)  # lifecycle doc URL
    source = Column(String(50), nullable=True)  # e.g. "endoflife.date"
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "os_name": self.os_name,
            "os_version": self.os_version,
            "codename": self.codename,
            "release_date": (
                self.release_date.isoformat() if self.release_date else None
            ),
            "support_end": self.support_end.isoformat() if self.support_end else None,
            "eol_date": self.eol_date.isoformat() if self.eol_date else None,
            "extended_support_end": (
                self.extended_support_end.isoformat()
                if self.extended_support_end
                else None
            ),
            "lts": bool(self.lts),
            "latest_release": self.latest_release,
            "upgrade_to": self.upgrade_to,
            "link": self.link,
        }

    def __repr__(self):
        return (
            f"<SharedOsLifecycle(os='{self.os_name}', version='{self.os_version}', "
            f"eol={self.eol_date})>"
        )


class OsLifecycleIngestionLog(Base):
    """Server-global lifecycle-registry refresh bookkeeping (mirrors CVE/advisory)."""

    __tablename__ = "shared_os_lifecycle_ingestion_log"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    source = Column(String(100), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False)  # running | success | failed
    releases_processed = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)


class ReleaseUpgradeJob(Base):
    """An operator-driven, schedulable distro release-upgrade job (tenant partition).

    Per-host operational state.  ``scheduled_at`` makes it maintenance-window
    aware (the same store-and-forward dispatch that 14.2 gates).
    """

    __tablename__ = "release_upgrade_job"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    host_id = Column(
        GUID(),
        ForeignKey("host.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_os_name = Column(String(100), nullable=True)
    from_version = Column(String(50), nullable=True)
    to_version = Column(String(50), nullable=True)
    method = Column(
        String(50), nullable=True
    )  # do-release-upgrade / dnf / zypper / ...
    status = Column(String(20), nullable=False, default=JOB_PENDING, index=True)
    scheduled_at = Column(DateTime, nullable=True)  # maintenance-window aware
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    precheck_results = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_by = Column(GUID(), nullable=True)  # soft ref to user.id
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "host_id": str(self.host_id),
            "from_os_name": self.from_os_name,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "method": self.method,
            "status": self.status,
            "scheduled_at": (
                self.scheduled_at.isoformat() if self.scheduled_at else None
            ),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "precheck_results": self.precheck_results,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return (
            f"<ReleaseUpgradeJob(host_id={self.host_id}, "
            f"{self.from_version}->{self.to_version}, status='{self.status}')>"
        )
