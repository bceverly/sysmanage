"""
This module holds the various models that are persistence backed by the
PostgreSQL database.

⚠️  TESTING ARCHITECTURE WARNING ⚠️

When adding new models to this file, you MUST also update:
- /tests/api/conftest.py (if API tests need the model)

Follow SQLite compatibility rules for test models:
- ✅ Use Integer primary keys (not BigInteger) for auto-increment in test models
- ✅ Use String instead of Text in test models for better performance

See README.md and TESTING.md for complete guidelines.
"""

import secrets
import uuid
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
import sqlalchemy as sa
from sqlalchemy.orm import relationship

from backend.persistence.db import Base


def generate_secure_host_token() -> str:
    """
    Generate a cryptographically secure host token.

    Uses a combination of UUID4 and additional entropy for maximum security.
    Format: <uuid4>-<8-random-hex-bytes>
    Example: 550e8400-e29b-41d4-a716-446655440000-a1b2c3d4e5f6g7h8
    """
    # Generate a UUID4 for uniqueness and structure
    token_uuid = str(uuid.uuid4())

    # Add additional entropy for security
    additional_entropy = secrets.token_hex(8)

    # Combine for final token
    return f"{token_uuid}-{additional_entropy}"


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
    host_token = Column(
        String(64), unique=True, nullable=True, index=True
    )  # Secure UUID-based token
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

    # User access data timestamp
    user_access_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Diagnostics request tracking
    diagnostics_requested_at = Column(DateTime(timezone=True), nullable=True)
    diagnostics_request_status = Column(
        String(50), nullable=True
    )  # 'pending', 'completed', 'failed'

    # Update management fields
    reboot_required = Column(Boolean, nullable=False, default=False, index=True)
    reboot_required_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Agent privilege status
    is_agent_privileged = Column(Boolean, nullable=True, default=False)

    # Script execution status
    script_execution_enabled = Column(Boolean, nullable=True, default=False)

    # Enabled shells for script execution (stored as JSON array)
    enabled_shells = Column(String, nullable=True)

    # Relationships to normalized hardware tables
    storage_devices = relationship(
        "StorageDevice", back_populates="host", cascade="all, delete-orphan"
    )
    network_interfaces = relationship(
        "NetworkInterface", back_populates="host", cascade="all, delete-orphan"
    )

    # Relationship to tags (many-to-many)
    tags = relationship(
        "Tag", secondary="host_tags", back_populates="hosts", lazy="dynamic"
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

    # Relationship to Ubuntu Pro information
    ubuntu_pro_info = relationship(
        "UbuntuProInfo",
        back_populates="host",
        cascade="all, delete-orphan",
        uselist=False,
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
    # Profile image fields
    profile_image = Column(LargeBinary, nullable=True)
    profile_image_type = Column(String(10), nullable=True)  # png, jpg, gif
    profile_image_uploaded_at = Column(DateTime(timezone=True), nullable=True)


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

    # Message expiration tracking
    expired_at = Column(DateTime(timezone=True), nullable=True)

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


class SavedScript(Base):
    """
    This class holds the object mapping for the saved_scripts table in the
    PostgreSQL database. Stores user-created scripts for later execution.
    """

    __tablename__ = "saved_scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    shell_type = Column(String(50), nullable=False)  # bash, zsh, powershell, cmd, etc.
    platform = Column(
        String(50), nullable=True, index=True
    )  # linux, windows, darwin, openbsd, etc.
    run_as_user = Column(
        String(100), nullable=True
    )  # User to run script as (if agent runs as root)
    is_active = Column(Boolean, nullable=False, server_default="true", index=True)
    created_by = Column(String(100), nullable=False)  # User who created the script
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    def __repr__(self):
        return (
            f"<SavedScript(id={self.id}, name='{self.name}', "
            f"shell_type='{self.shell_type}', platform='{self.platform}')>"
        )


class ScriptExecutionLog(Base):
    """
    This class holds the object mapping for the script_execution_log table in the
    PostgreSQL database. Tracks execution of scripts on remote hosts.
    """

    __tablename__ = "script_execution_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(
        Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=False, index=True
    )
    saved_script_id = Column(
        Integer, ForeignKey("saved_scripts.id", ondelete="SET NULL"), nullable=True
    )
    script_name = Column(String(255), nullable=True)  # Name for ad-hoc scripts
    script_content = Column(
        Text, nullable=False
    )  # Actual script content that was executed
    shell_type = Column(String(50), nullable=False)
    run_as_user = Column(String(100), nullable=True)
    requested_by = Column(String(100), nullable=False)  # User who requested execution
    execution_id = Column(
        String(36), nullable=False, unique=True, index=True
    )  # UUID for tracking
    execution_uuid = Column(
        String(36), nullable=True, unique=True, index=True
    )  # Separate UUID sent to agent to prevent duplicates
    status = Column(
        String(20), nullable=False, server_default="pending", index=True
    )  # pending, running, completed, failed, cancelled
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    exit_code = Column(Integer, nullable=True)
    stdout_output = Column(Text, nullable=True)
    stderr_output = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationships
    host = relationship("Host")
    saved_script = relationship("SavedScript")

    def __repr__(self):
        return (
            f"<ScriptExecutionLog(id={self.id}, execution_id='{self.execution_id}', "
            f"status='{self.status}', host_id={self.host_id})>"
        )


class DiagnosticReport(Base):
    """
    This class holds the object mapping for the diagnostic_reports table in the
    PostgreSQL database. Stores diagnostic information collected from agents.
    """

    __tablename__ = "diagnostic_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(
        Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Collection metadata
    collection_id = Column(
        String(36), nullable=False, unique=True, index=True
    )  # UUID for tracking
    requested_by = Column(String(100), nullable=False)  # User who requested diagnostics
    status = Column(
        String(20), nullable=False, server_default="pending", index=True
    )  # pending, collecting, completed, failed

    # Timestamps
    requested_at = Column(DateTime(timezone=True), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Diagnostic data (JSON stored as text)
    system_logs = Column(Text, nullable=True)  # JSON with log files and contents
    configuration_files = Column(Text, nullable=True)  # JSON with config files
    network_info = Column(Text, nullable=True)  # JSON with network diagnostics
    process_info = Column(Text, nullable=True)  # JSON with running processes
    disk_usage = Column(Text, nullable=True)  # JSON with disk usage info
    environment_variables = Column(Text, nullable=True)  # JSON with env vars
    agent_logs = Column(Text, nullable=True)  # JSON with agent-specific logs
    error_logs = Column(Text, nullable=True)  # JSON with system error logs

    # Collection results
    collection_size_bytes = Column(BigInteger, nullable=True)
    files_collected = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationships
    host = relationship("Host")

    def __repr__(self):
        return (
            f"<DiagnosticReport(id={self.id}, collection_id='{self.collection_id}', "
            f"status='{self.status}', host_id={self.host_id})>"
        )


class Tag(Base):
    """
    This class holds the object mapping for the tags table in the
    PostgreSQL database. Tags can be associated with hosts for categorization.
    """

    __tablename__ = "tags"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationships
    hosts = relationship(
        "Host", secondary="host_tags", back_populates="tags", lazy="dynamic"
    )

    def __repr__(self):
        return f"<Tag(id={self.id}, name='{self.name}')>"


class HostTag(Base):
    """
    This class holds the object mapping for the host_tags junction table in the
    PostgreSQL database. This represents the many-to-many relationship between
    hosts and tags.
    """

    __tablename__ = "host_tags"

    host_id = Column(
        BigInteger,
        ForeignKey("host.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    tag_id = Column(
        BigInteger,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), nullable=False)

    def __repr__(self):
        return f"<HostTag(host_id={self.host_id}, tag_id={self.tag_id})>"


class PasswordResetToken(Base):
    """
    This class holds the object mapping for the password_reset_tokens table in the
    PostgreSQL database. This stores tokens used for password reset functionality.
    """

    __tablename__ = "password_reset_tokens"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    user_id = Column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    token = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    is_used = Column(Boolean, default=False, nullable=False)

    # Relationship to User
    user = relationship("User", backref="password_reset_tokens")

    def __repr__(self):
        return f"<PasswordResetToken(id={self.id}, user_id={self.user_id}, is_used={self.is_used})>"


class UbuntuProInfo(Base):
    """
    This class holds the object mapping for the ubuntu_pro_info table in the
    PostgreSQL database. Stores Ubuntu Pro subscription status and service information.
    """

    __tablename__ = "ubuntu_pro_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(Integer, ForeignKey("host.id", ondelete="CASCADE"), nullable=False)

    # Ubuntu Pro availability and status
    available = Column(Boolean, nullable=False, default=False)
    attached = Column(Boolean, nullable=False, default=False)
    version = Column(String(50), nullable=True)
    expires = Column(DateTime(timezone=True), nullable=True)

    # Account and contract information
    account_name = Column(String(255), nullable=True)
    contract_name = Column(String(255), nullable=True)
    tech_support_level = Column(String(50), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationships
    host = relationship("Host", back_populates="ubuntu_pro_info")
    services = relationship(
        "UbuntuProService",
        back_populates="ubuntu_pro_info",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<UbuntuProInfo(id={self.id}, host_id={self.host_id}, "
            f"attached={self.attached}, available={self.available})>"
        )


class UbuntuProService(Base):
    """
    This class holds the object mapping for the ubuntu_pro_services table in the
    PostgreSQL database. Stores individual Ubuntu Pro service information.
    """

    __tablename__ = "ubuntu_pro_services"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ubuntu_pro_info_id = Column(
        Integer, ForeignKey("ubuntu_pro_info.id", ondelete="CASCADE"), nullable=False
    )

    # Service information
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    available = Column(Boolean, nullable=False, default=False)
    status = Column(String(50), nullable=True)  # enabled, disabled, n/a
    entitled = Column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship back to UbuntuProInfo
    ubuntu_pro_info = relationship("UbuntuProInfo", back_populates="services")

    def __repr__(self):
        return (
            f"<UbuntuProService(id={self.id}, name='{self.name}', "
            f"status='{self.status}', available={self.available})>"
        )


class UbuntuProSettings(Base):
    """
    This class holds the object mapping for the ubuntu_pro_settings table in the
    PostgreSQL database. Stores global Ubuntu Pro configuration like master keys.
    """

    __tablename__ = "ubuntu_pro_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Master Ubuntu Pro key for bulk enrollment
    master_key = Column(Text, nullable=True)

    # Optional settings
    organization_name = Column(String(255), nullable=True)
    auto_attach_enabled = Column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    def __repr__(self):
        return (
            f"<UbuntuProSettings(id={self.id}, "
            f"has_master_key={self.master_key is not None}, "
            f"organization_name='{self.organization_name}')>"
        )


class AvailablePackage(Base):
    """Model for storing available packages from different package managers across OS versions."""

    __tablename__ = "available_packages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    os_name = Column(String(100), nullable=False)
    os_version = Column(String(100), nullable=False)
    package_manager = Column(String(50), nullable=False)
    package_name = Column(String(255), nullable=False, index=True)
    package_version = Column(String(100), nullable=False)
    package_description = Column(Text, nullable=True)
    last_updated = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    # Additional indexes to match PostgreSQL schema
    __table_args__ = (
        Index(
            "ix_available_packages_os_version_pm",
            "os_name",
            "os_version",
            "package_manager",
        ),
        Index(
            "ix_available_packages_unique",
            "os_name",
            "os_version",
            "package_manager",
            "package_name",
            unique=True,
        ),
    )

    def __repr__(self):
        return (
            f"<AvailablePackage(id={self.id}, "
            f"name='{self.package_name}', "
            f"version='{self.package_version}', "
            f"manager='{self.package_manager}', "
            f"os='{self.os_name} {self.os_version}')>"
        )
