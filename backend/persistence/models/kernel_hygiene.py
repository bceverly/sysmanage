# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Package and kernel hygiene (ROADMAP 27.8).  Tenant data, like hosts.

* ``host_kernel_boot`` -- one row per boot the agent reported: when the
  host booted and which kernel it ran.  A kernel is PROVEN once a boot on it
  stayed up and checked in for ``kernel_boots.PROVEN_AFTER``; installed is
  never known good.  The old-kernel cleanup never removes the newest proven
  kernel, so a host that reboots into a new kernel keeps the one it last
  booted successfully until the new one has proven itself (Bryan,
  2026-11-27: Livepatch may be what keeps the old one safe).
* ``package_cleanup_run`` -- every cleanup asked of a host: a plan (what
  would be removed, and each kernel kept and why) or an apply (exactly the
  approved list).  Its id is the ``run_id`` the agent echoes.
"""

import uuid

from sqlalchemy import JSON, Column, DateTime, String, Text, UniqueConstraint

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class HostKernelBoot(Base):
    """One boot of a host, and the kernel it ran."""

    __tablename__ = "host_kernel_boot"
    __table_args__ = (
        UniqueConstraint("host_id", "boot_time", name="uq_host_kernel_boot"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), nullable=False, index=True)
    boot_time = Column(DateTime, nullable=False)
    kernel_release = Column(String(128), nullable=False)
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    proven_at = Column(DateTime, nullable=True)


class PackageCleanupRun(Base):
    """One plan or apply of the package and kernel cleanup on one host."""

    __tablename__ = "package_cleanup_run"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), nullable=False, index=True)
    mode = Column(String(8), nullable=False)  # plan | apply
    # queued, planned, done, refused, failed, unsupported, boot_path_broken
    status = Column(String(20), nullable=False, index=True)
    trigger = Column(
        String(16), nullable=False, default="manual"
    )  # manual | auto_update
    requested_by = Column(String(255), nullable=True)
    protected = Column(JSON, nullable=True)  # [{release, reason}]
    approved = Column(JSON, nullable=True)  # package names (apply)
    packages = Column(JSON, nullable=True)  # [{name, kernel, reason}]
    kept = Column(JSON, nullable=True)  # [{name, kernel, reason}]
    running_kernel = Column(String(128), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
