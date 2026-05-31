"""
Repository Mirroring models (Phase 10.4).

Three tables back the OSS-server side of the Pro+ repository_mirroring_engine:

  mirror_repository
      One row per mirrored upstream.  Stores the per-package-manager
      config the engine plan-builders consume (URL, suite/components,
      cron schedule, bandwidth cap, signing-key URL, network tier,
      enabled flag) plus per-row execution state (last_sync_at,
      last_sync_status, next_sync_at).

  mirror_snapshot
      Per-snapshot record.  Created when the engine's snapshot plan
      completes; retained until the GC plan removes the on-disk dir.
      Holds the manifest (size, file count) for UI display.

  mirror_settings
      Singleton row of admin defaults: filesystem mirror_root,
      retention window, integrity-check cadence, default bandwidth
      cap, default snapshot-keep count.

The OSS schema lives here so non-Pro+ deployments don't crash on
unknown tables; the engine reads/writes via SQLAlchemy when loaded.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

SINGLETON_MIRROR_SETTINGS_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")

# Reused FK targets — extracted as constants to dedupe the literal
# strings (Sonar S1192) and centralise the cascade behaviour so a
# future change to either is a one-line edit.
_HOST_ID_FK = "host.id"
_FK_SET_NULL = "SET NULL"


class MirrorRepository(Base):
    """One mirrored upstream package repository."""

    __tablename__ = "mirror_repository"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), unique=True, nullable=False)
    package_manager = Column(String(20), nullable=False)  # apt|dnf|zypper|pkg
    upstream_url = Column(String(500), nullable=False)
    # APT-specific.
    suite = Column(String(80), nullable=True)
    components = Column(String(200), nullable=True)
    architectures = Column(String(120), nullable=True)
    # DNF-specific.
    repoid = Column(String(120), nullable=True)
    gpgkey_url = Column(String(500), nullable=True)
    # zypper-specific.
    repo_alias = Column(String(120), nullable=True)
    # pkg-specific.
    release = Column(String(80), nullable=True)
    # Common: signing key (apt) + bandwidth cap + cron + tier.
    signing_key_url = Column(String(500), nullable=True)
    bandwidth_cap_kbps = Column(Integer, nullable=False, default=0)
    sync_cron = Column(String(120), nullable=False, default="0 4 * * *")
    network_tier = Column(
        String(40), nullable=True
    )  # free-form: "us-east", "edge", etc.
    enabled = Column(Boolean, nullable=False, default=True)
    # Owner host — the agent on this host runs the engine plan; one
    # mirror per host is the typical layout but nothing prevents
    # several repos pointing at the same host.
    host_id = Column(
        GUID(), ForeignKey(_HOST_ID_FK, ondelete="CASCADE"), nullable=False
    )
    # Phase 10.4.2: each mirror hangs off a per-platform config that
    # owns the host + filesystem defaults.  Nullable for backwards
    # compat — every row is backfilled at migration time.
    platform_config_id = Column(
        GUID(),
        ForeignKey("mirror_platform_config.id", ondelete=_FK_SET_NULL),
        nullable=True,
    )
    # Phase 10.4.4 — picked from the dropdown (mirror_known_version).
    # Free-text suite/repoid/etc. on this row are still authoritative
    # for plan emission, but ``known_version_id`` lets us know which
    # catalog entry the operator selected so default-mirror matching
    # can use the catalog's match_regex instead of guessing.
    known_version_id = Column(
        GUID(),
        ForeignKey("mirror_known_version.id", ondelete=_FK_SET_NULL),
        nullable=True,
    )
    # Lazy-loaded relationship so the airgap-collector code can resolve
    # the catalog row (os_family, version_key, default_suite) when it
    # derives target metadata from a picked mirror.
    known_version = relationship("MirrorKnownVersion", lazy="joined")
    # Execution state — one (at, status, error, message_id) group per
    # action.  Each group is written by the result handler in
    # backend/services/proplus_dispatch.py::_apply_mirror_sync_status.
    # ``last_*_message_id`` is stamped at dispatch and cleared on
    # result; the UI keys off non-NULL message_id to show an
    # "in-flight, X minutes ago" indicator with a spinner.
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(40), nullable=True)
    last_sync_error = Column(Text, nullable=True)
    last_sync_message_id = Column(String(80), nullable=True)
    # Count of consecutive failed syncs.  Reset to 0 on any success;
    # incremented by the result handler on failure.  ``tick_mirrors``
    # reads it to back off and eventually auto-disable a mirror that
    # keeps failing (e.g. one too large to sync without OOMing the host)
    # rather than re-dispatching it on every cron tick.
    consecutive_sync_failures = Column(Integer, nullable=False, default=0)
    next_sync_at = Column(DateTime, nullable=True)
    last_snapshot_at = Column(DateTime, nullable=True)
    last_snapshot_status = Column(String(40), nullable=True)
    last_snapshot_error = Column(Text, nullable=True)
    last_snapshot_message_id = Column(String(80), nullable=True)
    last_restore_at = Column(DateTime, nullable=True)
    last_restore_status = Column(String(40), nullable=True)
    last_restore_error = Column(Text, nullable=True)
    last_restore_message_id = Column(String(80), nullable=True)
    last_integrity_at = Column(DateTime, nullable=True)
    last_integrity_status = Column(String(40), nullable=True)
    last_integrity_error = Column(Text, nullable=True)
    last_integrity_message_id = Column(String(80), nullable=True)
    last_gc_at = Column(DateTime, nullable=True)
    last_gc_status = Column(String(40), nullable=True)
    last_gc_error = Column(Text, nullable=True)
    last_gc_message_id = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "package_manager": self.package_manager,
            "upstream_url": self.upstream_url,
            "suite": self.suite,
            "components": self.components,
            "architectures": self.architectures,
            "repoid": self.repoid,
            "gpgkey_url": self.gpgkey_url,
            "repo_alias": self.repo_alias,
            "release": self.release,
            "signing_key_url": self.signing_key_url,
            "bandwidth_cap_kbps": self.bandwidth_cap_kbps,
            "sync_cron": self.sync_cron,
            "network_tier": self.network_tier,
            "enabled": self.enabled,
            "host_id": str(self.host_id) if self.host_id else None,
            "platform_config_id": (
                str(self.platform_config_id) if self.platform_config_id else None
            ),
            "known_version_id": (
                str(self.known_version_id) if self.known_version_id else None
            ),
            "last_sync_at": (
                self.last_sync_at.isoformat() if self.last_sync_at else None
            ),
            "last_sync_status": self.last_sync_status,
            "last_sync_error": self.last_sync_error,
            "last_sync_message_id": self.last_sync_message_id,
            "consecutive_sync_failures": self.consecutive_sync_failures or 0,
            "next_sync_at": (
                self.next_sync_at.isoformat() if self.next_sync_at else None
            ),
            "last_snapshot_at": (
                self.last_snapshot_at.isoformat() if self.last_snapshot_at else None
            ),
            "last_snapshot_status": self.last_snapshot_status,
            "last_snapshot_error": self.last_snapshot_error,
            "last_snapshot_message_id": self.last_snapshot_message_id,
            "last_restore_at": (
                self.last_restore_at.isoformat() if self.last_restore_at else None
            ),
            "last_restore_status": self.last_restore_status,
            "last_restore_error": self.last_restore_error,
            "last_restore_message_id": self.last_restore_message_id,
            "last_integrity_at": (
                self.last_integrity_at.isoformat() if self.last_integrity_at else None
            ),
            "last_integrity_status": self.last_integrity_status,
            "last_integrity_error": self.last_integrity_error,
            "last_integrity_message_id": self.last_integrity_message_id,
            "last_gc_at": (self.last_gc_at.isoformat() if self.last_gc_at else None),
            "last_gc_status": self.last_gc_status,
            "last_gc_error": self.last_gc_error,
            "last_gc_message_id": self.last_gc_message_id,
        }


class MirrorSnapshot(Base):
    """A point-in-time snapshot of a mirror tree."""

    __tablename__ = "mirror_snapshot"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    repository_id = Column(
        GUID(),
        ForeignKey("mirror_repository.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_id = Column(String(80), nullable=False)  # YYYYMMDDTHHMMSS
    taken_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    size_bytes = Column(Integer, nullable=True)
    file_count = Column(Integer, nullable=True)
    manifest = Column(JSON, nullable=True)  # optional per-file SHA256 list
    retention_until = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "repository_id": str(self.repository_id),
            "snapshot_id": self.snapshot_id,
            "taken_at": self.taken_at.isoformat() if self.taken_at else None,
            "size_bytes": self.size_bytes,
            "file_count": self.file_count,
            "retention_until": (
                self.retention_until.isoformat() if self.retention_until else None
            ),
            "notes": self.notes,
        }


class MirrorSettings(Base):
    """Singleton row of admin-controlled mirror defaults."""

    __tablename__ = "mirror_settings"

    id = Column(GUID(), primary_key=True, default=lambda: SINGLETON_MIRROR_SETTINGS_ID)
    mirror_root_path = Column(String(500), nullable=False, default="/var/mirror")
    integrity_check_cadence_hours = Column(Integer, nullable=False, default=24)
    retention_window_days = Column(Integer, nullable=False, default=30)
    default_bandwidth_cap_kbps = Column(Integer, nullable=False, default=0)
    snapshot_count_to_keep = Column(Integer, nullable=False, default=10)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by = Column(
        GUID(), ForeignKey("user.id", ondelete=_FK_SET_NULL), nullable=True
    )

    def to_dict(self) -> dict:
        return {
            "mirror_root_path": self.mirror_root_path,
            "integrity_check_cadence_hours": self.integrity_check_cadence_hours,
            "retention_window_days": self.retention_window_days,
            "default_bandwidth_cap_kbps": self.default_bandwidth_cap_kbps,
            "snapshot_count_to_keep": self.snapshot_count_to_keep,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class MirrorKnownVersion(Base):
    """Pre-populated catalog of "known good" upstream versions per PM.

    The Add Mirror dialog's version field is sourced from this table
    so operators can't fat-finger ``noblee`` and silently produce a
    broken mirror.  Future versions land via dedicated migrations
    (no auto-discovery), so the catalog is auditable in code.
    """

    __tablename__ = "mirror_known_version"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    platform = Column(String(20), nullable=False)
    version_key = Column(String(80), nullable=False)
    label = Column(String(200), nullable=False)
    os_family = Column(String(40), nullable=False)
    match_regex = Column(String(400), nullable=False)
    default_upstream_url = Column(String(500), nullable=False)
    default_suite = Column(String(80), nullable=True)
    default_repoid = Column(String(120), nullable=True)
    default_repo_alias = Column(String(120), nullable=True)
    default_release = Column(String(80), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "platform": self.platform,
            "version_key": self.version_key,
            "label": self.label,
            "os_family": self.os_family,
            "match_regex": self.match_regex,
            "default_upstream_url": self.default_upstream_url,
            "default_suite": self.default_suite,
            "default_repoid": self.default_repoid,
            "default_repo_alias": self.default_repo_alias,
            "default_release": self.default_release,
            "is_active": self.is_active,
        }


class HostDefaultMirror(Base):
    """One row per (platform, version_key, os_family) tuple that has a
    chosen default mirror.  Null ``mirror_id`` means "Cloud" — hosts
    of that family/version are reverted to upstream.
    """

    __tablename__ = "host_default_mirror"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    platform = Column(String(20), nullable=False)
    version_key = Column(String(80), nullable=False)
    os_family = Column(String(40), nullable=False)
    mirror_id = Column(
        GUID(),
        ForeignKey("mirror_repository.id", ondelete=_FK_SET_NULL),
        nullable=True,
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "platform": self.platform,
            "version_key": self.version_key,
            "os_family": self.os_family,
            "mirror_id": str(self.mirror_id) if self.mirror_id else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class MirrorPlatformConfig(Base):
    """One row per (platform, host) pair that owns a mirror tree.

    Replaces the old singleton ``MirrorSettings`` as the source of
    truth for filesystem + retention defaults — those become per-platform
    so a Linux mirror on one host and a FreeBSD mirror on another can
    have independent root paths, retention windows, etc.

    The platform vocabulary today is ``linux`` and ``freebsd``.  More
    can be added (``openbsd``, ``netbsd``, ``macos``, ``windows``)
    once their install/probe plans are written; the column type is
    just a free string so adding a new platform doesn't require an
    enum migration.
    """

    __tablename__ = "mirror_platform_config"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    platform = Column(String(20), nullable=False)  # linux | freebsd | …
    host_id = Column(
        GUID(), ForeignKey(_HOST_ID_FK, ondelete="CASCADE"), nullable=False
    )
    mirror_root_path = Column(String(500), nullable=False, default="/var/mirror")
    integrity_check_cadence_hours = Column(Integer, nullable=False, default=24)
    retention_window_days = Column(Integer, nullable=False, default=30)
    default_bandwidth_cap_kbps = Column(Integer, nullable=False, default=0)
    snapshot_count_to_keep = Column(Integer, nullable=False, default=10)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "platform": self.platform,
            "host_id": str(self.host_id) if self.host_id else None,
            "mirror_root_path": self.mirror_root_path,
            "integrity_check_cadence_hours": self.integrity_check_cadence_hours,
            "retention_window_days": self.retention_window_days,
            "default_bandwidth_cap_kbps": self.default_bandwidth_cap_kbps,
            "snapshot_count_to_keep": self.snapshot_count_to_keep,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class MirrorSetupStatus(Base):
    """Cached result of the most recent mirror-tooling probe per host.

    Populated asynchronously: the UI's "Refresh" button dispatches a
    setup_check plan via ``apply_deployment_plan``; when the agent's
    command_result lands, ``proplus_dispatch.route_proplus_command_result``
    parses the probe stdout and upserts this row.  The card polls the
    GET endpoint while ``last_check_message_id`` is non-NULL.
    """

    __tablename__ = "mirror_setup_status"

    host_id = Column(
        GUID(), ForeignKey(_HOST_ID_FK, ondelete="CASCADE"), primary_key=True
    )
    tools = Column(JSON, nullable=False, default=dict)
    platform = Column(String(40), nullable=True)
    distro = Column(String(40), nullable=True)
    last_check_at = Column(DateTime, nullable=True)
    last_check_message_id = Column(String(36), nullable=True)
    last_check_error = Column(Text, nullable=True)
    install_status = Column(String(20), nullable=False, default="idle")
    last_install_at = Column(DateTime, nullable=True)
    last_install_message_id = Column(String(36), nullable=True)
    last_install_error = Column(Text, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    REQUIRED_TOOLS_BY_PM = {
        "apt": ("apt-mirror",),
        "dnf": ("reposync", "createrepo_c"),
        "zypper": ("createrepo_c",),
        "pkg": (),  # built-in on FreeBSD
    }

    def is_ready_for(self, package_manager: str) -> bool:
        required = self.REQUIRED_TOOLS_BY_PM.get((package_manager or "").lower(), ())
        if not isinstance(self.tools, dict):
            return not required
        return all(self.tools.get(t) == "present" for t in required)

    def to_dict(self) -> dict:
        return {
            "host_id": str(self.host_id),
            "tools": self.tools or {},
            "platform": self.platform,
            "distro": self.distro,
            "last_check_at": (
                self.last_check_at.isoformat() if self.last_check_at else None
            ),
            "last_check_message_id": self.last_check_message_id,
            "last_check_error": self.last_check_error,
            "install_status": self.install_status,
            "last_install_at": (
                self.last_install_at.isoformat() if self.last_install_at else None
            ),
            "last_install_message_id": self.last_install_message_id,
            "last_install_error": self.last_install_error,
            "ready_apt": self.is_ready_for("apt"),
            "ready_dnf": self.is_ready_for("dnf"),
            "ready_zypper": self.is_ready_for("zypper"),
            "ready_pkg": self.is_ready_for("pkg"),
        }
