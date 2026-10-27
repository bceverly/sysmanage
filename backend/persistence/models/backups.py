# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Fleet backup with restate (ROADMAP Phase 24, Community scope).

Tenant data, like hosts:

* ``backup_target`` -- where repositories live: the path hosts mount it at,
  the storage host (the NAS's own agent) and the path there.  Community has
  exactly one.  ``seal_mode`` says how the storage side makes each capture
  immutable (``zfs_snapshot``, ``btrfs_snapshot``) or that it does not
  (``none``) -- restate cannot enforce append-only from a host a root
  attacker controls, so the NAS must.  The ``storage_fs_*`` columns are what
  the storage host's agent last reported about the filesystem under
  ``storage_path`` (NULL until it does).
* ``backup_policy`` -- one per host in Community: how often, retention
  (``keep_last``), the check cadence, quiesce.  ``config_version`` bumps on
  every change; the ``*_acked_version`` columns record what the host and the
  storage host last confirmed, so the scheduler re-sends ``backup_configure``
  until both agree.
* ``backup_run`` -- one row per job sent: configure, capture, seal, prune,
  check, du, estimate, restore.  Its id is the ``run_id`` the agent echoes in
  ``backup_result``; ``command_id`` is the queue row that carried it.
* ``backup_snapshot`` -- the snapshots a host's repository holds, refreshed
  from capture, prune and du results; a pruned one keeps its row with
  ``gone_at`` set.
"""

import uuid

from sqlalchemy import (
    BigInteger,
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

_HOST_FK = "host.id"


class BackupTarget(Base):
    """Where a tenant's backup repositories live."""

    __tablename__ = "backup_target"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    host_mount_point = Column(String(1024), nullable=False)
    # Soft reference (no FK): a NAS host can be removed and re-registered
    # without taking the target's history with it.
    storage_host_id = Column(GUID(), nullable=True, index=True)
    storage_path = Column(String(1024), nullable=True)
    max_concurrent = Column(Integer, nullable=False, default=2)
    seal_mode = Column(String(16), nullable=False, default="none")
    zfs_dataset = Column(String(255), nullable=True)
    # btrfs seal: read-only snapshots of storage_path (the subvolume) go here.
    btrfs_snapshot_dir = Column(String(1024), nullable=True)
    # The storage host's backup account exports map hosts to (None = restate).
    service_account = Column(String(32), nullable=True)
    # Days the storage host keeps its seal snapshots (q60); NULL = 14.
    seal_keep_days = Column(Integer, nullable=True)
    # How often backup_engine rotates each encrypted policy's key on its own
    # (q66, Pro+ 24.6 S5); NULL = 365 days, 0 = never.
    key_rotation_days = Column(Integer, nullable=True)
    # When the storage path counts as filling up (q60); NULL = 85 / 95.
    space_low_percent = Column(Integer, nullable=True)
    space_critical_percent = Column(Integer, nullable=True)
    # GB of restate write cache per host before it is flagged (q60); NULL = 20.
    cache_budget_gb = Column(Integer, nullable=True)
    storage_fs_type = Column(String(64), nullable=True)
    storage_fs_mount = Column(String(1024), nullable=True)
    storage_fs_checked_at = Column(DateTime, nullable=True)
    storage_is_btrfs_subvolume = Column(Boolean, nullable=True)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False)


class BackupPolicy(Base):
    """One host's backup schedule and retention."""

    __tablename__ = "backup_policy"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(),
        ForeignKey(_HOST_FK, ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    target_id = Column(
        GUID(), ForeignKey("backup_target.id", ondelete="CASCADE"), nullable=False
    )
    enabled = Column(Boolean, nullable=False, default=True)
    interval_hours = Column(Integer, nullable=False, default=24)
    window_start_hour = Column(Integer, nullable=True)  # UTC, 0-23
    keep_last = Column(Integer, nullable=False, default=14)
    check_interval_days = Column(Integer, nullable=False, default=7)
    quiesce = Column(Boolean, nullable=False, default=False)
    quiesce_with = Column(Text, nullable=True)  # JSON list of hook names
    # JSON lists of restate path patterns: kept although the built-in rules
    # leave them out / left out.  The agent writes them as a rules file.
    keep_paths = Column(Text, nullable=True)
    skip_paths = Column(Text, nullable=True)
    # A bulk "Back up now" waiting for a free slot under the target's cap.
    capture_requested_at = Column(DateTime, nullable=True)
    # The storage host's latest audit of this host's repository (JSON list of
    # {code, level, params}): NFS baseline, own export, append-only layout.
    storage_audit = Column(Text, nullable=True)
    storage_audit_at = Column(DateTime, nullable=True)
    # The host's address as last sent to the storage host (q56): a change
    # re-sends the storage side's job files and re-prepares its export.
    storage_client_address = Column(String(64), nullable=True)
    # Where the host mounts its repository over NFSv4, as the storage host
    # reported it (q57); sent to the host, which mounts it per job.
    storage_nfs_path = Column(String(1024), nullable=True)
    # The storage host's restate has ``protect`` (2.1.0.1+) and its job is
    # installed (q59): capture -> protect -> seal -> prune.
    storage_protects = Column(Boolean, nullable=False, default=False)
    # Quiesce hooks the host's restate reports present (JSON list, q59).
    available_hooks = Column(Text, nullable=True)
    # What the host's restate offers: list / status / cache (JSON, q60).
    host_abilities = Column(Text, nullable=True)
    estimate_bytes = Column(BigInteger, nullable=True)
    # The estimate's largest directories, JSON [{path, bytes}] (24.8).
    estimate_dirs = Column(Text, nullable=True)
    # Encryption (Pro+ backup_engine, 24.6).  The repository directory under
    # the target, when it is not the default ``<fqdn>-<short id>`` -- an
    # encrypted repository is a NEW one (restate cannot convert in place);
    # the one before it stays read-only and restorable.  Only the public key
    # and fingerprint are here; the secret key is in OpenBAO
    # (``encrypt_key_ref``).  Community never sets any of them.
    repository_dir = Column(String(255), nullable=True)
    previous_repository_dir = Column(String(255), nullable=True)
    previous_nfs_path = Column(String(1024), nullable=True)
    encrypt_public_key = Column(Text, nullable=True)
    encrypt_fingerprint = Column(String(64), nullable=True)
    encrypt_key_ref = Column(String(1024), nullable=True)
    encrypted_at = Column(DateTime, nullable=True)
    # When the current key was made by a rotation (q66); every key the policy
    # has held is a BackupPolicyKey row.
    encrypt_rotated_at = Column(DateTime, nullable=True)
    repository_bytes = Column(BigInteger, nullable=True)
    config_version = Column(Integer, nullable=False, default=1)
    host_acked_version = Column(Integer, nullable=False, default=0)
    storage_acked_version = Column(Integer, nullable=False, default=0)
    restate_version = Column(String(64), nullable=True)
    storage_restate_version = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False)


class BackupRun(Base):
    """One backup job sent to a host or to the storage host."""

    __tablename__ = "backup_run"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    policy_id = Column(
        GUID(),
        ForeignKey("backup_policy.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Where it runs: the backed-up host, or the storage host.
    host_id = Column(
        GUID(), ForeignKey(_HOST_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    action = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="queued", index=True)
    exit_code = Column(Integer, nullable=True)
    queued_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    # When the agent fetched this run's decryption keys (Pro+, 24.6 S4): a
    # run's keys are released once, and never stored anywhere on the server.
    key_released_at = Column(DateTime, nullable=True)
    result = Column(Text, nullable=True)  # restate's result JSON, as sent
    snapshot = Column(String(255), nullable=True)
    progress = Column(Text, nullable=True)  # the latest progress line (JSON)
    message = Column(String(1000), nullable=True)
    restate_version = Column(String(64), nullable=True)
    requested_by = Column(String(255), nullable=True)
    command_id = Column(String(64), nullable=True, index=True)
    parameters = Column(Text, nullable=True)  # JSON: what was asked
    # "Clear" on the job list hides a finished run; it is not deleted (the
    # scheduler and the status read history; the audit log keeps it).
    dismissed_at = Column(DateTime, nullable=True)


class BackupSnapshot(Base):
    """A snapshot in one host's repository."""

    __tablename__ = "backup_snapshot"
    __table_args__ = (
        UniqueConstraint("policy_id", "name", name="uq_backup_snapshot_name"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    policy_id = Column(
        GUID(),
        ForeignKey("backup_policy.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    host_id = Column(
        GUID(), ForeignKey(_HOST_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    # Which of the policy's repositories holds it (NULL = the default one);
    # after encryption starts a new repository the old snapshots stay.
    repository_dir = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=True)
    bytes = Column(BigInteger, nullable=True)
    new_bytes = Column(BigInteger, nullable=True)
    unique_bytes = Column(BigInteger, nullable=True)
    files = Column(BigInteger, nullable=True)
    signed = Column(Boolean, nullable=False, default=False)
    seen_at = Column(DateTime, nullable=False)
    gone_at = Column(DateTime, nullable=True)


class BackupPolicyKey(Base):
    """One encryption key a policy has held (q66, Pro+ backup_engine 24.6
    S5).  Rotation makes a new, independent key pair; new captures use only
    the newest, and a restore is given every key not yet retired, since a
    capture after a rotation reuses packs written before it.  Only the
    fingerprint and the OpenBAO reference of the secret key are here."""

    __tablename__ = "backup_policy_key"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    policy_id = Column(
        GUID(),
        ForeignKey("backup_policy.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fingerprint = Column(String(64), nullable=False)
    # The encryption subkey's 16-hex key id, as restate's keyless ``du``
    # report names the key a file is sealed to.
    subkey_id = Column(String(16), nullable=True)
    key_ref = Column(String(1024), nullable=False)
    created_at = Column(DateTime, nullable=False)
    replaced_at = Column(DateTime, nullable=True)
    retired_at = Column(DateTime, nullable=True)


class BackupEquip(Base):
    """The last "Equip for backup" of a host: its agent installing restate
    (Ubuntu's PPA, FreeBSD's release package).  ``status`` is running, ok or
    failed; ``reason`` the agent's code on failure (unsupported, no_release,
    download_failed, checksum_mismatch, install_failed), ``detail`` the tail
    of the tool's output."""

    __tablename__ = "backup_equip"

    host_id = Column(GUID(), ForeignKey(_HOST_FK, ondelete="CASCADE"), primary_key=True)
    status = Column(String(16), nullable=False)
    reason = Column(String(32), nullable=True)
    detail = Column(Text, nullable=True)
    installed = Column(String(32), nullable=True)
    command_id = Column(String(36), nullable=True, index=True)
    requested_by = Column(String(255), nullable=True)
    requested_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
