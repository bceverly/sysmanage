"""
Test configuration and fixtures for API tests.

⚠️  CRITICAL MAINTENANCE WARNING ⚠️

This file uses MANUAL model definitions for fast, focused API testing.
When adding new database models, you MUST update BOTH:

1. Main conftest (/tests/conftest.py) - automatic via Alembic migrations
2. This file (/tests/api/v1/conftest.py) - manual SQLite-compatible models

SQLite Compatibility Rules:
- ✅ Use Integer primary keys (not BigInteger) for auto-increment
- ✅ Use String instead of Text for better performance
- ✅ Omit timezone info in DateTime columns

See README.md and TESTING.md for detailed guidelines.
"""

# pylint: disable=too-many-lines

import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

argon2_hasher = PasswordHasher()

from backend.main import app
from backend.persistence import models
from backend.persistence.db import get_engine
from backend.persistence.models.core import GUID


# Test database setup
@pytest.fixture(scope="function")
def test_db():
    """Create a fresh in-memory test database for each test.

    Uses in-memory SQLite with a ``StaticPool`` (one shared connection) rather
    than a temp file.  File-based SQLite is pathologically slow on Windows CI —
    every test paid real file create/fsync/delete plus Windows Defender scanning
    each op, which dominated the Windows backend test wall-clock.  In-memory
    eliminates all of that; ``StaticPool`` keeps the single connection alive so
    the schema created below persists across every session in the test.
    """
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # For SQLite, we need to modify BigInteger columns to Integer for autoincrement to work
    # Create a copy of metadata with modified column types
    from sqlalchemy import Column, ForeignKey, Integer
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import relationship

    TestBase = declarative_base()

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
        user_id = Column(
            GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
        )
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
        user_id = Column(
            GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
        )
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
        content = Column(
            String, nullable=False
        )  # Using String instead of Text for SQLite
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
        host_id = Column(
            GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False
        )
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
        update_type = Column(
            String(20), nullable=False
        )  # security, bugfix, enhancement
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
        host_id = Column(
            GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False
        )
        requested_by = Column(String(100), nullable=False)
        requested_at = Column(DateTime(timezone=True), nullable=False, index=True)
        completed_at = Column(DateTime(timezone=True), nullable=True)
        status = Column(
            String(20), nullable=False, server_default="pending", index=True
        )
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
        host_id = Column(
            GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False
        )
        package_name = Column(String(255), nullable=False)
        package_manager = Column(String(50), nullable=False)
        requested_version = Column(String(100), nullable=True)
        requested_by = Column(String(100), nullable=False)
        installation_id = Column(String(36), nullable=False, unique=True, index=True)
        status = Column(
            String(20), nullable=False, server_default="pending", index=True
        )
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

    # Phase 12.6 — federation_sites mirror.  Tests that exercise
    # registration-key ``site_id`` validation (Phase 12.4) INSERT
    # rows directly via the production SQLAlchemy class, so the
    # test schema must include every column the production INSERT
    # emits — not just the ones the tests read.  Columns kept in
    # lockstep with ``backend/persistence/models/federation.py``.
    class FederationSite(TestBase):
        __tablename__ = "federation_sites"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        name = Column(String(255), nullable=False, unique=True)
        location_label = Column(String(255), nullable=True)
        url = Column(String(512), nullable=False)
        tls_cert_pem = Column(Text, nullable=True)
        # Phase 12 strict trust — out-of-band identity-key pinning.
        site_identity_public_key_pem = Column(Text, nullable=True)
        enrollment_token_hash = Column(String(128), nullable=True)
        enrollment_token_expires_at = Column(DateTime, nullable=True)
        enrolled_at = Column(DateTime, nullable=True)
        sync_bearer_token_hash = Column(String(128), nullable=True)
        coordinator_outbound_bearer_token = Column(Text, nullable=True)
        status = Column(String(32), nullable=False, default="enrolled")
        host_count = Column(Integer, nullable=False, default=0)
        last_sync_at = Column(DateTime, nullable=True)
        last_sync_status = Column(String(32), nullable=True)
        sync_interval_seconds = Column(Integer, nullable=False, default=300)
        # Phase 12.2 — site-reported metadata (lockstep with the real model).
        sysmanage_version = Column(String(32), nullable=True)
        connection_state = Column(String(16), nullable=True)
        capabilities_json = Column(Text, nullable=True)
        last_metadata_at = Column(DateTime, nullable=True)
        agent_version_min = Column(String(32), nullable=True)
        geo_latitude = Column(Float, nullable=True)
        geo_longitude = Column(Float, nullable=True)
        geo_country_code = Column(String(2), nullable=True)
        created_at = Column(DateTime, nullable=False)
        updated_at = Column(DateTime, nullable=False)

    # Phase 8.1 — access groups + registration keys (test-side mirrors).
    class AccessGroup(TestBase):
        __tablename__ = "access_groups"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        name = Column(String(120), nullable=False)
        description = Column(Text, nullable=True)
        parent_id = Column(
            GUID(),
            ForeignKey("access_groups.id", ondelete="SET NULL"),
            nullable=True,
        )
        created_by = Column(
            GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        )
        created_at = Column(DateTime, nullable=True)
        updated_at = Column(DateTime, nullable=True)

    class RegistrationKey(TestBase):
        __tablename__ = "registration_keys"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        name = Column(String(120), nullable=False)
        key = Column(String(128), nullable=False, unique=True)
        access_group_id = Column(
            GUID(),
            ForeignKey("access_groups.id", ondelete="SET NULL"),
            nullable=True,
        )
        # Phase 12.4: federation-site scope.  No FK constraint here
        # because the test TestBase metadata doesn't include the
        # ``federation_sites`` table — referential integrity is
        # enforced in production via the m1fedschema FK; tests just
        # need the column to exist for SELECT/INSERT.
        site_id = Column(GUID(), nullable=True)
        auto_approve = Column(Boolean, nullable=False, default=False)
        revoked = Column(Boolean, nullable=False, default=False)
        max_uses = Column(Integer, nullable=True)
        use_count = Column(Integer, nullable=False, default=0)
        expires_at = Column(DateTime, nullable=True)
        created_by = Column(
            GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        )
        created_at = Column(DateTime, nullable=True)
        last_used_at = Column(DateTime, nullable=True)

    class HostAccessGroup(TestBase):
        __tablename__ = "host_access_groups"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        host_id = Column(
            GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False
        )
        access_group_id = Column(
            GUID(),
            ForeignKey("access_groups.id", ondelete="CASCADE"),
            nullable=False,
        )
        created_at = Column(DateTime, nullable=True)

    class UserAccessGroup(TestBase):
        __tablename__ = "user_access_groups"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        user_id = Column(
            GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
        )
        access_group_id = Column(
            GUID(),
            ForeignKey("access_groups.id", ondelete="CASCADE"),
            nullable=False,
        )
        granted_by = Column(
            GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        )
        created_at = Column(DateTime, nullable=True)

    # Phase 8.2 — upgrade profiles (test-side mirror).
    class UpgradeProfile(TestBase):
        __tablename__ = "upgrade_profiles"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        name = Column(String(120), nullable=False, unique=True)
        description = Column(Text, nullable=True)
        cron = Column(String(200), nullable=False)
        enabled = Column(Boolean, nullable=False, default=True)
        last_run = Column(DateTime, nullable=True)
        last_status = Column(String(40), nullable=True)
        next_run = Column(DateTime, nullable=True)
        security_only = Column(Boolean, nullable=False, default=False)
        package_managers = Column(Text, nullable=True)
        staggered_window_min = Column(Integer, nullable=False, default=0)
        tag_id = Column(
            GUID(), ForeignKey("tags.id", ondelete="SET NULL"), nullable=True
        )
        created_by = Column(
            GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        )
        created_at = Column(DateTime, nullable=True)
        updated_at = Column(DateTime, nullable=True)

    # Phase 11 — air-gap tables (test-side mirrors).  These mirror the
    # production models in ``backend/persistence/models/airgap.py`` —
    # the api conftest uses its own TestBase metadata so we have to
    # redeclare the schema for SQLite parity.
    class AirgapCollectionRun(TestBase):
        __tablename__ = "airgap_collection_run"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        iso_label = Column(String(80), nullable=False)
        media_size_bytes = Column(BigInteger, nullable=False, default=4_700_000_000)
        include_cve = Column(Boolean, nullable=False, default=True)
        include_compliance = Column(Boolean, nullable=False, default=True)
        status = Column(String(40), nullable=False, default="QUEUED")
        started_at = Column(DateTime, nullable=True)
        completed_at = Column(DateTime, nullable=True)
        error_message = Column(Text, nullable=True)
        # Phase 11.1 follow-up — cron_schedule for re-firing runs via tick.
        cron_schedule = Column(String(200), nullable=True)
        # Phase 11 B3 — delta runs reference their parent.  Self-FK
        # mirrors the real schema; included so the API's ORDER BY
        # SELECT doesn't crash against the SQLite test database.
        parent_run_id = Column(
            GUID(),
            ForeignKey("airgap_collection_run.id", ondelete="SET NULL"),
            nullable=True,
        )
        created_at = Column(DateTime, nullable=True)
        created_by = Column(
            GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        )
        # Phase 12 — orchestrator + optical burn opt-in.  Mirror the real
        # schema or every ``SELECT * FROM airgap_collection_run`` blows
        # up on the test SQLite session with "no such column".
        worker_message_id = Column(String(80), nullable=True)
        burn_device = Column(String(200), nullable=True)

    class AirgapCollectionSchedule(TestBase):
        __tablename__ = "airgap_collection_schedule"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        name = Column(String(120), nullable=False, unique=True)
        cron = Column(String(200), nullable=False)
        enabled = Column(Boolean, nullable=False, default=True)
        target_request_json = Column(Text, nullable=False)
        last_run = Column(DateTime, nullable=True)
        last_status = Column(String(40), nullable=True)
        last_run_id = Column(
            GUID(),
            ForeignKey("airgap_collection_run.id", ondelete="SET NULL"),
            nullable=True,
        )
        next_run = Column(DateTime, nullable=True)
        created_at = Column(DateTime, nullable=True)
        updated_at = Column(DateTime, nullable=True)

    # Phase 11 — per-distro target rows owned by a collection run.
    # The runs cascade-deletes them via the relationship; the table
    # must exist or DELETE on the parent row crashes the test session.
    class AirgapCollectionTarget(TestBase):
        __tablename__ = "airgap_collection_target"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        run_id = Column(
            GUID(),
            ForeignKey("airgap_collection_run.id", ondelete="CASCADE"),
            nullable=False,
        )
        distro = Column(String(40), nullable=False)
        version = Column(String(40), nullable=False)
        repos = Column(Text, nullable=True)
        byte_count = Column(BigInteger, nullable=True)
        file_count = Column(Integer, nullable=True)
        status = Column(String(40), nullable=True)
        # Phase 12 Option-B — each target binds to a specific mirror
        # and the snapshot of that mirror the orchestrator pinned.
        mirror_id = Column(
            GUID(),
            ForeignKey("mirror_repository.id", ondelete="SET NULL"),
            nullable=True,
        )
        source_snapshot_id = Column(
            GUID(),
            ForeignKey("mirror_snapshot.id", ondelete="SET NULL"),
            nullable=True,
        )

    # Phase 11 — produced-media manifests (test-side mirror for the
    # collector runs API).  Mirrors backend/persistence/models/airgap.py
    # ``AirgapMediaManifest``; columns are kept minimal for SQLite parity.
    class AirgapMediaManifest(TestBase):
        __tablename__ = "airgap_media_manifest"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        run_id = Column(
            GUID(),
            ForeignKey("airgap_collection_run.id", ondelete="CASCADE"),
            nullable=False,
        )
        disc_index = Column(Integer, nullable=False, default=1)
        disc_count = Column(Integer, nullable=False, default=1)
        iso_path = Column(String(500), nullable=False)
        iso_sha256 = Column(String(64), nullable=False)
        iso_size_bytes = Column(BigInteger, nullable=False)
        manifest_json = Column(Text, nullable=False)
        signature = Column(Text, nullable=False)
        signer_fingerprint = Column(String(128), nullable=False)
        signature_algorithm = Column(String(40), nullable=False, default="ed25519")
        format_version = Column(Integer, nullable=False, default=1)
        created_at = Column(DateTime, nullable=True)

    # Phase 8.3 — package compliance (test-side mirrors).
    from sqlalchemy import JSON as _JSON  # local import — only needed here

    class PackageProfile(TestBase):
        __tablename__ = "package_profiles"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        name = Column(String(120), nullable=False, unique=True)
        description = Column(Text, nullable=True)
        enabled = Column(Boolean, nullable=False, default=True)
        created_by = Column(
            GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        )
        created_at = Column(DateTime, nullable=True)
        updated_at = Column(DateTime, nullable=True)
        constraints = relationship(
            "PackageProfileConstraint",
            cascade="all, delete-orphan",
        )

    class PackageProfileConstraint(TestBase):
        __tablename__ = "package_profile_constraints"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        profile_id = Column(
            GUID(),
            ForeignKey("package_profiles.id", ondelete="CASCADE"),
            nullable=False,
        )
        package_name = Column(String(255), nullable=False)
        package_manager = Column(String(60), nullable=True)
        constraint_type = Column(String(20), nullable=False, default="REQUIRED")
        version_op = Column(String(4), nullable=True)
        version = Column(String(120), nullable=True)
        created_at = Column(DateTime, nullable=True)

    class HostPackageComplianceStatus(TestBase):
        __tablename__ = "host_package_compliance_status"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        host_id = Column(
            GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False
        )
        profile_id = Column(
            GUID(),
            ForeignKey("package_profiles.id", ondelete="CASCADE"),
            nullable=False,
        )
        status = Column(String(20), nullable=False, default="PENDING")
        violations = Column(_JSON, nullable=True)
        last_scan_at = Column(DateTime, nullable=True)
        created_at = Column(DateTime, nullable=True)
        updated_at = Column(DateTime, nullable=True)

    # Phase 8.7 — report branding singleton, custom report templates,
    # and dynamic-secret leases.
    class ReportBranding(TestBase):
        __tablename__ = "report_branding"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        company_name = Column(String(255), nullable=True)
        header_text = Column(String(500), nullable=True)
        logo_data = Column(LargeBinary, nullable=True)
        logo_mime_type = Column(String(80), nullable=True)
        updated_at = Column(DateTime, nullable=True)
        updated_by = Column(
            GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        )

    class ReportTemplate(TestBase):
        __tablename__ = "report_template"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        name = Column(String(255), nullable=False, unique=True)
        description = Column(Text, nullable=True)
        base_report_type = Column(String(50), nullable=False)
        selected_fields = Column(_JSON, nullable=False)
        enabled = Column(Boolean, nullable=False, default=True)
        created_by = Column(
            GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        )
        created_at = Column(DateTime, nullable=True)
        updated_at = Column(DateTime, nullable=True)

    class AirGapBundle(TestBase):
        __tablename__ = "airgap_bundle"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        product = Column(String(16), nullable=False)
        status = Column(String(16), nullable=False, default="queued")
        created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
        started_at = Column(DateTime, nullable=True)
        completed_at = Column(DateTime, nullable=True)
        file_path = Column(Text, nullable=True)
        size_bytes = Column(BigInteger, nullable=True)
        log_path = Column(Text, nullable=True)
        error_message = Column(Text, nullable=True)
        version = Column(String(64), nullable=True)
        created_by_user_id = Column(
            GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        )

    class DynamicSecretLease(TestBase):
        __tablename__ = "dynamic_secret_lease"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        name = Column(String(255), nullable=False)
        kind = Column(String(40), nullable=False)
        backend_role = Column(String(255), nullable=False)
        vault_lease_id = Column(String(500), nullable=True)
        ttl_seconds = Column(Integer, nullable=True)
        issued_at = Column(DateTime, nullable=False)
        expires_at = Column(DateTime, nullable=True)
        revoked_at = Column(DateTime, nullable=True)
        status = Column(String(20), nullable=False, default="ACTIVE")
        secret_metadata = Column(_JSON, nullable=True)
        issued_by = Column(
            GUID(), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        )
        note = Column(Text, nullable=True)

    # Phase 10.3: MFA tables.  The login flow queries
    # ``user_mfa_enrollment`` on every successful password verify, so
    # the table has to exist in the test fixture even for tests that
    # don't exercise MFA themselves.
    class UserMfaEnrollment(TestBase):
        __tablename__ = "user_mfa_enrollment"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        user_id = Column(
            GUID(),
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        )
        totp_secret_encrypted = Column(Text, nullable=False)
        backup_codes_hashed = Column(_JSON, nullable=False, default=list)
        enrolled_at = Column(DateTime, nullable=False)
        last_used_at = Column(DateTime, nullable=True)
        last_used_method = Column(String(20), nullable=True)

    class MfaSettings(TestBase):
        __tablename__ = "mfa_settings"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        issuer_name = Column(String(120), nullable=False, default="SysManage")
        totp_digits = Column(Integer, nullable=False, default=6)
        totp_period_seconds = Column(Integer, nullable=False, default=30)
        backup_code_count = Column(Integer, nullable=False, default=10)
        admin_required = Column(Boolean, nullable=False, default=False)
        grace_period_days = Column(Integer, nullable=False, default=14)
        updated_at = Column(DateTime, nullable=True)
        updated_by = Column(
            GUID(),
            ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        )

    # Phase 10.4 — repository-mirroring tables.
    class MirrorRepository(TestBase):
        __tablename__ = "mirror_repository"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        name = Column(String(120), unique=True, nullable=False)
        package_manager = Column(String(20), nullable=False)
        upstream_url = Column(String(500), nullable=False)
        suite = Column(String(80), nullable=True)
        components = Column(String(200), nullable=True)
        architectures = Column(String(120), nullable=True)
        repoid = Column(String(120), nullable=True)
        gpgkey_url = Column(String(500), nullable=True)
        repo_alias = Column(String(120), nullable=True)
        release = Column(String(80), nullable=True)
        signing_key_url = Column(String(500), nullable=True)
        bandwidth_cap_kbps = Column(Integer, nullable=False, default=0)
        sync_cron = Column(String(120), nullable=False, default="0 4 * * *")
        network_tier = Column(String(40), nullable=True)
        enabled = Column(Boolean, nullable=False, default=True)
        host_id = Column(
            GUID(),
            ForeignKey("host.id", ondelete="CASCADE"),
            nullable=False,
        )
        platform_config_id = Column(
            GUID(),
            ForeignKey("mirror_platform_config.id", ondelete="SET NULL"),
            nullable=True,
        )
        known_version_id = Column(
            GUID(),
            ForeignKey("mirror_known_version.id", ondelete="SET NULL"),
            nullable=True,
        )
        last_sync_at = Column(DateTime, nullable=True)
        last_sync_status = Column(String(40), nullable=True)
        last_sync_error = Column(Text, nullable=True)
        next_sync_at = Column(DateTime, nullable=True)
        created_at = Column(DateTime, nullable=True)
        updated_at = Column(DateTime, nullable=True)

    class MirrorKnownVersion(TestBase):
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
        created_at = Column(DateTime, nullable=True)

    class HostDefaultMirror(TestBase):
        __tablename__ = "host_default_mirror"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        platform = Column(String(20), nullable=False)
        version_key = Column(String(80), nullable=False)
        os_family = Column(String(40), nullable=False)
        mirror_id = Column(
            GUID(),
            ForeignKey("mirror_repository.id", ondelete="SET NULL"),
            nullable=True,
        )
        updated_at = Column(DateTime, nullable=True)

    class MirrorPlatformConfig(TestBase):
        __tablename__ = "mirror_platform_config"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        platform = Column(String(20), nullable=False)
        host_id = Column(
            GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False
        )
        mirror_root_path = Column(String(500), nullable=False, default="/var/mirror")
        integrity_check_cadence_hours = Column(Integer, nullable=False, default=24)
        retention_window_days = Column(Integer, nullable=False, default=30)
        default_bandwidth_cap_kbps = Column(Integer, nullable=False, default=0)
        snapshot_count_to_keep = Column(Integer, nullable=False, default=10)
        created_at = Column(DateTime, nullable=True)
        updated_at = Column(DateTime, nullable=True)

    class MirrorSnapshot(TestBase):
        __tablename__ = "mirror_snapshot"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        repository_id = Column(
            GUID(),
            ForeignKey("mirror_repository.id", ondelete="CASCADE"),
            nullable=False,
        )
        snapshot_id = Column(String(80), nullable=False)
        taken_at = Column(DateTime, nullable=False)
        size_bytes = Column(Integer, nullable=True)
        file_count = Column(Integer, nullable=True)
        manifest = Column(_JSON, nullable=True)
        retention_until = Column(DateTime, nullable=True)
        notes = Column(Text, nullable=True)

    class MirrorSettings(TestBase):
        __tablename__ = "mirror_settings"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        mirror_root_path = Column(String(500), nullable=False, default="/var/mirror")
        integrity_check_cadence_hours = Column(Integer, nullable=False, default=24)
        retention_window_days = Column(Integer, nullable=False, default=30)
        default_bandwidth_cap_kbps = Column(Integer, nullable=False, default=0)
        snapshot_count_to_keep = Column(Integer, nullable=False, default=10)
        updated_at = Column(DateTime, nullable=True)
        updated_by = Column(
            GUID(),
            ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        )

    # Phase 10.4.1 — mirror setup status (one row per host).
    class MirrorSetupStatus(TestBase):
        __tablename__ = "mirror_setup_status"
        host_id = Column(
            GUID(), ForeignKey("host.id", ondelete="CASCADE"), primary_key=True
        )
        tools = Column(_JSON, nullable=False, default=dict)
        platform = Column(String(40), nullable=True)
        distro = Column(String(40), nullable=True)
        last_check_at = Column(DateTime, nullable=True)
        last_check_message_id = Column(String(36), nullable=True)
        last_check_error = Column(Text, nullable=True)
        install_status = Column(String(20), nullable=False, default="idle")
        last_install_at = Column(DateTime, nullable=True)
        last_install_message_id = Column(String(36), nullable=True)
        last_install_error = Column(Text, nullable=True)
        created_at = Column(DateTime, nullable=True)
        updated_at = Column(DateTime, nullable=True)

    # Phase 10.5 — external IdP tables.
    class ExternalIdpProvider(TestBase):
        __tablename__ = "external_idp_provider"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        name = Column(String(120), unique=True, nullable=False)
        type = Column(String(20), nullable=False)
        enabled = Column(Boolean, nullable=False, default=True)
        ldap_server_url = Column(String(500), nullable=True)
        ldap_bind_dn = Column(String(500), nullable=True)
        ldap_bind_password_secret_id = Column(String(255), nullable=True)
        ldap_user_search_base = Column(String(500), nullable=True)
        ldap_user_search_filter = Column(String(500), nullable=True)
        ldap_group_search_base = Column(String(500), nullable=True)
        ldap_group_search_filter = Column(String(500), nullable=True)
        ldap_tls_ca_bundle_path = Column(String(500), nullable=True)
        ldap_connection_timeout = Column(Integer, nullable=False, default=10)
        oidc_issuer_url = Column(String(500), nullable=True)
        oidc_client_id = Column(String(255), nullable=True)
        oidc_client_secret_secret_id = Column(String(255), nullable=True)
        oidc_redirect_uri = Column(String(500), nullable=True)
        oidc_scopes = Column(
            String(500), nullable=False, default="openid profile email"
        )
        oidc_discovery_url = Column(String(500), nullable=True)
        oidc_group_claim = Column(String(120), nullable=False, default="groups")
        created_at = Column(DateTime, nullable=True)
        updated_at = Column(DateTime, nullable=True)

    class IdpRoleMapping(TestBase):
        __tablename__ = "idp_role_mapping"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        provider_id = Column(
            GUID(),
            ForeignKey("external_idp_provider.id", ondelete="CASCADE"),
            nullable=False,
        )
        external_group = Column(String(500), nullable=False)
        role_name = Column(String(120), nullable=False)
        default_for_unmapped = Column(Boolean, nullable=False, default=False)
        created_at = Column(DateTime, nullable=True)

    class ExternalIdpSettings(TestBase):
        __tablename__ = "external_idp_settings"
        id = Column(GUID(), primary_key=True, default=uuid.uuid4)
        local_account_fallback = Column(Boolean, nullable=False, default=True)
        max_failed_attempts = Column(Integer, nullable=False, default=5)
        updated_at = Column(DateTime, nullable=True)
        updated_by = Column(
            GUID(),
            ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        )

    # Create all tables with test models
    TestBase.metadata.create_all(bind=test_engine)

    # Populate security role groups and roles for testing
    # Create a session to populate initial data
    SessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=test_engine)
    session = SessionLocal()
    try:
        # Create security role groups with fixed UUIDs
        role_groups = [
            SecurityRoleGroup(
                id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                name="Host",
                description="Permissions related to host management",
            ),
            SecurityRoleGroup(
                id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                name="Package",
                description="Permissions related to package management",
            ),
            SecurityRoleGroup(
                id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
                name="Secrets",
                description="Permissions related to secret management",
            ),
            SecurityRoleGroup(
                id=uuid.UUID("00000000-0000-0000-0000-000000000004"),
                name="User",
                description="Permissions related to user management",
            ),
            SecurityRoleGroup(
                id=uuid.UUID("00000000-0000-0000-0000-000000000005"),
                name="Scripts",
                description="Permissions related to script management",
            ),
            SecurityRoleGroup(
                id=uuid.UUID("00000000-0000-0000-0000-000000000006"),
                name="Reports",
                description="Permissions related to report generation",
            ),
            SecurityRoleGroup(
                id=uuid.UUID("00000000-0000-0000-0000-000000000007"),
                name="Integrations",
                description="Permissions related to system integrations",
            ),
            SecurityRoleGroup(
                id=uuid.UUID("00000000-0000-0000-0000-000000000008"),
                name="Ubuntu Pro",
                description="Permissions related to Ubuntu Pro management",
            ),
            SecurityRoleGroup(
                id=uuid.UUID("00000000-0000-0000-0000-000000000010"),
                name="Settings",
                description="Permissions related to system settings",
            ),
        ]
        for group in role_groups:
            session.add(group)
        session.commit()

        # Create security roles - using the exact same UUIDs as the migration
        roles_data = [
            # Host group
            (
                "10000000-0000-0000-0000-000000000001",
                "Approve Host Registration",
                "Approve new host registrations",
                "00000000-0000-0000-0000-000000000001",
            ),
            (
                "10000000-0000-0000-0000-000000000002",
                "Delete Host",
                "Delete hosts from the system",
                "00000000-0000-0000-0000-000000000001",
            ),
            (
                "10000000-0000-0000-0000-000000000003",
                "View Host Details",
                "View detailed host information",
                "00000000-0000-0000-0000-000000000001",
            ),
            (
                "10000000-0000-0000-0000-000000000004",
                "Reboot Host",
                "Reboot hosts",
                "00000000-0000-0000-0000-000000000001",
            ),
            (
                "10000000-0000-0000-0000-000000000005",
                "Shutdown Host",
                "Shutdown hosts",
                "00000000-0000-0000-0000-000000000001",
            ),
            (
                "10000000-0000-0000-0000-000000000006",
                "Edit Tags",
                "Edit host tags",
                "00000000-0000-0000-0000-000000000001",
            ),
            (
                "10000000-0000-0000-0000-000000000010",
                "Stop Host Service",
                "Stop services on hosts",
                "00000000-0000-0000-0000-000000000001",
            ),
            (
                "10000000-0000-0000-0000-000000000011",
                "Start Host Service",
                "Start services on hosts",
                "00000000-0000-0000-0000-000000000001",
            ),
            (
                "10000000-0000-0000-0000-000000000012",
                "Restart Host Service",
                "Restart services on hosts",
                "00000000-0000-0000-0000-000000000001",
            ),
            # Package group
            (
                "10000000-0000-0000-0000-000000000007",
                "Add Package",
                "Add packages to hosts",
                "00000000-0000-0000-0000-000000000002",
            ),
            (
                "10000000-0000-0000-0000-000000000020",
                "Apply Software Update",
                "Apply software updates to hosts",
                "00000000-0000-0000-0000-000000000002",
            ),
            (
                "10000000-0000-0000-0000-000000000021",
                "Apply Host OS Upgrade",
                "Apply OS upgrades to hosts",
                "00000000-0000-0000-0000-000000000002",
            ),
            # Secrets group
            (
                "10000000-0000-0000-0000-000000000008",
                "Deploy SSH Key",
                "Deploy SSH keys to hosts",
                "00000000-0000-0000-0000-000000000003",
            ),
            (
                "10000000-0000-0000-0000-000000000009",
                "Deploy Certificate",
                "Deploy certificates to hosts",
                "00000000-0000-0000-0000-000000000003",
            ),
            (
                "10000000-0000-0000-0000-000000000022",
                "Add Secret",
                "Add secrets to the vault",
                "00000000-0000-0000-0000-000000000003",
            ),
            (
                "10000000-0000-0000-0000-000000000023",
                "Delete Secret",
                "Delete secrets from the vault",
                "00000000-0000-0000-0000-000000000003",
            ),
            (
                "10000000-0000-0000-0000-000000000024",
                "Edit Secret",
                "Edit existing secrets",
                "00000000-0000-0000-0000-000000000003",
            ),
            (
                "10000000-0000-0000-0000-000000000032",
                "Stop Vault",
                "Stop the vault service",
                "00000000-0000-0000-0000-000000000003",
            ),
            (
                "10000000-0000-0000-0000-000000000033",
                "Start Vault",
                "Start the vault service",
                "00000000-0000-0000-0000-000000000003",
            ),
            # User group
            (
                "10000000-0000-0000-0000-000000000015",
                "Add User",
                "Add new users to the system",
                "00000000-0000-0000-0000-000000000004",
            ),
            (
                "10000000-0000-0000-0000-000000000016",
                "Edit User",
                "Edit existing users",
                "00000000-0000-0000-0000-000000000004",
            ),
            (
                "10000000-0000-0000-0000-000000000017",
                "Lock User",
                "Lock user accounts",
                "00000000-0000-0000-0000-000000000004",
            ),
            (
                "10000000-0000-0000-0000-000000000018",
                "Unlock User",
                "Unlock user accounts",
                "00000000-0000-0000-0000-000000000004",
            ),
            (
                "10000000-0000-0000-0000-000000000019",
                "Delete User",
                "Delete users from the system",
                "00000000-0000-0000-0000-000000000004",
            ),
            (
                "10000000-0000-0000-0000-000000000036",
                "Reset User Password",
                "Reset user passwords",
                "00000000-0000-0000-0000-000000000004",
            ),
            # Scripts group
            (
                "10000000-0000-0000-0000-000000000025",
                "Add Script",
                "Add new scripts",
                "00000000-0000-0000-0000-000000000005",
            ),
            (
                "10000000-0000-0000-0000-000000000037",
                "Edit Script",
                "Edit existing scripts",
                "00000000-0000-0000-0000-000000000005",
            ),
            (
                "10000000-0000-0000-0000-000000000026",
                "Delete Script",
                "Delete scripts",
                "00000000-0000-0000-0000-000000000005",
            ),
            (
                "10000000-0000-0000-0000-000000000027",
                "Run Script",
                "Execute scripts on hosts",
                "00000000-0000-0000-0000-000000000005",
            ),
            (
                "10000000-0000-0000-0000-000000000028",
                "Delete Script Execution",
                "Delete script execution history",
                "00000000-0000-0000-0000-000000000005",
            ),
            # Reports group
            (
                "10000000-0000-0000-0000-000000000029",
                "View Report",
                "View system reports",
                "00000000-0000-0000-0000-000000000006",
            ),
            (
                "10000000-0000-0000-0000-000000000030",
                "Generate PDF Report",
                "Generate PDF reports",
                "00000000-0000-0000-0000-000000000006",
            ),
            # Integrations group
            (
                "10000000-0000-0000-0000-000000000031",
                "Delete Queue Message",
                "Delete messages from the queue",
                "00000000-0000-0000-0000-000000000007",
            ),
            (
                "10000000-0000-0000-0000-000000000034",
                "Enable Grafana Integration",
                "Enable and configure Grafana integration",
                "00000000-0000-0000-0000-000000000007",
            ),
            # Ubuntu Pro group
            (
                "10000000-0000-0000-0000-000000000013",
                "Attach Ubuntu Pro",
                "Attach Ubuntu Pro to hosts",
                "00000000-0000-0000-0000-000000000008",
            ),
            (
                "10000000-0000-0000-0000-000000000014",
                "Detach Ubuntu Pro",
                "Detach Ubuntu Pro from hosts",
                "00000000-0000-0000-0000-000000000008",
            ),
            (
                "10000000-0000-0000-0000-000000000035",
                "Change Ubuntu Pro Master Key",
                "Change the Ubuntu Pro master key",
                "00000000-0000-0000-0000-000000000008",
            ),
            # Settings group - Default Repositories
            (
                "10000000-0000-0000-0000-000000000060",
                "Add Default Repository",
                "Add default repositories to the system",
                "00000000-0000-0000-0000-000000000010",
            ),
            (
                "10000000-0000-0000-0000-000000000061",
                "Remove Default Repository",
                "Remove default repositories from the system",
                "00000000-0000-0000-0000-000000000010",
            ),
            (
                "10000000-0000-0000-0000-000000000062",
                "View Default Repositories",
                "View default repositories in the system",
                "00000000-0000-0000-0000-000000000010",
            ),
            # Settings group - Enabled Package Managers
            (
                "10000000-0000-0000-0000-000000000063",
                "Add Enabled Package Manager",
                "Add enabled package managers to the system",
                "00000000-0000-0000-0000-000000000010",
            ),
            (
                "10000000-0000-0000-0000-000000000064",
                "Remove Enabled Package Manager",
                "Remove enabled package managers from the system",
                "00000000-0000-0000-0000-000000000010",
            ),
            (
                "10000000-0000-0000-0000-000000000065",
                "View Enabled Package Managers",
                "View enabled package managers in the system",
                "00000000-0000-0000-0000-000000000010",
            ),
            # Settings group - Firewall Roles
            (
                "10000000-0000-0000-0000-000000000070",
                "Add Firewall Role",
                "Add firewall roles to the system",
                "00000000-0000-0000-0000-000000000010",
            ),
            (
                "10000000-0000-0000-0000-000000000071",
                "Edit Firewall Role",
                "Edit firewall roles in the system",
                "00000000-0000-0000-0000-000000000010",
            ),
            (
                "10000000-0000-0000-0000-000000000072",
                "Delete Firewall Role",
                "Delete firewall roles from the system",
                "00000000-0000-0000-0000-000000000010",
            ),
            (
                "10000000-0000-0000-0000-000000000073",
                "View Firewall Roles",
                "View firewall roles in the system",
                "00000000-0000-0000-0000-000000000010",
            ),
            # Host group — host firewall role assignment
            (
                "10000000-0000-0000-0000-000000000074",
                "Assign Host Firewall Roles",
                "Assign firewall roles to hosts",
                "00000000-0000-0000-0000-000000000001",
            ),
        ]

        for role_id, name, description, group_id in roles_data:
            role = SecurityRole(
                id=uuid.UUID(role_id),
                name=name,
                description=description,
                group_id=uuid.UUID(group_id),
            )
            session.add(role)
        session.commit()

        # Note: We don't create an admin user here because some tests create their own
        # admin@sysmanage.org user. Tests that need an admin user with roles should
        # use the create_admin_user fixture or create their own user.

    finally:
        session.close()

    # Monkey patch models to use test models during testing
    # ⚠️  ADD NEW MODEL MONKEY PATCHES HERE: Store original and patch models!
    original_host = models.Host
    original_user = models.User
    original_security_role_group = models.SecurityRoleGroup
    original_security_role = models.SecurityRole
    original_user_security_role = models.UserSecurityRole
    original_tag = models.Tag
    original_host_tag = models.HostTag
    original_password_reset_token = models.PasswordResetToken
    original_message_queue = models.MessageQueue
    original_ubuntu_pro_settings = models.UbuntuProSettings
    original_package_update = models.PackageUpdate
    original_available_package = models.AvailablePackage
    original_installation_request = models.InstallationRequest
    original_installation_package = models.InstallationPackage
    original_software_installation_log = models.SoftwareInstallationLog
    original_audit_log = models.AuditLog
    original_enabled_package_manager = models.EnabledPackageManager
    original_firewall_role = models.FirewallRole
    original_firewall_role_open_port = models.FirewallRoleOpenPort
    models.Host = Host
    models.User = User
    models.SecurityRoleGroup = SecurityRoleGroup
    models.SecurityRole = SecurityRole
    models.UserSecurityRole = UserSecurityRole
    models.Tag = Tag
    models.HostTag = HostTag
    models.PasswordResetToken = PasswordResetToken
    models.MessageQueue = MessageQueue
    models.UbuntuProSettings = UbuntuProSettings
    models.PackageUpdate = PackageUpdate
    models.AvailablePackage = AvailablePackage
    models.InstallationRequest = InstallationRequest
    models.InstallationPackage = InstallationPackage
    models.SoftwareInstallationLog = SoftwareInstallationLog
    models.AuditLog = AuditLog
    models.EnabledPackageManager = EnabledPackageManager
    models.FirewallRole = FirewallRole
    models.FirewallRoleOpenPort = FirewallRoleOpenPort
    models.HostFirewallRole = HostFirewallRole

    # Override the get_engine dependency
    def override_get_engine():
        return test_engine

    # Create a shared sessionmaker for consistent sessions
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=True, bind=test_engine
    )

    # Override the get_db dependency for tag tests
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_engine] = override_get_engine
    from backend.persistence.db import get_db

    app.dependency_overrides[get_db] = override_get_db

    # Store the sessionmaker for the session fixture to use
    test_engine._testing_sessionmaker = TestingSessionLocal

    yield test_engine

    # Restore original models
    # ⚠️  ADD NEW MODEL CLEANUP HERE: Restore original model classes!
    models.Host = original_host
    models.User = original_user
    models.SecurityRoleGroup = original_security_role_group
    models.SecurityRole = original_security_role
    models.UserSecurityRole = original_user_security_role
    models.Tag = original_tag
    models.HostTag = original_host_tag
    models.PasswordResetToken = original_password_reset_token
    models.MessageQueue = original_message_queue
    models.UbuntuProSettings = original_ubuntu_pro_settings
    models.PackageUpdate = original_package_update
    models.AvailablePackage = original_available_package
    models.InstallationRequest = original_installation_request
    models.InstallationPackage = original_installation_package
    models.SoftwareInstallationLog = original_software_installation_log
    models.AuditLog = original_audit_log
    models.EnabledPackageManager = original_enabled_package_manager
    models.FirewallRole = original_firewall_role
    models.FirewallRoleOpenPort = original_firewall_role_open_port

    # Clean up database connections.  In-memory DB: disposing the engine drops
    # the StaticPool's single connection and the schema with it — no temp file
    # to close/unlink, and no Windows file-handle-release wait needed.
    test_engine.dispose()

    app.dependency_overrides.clear()


@pytest.fixture
def client(test_db):
    """Create a FastAPI test client."""
    from contextlib import asynccontextmanager

    # Mock the FastAPI app lifespan to prevent service startup during tests
    @asynccontextmanager
    async def mock_lifespan(app):
        # Mock startup - do nothing
        yield
        # Mock shutdown - do nothing

    # Replace the lifespan manager
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = mock_lifespan

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # Restore original lifespan
        app.router.lifespan_context = original_lifespan


@pytest.fixture
def session(test_db):
    """Create a database session for testing."""
    # Use the same sessionmaker that the API uses for consistency
    SessionLocal = getattr(test_db, "_testing_sessionmaker", None)
    if SessionLocal is None:
        # Fallback if attribute not set
        SessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=test_db)

    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def test_user_data():
    """Sample user data for testing."""
    return {
        "userid": "test@example.com",
        "password": "TestPassword123!",
        "active": True,
    }


@pytest.fixture
def test_host_data():
    """Sample host data for testing."""
    return {
        "active": True,
        "fqdn": "test.example.com",
        "hostname": "test",
        "ipv4": "192.168.1.100",
        "ipv6": "2001:db8::1",
        "platform": "Linux",
        "platform_release": "5.4.0",
        "platform_version": "Ubuntu 20.04",
        "architecture": "x86_64",
        "processor": "Intel Core i7",
    }


@pytest.fixture
def admin_token(mock_config):
    """Create a valid admin JWT token for testing."""
    import time

    import jwt

    # Use the mocked config to create token
    config_data = mock_config
    payload = {
        "user_id": "admin@sysmanage.org",
        "expires": time.time() + int(config_data["security"]["jwt_auth_timeout"]),
    }

    # Encode the token using mocked config
    token = jwt.encode(
        payload,
        config_data["security"]["jwt_secret"],
        algorithm=config_data["security"]["jwt_algorithm"],
    )

    return token


@pytest.fixture
def auth_headers(admin_token, create_admin_user_with_roles):
    """
    Create authorization headers with admin token.

    This fixture automatically creates an admin user with all security roles
    to ensure the JWT token is valid and the user has all necessary permissions.
    """
    from backend.auth.auth_bearer import get_current_user

    # Override get_current_user to return the admin user ID
    def override_get_current_user():
        return "admin@sysmanage.org"

    app.dependency_overrides[get_current_user] = override_get_current_user

    yield {"Authorization": f"Bearer {admin_token}"}

    # Clean up the override
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]


@pytest.fixture(autouse=True)
def mock_config(test_db):
    """Mock the configuration system for all tests."""
    config_data = {
        "database": {
            "user": "test",
            "password": "test",
            "host": "localhost",
            "port": 5432,
            "name": "test",
        },
        "security": {
            "password_salt": "test_salt",
            "admin_userid": "admin@sysmanage.org",
            "admin_password": "admin_pass",
            "jwt_secret": "test_jwt_secret_key_for_testing_purposes_32bytes",
            "jwt_algorithm": "HS256",
            "jwt_auth_timeout": 3600,
            "jwt_refresh_timeout": 86400,
        },
    }

    with patch("backend.config.config.get_config", return_value=config_data), patch(
        "backend.persistence.db.get_engine", return_value=test_db
    ), patch(
        "backend.auth.auth_handler.JWT_SECRET", config_data["security"]["jwt_secret"]
    ), patch(
        "backend.auth.auth_handler.JWT_ALGORITHM",
        config_data["security"]["jwt_algorithm"],
    ), patch(
        "backend.auth.auth_handler.the_config", config_data
    ):
        yield config_data


@pytest.fixture
def mock_login_security():
    """Mock the login security system."""
    mock_security = Mock()
    mock_security.validate_login_attempt.return_value = (True, "")
    mock_security.record_failed_login.return_value = None
    mock_security.record_successful_login.return_value = None
    mock_security.is_user_account_locked.return_value = False
    mock_security.record_failed_login_for_user.return_value = False
    mock_security.reset_failed_login_attempts.return_value = None

    with patch("backend.api.auth.login_security", mock_security):
        with patch("backend.api.user.login_security", mock_security):
            yield mock_security


@pytest.fixture
def mock_current_user(session):
    """Mock the current user dependency for authenticated tests."""
    from backend.auth.auth_bearer import get_current_user

    # Return a string userid instead of a Mock object to avoid database binding issues
    test_userid = "test@example.com"

    # Create test user with all roles if it doesn't exist
    existing_user = (
        session.query(models.User).filter(models.User.userid == test_userid).first()
    )

    if not existing_user:
        # Create test user
        password_hasher = PasswordHasher()
        test_user = models.User(
            userid=test_userid,
            hashed_password=password_hasher.hash("testpassword"),
            first_name="Test",
            last_name="User",
            active=True,
            is_admin=False,
        )
        session.add(test_user)
        session.commit()
        session.refresh(test_user)

        # Assign all roles to test user
        all_roles = session.query(models.SecurityRole).all()
        for role in all_roles:
            user_role = models.UserSecurityRole(
                user_id=test_user.id,
                role_id=role.id,
                granted_by=test_user.id,
            )
            session.add(user_role)
        session.commit()

        # Load role cache for quick permission checking
        test_user.load_role_cache(session)
    else:
        # Load role cache if user already exists
        existing_user.load_role_cache(session)

    def override_get_current_user():
        return test_userid

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield test_userid
    # Clean up the override
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]


@pytest.fixture
def create_admin_user_with_roles(session):
    """
    Create an admin user with all security roles.

    This fixture should be used by tests that require a fully-privileged admin user
    for testing RBAC-protected endpoints. The user created has the email
    'admin@sysmanage.org' and all 35 security roles assigned.

    Returns:
        User: The created admin user object with role cache loaded
    """
    # Check if admin user already exists (some tests create it themselves)
    existing_admin = (
        session.query(models.User)
        .filter(models.User.userid == "admin@sysmanage.org")
        .first()
    )

    if existing_admin:
        # Load role cache and return existing user
        existing_admin.load_role_cache(session)
        return existing_admin

    # Create admin user
    password_hasher = PasswordHasher()
    admin_user = models.User(
        userid="admin@sysmanage.org",
        hashed_password=password_hasher.hash("admin_pass"),
        first_name="Admin",
        last_name="User",
        active=True,
        is_admin=True,
    )
    session.add(admin_user)
    session.commit()
    session.refresh(admin_user)

    # Get all security roles and assign them to admin
    all_roles = session.query(models.SecurityRole).all()
    for role in all_roles:
        user_role = models.UserSecurityRole(
            user_id=admin_user.id,
            role_id=role.id,
            granted_by=admin_user.id,
        )
        session.add(user_role)
    session.commit()

    # Load role cache for quick permission checking
    admin_user.load_role_cache(session)

    return admin_user
