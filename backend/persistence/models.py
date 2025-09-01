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


class User(Base):
    """
    This class holds the object mapping for the user table in the PostgreSQL
    database.
    """

    __tablename__ = "user"
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    active = Column(Boolean, unique=False, index=False)
    userid = Column(String)
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
