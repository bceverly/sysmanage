# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
API-test ORM schema mirror, part C: automatic updates (ROADMAP 26.1-26.4).

SQLite-compatible, hand-written mirrors of the production models.  See
``tests/api/conftest.py`` for the full rationale and the maintenance warning.
"""

import uuid

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String

from backend.persistence.models.core import GUID
from tests.api._orm_mirror_base import TestBase


class UpgradeProfileHost(TestBase):
    __tablename__ = "upgrade_profile_host"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_id = Column(GUID(), nullable=False)
    host_id = Column(GUID(), nullable=False)


class AutoUpdateSettings(TestBase):
    __tablename__ = "auto_update_settings"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    hold_all = Column(Boolean, nullable=False, default=False, server_default="0")
    hold_reason = Column(String(1000), nullable=True)
    hold_by = Column(String(255), nullable=True)
    hold_at = Column(DateTime, nullable=True)
    retry_after_hours = Column(Integer, nullable=False, default=24)
    reboot_timeout_minutes = Column(Integer, nullable=False, default=30)
    critical_threshold = Column(
        String(8), nullable=False, default="critical", server_default="critical"
    )
    # 27.8 (q119kernelhygiene)
    cleanup_mode = Column(
        String(8), nullable=False, default="apply", server_default="apply"
    )
    updated_at = Column(DateTime, nullable=True)


class AutoUpdateRun(TestBase):
    __tablename__ = "auto_update_run"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_id = Column(GUID(), nullable=True)
    profile_name = Column(String(120), nullable=False)
    host_id = Column(GUID(), nullable=False)
    status = Column(String(16), nullable=False)
    reason = Column(String(40), nullable=True)
    triggered_by = Column(String(255), nullable=True)
    packages = Column(JSON, nullable=True)
    skipped = Column(JSON, nullable=True)
    applied_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    failures = Column(JSON, nullable=True)
    reboot_needed = Column(Boolean, nullable=False, default=False, server_default="0")
    reboot_status = Column(String(12), nullable=False, default="none")
    reboot_queued_at = Column(DateTime, nullable=True)
    reboot_back_at = Column(DateTime, nullable=True)
    command_id = Column(String(36), nullable=True)
    queued_at = Column(DateTime, nullable=False)
    release_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(255), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    rollout_id = Column(GUID(), nullable=True)
    rollout_stage = Column(Integer, nullable=True)


class UpgradeProfileRolloutStage(TestBase):
    __tablename__ = "upgrade_profile_rollout_stage"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_id = Column(GUID(), nullable=False)
    position = Column(Integer, nullable=False)
    name = Column(String(120), nullable=False)
    tag_id = Column(GUID(), nullable=True)
    soak_minutes = Column(Integer, nullable=False, default=0, server_default="0")


class AutoUpdateRollout(TestBase):
    __tablename__ = "auto_update_rollout"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_id = Column(GUID(), nullable=True)
    profile_name = Column(String(120), nullable=False)
    status = Column(String(16), nullable=False)
    stage_index = Column(Integer, nullable=False, default=0, server_default="0")
    stages = Column(JSON, nullable=True)
    triggered_by = Column(String(255), nullable=True)
    started_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    halt_reason = Column(String(40), nullable=True)
    halt_detail = Column(JSON, nullable=True)
    halted_at = Column(DateTime, nullable=True)
    ended_by = Column(String(255), nullable=True)
    end_reason = Column(String(1000), nullable=True)
