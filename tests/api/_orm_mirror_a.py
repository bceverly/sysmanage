# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
API-test ORM schema mirror, part A (Host .. HostFirewallRole).

SQLite-compatible, hand-written mirrors of the production models.  See
``tests/api/conftest.py`` for the full rationale and the maintenance warning.
All classes register on the shared ``TestBase`` from ``_orm_mirror_base`` so
that string-based relationships resolve across the mirror modules.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.persistence.models.core import GUID
from tests.api._orm_mirror_base import TestBase


# Create test version of Host model with Integer ID for SQLite compatibility
class Host(TestBase):
    __tablename__ = "host"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    active = Column(Boolean, unique=False, index=False)
    fqdn = Column(String, index=True)
    ipv4 = Column(String)
    ipv6 = Column(String)
    host_token = Column(String(256), nullable=True, unique=True)
    last_access = Column(DateTime)
    status = Column(String(20), nullable=False, server_default="up")
    approval_status = Column(String(20), nullable=False, server_default="pending")
    client_certificate = Column(
        String, nullable=True
    )  # Using String instead of Text for SQLite
    certificate_serial = Column(String(64), nullable=True)
    certificate_issued_at = Column(
        DateTime, nullable=True
    )  # Timezone not supported in SQLite

    # OS Version fields
    platform = Column(String(50), nullable=True)
    platform_release = Column(String(100), nullable=True)
    platform_version = Column(
        String, nullable=True
    )  # Using String instead of Text for SQLite
    machine_architecture = Column(String(50), nullable=True)
    processor = Column(String(100), nullable=True)
    timezone = Column(String(100), nullable=True)
    os_details = Column(
        String, nullable=True
    )  # Using String instead of Text for SQLite
    os_version_updated_at = Column(DateTime, nullable=True)

    # FIPS compliance-mode fields (Phase 14.4)
    fips_status = Column(String(20), nullable=True)
    fips_enabled = Column(Boolean, nullable=True)
    fips_available = Column(Boolean, nullable=True)
    fips_kernel_enforced = Column(Boolean, nullable=True)
    fips_vendor = Column(String(50), nullable=True)
    fips_package_version = Column(String(100), nullable=True)
    fips_updated_at = Column(DateTime, nullable=True)

    # Hardware inventory fields
    cpu_vendor = Column(String(100), nullable=True)
    cpu_model = Column(String(200), nullable=True)
    cpu_cores = Column(Integer, nullable=True)
    cpu_threads = Column(Integer, nullable=True)
    cpu_frequency_mhz = Column(Integer, nullable=True)
    memory_total_mb = Column(
        Integer, nullable=True
    )  # Using Integer instead of BigInteger
    storage_details = Column(
        String, nullable=True
    )  # Using String instead of Text for SQLite
    network_details = Column(
        String, nullable=True
    )  # Using String instead of Text for SQLite
    hardware_details = Column(
        String, nullable=True
    )  # Using String instead of Text for SQLite
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
    reboot_required_reason = Column(String(255), nullable=True)
    reboot_required_updated_at = Column(DateTime, nullable=True)

    # Agent privilege status
    is_agent_privileged = Column(Boolean, nullable=True, default=False)

    # Agent version tracking
    agent_version = Column(String(50), nullable=True)

    # Script execution permission
    script_execution_enabled = Column(Boolean, nullable=False, default=False)

    # Available shells on the host (JSON)
    enabled_shells = Column(
        String, nullable=True
    )  # Using String instead of Text for SQLite

    # Virtualization capability fields
    virtualization_types = Column(
        String, nullable=True
    )  # Comma-separated list of virtualization types
    virtualization_capabilities = Column(
        String, nullable=True
    )  # JSON dict with per-type info
    virtualization_updated_at = Column(DateTime, nullable=True)

    # Parent host for child hosts (WSL, containers, VMs)
    parent_host_id = Column(
        GUID(), ForeignKey("host.id", ondelete="SET NULL"), nullable=True
    )

    # Phase 12.7: agent-reported public IP + GeoLite2 resolution
    public_ip = Column(String(45), nullable=True)
    public_ip_resolved_at = Column(DateTime, nullable=True)
    geo_country_code = Column(String(2), nullable=True)
    geo_subdivision_code = Column(String(10), nullable=True)
    geo_city = Column(String(200), nullable=True)
    geo_latitude = Column(Float, nullable=True)
    geo_longitude = Column(Float, nullable=True)

    # Add relationship
    tags = relationship(
        "Tag", secondary="host_tags", back_populates="hosts", lazy="dynamic"
    )
    package_updates = relationship("PackageUpdate", back_populates="host")
    software_installation_logs = relationship(
        "SoftwareInstallationLog", back_populates="host"
    )
    firewall_roles = relationship(
        "HostFirewallRole", back_populates="host", cascade="all, delete-orphan"
    )


# Create test version of User model with Integer ID for SQLite compatibility
class User(TestBase):
    __tablename__ = "user"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    active = Column(Boolean, unique=False, index=False)
    userid = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    last_access = Column(DateTime, nullable=True)
    is_locked = Column(Boolean, nullable=False, default=False)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_at = Column(DateTime, nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    profile_image = Column(
        String, nullable=True
    )  # Using String instead of LargeBinary for SQLite
    profile_image_type = Column(String(10), nullable=True)
    profile_image_uploaded_at = Column(DateTime, nullable=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
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


# Create test version of SecurityRoleGroup model for SQLite compatibility
class SecurityRoleGroup(TestBase):
    __tablename__ = "security_role_groups"
    id = Column(GUID(), primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(500), nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


# Create test version of SecurityRole model for SQLite compatibility
class SecurityRole(TestBase):
    __tablename__ = "security_roles"
    id = Column(GUID(), primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(String(500), nullable=True)
    group_id = Column(
        GUID(),
        ForeignKey("security_role_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


# Create test version of UserSecurityRole model for SQLite compatibility
class UserSecurityRole(TestBase):
    __tablename__ = "user_security_roles"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(
        GUID(), ForeignKey("security_roles.id", ondelete="CASCADE"), nullable=False
    )
    granted_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    granted_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


# Create test version of Tag model with UUID for consistency with production
class Tag(TestBase):
    __tablename__ = "tags"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # Add relationship
    hosts = relationship(
        "Host", secondary="host_tags", back_populates="tags", lazy="dynamic"
    )


# Create test version of HostTag junction table with UUID foreign keys
class HostTag(TestBase):
    __tablename__ = "host_tags"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(),
        ForeignKey("host.id", ondelete="CASCADE"),
        nullable=False,
    )
    tag_id = Column(
        GUID(),
        ForeignKey("tags.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


# Create test version of PasswordResetToken model with Integer ID for SQLite compatibility
class PasswordResetToken(TestBase):
    __tablename__ = "password_reset_tokens"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


# Create test version of MessageQueue model with Integer ID for SQLite compatibility
class MessageQueue(TestBase):
    __tablename__ = "message_queue"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        Integer,
        ForeignKey("host.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    message_id = Column(String(36), unique=True, nullable=False, index=True)
    direction = Column(String(10), nullable=False, index=True)
    message_type = Column(String(50), nullable=False, index=True)
    message_data = Column(Text, nullable=False)
    status = Column(String(15), nullable=False, default="pending", index=True)
    priority = Column(String(10), nullable=False, default="normal", index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    last_error_at = Column(DateTime, nullable=True)
    expired_at = Column(DateTime, nullable=True)
    correlation_id = Column(String(36), nullable=True, index=True)
    reply_to = Column(String(36), nullable=True, index=True)


# Create test version of SavedScript model for SQLite compatibility
class SavedScript(TestBase):
    __tablename__ = "saved_scripts"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    description = Column(
        String, nullable=True
    )  # Using String instead of Text for SQLite
    content = Column(String, nullable=False)  # Using String instead of Text for SQLite
    shell_type = Column(String(50), nullable=False)
    platform = Column(String(50), nullable=True)
    run_as_user = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(String(255), nullable=False)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


# Create test version of ScriptExecutionLog model for SQLite compatibility
class ScriptExecutionLog(TestBase):
    __tablename__ = "script_execution_log"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    execution_id = Column(String(36), nullable=False, unique=True, index=True)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    saved_script_id = Column(
        GUID(), ForeignKey("saved_scripts.id", ondelete="SET NULL"), nullable=True
    )
    script_name = Column(String(255), nullable=True)
    script_content = Column(
        String, nullable=False
    )  # Using String instead of Text for SQLite
    shell_type = Column(String(50), nullable=False)
    run_as_user = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    requested_by = Column(String(255), nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    exit_code = Column(Integer, nullable=True)
    stdout_output = Column(
        String, nullable=True
    )  # Using String instead of Text for SQLite
    stderr_output = Column(
        String, nullable=True
    )  # Using String instead of Text for SQLite
    error_message = Column(
        String, nullable=True
    )  # Using String instead of Text for SQLite
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    execution_uuid = Column(String(36), nullable=True, unique=True, index=True)


# Create test version of UbuntuProSettings model for SQLite compatibility
class UbuntuProSettings(TestBase):
    __tablename__ = "ubuntu_pro_settings"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    master_key = Column(Text, nullable=True)
    organization_name = Column(String(255), nullable=True)
    auto_attach_enabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class PackageUpdate(TestBase):
    __tablename__ = "package_updates"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id"), nullable=False)
    package_name = Column(String(255), nullable=False)
    current_version = Column(String(100), nullable=True)
    available_version = Column(String(100), nullable=False)
    package_manager = Column(String(50), nullable=False)
    update_type = Column(String(20), nullable=False)  # security, bugfix, enhancement
    source = Column(String(255), nullable=True)
    is_security_update = Column(Boolean, nullable=False, default=False)
    is_system_update = Column(Boolean, nullable=False, default=False)
    requires_reboot = Column(Boolean, nullable=False, default=False)
    update_size_bytes = Column(Integer, nullable=True)
    bundle_id = Column(String(255), nullable=True)
    repository = Column(String(255), nullable=True)
    channel = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="available")
    detected_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)

    # Add relationship back to host
    host = relationship("Host", back_populates="package_updates")


# Create test version of AvailablePackage model for SQLite compatibility
# ⚠️  ADD NEW MODELS HERE: When adding models, follow this pattern with Integer primary keys!
class AvailablePackage(TestBase):
    __tablename__ = "available_packages"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    package_name = Column(String(255), nullable=False, index=True)
    package_version = Column(String(100), nullable=False)
    package_description = Column(Text, nullable=True)
    package_manager = Column(String(50), nullable=False, index=True)
    os_name = Column(String(100), nullable=False, index=True)
    os_version = Column(String(100), nullable=False, index=True)
    last_updated = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False)


class InstallationRequest(TestBase):
    __tablename__ = "installation_requests"
    id = Column(String(36), primary_key=True)  # UUID
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    requested_by = Column(String(100), nullable=False)
    requested_at = Column(DateTime(timezone=True), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, server_default="pending", index=True)
    operation_type = Column(
        String(20), nullable=False, server_default="install", index=True
    )
    result_log = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    host = relationship("Host")
    packages = relationship(
        "InstallationPackage",
        back_populates="installation_request",
        cascade="all, delete-orphan",
    )


class InstallationPackage(TestBase):
    __tablename__ = "installation_packages"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    installation_request_id = Column(
        String(36),
        ForeignKey("installation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    package_name = Column(String(255), nullable=False)
    package_manager = Column(String(50), nullable=False)
    installation_request = relationship(
        "InstallationRequest", back_populates="packages"
    )


class SoftwareInstallationLog(TestBase):
    __tablename__ = "software_installation_log"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    package_name = Column(String(255), nullable=False)
    package_manager = Column(String(50), nullable=False)
    requested_version = Column(String(100), nullable=True)
    requested_by = Column(String(100), nullable=False)
    installation_id = Column(String(36), nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, server_default="pending", index=True)
    requested_at = Column(DateTime(timezone=True), nullable=False, index=True)
    queued_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    installed_version = Column(String(100), nullable=True)
    success = Column(Boolean, nullable=True)
    error_message = Column(Text, nullable=True)
    installation_log = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    host = relationship("Host", back_populates="software_installation_logs")


# Create test version of AuditLog model for SQLite compatibility
class AuditLog(TestBase):
    __tablename__ = "audit_log"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        index=True,
    )
    user_id = Column(GUID(), nullable=True, index=True)
    username = Column(String(255), nullable=True)
    action_type = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(String(255), nullable=True)
    entity_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)
    details = Column(Text, nullable=True)  # Using Text instead of JSON for SQLite
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    result = Column(String(20), nullable=False)
    error_message = Column(Text, nullable=True)
    category = Column(String(50), nullable=True, index=True)
    entry_type = Column(String(50), nullable=True, index=True)
    integrity_hash = Column(
        String(64), nullable=True
    )  # SHA-256 hash for tamper-evident logging


# Create test version of EnabledPackageManager model for SQLite compatibility
class EnabledPackageManager(TestBase):
    __tablename__ = "enabled_package_manager"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    os_name = Column(String(100), nullable=False, index=True)
    package_manager = Column(String(50), nullable=False, index=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    created_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )


# Create test version of FirewallRole model for SQLite compatibility
class FirewallRole(TestBase):
    __tablename__ = "firewall_role"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True, index=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    created_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    # Relationships
    open_ports = relationship(
        "FirewallRoleOpenPort",
        back_populates="firewall_role",
        cascade="all, delete-orphan",
    )
    host_assignments = relationship(
        "HostFirewallRole",
        back_populates="firewall_role",
        cascade="all, delete-orphan",
    )


# Create test version of FirewallRoleOpenPort model for SQLite compatibility
class FirewallRoleOpenPort(TestBase):
    __tablename__ = "firewall_role_open_port"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    firewall_role_id = Column(
        GUID(),
        ForeignKey("firewall_role.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    port_number = Column(Integer, nullable=False, index=True)
    tcp = Column(Boolean, nullable=False, default=True)
    udp = Column(Boolean, nullable=False, default=False)
    ipv4 = Column(Boolean, nullable=False, default=True)
    ipv6 = Column(Boolean, nullable=False, default=True)
    firewall_role = relationship("FirewallRole", back_populates="open_ports")


# Create test version of HostFirewallRole model for SQLite compatibility
class HostFirewallRole(TestBase):
    __tablename__ = "host_firewall_role"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(),
        ForeignKey("host.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    firewall_role_id = Column(
        GUID(),
        ForeignKey("firewall_role.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    created_by = Column(
        GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    # Relationships
    host = relationship("Host", back_populates="firewall_roles")
    firewall_role = relationship("FirewallRole", back_populates="host_assignments")
