# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Automatic update policies (ROADMAP 26.1, Enterprise).

An ``UpgradeProfile`` with ``auto_apply`` on is a policy; the server's
driver (``backend/services/auto_update_runner.py``) runs it on its cron.

  - ``UpgradeProfileHost``  the hosts a policy lists by name (its scope when
                            any are listed; else its tag; else every host)
  - ``AutoUpdateSettings``  the tenant's one row: the hold on every policy at
                            once, how long a failed host waits before it is
                            tried again, how long a reboot may take
  - ``AutoUpdateRun``       one policy firing on one host: what it planned,
                            what it applied, what it left out and why, and
                            the reboot that followed

All tenant data (tenant alembic chain q94autoupdate).
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
    UniqueConstraint,
    false,
)

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

HOST_ID = "host.id"


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value):
    return value.isoformat() if value else None


class UpgradeProfileHost(Base):
    """A host a policy lists by name."""

    __tablename__ = "upgrade_profile_host"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_id = Column(
        GUID(),
        ForeignKey("upgrade_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    host_id = Column(
        GUID(), ForeignKey(HOST_ID, ondelete="CASCADE"), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("profile_id", "host_id", name="uq_upgrade_profile_host"),
    )


class AutoUpdateSettings(Base):
    """The tenant's automatic-update switches (one row)."""

    __tablename__ = "auto_update_settings"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    hold_all = Column(Boolean, nullable=False, default=False, server_default=false())
    hold_reason = Column(String(1000), nullable=True)
    hold_by = Column(String(255), nullable=True)
    hold_at = Column(DateTime, nullable=True)
    retry_after_hours = Column(Integer, nullable=False, default=24)
    reboot_timeout_minutes = Column(Integer, nullable=False, default=30)
    # 26.3: "critical" only, or "high" and critical (q95autoupdatetiming)
    critical_threshold = Column(
        String(8), nullable=False, default="critical", server_default="critical"
    )
    updated_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "hold_all": bool(self.hold_all),
            "hold_reason": self.hold_reason,
            "hold_by": self.hold_by,
            "hold_at": _iso(self.hold_at),
            "retry_after_hours": self.retry_after_hours,
            "reboot_timeout_minutes": self.reboot_timeout_minutes,
            "critical_threshold": self.critical_threshold or "critical",
        }


class AutoUpdateRun(Base):
    """One policy firing on one host."""

    __tablename__ = "auto_update_run"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_id = Column(
        GUID(),
        ForeignKey("upgrade_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    profile_name = Column(String(120), nullable=False)
    host_id = Column(
        GUID(), ForeignKey(HOST_ID, ondelete="CASCADE"), nullable=False, index=True
    )
    # waiting (26.2: for its maintenance window) / queued / succeeded /
    # partial / failed / nothing_to_do / skipped / timed_out
    status = Column(String(16), nullable=False, index=True)
    reason = Column(String(40), nullable=True)  # why skipped
    triggered_by = Column(String(255), nullable=True)  # None = the schedule
    packages = Column(JSON, nullable=True)  # [{package_name, package_manager, ...}]
    skipped = Column(JSON, nullable=True)  # [{package_name, package_manager, reason}]
    applied_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    failures = Column(JSON, nullable=True)  # [{package_name, package_manager, error}]
    reboot_needed = Column(Boolean, nullable=False, default=False)
    # none / not_wanted (the policy did not allow one) / next_window (26.2:
    # waiting for a window it fits in) / not_needed (rebooted meanwhile) /
    # queued / back / not_back
    reboot_status = Column(String(12), nullable=False, default="none")
    reboot_queued_at = Column(DateTime, nullable=True)
    reboot_back_at = Column(DateTime, nullable=True)
    command_id = Column(String(36), nullable=True, index=True)
    queued_at = Column(DateTime, nullable=False, default=_utcnow, index=True)
    release_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(255), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    # The rollout and fleet this run belongs to (26.4); NULL outside one.
    rollout_id = Column(GUID(), nullable=True, index=True)
    rollout_stage = Column(Integer, nullable=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "profile_id": str(self.profile_id) if self.profile_id else None,
            "profile_name": self.profile_name,
            "host_id": str(self.host_id),
            "rollout_id": str(self.rollout_id) if self.rollout_id else None,
            "rollout_stage": self.rollout_stage,
            "status": self.status,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
            "packages": self.packages or [],
            "skipped": self.skipped or [],
            "applied_count": self.applied_count,
            "failed_count": self.failed_count,
            "failures": self.failures or [],
            "reboot_needed": bool(self.reboot_needed),
            "reboot_status": self.reboot_status,
            "reboot_queued_at": _iso(self.reboot_queued_at),
            "reboot_back_at": _iso(self.reboot_back_at),
            "queued_at": _iso(self.queued_at),
            "release_at": _iso(self.release_at),
            "completed_at": _iso(self.completed_at),
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": _iso(self.acknowledged_at),
        }


class AutoUpdateRollout(Base):
    """One fleet-by-fleet rollout of a policy (26.4).

    ``stages`` is the plan as it started: ``[{"name", "tag_id",
    "soak_minutes", "host_ids", "remaining", "started_at", "finished_at",
    "status", "forced"}]`` -- each host in the first fleet that contains it,
    once.  ``stage_index`` is the fleet in progress; only one runs at a time.
    running / halted (``halt_reason``, ``halt_detail``: the hosts that
    caused it) / completed / canceled."""

    __tablename__ = "auto_update_rollout"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_id = Column(
        GUID(),
        ForeignKey("upgrade_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    profile_name = Column(String(120), nullable=False)
    status = Column(String(16), nullable=False, index=True)
    stage_index = Column(Integer, nullable=False, default=0, server_default="0")
    stages = Column(JSON, nullable=True)
    triggered_by = Column(String(255), nullable=True)  # None = the schedule
    started_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    halt_reason = Column(String(40), nullable=True)
    halt_detail = Column(JSON, nullable=True)
    halted_at = Column(DateTime, nullable=True)
    ended_by = Column(String(255), nullable=True)  # who resumed or canceled
    end_reason = Column(String(1000), nullable=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "profile_id": str(self.profile_id) if self.profile_id else None,
            "profile_name": self.profile_name,
            "status": self.status,
            "stage_index": self.stage_index,
            "stages": self.stages or [],
            "triggered_by": self.triggered_by,
            "started_at": _iso(self.started_at),
            "updated_at": _iso(self.updated_at),
            "completed_at": _iso(self.completed_at),
            "halt_reason": self.halt_reason,
            "halt_detail": self.halt_detail or {},
            "halted_at": _iso(self.halted_at),
            "ended_by": self.ended_by,
            "end_reason": self.end_reason,
        }


# Imported here so the model module stays the one place that names them.
__all__ = [
    "UpgradeProfileHost",
    "AutoUpdateSettings",
    "AutoUpdateRun",
    "AutoUpdateRollout",
]
