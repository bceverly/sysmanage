"""
Software management models for SysManage - packages, updates, and installations.
"""

import uuid
from datetime import datetime, timezone

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
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class CrossPlatformDateTime(TypeDecorator):  # pylint: disable=too-many-ancestors
    """
    Cross-platform DateTime type that handles timezone differences between PostgreSQL and SQLite.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(DateTime(timezone=True))
        # For SQLite, use plain DateTime without timezone
        return dialect.type_descriptor(DateTime(timezone=False))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value

        # Ensure we have a datetime object
        from datetime import datetime

        if not isinstance(value, datetime):
            return value

        if dialect.name == "sqlite":
            # For SQLite, ensure datetime is naive (no timezone)
            if hasattr(value, "tzinfo") and value.tzinfo is not None:
                # Convert timezone-aware to naive UTC datetime
                import datetime as dt

                utc_dt = value.astimezone(dt.timezone.utc)
                return utc_dt.replace(tzinfo=None)
            return value

        # For PostgreSQL, keep as-is (timezone-aware preferred)
        return value

    def process_result_value(self, value, dialect):
        """Process values retrieved from the database."""
        return value

    def process_literal_param(self, value, dialect):
        """Process literal parameters."""
        return repr(value)

    @property
    def python_type(self):
        """Return the Python type."""
        from datetime import datetime

        return datetime


class SoftwarePackage(Base):
    """
    This class holds the object mapping for the software_package table in the
    PostgreSQL database.
    """

    __tablename__ = "software_package"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    package_name = Column(String(255), nullable=False, index=True)
    package_version = Column(String(100), nullable=False)
    package_description = Column(Text, nullable=True)
    package_manager = Column(String(50), nullable=False)  # apt, yum, brew, etc.
    architecture = Column(String(50), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    vendor = Column(String(255), nullable=True)
    category = Column(String(100), nullable=True)
    license = Column(String(255), nullable=True)
    install_path = Column(String(500), nullable=True)
    install_date = Column(DateTime, nullable=True)
    is_system_package = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Relationship back to Host
    host = relationship("Host", back_populates="software_packages")

    def __repr__(self):
        return f"<SoftwarePackage(id={self.id}, package_name='{self.package_name}', version='{self.package_version}', host_id={self.host_id})>"


class PackageUpdate(Base):
    """
    This class holds the object mapping for the package_update table in the
    PostgreSQL database. It tracks available updates for installed packages.
    """

    __tablename__ = "package_update"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    package_name = Column(String(255), nullable=False, index=True)
    bundle_id = Column(
        String(255), nullable=True, index=True
    )  # Actual package ID for package managers
    current_version = Column(String(100), nullable=False)
    available_version = Column(String(100), nullable=False)
    package_manager = Column(String(50), nullable=False)
    update_type = Column(String(20), nullable=False)  # security, bugfix, enhancement
    priority = Column(String(20), nullable=True)  # low, medium, high, critical
    description = Column(Text, nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    requires_reboot = Column(Boolean, nullable=False, default=False)
    status = Column(
        String(20), nullable=False, default="available", index=True
    )  # available, updating, failed
    discovered_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Relationship back to Host
    host = relationship("Host", back_populates="package_updates")

    def __repr__(self):
        return f"<PackageUpdate(id={self.id}, package_name='{self.package_name}', current='{self.current_version}', available='{self.available_version}', host_id={self.host_id})>"


class AvailablePackage(Base):
    """
    This class holds the object mapping for the available_packages table in the
    PostgreSQL database. It stores packages available for installation from
    configured repositories on each host.
    """

    __tablename__ = "available_packages"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    package_name = Column(String(255), nullable=False, index=True)
    package_version = Column(String(100), nullable=False)
    package_description = Column(Text, nullable=True)
    package_manager = Column(String(50), nullable=False, index=True)
    os_name = Column(String(100), nullable=False, index=True)
    os_version = Column(String(100), nullable=False, index=True)
    last_updated = Column(DateTime(), nullable=False)
    created_at = Column(DateTime(), nullable=False)

    def __repr__(self):
        return f"<AvailablePackage(id={self.id}, package_name='{self.package_name}', version='{self.package_version}', os='{self.os_name} {self.os_version}')>"


class SoftwareInstallationLog(Base):
    """
    This class holds the object mapping for the software_installation_log table in the
    PostgreSQL database. Tracks package installation requests and their execution.
    """

    __tablename__ = "software_installation_log"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)

    # Installation request details
    package_name = Column(String(255), nullable=False)
    package_manager = Column(String(50), nullable=False)
    requested_version = Column(String(100), nullable=True)
    requested_by = Column(
        String(100), nullable=False
    )  # User who requested installation

    # Request tracking
    installation_id = Column(
        String(36), nullable=False, unique=True, index=True
    )  # UUID for tracking
    status = Column(
        String(20), nullable=False, server_default="pending", index=True
    )  # pending, queued, installing, completed, failed, cancelled

    # Timestamps
    requested_at = Column(DateTime, nullable=False, index=True)
    queued_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Installation results
    installed_version = Column(String(100), nullable=True)
    success = Column(Boolean, nullable=True)
    error_message = Column(Text, nullable=True)
    installation_log = Column(Text, nullable=True)  # Command output/logs

    # Metadata
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Relationships
    host = relationship("Host", back_populates="software_installation_logs")

    def __repr__(self):
        return (
            f"<SoftwareInstallationLog(id={self.id}, installation_id='{self.installation_id}', "
            f"package_name='{self.package_name}', status='{self.status}', host_id={self.host_id})>"
        )


class InstallationRequest(Base):
    """
    Primary table for tracking package installation requests.
    Each row represents one user request which may include multiple packages.
    """

    __tablename__ = "installation_requests"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)

    # Request metadata
    requested_by = Column(
        String(100), nullable=False
    )  # User who requested installation
    requested_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)

    # Status tracking
    status = Column(
        String(20), nullable=False, server_default="pending", index=True
    )  # pending, in_progress, completed, failed

    # Operation type - install or uninstall
    operation_type = Column(
        String(20), nullable=False, server_default="install", index=True
    )  # install, uninstall

    # Results
    result_log = Column(Text, nullable=True)  # Captured output from agent

    # Timestamps
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Relationships
    host = relationship("Host")
    packages = relationship(
        "InstallationPackage",
        back_populates="installation_request",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<InstallationRequest(id='{self.id}', status='{self.status}', "
            f"requested_by='{self.requested_by}', host_id={self.host_id})>"
        )


class InstallationPackage(Base):
    """
    Secondary table for tracking individual packages within an installation request.
    Many-to-one relationship with InstallationRequest.
    """

    __tablename__ = "installation_packages"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    installation_request_id = Column(
        GUID(),
        ForeignKey("installation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Package details
    package_name = Column(String(255), nullable=False)
    package_manager = Column(String(50), nullable=False)

    # Relationships
    installation_request = relationship(
        "InstallationRequest", back_populates="packages"
    )

    def __repr__(self):
        return (
            f"<InstallationPackage(id={self.id}, package_name='{self.package_name}', "
            f"installation_request_id='{self.installation_request_id}')>"
        )


class ThirdPartyRepository(Base):
    """
    This class holds the object mapping for the third_party_repository table.
    Tracks third-party repositories (PPAs, COPRs, OBS, etc.) configured on each host.
    """

    __tablename__ = "third_party_repository"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)  # Repository name
    type = Column(String(50), nullable=False)  # ppa, copr, obs, zypper, etc.
    url = Column(String(500), nullable=True)  # Repository URL
    enabled = Column(Boolean, nullable=False, default=True)  # Whether repo is enabled
    file_path = Column(String(500), nullable=True)  # Path to repo config file
    last_updated = Column(DateTime, nullable=False)  # When this record was last updated

    # Relationship back to Host
    host = relationship("Host", back_populates="third_party_repositories")

    def __repr__(self):
        return (
            f"<ThirdPartyRepository(id={self.id}, name='{self.name}', "
            f"type='{self.type}', enabled={self.enabled}, host_id={self.host_id})>"
        )


class AntivirusDefault(Base):
    """
    This class holds the object mapping for the antivirus_default table.
    Stores the default antivirus software for each operating system.
    """

    __tablename__ = "antivirus_default"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    os_name = Column(
        String(100), nullable=False, unique=True, index=True
    )  # Ubuntu, Fedora, Windows, etc.
    antivirus_package = Column(
        String(255), nullable=False
    )  # Package name (e.g., clamav, sophos-av)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    def __repr__(self):
        return f"<AntivirusDefault(id={self.id}, os_name='{self.os_name}', antivirus_package='{self.antivirus_package}')>"


class AntivirusStatus(Base):
    """
    This class holds the object mapping for the antivirus_status table.
    Stores the current antivirus software status for each host.
    """

    __tablename__ = "antivirus_status"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False, index=True
    )
    software_name = Column(String(255), nullable=True)  # Name of antivirus software
    install_path = Column(String(512), nullable=True)  # Installation path
    version = Column(String(100), nullable=True)  # Version number
    enabled = Column(Boolean, nullable=True)  # Whether antivirus is enabled
    last_updated = Column(DateTime, nullable=False)  # UTC datetime, stored as naive

    # Relationship back to Host
    host = relationship("Host", back_populates="antivirus_status")

    def __repr__(self):
        return (
            f"<AntivirusStatus(id={self.id}, host_id={self.host_id}, "
            f"software_name='{self.software_name}', enabled={self.enabled})>"
        )


class CommercialAntivirusStatus(Base):
    """
    This class holds the object mapping for the commercial_antivirus_status table.
    Stores commercial antivirus software status for hosts (e.g., Microsoft Defender, McAfee, Symantec).
    """

    __tablename__ = "commercial_antivirus_status"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Product identification
    product_name = Column(
        String(255), nullable=True
    )  # Name of commercial AV (e.g., "Microsoft Defender")
    product_version = Column(String(100), nullable=True)  # Version of the AV software

    # Core service status flags
    service_enabled = Column(Boolean, nullable=True)  # Core AV service enabled
    antispyware_enabled = Column(
        Boolean, nullable=True
    )  # Antispyware protection enabled
    antivirus_enabled = Column(Boolean, nullable=True)  # Antivirus protection enabled
    realtime_protection_enabled = Column(
        Boolean, nullable=True
    )  # Real-time protection enabled

    # Scan age (in days since last scan)
    # Using BigInteger to handle Windows Defender's 4294967295 (2^32-1) for "never scanned"
    full_scan_age = Column(BigInteger, nullable=True)  # Days since last full scan
    quick_scan_age = Column(BigInteger, nullable=True)  # Days since last quick scan

    # Scan end times (naive UTC datetime)
    full_scan_end_time = Column(
        DateTime, nullable=True
    )  # Last full scan completion time
    quick_scan_end_time = Column(
        DateTime, nullable=True
    )  # Last quick scan completion time

    # Signature/definition information - last updated (naive UTC datetime)
    signature_last_updated = Column(
        DateTime, nullable=True
    )  # When signatures were last updated
    signature_version = Column(String(100), nullable=True)  # Current signature version

    # Additional status
    tamper_protection_enabled = Column(
        Boolean, nullable=True
    )  # Tamper protection status

    # Timestamps
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    last_updated = Column(DateTime, nullable=False)  # UTC datetime, stored as naive

    # Relationship back to Host
    host = relationship("Host", back_populates="commercial_antivirus_status")

    def __repr__(self):
        return (
            f"<CommercialAntivirusStatus(id={self.id}, host_id={self.host_id}, "
            f"product_name='{self.product_name}', "
            f"antivirus_enabled={self.antivirus_enabled})>"
        )


class FirewallStatus(Base):
    """
    This class holds the object mapping for the firewall_status table.
    Stores the current firewall status and rules for each host.
    """

    __tablename__ = "firewall_status"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firewall_name = Column(
        String(255), nullable=True
    )  # Name of firewall software (pf, ufw, Windows Firewall, etc.)
    enabled = Column(
        Boolean, nullable=False, default=False
    )  # Whether firewall is enabled
    tcp_open_ports = Column(
        Text, nullable=True
    )  # JSON array of open TCP ports/ranges (legacy)
    udp_open_ports = Column(
        Text, nullable=True
    )  # JSON array of open UDP ports/ranges (legacy)
    ipv4_ports = Column(
        Text, nullable=True
    )  # JSON array of IPv4 ports with protocol tags: [{"port": "22", "protocols": ["tcp"]}]
    ipv6_ports = Column(
        Text, nullable=True
    )  # JSON array of IPv6 ports with protocol tags: [{"port": "22", "protocols": ["tcp"]}]
    last_updated = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )  # UTC datetime, stored as naive

    # Relationship back to Host
    host = relationship("Host", back_populates="firewall_status")

    def __repr__(self):
        return (
            f"<FirewallStatus(id={self.id}, host_id={self.host_id}, "
            f"firewall_name='{self.firewall_name}', enabled={self.enabled})>"
        )


class DefaultRepository(Base):
    """
    This class holds the object mapping for the default_repository table.
    Stores default third-party repositories that should be applied to new hosts
    based on their operating system and package manager.
    """

    __tablename__ = "default_repository"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    os_name = Column(String(100), nullable=False, index=True)
    package_manager = Column(String(50), nullable=False, index=True)
    repository_url = Column(String(1000), nullable=False)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    created_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    # Relationship to User
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return (
            f"<DefaultRepository(id={self.id}, os_name='{self.os_name}', "
            f"package_manager='{self.package_manager}', repository_url='{self.repository_url}')>"
        )


class EnabledPackageManager(Base):
    """
    This class holds the object mapping for the enabled_package_manager table.
    Stores additional (non-default) package managers that should be enabled on hosts
    based on their operating system. For example, enabling snap or flatpak on Ubuntu
    in addition to the default APT.
    """

    __tablename__ = "enabled_package_manager"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    os_name = Column(String(100), nullable=False, index=True)
    package_manager = Column(String(50), nullable=False, index=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    created_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    # Relationship to User
    creator = relationship("User", foreign_keys=[created_by])

    # Unique constraint on os_name + package_manager
    __table_args__ = (
        UniqueConstraint("os_name", "package_manager", name="uq_enabled_pm_os_pm"),
    )

    def __repr__(self):
        return (
            f"<EnabledPackageManager(id={self.id}, os_name='{self.os_name}', "
            f"package_manager='{self.package_manager}')>"
        )
