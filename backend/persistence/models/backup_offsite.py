# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
The off-site cloud copy: S3 Glacier Deep Archive (ROADMAP 27.3).

Tenant data, like backup targets.  A storage host sends its ZFS datasets
straight to the operator's S3 bucket; the server only keeps the settings,
the record of what is in the bucket, and the secrets' OpenBAO paths.

* ``backup_offsite_copy`` -- one per backup target: the bucket, region,
  prefix and settings (schedule, retention, exclusions, bandwidth).  The AWS
  CREDENTIALS are never here -- ``credentials_ref`` is their OpenBAO path.
* ``backup_offsite_key`` -- the copy's AES-256 keys, newest current; a
  rotated key is kept (``retired_at``) for as long as anything in the bucket
  needs it.  ``key_ref`` is the OpenBAO path; ``key_id`` names the key
  without revealing it (the agent's ``crypto.key_id``).
* ``backup_offsite_run`` -- every job sent: check, upload, restore.  Its id
  is the ``run_id`` the agent echoes.
* ``backup_offsite_stream`` -- one ``zfs send`` stream in the bucket (a full
  or an incremental of one dataset): its parts' keys, sizes and SHA-256s,
  the manifest's key, and when the bucket's lifecycle rule will expire it.
  Its id is the agent's stream id.  This is what a restore is planned from,
  without thawing anything.
"""

import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, Text

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class BackupOffsiteCopy(Base):
    """The off-site cloud copy of one backup target's storage host."""

    __tablename__ = "backup_offsite_copy"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    target_id = Column(GUID(), nullable=False, unique=True)
    enabled = Column(Boolean, nullable=False, default=True)
    bucket = Column(String(63), nullable=False)
    region = Column(String(32), nullable=False)
    endpoint = Column(String(255), nullable=True)
    prefix = Column(String(200), nullable=False, default="")
    storage_class = Column(String(16), nullable=False, default="DEEP_ARCHIVE")
    object_lock = Column(Boolean, nullable=False, default=True)
    # JSON: schedule, retention, exclude / include, bandwidth, part size
    settings = Column(Text, nullable=True)
    credentials_ref = Column(String(512), nullable=True)
    access_key_hint = Column(String(32), nullable=True)
    next_run_at = Column(DateTime, nullable=True, index=True)
    last_run_id = Column(GUID(), nullable=True)
    last_ok_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    # what the last check found: True / False, None = never asked or not allowed
    lock_verified = Column(Boolean, nullable=True)
    checked_at = Column(DateTime, nullable=True)
    alerted_at = Column(DateTime, nullable=True)
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=True)


class BackupOffsiteKey(Base):
    """One AES-256 key of a copy (current, or retired and still needed)."""

    __tablename__ = "backup_offsite_key"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    copy_id = Column(GUID(), nullable=False, index=True)
    key_id = Column(String(16), nullable=False, index=True)
    key_ref = Column(String(512), nullable=False)
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False)
    retired_at = Column(DateTime, nullable=True)


class BackupOffsiteRun(Base):
    """One job sent to the storage host's agent."""

    __tablename__ = "backup_offsite_run"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    copy_id = Column(GUID(), nullable=False, index=True)
    host_id = Column(GUID(), nullable=False)
    # check / upload / restore
    action = Column(String(16), nullable=False)
    # queued / running / ok / partial / failed / interrupted
    status = Column(String(16), nullable=False, default="queued", index=True)
    command_id = Column(String(64), nullable=True, index=True)
    queued_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    requested_by = Column(String(255), nullable=True)
    key_id = Column(String(16), nullable=True)
    snapshot = Column(String(64), nullable=True)
    progress = Column(Text, nullable=True)
    message = Column(Text, nullable=True)
    bytes_moved = Column(BigInteger, nullable=True)
    secrets_released_at = Column(DateTime, nullable=True)
    # a restore: the dataset it makes and the streams it receives (JSON ids)
    target_dataset = Column(String(255), nullable=True)
    streams = Column(Text, nullable=True)


class BackupOffsiteStream(Base):
    """One ``zfs send`` stream in the bucket."""

    __tablename__ = "backup_offsite_stream"

    id = Column(GUID(), primary_key=True)
    copy_id = Column(GUID(), nullable=False, index=True)
    run_id = Column(GUID(), nullable=True)
    dataset = Column(String(255), nullable=False, index=True)
    snapshot = Column(String(64), nullable=False)
    base_snapshot = Column(String(64), nullable=True)
    # full / incremental
    kind = Column(String(12), nullable=False)
    key_id = Column(String(16), nullable=False)
    storage_class = Column(String(16), nullable=False)
    retention_days = Column(Integer, nullable=False)
    parts = Column(Text, nullable=False)
    part_count = Column(Integer, nullable=False)
    bytes_stored = Column(BigInteger, nullable=False)
    stream_bytes = Column(BigInteger, nullable=True)
    manifest_key = Column(String(1024), nullable=False)
    created_at = Column(DateTime, nullable=False)
    uploaded_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
