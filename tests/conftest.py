"""
Pytest configuration and shared fixtures for SysManage server tests.
"""

import logging

# Silence FastAPI startup-phase logger chatter BEFORE we import backend.main.
# That import builds the app (CORS generation, route registration,
# exception-handler setup, websocket queue init, lifespan probe), and each
# of those phases emits ~5–15 INFO lines.  Setting the floor to WARNING for
# the relevant package roots keeps test output focused on actual test
# results.  The pytest.ini ``log_level = WARNING`` covers test-time capture;
# this block covers import-time logging.
for _noisy_logger in (
    "backend.startup",
    "backend.websocket",
    "backend.api",
    "backend.api.proplus_routes",
    "websocket.agent",
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
):
    logging.getLogger(_noisy_logger).setLevel(logging.WARNING)

# Silence FlexibleLogger.debug/info during the import of backend.main below.
# FlexibleLogger (backend/utils/verbosity_logger.py) has its own gate that
# bypasses the standard ``logging`` level system — it always installs a
# DEBUG-level handler and decides per-call from a parsed config.  Both
# behaviours mean backend.main's ~50 import-time INFO lines reach stderr
# regardless of pytest.ini ``log_level``.  We swap the methods to no-ops
# only for the duration of the import; tests that exercise
# FlexibleLogger.debug/info directly (test_verbosity_logger_comprehensive)
# get the originals back afterwards.
import backend.utils.verbosity_logger as _verbosity_logger  # noqa: E402

_orig_debug = _verbosity_logger.FlexibleLogger.debug
_orig_info = _verbosity_logger.FlexibleLogger.info
_verbosity_logger.FlexibleLogger.debug = lambda *_a, **_k: None
_verbosity_logger.FlexibleLogger.info = lambda *_a, **_k: None

from typing import Generator
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth.auth_bearer import JWTBearer
from backend.main import app
from backend.api.proplus_routes import mount_proplus_stub_routes
from backend.persistence.db import Base, get_db
from backend.persistence.models import *  # Import all models explicitly
from backend.websocket.connection_manager import ConnectionManager

# Register stub routes for Pro+ modules (no modules loaded in test environment).
# Done while FlexibleLogger.info is still no-op'd so the "Mounted 10 Pro+ stub
# route group(s)" line doesn't trail the test summary.
mount_proplus_stub_routes(app, {})

# Restore FlexibleLogger.debug/info now that backend.main's import-time spam
# has been suppressed.  Tests that exercise FlexibleLogger (e.g.
# test_verbosity_logger_comprehensive) need the real methods.
_verbosity_logger.FlexibleLogger.debug = _orig_debug
_verbosity_logger.FlexibleLogger.info = _orig_info

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
        "jwt_secret": "test_jwt_secret_key_for_testing_purposes_32bytes",
        "jwt_algorithm": "HS256",
        "jwt_auth_timeout": 3600,
        "jwt_refresh_timeout": 86400,
        "max_failed_logins": 5,
        "account_lockout_duration": 15,
    },
}


@pytest.fixture(scope="function")
def engine():
    """Create a test database engine with a fresh schema for each test.

    Uses an **in-memory** SQLite database shared across connections via
    ``StaticPool`` (so separate sessions — e.g. the partition resolver's own
    sessionmaker — see the same data).  In-memory avoids the per-test file
    create/fsync/unlink that makes the suite crawl on Windows; the DB is
    discarded when the engine is disposed at test teardown.
    """
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enter test mode to prevent production database access
    from backend.persistence.db import enter_test_mode

    enter_test_mode(test_engine)

    # Import models to ensure metadata registration, then build the schema once.
    from backend.persistence import models  # noqa: F401

    Base.metadata.create_all(bind=test_engine)

    yield test_engine

    # Dispose closes the single pooled connection, discarding the in-memory DB.
    test_engine.dispose()

    from backend.persistence.db import exit_test_mode

    exit_test_mode()


@pytest.fixture(scope="function")
def db_session(engine):
    """Create a test database session.

    The ``engine`` fixture already built the schema on a fresh per-test
    in-memory database, so this just opens a session — no redundant
    drop/create (which doubled the schema work on every test) and no
    per-test debug output (slow on the Windows console).
    """
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


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
        role_id = UUID(
            hashlib.blake2b(role_enum.value.encode(), digest_size=16).hexdigest()
        )
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

        async def mock_jwt_call(self, request=None):
            return "test_token"

        with patch("backend.auth.auth_bearer.JWTBearer.__call__", new=mock_jwt_call):
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
        role_id = UUID(
            hashlib.blake2b(role_enum.value.encode(), digest_size=16).hexdigest()
        )
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
        async def mock_jwt_auth(self, request=None):
            return "test_token"

        with patch("backend.auth.auth_bearer.JWTBearer.__call__", new=mock_jwt_auth):
            with TestClient(app) as test_client:
                yield test_client

        app.dependency_overrides.clear()
    finally:
        # Restore original lifespan
        app.router.lifespan_context = original_lifespan


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


# Async test helper
def pytest_configure(config):
    """Configure pytest for async testing."""
    import sys

    # Silence the chatty startup/route-registration narration during tests.
    # Operational INFO from `backend.startup.*` is useful only at first
    # boot of a real server; in pytest it just floods stderr with hundreds
    # of "Adding X router" lines per worker.  Bumping `backend` to WARNING
    # keeps real warnings/errors visible while suppressing the noise.
    # Crank back up locally with: `pytest -o log_cli=true --log-cli-level=DEBUG`
    logging.getLogger("backend").setLevel(logging.WARNING)
    # httpx logs every test request at INFO; same treatment.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Ensure auth_handler has a usable JWT secret BEFORE any test module is
    # collected.  Under the v3.0 minimal-config layout jwt_secret lives in
    # OpenBAO and is absent from the YAML, so auth_handler captures "" at
    # import time.  ``pytest_configure`` runs before collection, so setting it
    # here means even modules that do ``from ...auth_handler import JWT_SECRET``
    # at top level bind the correct value (a top-level import otherwise captures
    # the stale "").  Mirrors the OpenBAO overlay's runtime reassignment in
    # secrets_bootstrap.refresh_secrets_from_openbao.
    from backend.auth import auth_handler

    auth_handler.JWT_SECRET = TEST_CONFIG["security"]["jwt_secret"]
    auth_handler.JWT_ALGORITHM = TEST_CONFIG["security"]["jwt_algorithm"]

    if sys.version_info >= (3, 7):
        # For Python 3.7+, use the built-in asyncio support
        pass
    else:
        # For older versions, ensure asyncio mode works
        config.option.asyncio_mode = "auto"


# ---------------------------------------------------------------------------
# Pro+ relocation (Phase 2): a fixture that registers the REAL compiled
# multitenancy_engine into the seam, so behavioral tests of relocated logic run
# against the actual artifact.  Skips when the .so isn't importable (pure OSS
# CI), so the OSS suite never hard-depends on the Pro+ build.
# ---------------------------------------------------------------------------
@pytest.fixture
def real_engine():
    """Register the REAL compiled multitenancy_engine into the seam.

    Discovery/loading is centralized in :mod:`tests._engine_loader`.
    ``require_engine`` skips only on a genuine OSS-only run (no Pro+ checkout)
    and fails loudly if the engine is present but won't load for this
    platform/interpreter — so this stops silently skipping.
    """
    from unittest.mock import MagicMock

    from backend.multitenancy import seam

    from tests._engine_loader import require_engine

    mod = require_engine("multitenancy_engine")
    seam.register_engine(MagicMock(), module=mod)
    yield mod
    seam.unregister_engine()
