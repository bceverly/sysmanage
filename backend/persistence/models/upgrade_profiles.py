"""
Scheduled update profiles (Phase 8.2).

An ``UpgradeProfile`` is an admin-defined recipe for "what to update,
where, and when":

  - ``cron``                   5-field cron expression
  - ``security_only``          if True, only security updates apply
  - ``staggered_window_min``   non-zero values spread the rollout across
                                up to N minutes to avoid a thundering herd
  - ``tag_id``                 only hosts carrying this tag participate
                                (NULL = the entire fleet)

Each profile carries its own ``last_run`` and ``next_run`` timestamps.
The OSS scheduler is a periodic tick that selects profiles where
``next_run <= now AND enabled = True``, dispatches the update, and
recomputes ``next_run`` via ``next_run_from_cron``.  Pro+ can layer a
real APScheduler-backed runner on top of this same schema.
"""

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

# Operators reach for these for their typical "every N minutes" /
# "daily at 03:00" patterns.  We don't try to support full cron syntax
# in the OSS next-run computer; complex patterns require the Pro+
# scheduler engine.  See ``next_run_from_cron`` in
# backend/services/upgrade_scheduler.py.
DEFAULT_CRON = "0 3 * * *"  # daily at 03:00


class UpgradeProfile(Base):
    """A named, reusable, schedulable update plan."""

    __tablename__ = "upgrade_profiles"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Schedule
    cron = Column(String(200), nullable=False, default=DEFAULT_CRON)
    enabled = Column(Boolean, nullable=False, default=True)
    last_run = Column(DateTime, nullable=True)
    last_status = Column(String(40), nullable=True)  # SUCCESS / FAILURE / SKIPPED
    next_run = Column(DateTime, nullable=True)

    # What to apply
    security_only = Column(Boolean, nullable=False, default=False)
    package_managers = Column(
        Text, nullable=True
    )  # comma-separated allowlist; NULL = all
    staggered_window_min = Column(
        Integer, nullable=False, default=0
    )  # 0 = launch all hosts simultaneously

    # Where to apply
    tag_id = Column(GUID(), ForeignKey("tags.id", ondelete="SET NULL"), nullable=True)

    created_by = Column(GUID(), ForeignKey("user.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tag = relationship("Tag")

    __table_args__ = (
        Index("ix_upgrade_profiles_enabled_next_run", "enabled", "next_run"),
        Index("ix_upgrade_profiles_tag_id", "tag_id"),
    )

    def __repr__(self):
        return (
            f"<UpgradeProfile(id={self.id}, name='{self.name}', "
            f"cron='{self.cron}', enabled={self.enabled})>"
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "cron": self.cron,
            "enabled": self.enabled,
            "security_only": self.security_only,
            "package_managers": (
                self.package_managers.split(",") if self.package_managers else []
            ),
            "staggered_window_min": self.staggered_window_min,
            "tag_id": str(self.tag_id) if self.tag_id else None,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_status": self.last_status,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
