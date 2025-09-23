"""
Core models for SysManage - Host, User, and authentication related models.
"""

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from backend.persistence.db import Base


class GUID(TypeDecorator):  # pylint: disable=too-many-ancestors
    """
    Platform-independent GUID type.
    Uses PostgreSQL's UUID type when available, otherwise stores as string.
    """

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value) if not isinstance(value, uuid.UUID) else value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value)
        return value

    def process_literal_param(self, value, dialect):
        """Process literal parameter for inline SQL compilation."""
        if value is None:
            return None
        return str(value)

    @property
    def python_type(self):
        return uuid.UUID


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

    return f"{token_uuid}-{additional_entropy}"


class BearerToken(Base):
    """
    Bearer token model for agent authentication.
    """

    __tablename__ = "bearer_token"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    token = Column(String(256), unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False)


class Host(Base):
    """
    This class holds the object mapping for the host table in the
    PostgreSQL database.
    """

    __tablename__ = "host"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    active = Column(Boolean, unique=False, index=False)
    fqdn = Column(String, index=True)
    ipv4 = Column(String)
    ipv6 = Column(String)
    host_token = Column(String(256), nullable=True, unique=True)
    last_access = Column(DateTime)
    status = Column(String(20), nullable=False, server_default="up")
    approval_status = Column(String(20), nullable=False, server_default="pending")
    client_certificate = Column(Text, nullable=True)
    certificate_serial = Column(String(64), nullable=True)
    certificate_issued_at = Column(DateTime(timezone=True), nullable=True)

    # OS Version fields
    platform = Column(String(50), nullable=True)
    platform_release = Column(String(100), nullable=True)
    platform_version = Column(Text, nullable=True)
    machine_architecture = Column(String(50), nullable=True)
    processor = Column(String(100), nullable=True)
    os_details = Column(Text, nullable=True)
    os_version_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Hardware inventory fields
    cpu_vendor = Column(String(100), nullable=True)
    cpu_model = Column(String(200), nullable=True)
    cpu_cores = Column(Integer, nullable=True)
    cpu_threads = Column(Integer, nullable=True)
    cpu_frequency_mhz = Column(Integer, nullable=True)
    memory_total_mb = Column(BigInteger, nullable=True)
    storage_details = Column(Text, nullable=True)
    network_details = Column(Text, nullable=True)
    hardware_details = Column(Text, nullable=True)
    hardware_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Software inventory fields
    software_updated_at = Column(DateTime(timezone=True), nullable=True)

    # User access data timestamp
    user_access_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Diagnostics request tracking
    diagnostics_requested_at = Column(DateTime(timezone=True), nullable=True)
    diagnostics_request_status = Column(String(50), nullable=True)

    # Update management fields
    reboot_required = Column(Boolean, nullable=False, default=False)
    reboot_required_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Agent privilege status
    is_agent_privileged = Column(Boolean, nullable=True, default=False)

    # Script execution permission
    script_execution_enabled = Column(Boolean, nullable=False, default=False)

    # Available shells on the host (JSON)
    enabled_shells = Column(Text, nullable=True)

    # Relationships
    tags = relationship(
        "Tag", secondary="host_tags", back_populates="hosts", lazy="dynamic"
    )
    package_updates = relationship("PackageUpdate", back_populates="host")
    software_installation_logs = relationship(
        "SoftwareInstallationLog", back_populates="host"
    )
    software_packages = relationship("SoftwarePackage", back_populates="host")
    user_accounts = relationship("UserAccount", back_populates="host")
    user_groups = relationship("UserGroup", back_populates="host")

    def __repr__(self):
        return f"<Host(id={self.id}, fqdn='{self.fqdn}', active={self.active})>"


class User(Base):
    """
    This class holds the object mapping for the user table in the
    PostgreSQL database.
    """

    __tablename__ = "user"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    active = Column(Boolean, unique=False, index=False)
    userid = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    last_access = Column(DateTime(timezone=True), nullable=True)
    is_locked = Column(Boolean, nullable=False, default=False)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    profile_image = Column(LargeBinary, nullable=True)
    profile_image_type = Column(String(10), nullable=True)
    profile_image_uploaded_at = Column(DateTime(timezone=True), nullable=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<User(id={self.id}, userid='{self.userid}', active={self.active}, is_admin={self.is_admin})>"
