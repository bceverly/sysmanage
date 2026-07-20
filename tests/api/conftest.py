# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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

import uuid
from unittest.mock import Mock, patch

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.persistence import models
from backend.persistence.db import get_engine


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

    # SQLite-compatible ORM schema mirror.  BigInteger primary keys are
    # declared as Integer so autoincrement works under SQLite; the mirror
    # classes live in ``_orm_mirror_a`` / ``_orm_mirror_b`` (split for file
    # size) and all register on the shared ``TestBase``.
    # ⚠️  ADD NEW MODELS to the appropriate _orm_mirror_* module.
    from tests.api._orm_mirror_base import TestBase
    from tests.api._orm_mirror_a import (  # noqa: F401  pylint: disable=unused-import
        AuditLog,
        AvailablePackage,
        EnabledPackageManager,
        FirewallRole,
        FirewallRoleOpenPort,
        Host,
        HostFirewallRole,
        HostTag,
        InstallationPackage,
        InstallationRequest,
        MessageQueue,
        PackageUpdate,
        PasswordResetToken,
        SavedScript,
        ScriptExecutionLog,
        SecurityRole,
        SecurityRoleGroup,
        SoftwareInstallationLog,
        Tag,
        UbuntuProSettings,
        User,
        UserSecurityRole,
    )
    from tests.api._orm_mirror_b import (  # noqa: F401  pylint: disable=unused-import
        AccessGroup,
        AirGapBundle,
        AirgapCollectionRun,
        AirgapCollectionSchedule,
        AirgapCollectionTarget,
        AirgapMediaManifest,
        DynamicSecretLease,
        ExternalIdpProvider,
        ExternalIdpSettings,
        FederationSite,
        HostAccessGroup,
        HostDefaultMirror,
        HostPackageComplianceStatus,
        IdpRoleMapping,
        MfaSettings,
        MirrorKnownVersion,
        MirrorPlatformConfig,
        MirrorRepository,
        MirrorSettings,
        MirrorSetupStatus,
        MirrorSnapshot,
        PackageProfile,
        PackageProfileConstraint,
        RegistrationKey,
        ReportBranding,
        ReportTemplate,
        UpgradeProfile,
        UserAccessGroup,
        UserMfaEnrollment,
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
