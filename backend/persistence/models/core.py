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
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
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
    certificate_issued_at = Column(DateTime, nullable=True)

    # OS Version fields
    platform = Column(String(50), nullable=True)
    platform_release = Column(String(100), nullable=True)
    platform_version = Column(Text, nullable=True)
    machine_architecture = Column(String(50), nullable=True)
    processor = Column(String(100), nullable=True)
    os_details = Column(Text, nullable=True)
    os_version_updated_at = Column(DateTime, nullable=True)

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
    hardware_updated_at = Column(DateTime, nullable=True)

    # Software inventory fields
    software_updated_at = Column(DateTime, nullable=True)

    # User access data timestamp
    user_access_updated_at = Column(DateTime, nullable=True)

    # Diagnostics request tracking
    diagnostics_requested_at = Column(DateTime, nullable=True)
    diagnostics_request_status = Column(String(50), nullable=True)

    # Update management fields
    reboot_required = Column(Boolean, nullable=False, default=False)
    reboot_required_updated_at = Column(DateTime, nullable=True)

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
    third_party_repositories = relationship(
        "ThirdPartyRepository", back_populates="host"
    )
    antivirus_status = relationship(
        "AntivirusStatus", back_populates="host", uselist=False
    )
    user_accounts = relationship("UserAccount", back_populates="host")
    user_groups = relationship("UserGroup", back_populates="host")
    certificates = relationship(
        "HostCertificate", back_populates="host", cascade="all, delete-orphan"
    )
    roles = relationship(
        "HostRole", back_populates="host", cascade="all, delete-orphan"
    )
    grafana_integration = relationship(
        "GrafanaIntegrationSettings", back_populates="host", uselist=False
    )

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
    last_access = Column(DateTime, nullable=True)
    is_locked = Column(Boolean, nullable=False, default=False)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_at = Column(DateTime, nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    profile_image = Column(LargeBinary, nullable=True)
    profile_image_type = Column(String(10), nullable=True)
    profile_image_uploaded_at = Column(DateTime, nullable=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    last_login_at = Column(DateTime, nullable=True)
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

    # Relationships
    security_roles = relationship(
        "SecurityRole",
        secondary="user_security_roles",
        primaryjoin="User.id == UserSecurityRole.user_id",
        secondaryjoin="SecurityRole.id == UserSecurityRole.role_id",
        back_populates="users",
    )

    # Runtime role cache (not stored in database)
    _role_cache = None

    def load_role_cache(self, db_session):
        """
        Load security roles into cache for quick permission checking.

        This should be called after user authentication to populate the role cache.

        Args:
            db_session: SQLAlchemy database session
        """
        from backend.security.roles import load_user_roles

        self._role_cache = load_user_roles(db_session, self.id)

    def has_role(self, role):
        """
        Check if user has a specific security role.

        Args:
            role: SecurityRoles enum value

        Returns:
            True if user has the role, False otherwise

        Note:
            load_role_cache() must be called first, otherwise this returns False.
        """
        if self._role_cache is None:
            return False

        return self._role_cache.has_role(role)

    def has_any_role(self, roles):
        """
        Check if user has any of the specified roles.

        Args:
            roles: List of SecurityRoles enum values

        Returns:
            True if user has at least one of the roles, False otherwise

        Note:
            load_role_cache() must be called first, otherwise this returns False.
        """
        if self._role_cache is None:
            return False

        return self._role_cache.has_any_role(roles)

    def has_all_roles(self, roles):
        """
        Check if user has all of the specified roles.

        Args:
            roles: List of SecurityRoles enum values

        Returns:
            True if user has all of the roles, False otherwise

        Note:
            load_role_cache() must be called first, otherwise this returns False.
        """
        if self._role_cache is None:
            return False

        return self._role_cache.has_all_roles(roles)

    def get_roles(self):
        """
        Get all security roles the user has.

        Returns:
            Set of SecurityRoles enum values, or empty set if cache not loaded

        Note:
            load_role_cache() must be called first to get accurate results.
        """
        if self._role_cache is None:
            return set()

        return self._role_cache.get_roles()

    def __repr__(self):
        return f"<User(id={self.id}, userid='{self.userid}', active={self.active}, is_admin={self.is_admin})>"


class SecurityRoleGroup(Base):
    """
    Security role groups for organizing permissions.
    """

    __tablename__ = "security_role_groups"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationships
    roles = relationship(
        "SecurityRole", back_populates="group", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<SecurityRoleGroup(id={self.id}, name='{self.name}')>"


class SecurityRole(Base):
    """
    Security roles for fine-grained permission control.
    """

    __tablename__ = "security_roles"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    group_id = Column(
        GUID(),
        ForeignKey("security_role_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationships
    group = relationship("SecurityRoleGroup", back_populates="roles")
    users = relationship(
        "User",
        secondary="user_security_roles",
        primaryjoin="SecurityRole.id == UserSecurityRole.role_id",
        secondaryjoin="User.id == UserSecurityRole.user_id",
        back_populates="security_roles",
    )

    def __repr__(self):
        return f"<SecurityRole(id={self.id}, name='{self.name}', group_id={self.group_id})>"


class UserSecurityRole(Base):
    """
    Mapping table for users to security roles.
    """

    __tablename__ = "user_security_roles"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id = Column(
        GUID(),
        ForeignKey("security_roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    granted_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    granted_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self):
        return f"<UserSecurityRole(user_id={self.user_id}, role_id={self.role_id})>"


class UserDataGridColumnPreference(Base):
    """
    User preferences for DataGrid column visibility.
    Stores which columns a user has hidden for each grid.
    """

    __tablename__ = "user_datagrid_column_preferences"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grid_identifier = Column(
        String(255), nullable=False, index=True
    )  # e.g., "hosts-grid", "users-grid"
    hidden_columns = Column(
        JSON, nullable=False
    )  # JSON array of hidden column field names
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<UserDataGridColumnPreference(user_id={self.user_id}, grid_identifier='{self.grid_identifier}')>"
