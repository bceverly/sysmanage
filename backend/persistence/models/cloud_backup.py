# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Cloud storage to local: iCloud Photos (ROADMAP 24.12, Community).

Tenant data, like backup policies.  The work runs on the backup target's
STORAGE HOST only -- never on a backed-up host -- with icloudpd installed and
driven by that host's agent (``cloud_backup/`` in sysmanage-agent).

* ``cloud_backup_enable`` -- the storage host's "Enable iCloud backup": the
  latest attempt (installing the pinned icloudpd, preparing the cloud root
  under the storage path, the root-only session directory), and what got
  installed.  One row per target.
* ``cloud_backup_account`` -- one iCloud account (an Apple ID and one of its
  libraries): its schedule, deletion policy and status.  The Apple ID
  PASSWORD is never here -- it lives in OpenBAO (``password_ref`` is only
  the path) and reaches the storage host for one job at a time.
* ``cloud_backup_run`` -- every job sent: enable, connect (two-factor
  sign-in), download, reconcile (the weekly full pass), libraries, remove.
  Its id is the ``run_id`` the agent echoes.  ``mfa_code`` holds the
  operator's two-factor code only until the job collects it (then NULL).
"""

import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, Text

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class CloudBackupEnable(Base):
    """The storage host's last "Enable iCloud backup" (one per target)."""

    __tablename__ = "cloud_backup_enable"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    target_id = Column(GUID(), nullable=False, index=True, unique=True)
    host_id = Column(GUID(), nullable=False)
    # running / ok / failed
    status = Column(String(16), nullable=False, default="running")
    reason = Column(String(64), nullable=True)
    detail = Column(Text, nullable=True)
    tool_version = Column(String(32), nullable=True)
    # "binary" (Linux release, checksum-checked) or "venv" (PyPI, the BSDs)
    install_method = Column(String(16), nullable=True)
    cloud_root = Column(String(1024), nullable=True)
    run_id = Column(GUID(), nullable=True)
    requested_by = Column(String(255), nullable=True)
    requested_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class CloudBackupAccount(Base):
    """One iCloud account (Apple ID + library) downloaded to local storage."""

    __tablename__ = "cloud_backup_account"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    target_id = Column(GUID(), nullable=False, index=True)
    provider = Column(String(16), nullable=False, default="icloud")
    apple_id = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)
    library = Column(String(255), nullable=False, default="PrimarySync")
    # JSON list of the libraries the account offered at its last listing.
    libraries = Column(Text, nullable=True)
    # OpenBAO path of the password; never the password.
    password_ref = Column(String(512), nullable=True)
    password_set_at = Column(DateTime, nullable=True)
    # "icloud-<8 hex>" -- its own dataset / directory under the cloud root.
    dir_name = Column(String(64), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    interval_hours = Column(Integer, nullable=False, default=24)
    window_start_hour = Column(Integer, nullable=True)
    until_found = Column(Integer, nullable=False, default=50)
    # new / needs_sign_in / ok / failed
    state = Column(String(16), nullable=False, default="new")
    state_message = Column(Text, nullable=True)
    session_created_at = Column(DateTime, nullable=True)
    session_warned_at = Column(DateTime, nullable=True)
    last_good_at = Column(DateTime, nullable=True)
    last_full_at = Column(DateTime, nullable=True)
    photos_local = Column(Integer, nullable=True)
    bytes_local = Column(BigInteger, nullable=True)
    run_requested_at = Column(DateTime, nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class CloudBackupRun(Base):
    """One job sent to the storage host's agent."""

    __tablename__ = "cloud_backup_run"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    target_id = Column(GUID(), nullable=False, index=True)
    account_id = Column(GUID(), nullable=True, index=True)
    host_id = Column(GUID(), nullable=False)
    # enable / connect / download / reconcile / libraries / remove
    action = Column(String(16), nullable=False)
    # queued / running / waiting_code / ok / failed / needs_sign_in
    status = Column(String(16), nullable=False, default="queued", index=True)
    command_id = Column(String(64), nullable=True, index=True)
    queued_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    requested_by = Column(String(255), nullable=True)
    progress = Column(Text, nullable=True)
    result = Column(Text, nullable=True)
    message = Column(Text, nullable=True)
    exit_code = Column(Integer, nullable=True)
    downloaded = Column(Integer, nullable=True)
    present = Column(Integer, nullable=True)
    failed_count = Column(Integer, nullable=True)
    bytes_downloaded = Column(BigInteger, nullable=True)
    password_released_at = Column(DateTime, nullable=True)
    code_requested_at = Column(DateTime, nullable=True)
    mfa_code = Column(String(16), nullable=True)
    code_released_at = Column(DateTime, nullable=True)
