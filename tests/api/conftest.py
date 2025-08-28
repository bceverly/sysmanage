"""
Test configuration and fixtures for API tests.
"""

import os
import tempfile
from unittest.mock import Mock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, Integer, Column, Boolean, String, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from pyargon2 import hash as argon2_hash

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
    from sqlalchemy import Integer, Column
    from sqlalchemy.ext.declarative import declarative_base

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

    # Create test version of User model with Integer ID for SQLite compatibility
    class User(TestBase):
        __tablename__ = "user"
        id = Column(
            Integer, primary_key=True, index=True, autoincrement=True
        )  # Changed from BigInteger
        active = Column(Boolean, unique=False, index=False)
        userid = Column(String, index=True)
        hashed_password = Column(String)
        last_access = Column(DateTime)
        is_locked = Column(Boolean, default=False, nullable=False)
        failed_login_attempts = Column(Integer, default=0, nullable=False)
        locked_at = Column(DateTime, nullable=True)

    # Create all tables with test models
    TestBase.metadata.create_all(bind=test_engine)

    # Monkey patch models to use test models during testing
    original_host = models.Host
    original_user = models.User
    models.Host = Host
    models.User = User

    # Override the get_engine dependency
    def override_get_engine():
        return test_engine

    app.dependency_overrides[get_engine] = override_get_engine

    yield test_engine

    # Restore original models
    models.Host = original_host
    models.User = original_user

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)
    app.dependency_overrides.clear()


@pytest.fixture
def client(test_db):
    """Create a FastAPI test client."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session(test_db):
    """Create a database session for testing."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db)
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
def admin_token():
    """Create a valid admin JWT token for testing."""
    # Create JWT token with admin userid string
    return sign_jwt("admin@sysmanage.org")


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
