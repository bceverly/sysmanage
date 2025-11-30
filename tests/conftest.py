"""
Pytest configuration and shared fixtures for SysManage server tests.
"""

import asyncio
import os

# Test database URL - using temporary SQLite file for tests
import tempfile
import time
from typing import Generator
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer
from backend.main import app
from backend.persistence.db import Base, get_db
from backend.persistence.models import *  # Import all models explicitly
from backend.websocket.connection_manager import ConnectionManager

# Use secure temporary file for test database
_test_db_fd, _test_db_file = tempfile.mkstemp(suffix=f"_{int(time.time())}.db")
os.close(_test_db_fd)  # Close the file descriptor, we only need the path
TEST_DATABASE_URL = f"sqlite:///{_test_db_file}"

# Test configuration with different ports to avoid conflicts with dev server
TEST_CONFIG = {
    "api": {
        "host": "localhost",
        "port": 9443,  # Different from dev server (6443)
        "certFile": "/tmp/test-cert.pem",
        "chainFile": "/tmp/test-chain.pem",
        "keyFile": "/tmp/test-key.pem",
    },
    "webui": {"host": "localhost", "port": 9080},  # Different from dev server (8080)
    "monitoring": {"heartbeat_timeout": 5},
    "security": {
        "password_salt": "test_salt",
        "admin_userid": "admin@test.com",
        "admin_password": "testpass",
        "jwt_secret": "test_secret",
        "jwt_algorithm": "HS256",
        "jwt_auth_timeout": 3600,
        "jwt_refresh_timeout": 86400,
        "max_failed_logins": 5,
        "account_lockout_duration": 15,
    },
}


@pytest.fixture(scope="function")
def engine():
    """Create test database engine with fresh schema for each test."""
    # Create a unique database file for each test
    import uuid

    test_db_fd, test_db_file = tempfile.mkstemp(suffix=f"_{uuid.uuid4().hex}.db")
    os.close(test_db_fd)  # Close the file descriptor, we only need the path
    test_db_url = f"sqlite:///{test_db_file}"

    test_engine = create_engine(test_db_url, connect_args={"check_same_thread": False})

    # Enter test mode to prevent production database access
    from backend.persistence.db import enter_test_mode

    enter_test_mode(test_engine)

    # Import models to ensure metadata registration
    from backend.persistence import models  # noqa: F401

    Base.metadata.create_all(bind=test_engine)

    yield test_engine

    # Properly dispose of the engine to close all connections
    test_engine.dispose()

    # Exit test mode after test
    from backend.persistence.db import exit_test_mode

    exit_test_mode()

    # Clean up the temporary database file after test
    try:
        if os.path.exists(test_db_file):
            os.unlink(test_db_file)
    except OSError:
        pass


@pytest.fixture(scope="function")
def db_session(engine):
    """Create a test database session."""
    # Ensure all models are imported before creating tables
    from backend.persistence import models  # Import all models
    from backend.persistence.db import Base

    # Drop and recreate all tables to ensure all models are included
    Base.metadata.drop_all(bind=engine)

    # For SQLite test databases, create tables directly using SQLAlchemy metadata
    # This avoids Alembic migration timezone compatibility issues with SQLite
    print("Creating SQLite test schema directly from models (skipping Alembic)")
    from backend.persistence import models  # Import all models
    from backend.persistence.db import Base

    Base.metadata.create_all(bind=engine)

    # Debug: Check what was actually created
    from sqlalchemy import text

    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='available_packages'"
            )
        )
        table_exists = len(result.fetchall()) > 0
        print(f"DEBUG: available_packages table created in test DB: {table_exists}")
        print(f"DEBUG: Test database URL: {engine.url}")

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    # Commit the session to ensure any pending transactions are finalized
    session.commit()

    try:
        yield session
    finally:
        # Close session and clear connection pool
        session.rollback()
        session.close()
        # Remove connection from the pool
        session.get_bind().dispose()


@pytest.fixture(scope="function")
def mock_config():
    """Mock the configuration system to use test config."""
    with patch("backend.config.config.get_config", return_value=TEST_CONFIG):
        yield TEST_CONFIG


@pytest.fixture(scope="function")
def session(db_session):
    """Alias for db_session to match test expectations."""
    return db_session


@pytest.fixture(scope="function")
def client(engine, db_session, mock_config):
    """Create a test client with test database and mocked config."""
    from backend.auth.auth_bearer import get_current_user
    from backend.persistence.models import (
        User,
        SecurityRole,
        SecurityRoleGroup,
        UserSecurityRole,
    )
    from argon2 import PasswordHasher
    from backend.security.roles import SecurityRoles
    from uuid import UUID
    import hashlib

    # Create security role groups and roles in test database
    groups = [
        {
            "id": UUID("00000000-0000-0000-0000-000000000001"),
            "name": "Host Management",
            "description": "Roles for managing hosts",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000002"),
            "name": "Package Management",
            "description": "Roles for managing packages",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000003"),
            "name": "Secrets Management",
            "description": "Roles for managing secrets",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000004"),
            "name": "User Management",
            "description": "Roles for managing users",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000005"),
            "name": "Script Management",
            "description": "Roles for managing scripts",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000006"),
            "name": "Report Management",
            "description": "Roles for managing reports",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000007"),
            "name": "Integration Management",
            "description": "Roles for managing integrations",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000008"),
            "name": "Ubuntu Pro Management",
            "description": "Roles for Ubuntu Pro",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000010"),
            "name": "Settings",
            "description": "Permissions related to system settings",
        },
    ]

    for group_data in groups:
        group = SecurityRoleGroup(**group_data)
        db_session.merge(group)

    role_to_group = {
        SecurityRoles.APPROVE_HOST_REGISTRATION: UUID(
            "00000000-0000-0000-0000-000000000001"
        ),
        SecurityRoles.DELETE_HOST: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.VIEW_HOST_DETAILS: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.REBOOT_HOST: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.SHUTDOWN_HOST: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.EDIT_TAGS: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.STOP_HOST_SERVICE: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.START_HOST_SERVICE: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.RESTART_HOST_SERVICE: UUID(
            "00000000-0000-0000-0000-000000000001"
        ),
        SecurityRoles.ADD_PACKAGE: UUID("00000000-0000-0000-0000-000000000002"),
        SecurityRoles.APPLY_SOFTWARE_UPDATE: UUID(
            "00000000-0000-0000-0000-000000000002"
        ),
        SecurityRoles.APPLY_HOST_OS_UPGRADE: UUID(
            "00000000-0000-0000-0000-000000000002"
        ),
        SecurityRoles.DEPLOY_SSH_KEY: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.DEPLOY_CERTIFICATE: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.ADD_SECRET: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.DELETE_SECRET: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.EDIT_SECRET: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.STOP_VAULT: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.START_VAULT: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.ADD_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.EDIT_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.LOCK_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.UNLOCK_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.DELETE_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.RESET_USER_PASSWORD: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.ADD_SCRIPT: UUID("00000000-0000-0000-0000-000000000005"),
        SecurityRoles.EDIT_SCRIPT: UUID("00000000-0000-0000-0000-000000000005"),
        SecurityRoles.DELETE_SCRIPT: UUID("00000000-0000-0000-0000-000000000005"),
        SecurityRoles.RUN_SCRIPT: UUID("00000000-0000-0000-0000-000000000005"),
        SecurityRoles.DELETE_SCRIPT_EXECUTION: UUID(
            "00000000-0000-0000-0000-000000000005"
        ),
        SecurityRoles.VIEW_REPORT: UUID("00000000-0000-0000-0000-000000000006"),
        SecurityRoles.GENERATE_PDF_REPORT: UUID("00000000-0000-0000-0000-000000000006"),
        SecurityRoles.DELETE_QUEUE_MESSAGE: UUID(
            "00000000-0000-0000-0000-000000000007"
        ),
        SecurityRoles.ENABLE_GRAFANA_INTEGRATION: UUID(
            "00000000-0000-0000-0000-000000000007"
        ),
        SecurityRoles.ATTACH_UBUNTU_PRO: UUID("00000000-0000-0000-0000-000000000008"),
        SecurityRoles.DETACH_UBUNTU_PRO: UUID("00000000-0000-0000-0000-000000000008"),
        SecurityRoles.CHANGE_UBUNTU_PRO_MASTER_KEY: UUID(
            "00000000-0000-0000-0000-000000000008"
        ),
        # Settings group - Firewall Roles
        SecurityRoles.ADD_FIREWALL_ROLE: UUID("00000000-0000-0000-0000-000000000010"),
        SecurityRoles.EDIT_FIREWALL_ROLE: UUID("00000000-0000-0000-0000-000000000010"),
        SecurityRoles.DELETE_FIREWALL_ROLE: UUID(
            "00000000-0000-0000-0000-000000000010"
        ),
        SecurityRoles.VIEW_FIREWALL_ROLES: UUID("00000000-0000-0000-0000-000000000010"),
    }

    for role_enum, group_id in role_to_group.items():
        role_id = UUID(hashlib.md5(role_enum.value.encode()).hexdigest())
        role = SecurityRole(
            id=role_id,
            name=role_enum.value,
            description=f"Permission to {role_enum.value.lower()}",
            group_id=group_id,
        )
        db_session.merge(role)

    db_session.commit()

    # Create test user with all roles
    password_hasher = PasswordHasher()
    hashed_password = password_hasher.hash("testpassword")

    test_user = User(
        userid="test_user@example.com",
        hashed_password=hashed_password,
        first_name="Test",
        last_name="User",
        active=True,
        is_admin=False,
    )
    db_session.add(test_user)
    db_session.commit()
    db_session.refresh(test_user)

    # Assign all roles to test user
    all_roles = db_session.query(SecurityRole).all()
    for role in all_roles:
        user_role = UserSecurityRole(
            user_id=test_user.id,
            role_id=role.id,
            granted_by=test_user.id,
        )
        db_session.add(user_role)

    db_session.commit()
    test_user.load_role_cache(db_session)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_current_user():
        return "test_user@example.com"

    # Mock the FastAPI app lifespan to prevent service startup during tests
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    # Replace the lifespan manager
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = mock_lifespan

    try:
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user

        with patch("backend.auth.auth_bearer.JWTBearer.__call__") as mock_jwt:

            async def mock_jwt_call(*args, **kwargs):
                return "test_token"

            mock_jwt.side_effect = mock_jwt_call

            with TestClient(app) as test_client:
                yield test_client

        app.dependency_overrides.clear()
    finally:
        app.router.lifespan_context = original_lifespan


@pytest.fixture(scope="function")
def authenticated_client(db_session, mock_config):
    """Create a test client with test database and mocked JWT auth."""
    from unittest.mock import patch
    from backend.persistence.models import (
        User,
        SecurityRole,
        SecurityRoleGroup,
        UserSecurityRole,
    )
    from argon2 import PasswordHasher
    from backend.security.roles import SecurityRoles
    from uuid import UUID
    import hashlib

    # Create security role groups and roles in test database
    groups = [
        {
            "id": UUID("00000000-0000-0000-0000-000000000001"),
            "name": "Host Management",
            "description": "Roles for managing hosts",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000002"),
            "name": "Package Management",
            "description": "Roles for managing packages",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000003"),
            "name": "Secrets Management",
            "description": "Roles for managing secrets",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000004"),
            "name": "User Management",
            "description": "Roles for managing users",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000005"),
            "name": "Script Management",
            "description": "Roles for managing scripts",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000006"),
            "name": "Report Management",
            "description": "Roles for managing reports",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000007"),
            "name": "Integration Management",
            "description": "Roles for managing integrations",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000008"),
            "name": "Ubuntu Pro Management",
            "description": "Roles for Ubuntu Pro",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000010"),
            "name": "Settings",
            "description": "Permissions related to system settings",
        },
    ]

    for group_data in groups:
        group = SecurityRoleGroup(**group_data)
        db_session.merge(group)

    role_to_group = {
        SecurityRoles.APPROVE_HOST_REGISTRATION: UUID(
            "00000000-0000-0000-0000-000000000001"
        ),
        SecurityRoles.DELETE_HOST: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.VIEW_HOST_DETAILS: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.REBOOT_HOST: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.SHUTDOWN_HOST: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.EDIT_TAGS: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.STOP_HOST_SERVICE: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.START_HOST_SERVICE: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.RESTART_HOST_SERVICE: UUID(
            "00000000-0000-0000-0000-000000000001"
        ),
        SecurityRoles.ADD_PACKAGE: UUID("00000000-0000-0000-0000-000000000002"),
        SecurityRoles.APPLY_SOFTWARE_UPDATE: UUID(
            "00000000-0000-0000-0000-000000000002"
        ),
        SecurityRoles.APPLY_HOST_OS_UPGRADE: UUID(
            "00000000-0000-0000-0000-000000000002"
        ),
        SecurityRoles.DEPLOY_SSH_KEY: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.DEPLOY_CERTIFICATE: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.ADD_SECRET: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.DELETE_SECRET: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.EDIT_SECRET: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.STOP_VAULT: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.START_VAULT: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.ADD_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.EDIT_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.LOCK_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.UNLOCK_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.DELETE_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.RESET_USER_PASSWORD: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.ADD_SCRIPT: UUID("00000000-0000-0000-0000-000000000005"),
        SecurityRoles.EDIT_SCRIPT: UUID("00000000-0000-0000-0000-000000000005"),
        SecurityRoles.DELETE_SCRIPT: UUID("00000000-0000-0000-0000-000000000005"),
        SecurityRoles.RUN_SCRIPT: UUID("00000000-0000-0000-0000-000000000005"),
        SecurityRoles.DELETE_SCRIPT_EXECUTION: UUID(
            "00000000-0000-0000-0000-000000000005"
        ),
        SecurityRoles.VIEW_REPORT: UUID("00000000-0000-0000-0000-000000000006"),
        SecurityRoles.GENERATE_PDF_REPORT: UUID("00000000-0000-0000-0000-000000000006"),
        SecurityRoles.DELETE_QUEUE_MESSAGE: UUID(
            "00000000-0000-0000-0000-000000000007"
        ),
        SecurityRoles.ENABLE_GRAFANA_INTEGRATION: UUID(
            "00000000-0000-0000-0000-000000000007"
        ),
        SecurityRoles.ATTACH_UBUNTU_PRO: UUID("00000000-0000-0000-0000-000000000008"),
        SecurityRoles.DETACH_UBUNTU_PRO: UUID("00000000-0000-0000-0000-000000000008"),
        SecurityRoles.CHANGE_UBUNTU_PRO_MASTER_KEY: UUID(
            "00000000-0000-0000-0000-000000000008"
        ),
        # Settings group - Firewall Roles
        SecurityRoles.ADD_FIREWALL_ROLE: UUID("00000000-0000-0000-0000-000000000010"),
        SecurityRoles.EDIT_FIREWALL_ROLE: UUID("00000000-0000-0000-0000-000000000010"),
        SecurityRoles.DELETE_FIREWALL_ROLE: UUID(
            "00000000-0000-0000-0000-000000000010"
        ),
        SecurityRoles.VIEW_FIREWALL_ROLES: UUID("00000000-0000-0000-0000-000000000010"),
    }

    for role_enum, group_id in role_to_group.items():
        role_id = UUID(hashlib.md5(role_enum.value.encode()).hexdigest())
        role = SecurityRole(
            id=role_id,
            name=role_enum.value,
            description=f"Permission to {role_enum.value.lower()}",
            group_id=group_id,
        )
        db_session.merge(role)

    db_session.commit()

    # Create test user with all roles if it doesn't exist
    test_user = (
        db_session.query(User).filter(User.userid == "test_user@example.com").first()
    )

    if not test_user:
        password_hasher = PasswordHasher()
        test_user = User(
            userid="test_user@example.com",
            hashed_password=password_hasher.hash("testpassword"),
            first_name="Test",
            last_name="User",
            active=True,
            is_admin=False,
        )
        db_session.add(test_user)
        db_session.commit()
        db_session.refresh(test_user)

        # Assign all roles to test user
        all_roles = db_session.query(SecurityRole).all()
        for role in all_roles:
            user_role = UserSecurityRole(
                user_id=test_user.id,
                role_id=role.id,
                granted_by=test_user.id,
            )
            db_session.add(user_role)

        db_session.commit()

    # Load role cache for quick permission checking
    test_user.load_role_cache(db_session)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    async def mock_jwt_call(self, request):
        """Mock JWT bearer call that always returns authenticated user."""
        return "mocked_user_id"

    # Mock the FastAPI app lifespan to prevent service startup during tests
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_lifespan(app):
        # Mock startup - do nothing
        yield
        # Mock shutdown - do nothing

    # Replace the lifespan manager
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = mock_lifespan

    try:
        # Override database dependency
        app.dependency_overrides[get_db] = override_get_db

        # Override get_current_user dependency
        from backend.auth.auth_bearer import JWTBearer, get_current_user

        def override_get_current_user():
            return "test_user@example.com"

        app.dependency_overrides[get_current_user] = override_get_current_user

        # Override JWTBearer dependency to return a test token
        def override_jwt_bearer():
            return "test_token"

        # Create an instance to override
        jwt_bearer_instance = JWTBearer()
        app.dependency_overrides[jwt_bearer_instance] = override_jwt_bearer

        # Patch JWTBearer to always succeed
        with patch("backend.auth.auth_bearer.JWTBearer.__call__") as mock_jwt:
            mock_jwt.return_value = "test_token"

            with TestClient(app) as test_client:
                yield test_client

        app.dependency_overrides.clear()
    finally:
        # Restore original lifespan
        app.router.lifespan_context = original_lifespan


@pytest.fixture
def session(db_session):
    """Alias for db_session fixture for compatibility."""
    return db_session


@pytest.fixture
def security_roles_populated(db_session):
    """Populate security roles and groups in test database."""
    from backend.persistence.models import SecurityRole, SecurityRoleGroup
    from uuid import UUID

    # Create role groups (matching migration 54fcacb0e742)
    groups = [
        {
            "id": UUID("00000000-0000-0000-0000-000000000001"),
            "name": "Host Management",
            "description": "Roles for managing hosts",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000002"),
            "name": "Package Management",
            "description": "Roles for managing packages",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000003"),
            "name": "Secrets Management",
            "description": "Roles for managing secrets",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000004"),
            "name": "User Management",
            "description": "Roles for managing users",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000005"),
            "name": "Script Management",
            "description": "Roles for managing scripts",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000006"),
            "name": "Report Management",
            "description": "Roles for managing reports",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000007"),
            "name": "Integration Management",
            "description": "Roles for managing integrations",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000008"),
            "name": "Ubuntu Pro Management",
            "description": "Roles for Ubuntu Pro",
        },
        {
            "id": UUID("00000000-0000-0000-0000-000000000010"),
            "name": "Settings",
            "description": "Permissions related to system settings",
        },
    ]

    for group_data in groups:
        group = SecurityRoleGroup(**group_data)
        db_session.merge(group)

    # Create all security roles from the SecurityRoles enum
    from backend.security.roles import SecurityRoles

    role_to_group = {
        SecurityRoles.APPROVE_HOST_REGISTRATION: UUID(
            "00000000-0000-0000-0000-000000000001"
        ),
        SecurityRoles.DELETE_HOST: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.VIEW_HOST_DETAILS: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.REBOOT_HOST: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.SHUTDOWN_HOST: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.EDIT_TAGS: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.STOP_HOST_SERVICE: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.START_HOST_SERVICE: UUID("00000000-0000-0000-0000-000000000001"),
        SecurityRoles.RESTART_HOST_SERVICE: UUID(
            "00000000-0000-0000-0000-000000000001"
        ),
        SecurityRoles.ADD_PACKAGE: UUID("00000000-0000-0000-0000-000000000002"),
        SecurityRoles.APPLY_SOFTWARE_UPDATE: UUID(
            "00000000-0000-0000-0000-000000000002"
        ),
        SecurityRoles.APPLY_HOST_OS_UPGRADE: UUID(
            "00000000-0000-0000-0000-000000000002"
        ),
        SecurityRoles.DEPLOY_SSH_KEY: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.DEPLOY_CERTIFICATE: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.ADD_SECRET: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.DELETE_SECRET: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.EDIT_SECRET: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.STOP_VAULT: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.START_VAULT: UUID("00000000-0000-0000-0000-000000000003"),
        SecurityRoles.ADD_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.EDIT_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.LOCK_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.UNLOCK_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.DELETE_USER: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.RESET_USER_PASSWORD: UUID("00000000-0000-0000-0000-000000000004"),
        SecurityRoles.ADD_SCRIPT: UUID("00000000-0000-0000-0000-000000000005"),
        SecurityRoles.EDIT_SCRIPT: UUID("00000000-0000-0000-0000-000000000005"),
        SecurityRoles.DELETE_SCRIPT: UUID("00000000-0000-0000-0000-000000000005"),
        SecurityRoles.RUN_SCRIPT: UUID("00000000-0000-0000-0000-000000000005"),
        SecurityRoles.DELETE_SCRIPT_EXECUTION: UUID(
            "00000000-0000-0000-0000-000000000005"
        ),
        SecurityRoles.VIEW_REPORT: UUID("00000000-0000-0000-0000-000000000006"),
        SecurityRoles.GENERATE_PDF_REPORT: UUID("00000000-0000-0000-0000-000000000006"),
        SecurityRoles.DELETE_QUEUE_MESSAGE: UUID(
            "00000000-0000-0000-0000-000000000007"
        ),
        SecurityRoles.ENABLE_GRAFANA_INTEGRATION: UUID(
            "00000000-0000-0000-0000-000000000007"
        ),
        SecurityRoles.ATTACH_UBUNTU_PRO: UUID("00000000-0000-0000-0000-000000000008"),
        SecurityRoles.DETACH_UBUNTU_PRO: UUID("00000000-0000-0000-0000-000000000008"),
        SecurityRoles.CHANGE_UBUNTU_PRO_MASTER_KEY: UUID(
            "00000000-0000-0000-0000-000000000008"
        ),
        # Settings group - Firewall Roles
        SecurityRoles.ADD_FIREWALL_ROLE: UUID("00000000-0000-0000-0000-000000000010"),
        SecurityRoles.EDIT_FIREWALL_ROLE: UUID("00000000-0000-0000-0000-000000000010"),
        SecurityRoles.DELETE_FIREWALL_ROLE: UUID(
            "00000000-0000-0000-0000-000000000010"
        ),
        SecurityRoles.VIEW_FIREWALL_ROLES: UUID("00000000-0000-0000-0000-000000000010"),
    }

    import hashlib

    for role_enum, group_id in role_to_group.items():
        # Generate deterministic UUID based on role name
        role_id = UUID(hashlib.md5(role_enum.value.encode()).hexdigest())
        role = SecurityRole(
            id=role_id,
            name=role_enum.value,
            description=f"Permission to {role_enum.value.lower()}",
            group_id=group_id,
        )
        db_session.merge(role)

    db_session.commit()
    return True


@pytest.fixture
def test_user_with_all_roles(db_session, security_roles_populated):
    """Create a test user with all security roles for testing."""
    from backend.persistence.models import User, SecurityRole, UserSecurityRole
    from argon2 import PasswordHasher

    # Create test user
    password_hasher = PasswordHasher()
    hashed_password = password_hasher.hash("testpassword")

    test_user = User(
        userid="test_user@example.com",
        hashed_password=hashed_password,
        first_name="Test",
        last_name="User",
        active=True,
        is_admin=False,
    )
    db_session.add(test_user)
    db_session.commit()
    db_session.refresh(test_user)

    # Get all security roles and assign them to the test user
    all_roles = db_session.query(SecurityRole).all()
    for role in all_roles:
        user_role = UserSecurityRole(
            user_id=test_user.id,
            role_id=role.id,
            granted_by=test_user.id,
        )
        db_session.add(user_role)

    db_session.commit()

    # Initialize role cache
    test_user.load_role_cache(db_session)

    return test_user


@pytest.fixture
def auth_headers(client, mock_config):
    """Provide authentication headers for test requests."""
    # The test user is already created in the client fixture
    # Create a valid JWT token for the test user
    import time
    import jwt

    payload = {
        "user_id": "test_user@example.com",
        "expires": time.time() + int(mock_config["security"]["jwt_auth_timeout"]),
    }

    token = jwt.encode(
        payload,
        mock_config["security"]["jwt_secret"],
        algorithm=mock_config["security"]["jwt_algorithm"],
    )

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_login_security():
    """Mock the login security service."""
    mock_security = Mock()
    mock_security.unlock_user_account = Mock()
    mock_security.is_account_locked = Mock(return_value=False)
    mock_security.record_failed_login = Mock()
    mock_security.record_successful_login = Mock()

    with patch("backend.security.login_security.login_security", mock_security):
        yield mock_security


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket for testing."""
    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()
    mock_ws.send_text = AsyncMock()
    mock_ws.receive_text = AsyncMock(return_value='{"test": "data"}')
    return mock_ws


@pytest.fixture
def connection_manager():
    """Create a fresh connection manager for testing."""
    return ConnectionManager()


@pytest.fixture
def sample_host_data():
    """Sample host data for testing."""
    return {
        "hostname": "test.example.com",
        "ipv4": "192.168.1.100",
        "ipv6": "2001:db8::1",
        "platform": "Linux",
    }


@pytest.fixture
def sample_system_info_message(sample_host_data):
    """Sample system info message."""
    return {
        "message_type": "system_info",
        "message_id": "test-message-123",
        "timestamp": "2024-01-01T00:00:00.000000",
        "data": sample_host_data,
    }


@pytest.fixture
def sample_command_message():
    """Sample command message."""
    return {
        "message_type": "command",
        "message_id": "test-command-123",
        "timestamp": "2024-01-01T00:00:00.000000",
        "data": {
            "command_type": "execute_shell",
            "parameters": {"command": "echo hello"},
            "timeout": 300,
        },
    }


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Async test helper
def pytest_configure(config):
    """Configure pytest for async testing."""
    import sys

    if sys.version_info >= (3, 7):
        # For Python 3.7+, use the built-in asyncio support
        pass
    else:
        # For older versions, ensure asyncio mode works
        config.option.asyncio_mode = "auto"
