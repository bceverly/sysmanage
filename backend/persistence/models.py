"""
This module holds the various models that are persistence backed by the
PostgreSQL database.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship

from backend.persistence.db import Base


class BearerToken(Base):
    """
    This class holds the object mapping for the bearer token table in the
    PostgreSQL database.
    """

    __tablename__ = "bearer_token"
    token = Column(String(200), primary_key=True, index=True)
    created_datetime = Column(DateTime)


class Host(Base):
    """
    This class holds the object mapping for the host table in the PostgreSQL
    database.
    """

    __tablename__ = "host"
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    active = Column(Boolean, unique=False, index=False)
    fqdn = Column(String, index=True)
    ipv4 = Column(String)
    ipv6 = Column(String)
    last_access = Column(DateTime(timezone=True))
    status = Column(String(20), nullable=False, server_default="up")
    approval_status = Column(String(20), nullable=False, server_default="pending")
    client_certificate = Column(Text, nullable=True)
    certificate_serial = Column(String(64), nullable=True)
    certificate_issued_at = Column(DateTime(timezone=True), nullable=True)
    # OS Version fields
    platform = Column(String(50), nullable=True)
    platform_release = Column(String(100), nullable=True)
    platform_version = Column(Text, nullable=True)
    machine_architecture = Column(String(50), nullable=True)  # x86_64, arm64, etc.
    processor = Column(String(100), nullable=True)
    os_details = Column(Text, nullable=True)  # JSON field for additional OS info
    os_version_updated_at = Column(DateTime(timezone=True), nullable=True)
    # Hardware inventory fields
    cpu_vendor = Column(String(100), nullable=True)
    cpu_model = Column(String(200), nullable=True)
    cpu_cores = Column(Integer, nullable=True)
    cpu_threads = Column(Integer, nullable=True)
    cpu_frequency_mhz = Column(Integer, nullable=True)
    memory_total_mb = Column(BigInteger, nullable=True)
    storage_details = Column(Text, nullable=True)  # JSON field for storage devices
    network_details = Column(Text, nullable=True)  # JSON field for network interfaces
    hardware_details = Column(
        Text, nullable=True
    )  # JSON field for additional hardware info
    hardware_updated_at = Column(DateTime(timezone=True), nullable=True)
    # Software inventory fields
    software_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships to normalized hardware tables
    storage_devices = relationship(
        "StorageDevice", back_populates="host", cascade="all, delete-orphan"
    )
    network_interfaces = relationship(
        "NetworkInterface", back_populates="host", cascade="all, delete-orphan"
    )

    # Relationships to user access tables
    user_accounts = relationship(
        "UserAccount", back_populates="host", cascade="all, delete-orphan"
    )
    user_groups = relationship(
        "UserGroup", back_populates="host", cascade="all, delete-orphan"
    )
    user_group_memberships = relationship(
        "UserGroupMembership", back_populates="host", cascade="all, delete-orphan"
    )

    # Relationship to software inventory table
    software_packages = relationship(
        "SoftwarePackage", back_populates="host", cascade="all, delete-orphan"
    )

    # Relationships to update management tables
    package_updates = relationship(
        "PackageUpdate", back_populates="host", cascade="all, delete-orphan"
    )


class User(Base):
    """
    This class holds the object mapping for the user table in the PostgreSQL
    database.
    """

    __tablename__ = "user"
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    active = Column(Boolean, unique=False, index=False)
    userid = Column(String)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    hashed_password = Column(String, unique=False, index=False)
    last_access = Column(DateTime(timezone=True))
    # Account locking fields
    is_locked = Column(Boolean, default=False, nullable=False)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_at = Column(DateTime, nullable=True)


class StorageDevice(Base):
    """
    This class holds the object mapping for the storage_devices table in the
    PostgreSQL database.
    """

    __tablename__ = "storage_devices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=True)
    device_path = Column(String(255), nullable=True)
    mount_point = Column(String(255), nullable=True)
    file_system = Column(String(100), nullable=True)
    device_type = Column(String(100), nullable=True)
    capacity_bytes = Column(BigInteger, nullable=True)
    used_bytes = Column(BigInteger, nullable=True)
    available_bytes = Column(BigInteger, nullable=True)
    is_physical = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship back to Host
    host = relationship("Host", back_populates="storage_devices")


class NetworkInterface(Base):
    """
    This class holds the object mapping for the network_interfaces table in the
    PostgreSQL database.
    """

    __tablename__ = "network_interfaces"
    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=True)
    interface_type = Column(String(100), nullable=True)
    hardware_type = Column(String(100), nullable=True)
    mac_address = Column(String(17), nullable=True)
    ipv4_address = Column(String(15), nullable=True)
    ipv6_address = Column(String(39), nullable=True)
    subnet_mask = Column(String(15), nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    speed_mbps = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship back to Host
    host = relationship("Host", back_populates="network_interfaces")


class UserAccount(Base):
    """
    This class holds the object mapping for the user_accounts table in the
    PostgreSQL database.
    """

    __tablename__ = "user_accounts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    username = Column(String(255), nullable=False)
    uid = Column(Integer, nullable=True)  # Linux/macOS user ID
    home_directory = Column(String(500), nullable=True)
    shell = Column(String(255), nullable=True)
    is_system_user = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship back to Host
    host = relationship("Host", back_populates="user_accounts")


class UserGroup(Base):
    """
    This class holds the object mapping for the user_groups table in the
    PostgreSQL database.
    """

    __tablename__ = "user_groups"
    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    group_name = Column(String(255), nullable=False)
    gid = Column(Integer, nullable=True)  # Linux/macOS group ID
    is_system_group = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship back to Host
    host = relationship("Host", back_populates="user_groups")


class UserGroupMembership(Base):
    """
    This class holds the object mapping for the user_group_memberships table in the
    PostgreSQL database. This table stores many-to-many relationships between
    users and groups.
    """

    __tablename__ = "user_group_memberships"
    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    user_account_id = Column(
        Integer, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    user_group_id = Column(
        Integer, ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationships
    host = relationship("Host", back_populates="user_group_memberships")
    user_account = relationship("UserAccount")
    user_group = relationship("UserGroup")


class SoftwarePackage(Base):
    """
    This class holds the object mapping for the software_packages table in the
    PostgreSQL database. Stores comprehensive software inventory across all platforms.
    """

    __tablename__ = "software_packages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=False)

    # Core package information
    package_name = Column(String(255), nullable=False, index=True)
    version = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)

    # Package manager and source information
    package_manager = Column(
        String(50), nullable=False, index=True
    )  # apt, snap, homebrew, etc.
    source = Column(String(100), nullable=True)  # repository, store, local install

    # Technical details
    architecture = Column(String(50), nullable=True)  # x86_64, arm64, universal, etc.
    size_bytes = Column(BigInteger, nullable=True)
    install_date = Column(DateTime(timezone=True), nullable=True)

    # Metadata
    vendor = Column(String(255), nullable=True)  # Publisher/developer
    category = Column(String(100), nullable=True)  # Application category
    license_type = Column(String(100), nullable=True)  # GPL, MIT, Commercial, etc.

    # Platform-specific fields
    bundle_id = Column(String(255), nullable=True)  # macOS bundle identifier
    app_store_id = Column(String(50), nullable=True)  # Store-specific ID
    installation_path = Column(String(500), nullable=True)  # Installation directory

    # System classification
    is_system_package = Column(Boolean, nullable=False, default=False)
    is_user_installed = Column(Boolean, nullable=False, default=True)

    # Audit fields
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    software_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Relationship back to Host
    host = relationship("Host", back_populates="software_packages")


class PackageUpdate(Base):
    """
    This class holds the object mapping for the package_updates table in the
    PostgreSQL database. Stores available package updates detected by agents.
    """

    __tablename__ = "package_updates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=False)

    # Package identification
    package_name = Column(String(255), nullable=False, index=True)
    current_version = Column(String(100), nullable=True)
    available_version = Column(String(100), nullable=False)

    # Package manager information
    package_manager = Column(
        String(50), nullable=False, index=True
    )  # apt, snap, homebrew, etc.
    source = Column(String(100), nullable=True)  # repository, store source

    # Update classification
    is_security_update = Column(Boolean, nullable=False, default=False, index=True)
    is_system_update = Column(Boolean, nullable=False, default=False, index=True)
    requires_reboot = Column(Boolean, nullable=False, default=False)

    # Update metadata
    update_size_bytes = Column(BigInteger, nullable=True)
    bundle_id = Column(String(255), nullable=True)  # Platform-specific ID
    repository = Column(String(100), nullable=True)  # Source repository
    channel = Column(String(50), nullable=True)  # Snap channels, etc.

    # Status tracking
    status = Column(
        String(20), nullable=False, default="available", index=True
    )  # available, updating, completed, failed

    # Timestamps
    detected_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    last_checked_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship back to Host
    host = relationship("Host", back_populates="package_updates")


class UpdateExecutionLog(Base):
    """
    This class holds the object mapping for the update_execution_log table in the
    PostgreSQL database. Tracks execution of package updates.
    """

    __tablename__ = "update_execution_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    package_update_id = Column(
        Integer, ForeignKey("package_updates.id", ondelete="CASCADE"), nullable=True
    )

    # Execution details
    package_name = Column(String(255), nullable=False)
    package_manager = Column(String(50), nullable=False)
    from_version = Column(String(100), nullable=True)
    to_version = Column(String(100), nullable=False)

    # Execution status
    status = Column(
        String(20), nullable=False, index=True
    )  # pending, running, completed, failed
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Result information
    success = Column(Boolean, nullable=True)
    error_message = Column(Text, nullable=True)
    execution_log = Column(Text, nullable=True)  # Command output/logs

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationships
    host = relationship("Host")
    package_update = relationship("PackageUpdate")


class MessageQueue(Base):
    """
    Message queue table for persistent message storage between server and agents.

    This table stores both inbound (from agents) and outbound (to agents) messages
    with their processing status, priority, and timestamps for reliable delivery.
    """

    __tablename__ = "message_queue"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Host association (nullable for broadcast messages)
    host_id = Column(
        Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Message identification
    message_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    direction = Column(String(10), nullable=False, index=True)  # inbound/outbound

    # Message content
    message_type = Column(String(50), nullable=False, index=True)
    message_data = Column(Text, nullable=False)  # JSON serialized message

    # Queue management
    status = Column(String(15), nullable=False, default="pending", index=True)
    priority = Column(String(10), nullable=False, default="normal", index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)

    # Timestamps (PostgreSQL handles timezone automatically)
    created_at = Column(DateTime(timezone=True), nullable=False)
    scheduled_at = Column(
        DateTime(timezone=True), nullable=True
    )  # When to process (for delays)
    started_at = Column(
        DateTime(timezone=True), nullable=True
    )  # When processing started
    completed_at = Column(
        DateTime(timezone=True), nullable=True
    )  # When processing finished

    # Error handling
    error_message = Column(Text, nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)

    # Metadata
    correlation_id = Column(
        String(36), nullable=True, index=True
    )  # For message correlation
    reply_to = Column(String(36), nullable=True, index=True)  # For message replies

    # Create composite indexes for common queries
    __table_args__ = (
        Index(
            "idx_queue_processing", "direction", "status", "priority", "scheduled_at"
        ),
        Index("idx_queue_cleanup", "status", "completed_at"),
        Index("idx_queue_retry", "status", "retry_count", "max_retries"),
        Index("idx_queue_host_direction", "host_id", "direction", "status"),
    )

    # Relationship back to Host
    host = relationship("Host")

    def __repr__(self):
        return (
            f"<MessageQueue(id={self.id}, message_id='{self.message_id}', "
            f"type='{self.message_type}', direction='{self.direction}', "
            f"status='{self.status}', host_id={self.host_id})>"
        )


class QueueMetrics(Base):
    """
    Table for storing queue performance metrics and statistics.
    Tracks message processing performance and error rates.
    """

    __tablename__ = "queue_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Metric identification
    metric_name = Column(String(50), nullable=False, index=True)
    direction = Column(String(10), nullable=False, index=True)  # inbound/outbound
    host_id = Column(
        Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Metric values
    count = Column(Integer, nullable=False, default=0)
    total_time_ms = Column(Integer, nullable=False, default=0)
    avg_time_ms = Column(Integer, nullable=False, default=0)
    min_time_ms = Column(Integer, nullable=True)
    max_time_ms = Column(Integer, nullable=True)

    # Error tracking
    error_count = Column(Integer, nullable=False, default=0)

    # Timestamps
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Indexes for efficient querying
    __table_args__ = (
        Index(
            "idx_metrics_period",
            "metric_name",
            "direction",
            "period_start",
            "period_end",
        ),
        Index("idx_metrics_latest", "metric_name", "direction", "updated_at"),
        Index("idx_metrics_host", "host_id", "metric_name", "direction"),
    )

    # Relationship back to Host
    host = relationship("Host")

    def __repr__(self):
        return (
            f"<QueueMetrics(id={self.id}, metric='{self.metric_name}', "
            f"direction='{self.direction}', count={self.count}, host_id={self.host_id})>"
        )
