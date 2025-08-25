"""
Pytest configuration and shared fixtures for SysManage server tests.
"""

import asyncio
from typing import Generator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.persistence.db import Base, get_db
from backend.websocket.connection_manager import ConnectionManager
from backend.auth.auth_bearer import JWTBearer

# Test database URL - using SQLite in memory for tests
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    """Create test database engine."""
    test_engine = create_engine(
        TEST_DATABASE_URL, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=test_engine)
    return test_engine


@pytest.fixture(scope="function")
def db_session(engine):
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with test database."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def authenticated_client(db_session):
    """Create a test client with test database and mocked JWT auth."""
    from unittest.mock import patch

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    async def mock_jwt_call(self, request):
        """Mock JWT bearer call that always returns authenticated user."""
        return "mocked_user_id"

    # Override database dependency
    app.dependency_overrides[get_db] = override_get_db

    # Patch the JWTBearer __call__ method to always return success
    with patch("backend.auth.auth_bearer.JWTBearer.__call__", mock_jwt_call):
        with TestClient(app) as test_client:
            yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket for testing."""
    mock_ws = Mock()
    mock_ws.accept = Mock(return_value=asyncio.coroutine(lambda: None)())
    mock_ws.send_text = Mock(return_value=asyncio.coroutine(lambda x: None)())
    mock_ws.receive_text = Mock(
        return_value=asyncio.coroutine(lambda: '{"test": "data"}')()
    )
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
