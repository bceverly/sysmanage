"""
Child Host models for SysManage - Virtual machine and container management.

This module provides models for managing child hosts including:
- WSL (Windows Subsystem for Linux) instances
- LXD/LXC containers
- VirtualBox VMs
- Hyper-V VMs
- VMM/vmd (OpenBSD)
- bhyve (FreeBSD)
- KVM/QEMU (Linux)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship, synonym

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class HostChild(Base):
    """
    Represents a child host relationship - a VM, container, or WSL instance
    running on a parent host.

    The child_host_id links to the hosts table once the child's agent
    has registered and been approved.
    """

    __tablename__ = "host_child"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    parent_host_id = Column(
        GUID(),
        ForeignKey("host.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    child_host_id = Column(
        GUID(),
        ForeignKey("host.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Child host identification
    child_name = Column(String(255), nullable=False)
    child_type = Column(
        String(50), nullable=False
    )  # 'wsl', 'lxd', 'virtualbox', 'hyperv', 'vmm', 'bhyve', 'kvm'

    # Alias for Cython modules that reference vm_type instead of child_type
    vm_type = synonym("child_type")

    # Distribution/OS info
    distribution = Column(String(100), nullable=True)
    distribution_version = Column(String(50), nullable=True)

    # Configuration
    install_path = Column(String(500), nullable=True)
    default_username = Column(String(100), nullable=True)
    hostname = Column(String(255), nullable=True)

    # WSL-specific: unique GUID assigned by Windows to each WSL instance
    # Used to prevent stale delete commands from affecting newly created instances
    wsl_guid = Column(String(36), nullable=True)

    # Auto-approve token: UUID sent to agent during creation, returned during registration
    # When this token is present and matches, the child host is automatically approved
    auto_approve_token = Column(String(36), nullable=True, index=True)

    # State tracking
    status = Column(
        String(50), nullable=False, default="pending"
    )  # pending, creating, installing, running, stopped, error, uninstalling
    installation_step = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    installed_at = Column(DateTime, nullable=True)

    # Relationships
    parent_host = relationship(
        "Host",
        foreign_keys=[parent_host_id],
        backref="child_hosts",
    )
    child_host = relationship(
        "Host",
        foreign_keys=[child_host_id],
    )

    def __repr__(self):
        return (
            f"<HostChild(id={self.id}, name='{self.child_name}', "
            f"type='{self.child_type}', status='{self.status}')>"
        )


class ChildHostDistribution(Base):
    """
    Represents a supported distribution/OS for child hosts.

    This table is pre-populated with known-good distributions but
    administrators can add custom entries.
    """

    __tablename__ = "child_host_distribution"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    child_type = Column(String(50), nullable=False, index=True)  # 'wsl', 'lxd', etc.
    distribution_name = Column(String(100), nullable=False)  # 'Ubuntu', 'Debian', etc.
    distribution_version = Column(String(50), nullable=False)  # '24.04', '12', etc.
    display_name = Column(String(200), nullable=False)  # 'Ubuntu 24.04 LTS (Noble)'

    # Installation details
    install_identifier = Column(
        String(200), nullable=True
    )  # WSL: 'Ubuntu-24.04', LXD: 'ubuntu:24.04'
    executable_name = Column(String(100), nullable=True)  # WSL only: 'ubuntu2404.exe'
    cloud_image_url = Column(
        String(500), nullable=True
    )  # KVM: URL to cloud image for cloud-init based provisioning
    iso_url = Column(String(500), nullable=True)  # VMM/KVM: URL to installation ISO

    # Agent installation
    agent_install_method = Column(
        String(50), nullable=True
    )  # 'apt_launchpad', 'dnf_copr', 'zypper_obs', 'manual'
    agent_install_commands = Column(Text, nullable=True)  # JSON array of commands

    # Metadata
    is_active = Column(Boolean, nullable=False, default=True)
    min_agent_version = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return (
            f"<ChildHostDistribution(id={self.id}, type='{self.child_type}', "
            f"name='{self.distribution_name}', version='{self.distribution_version}')>"
        )


class RebootOrchestration(Base):
    """
    Tracks orchestrated reboot sequences for parent hosts with running child hosts.

    When a parent host is rebooted via Pro+ orchestration, this record tracks the
    full lifecycle: shutting down children → rebooting parent → restarting children.

    Status flow:
        pending_shutdown → shutting_down → rebooting → pending_restart → restarting → completed | failed
    """

    __tablename__ = "reboot_orchestration"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    parent_host_id = Column(
        GUID(),
        ForeignKey("host.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # State machine status
    status = Column(
        String(50), nullable=False, default="pending_shutdown"
    )  # pending_shutdown, shutting_down, rebooting, pending_restart, restarting, completed, failed

    # Snapshot of running children at orchestration start (JSON array)
    # Each entry: {id, child_name, child_type, pre_reboot_status}
    child_hosts_snapshot = Column(Text, nullable=False)

    # Restart progress tracking (JSON array)
    # Each entry: {id, child_name, restart_status, error}
    child_hosts_restart_status = Column(Text, nullable=True)

    # Configuration
    shutdown_timeout_seconds = Column(Integer, nullable=False, default=120)

    # Who initiated the reboot
    initiated_by = Column(String(255), nullable=False)

    # Lifecycle timestamps
    initiated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    shutdown_completed_at = Column(DateTime, nullable=True)
    reboot_issued_at = Column(DateTime, nullable=True)
    agent_reconnected_at = Column(DateTime, nullable=True)
    restart_completed_at = Column(DateTime, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Relationships
    parent_host = relationship(
        "Host",
        foreign_keys=[parent_host_id],
    )

    def __repr__(self):
        return (
            f"<RebootOrchestration(id={self.id}, parent_host_id={self.parent_host_id}, "
            f"status='{self.status}')>"
        )
