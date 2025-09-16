"""
Test configuration and fixtures for API tests.
"""

import os
import tempfile
from unittest.mock import Mock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, Integer, Column, Boolean, String, DateTime, Text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from argon2 import PasswordHasher

argon2_hasher = PasswordHasher()

from backend.main import app
from backend.persistence import models
from backend.persistence.db import get_engine
from backend.auth.auth_handler import sign_jwt


# Test database setup
@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database for each test."""
    # Create temporary database
    db_fd, db_path = tempfile.mkstemp()
    test_engine = create_engine(f"sqlite:///{db_path}")

    # For SQLite, we need to modify BigInteger columns to Integer for autoincrement to work
    # Create a copy of metadata with modified column types
    from sqlalchemy import Integer, Column, ForeignKey
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import relationship

    TestBase = declarative_base()

    # Create test version of Host model with Integer ID for SQLite compatibility
    class Host(TestBase):
        __tablename__ = "host"
        id = Column(
            Integer, primary_key=True, index=True, autoincrement=True
        )  # Changed from BigInteger
        active = Column(Boolean, unique=False, index=False)
        fqdn = Column(String, index=True)
        ipv4 = Column(String)
        ipv6 = Column(String)
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
        os_details = Column(
            String, nullable=True
        )  # Using String instead of Text for SQLite
        os_version_updated_at = Column(DateTime, nullable=True)

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
        reboot_required_updated_at = Column(DateTime, nullable=True)

        # Agent privilege status
        is_agent_privileged = Column(Boolean, nullable=True, default=False)

        # Add relationship
        tags = relationship(
            "Tag", secondary="host_tags", back_populates="hosts", lazy="dynamic"
        )

    # Create test version of User model with Integer ID for SQLite compatibility
    class User(TestBase):
        __tablename__ = "user"
        id = Column(
            Integer, primary_key=True, index=True, autoincrement=True
        )  # Changed from BigInteger
        active = Column(Boolean, unique=False, index=False)
        userid = Column(String, index=True)
        first_name = Column(String(100), nullable=True)
        last_name = Column(String(100), nullable=True)
        hashed_password = Column(String)
        last_access = Column(DateTime)
        is_locked = Column(Boolean, default=False, nullable=False)
        failed_login_attempts = Column(Integer, default=0, nullable=False)
        locked_at = Column(DateTime, nullable=True)

    # Create test version of Tag model with Integer ID for SQLite compatibility
    class Tag(TestBase):
        __tablename__ = "tags"
        id = Column(
            Integer, primary_key=True, index=True, autoincrement=True
        )  # Changed from BigInteger
        name = Column(String(100), nullable=False, unique=True, index=True)
        description = Column(String(500), nullable=True)
        created_at = Column(DateTime, nullable=False)
        updated_at = Column(DateTime, nullable=False)

        # Add relationship
        hosts = relationship(
            "Host", secondary="host_tags", back_populates="tags", lazy="dynamic"
        )

    # Create test version of HostTag junction table for SQLite compatibility
    class HostTag(TestBase):
        __tablename__ = "host_tags"
        host_id = Column(
            Integer,
            ForeignKey("host.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
        tag_id = Column(
            Integer,
            ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
        created_at = Column(DateTime, nullable=False)

    # Create test version of PasswordResetToken model with Integer ID for SQLite compatibility
    class PasswordResetToken(TestBase):
        __tablename__ = "password_reset_tokens"
        id = Column(
            Integer, primary_key=True, index=True, autoincrement=True
        )  # Changed from BigInteger
        user_id = Column(
            Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
        )
        token = Column(String(255), unique=True, nullable=False, index=True)
        created_at = Column(DateTime, nullable=False)
        expires_at = Column(DateTime, nullable=False)
        used_at = Column(DateTime, nullable=True)
        is_used = Column(Boolean, default=False, nullable=False)

    # Create test version of MessageQueue model with Integer ID for SQLite compatibility
    class MessageQueue(TestBase):
        __tablename__ = "message_queue"
        id = Column(Integer, primary_key=True, autoincrement=True)
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
        created_at = Column(DateTime, nullable=False)
        scheduled_at = Column(DateTime, nullable=True)
        started_at = Column(DateTime, nullable=True)
        completed_at = Column(DateTime, nullable=True)
        error_message = Column(Text, nullable=True)
        last_error_at = Column(DateTime, nullable=True)
        expired_at = Column(DateTime, nullable=True)
        correlation_id = Column(String(36), nullable=True, index=True)
        reply_to = Column(String(36), nullable=True, index=True)

    # Create test version of UbuntuProSettings model for SQLite compatibility
    class UbuntuProSettings(TestBase):
        __tablename__ = "ubuntu_pro_settings"
        id = Column(Integer, primary_key=True, autoincrement=True)
        master_key = Column(Text, nullable=True)
        organization_name = Column(String(255), nullable=True)
        auto_attach_enabled = Column(Boolean, nullable=False, default=False)
        created_at = Column(DateTime, nullable=False)
        updated_at = Column(DateTime, nullable=False)

    # Create all tables with test models
    TestBase.metadata.create_all(bind=test_engine)

    # Monkey patch models to use test models during testing
    original_host = models.Host
    original_user = models.User
    original_tag = models.Tag
    original_host_tag = models.HostTag
    original_password_reset_token = models.PasswordResetToken
    original_message_queue = models.MessageQueue
    original_ubuntu_pro_settings = models.UbuntuProSettings
    models.Host = Host
    models.User = User
    models.Tag = Tag
    models.HostTag = HostTag
    models.PasswordResetToken = PasswordResetToken
    models.MessageQueue = MessageQueue
    models.UbuntuProSettings = UbuntuProSettings

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
    models.Host = original_host
    models.User = original_user
    models.Tag = original_tag
    models.HostTag = original_host_tag
    models.PasswordResetToken = original_password_reset_token
    models.MessageQueue = original_message_queue
    models.UbuntuProSettings = original_ubuntu_pro_settings

    # Clean up database connections
    test_engine.dispose()  # Close all connections in the connection pool

    # Give Windows time to release file handles
    import time

    time.sleep(0.1)

    # Cleanup
    try:
        os.close(db_fd)
    except:
        pass  # File descriptor might already be closed

    # Try to delete the file, but don't fail the test if it can't be deleted
    try:
        os.unlink(db_path)
    except PermissionError:
        # On Windows, the file might still be locked
        # It will be cleaned up eventually by the OS
        pass

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
def auth_headers(admin_token):
    """Create authorization headers with admin token."""
    return {"Authorization": f"Bearer {admin_token}"}


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
            "jwt_secret": "test_secret_key_123",
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
def mock_current_user():
    """Mock the current user dependency for authenticated tests."""
    from backend.auth.auth_bearer import get_current_user

    mock_user = Mock()
    mock_user.id = 1
    mock_user.userid = "test@example.com"
    mock_user.active = True

    def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield mock_user
    # Clean up the override
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]
