"""
Pytest configuration for message handler tests.

This conftest inherits fixtures from the parent tests/conftest.py.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

# Import fixtures from parent conftest - pytest will auto-discover them
# These fixtures are available: engine, db_session, session, mock_config


@pytest.fixture
def mock_connection():
    """Mock WebSocket connection with host_id for handler tests."""
    connection = MagicMock()
    connection.host_id = "test-host-id-12345678"
    connection.websocket = AsyncMock()
    connection.websocket.send_json = AsyncMock()
    return connection


@pytest.fixture
def sample_system_info_message():
    """Sample system info message for testing."""
    return {
        "message_type": "system_info",
        "data": {
            "hostname": "test-host.example.com",
            "os": "Linux",
            "os_version": "5.15.0",
            "distribution": "Ubuntu",
            "distribution_version": "22.04",
            "cpu_count": 4,
            "memory_total": 8589934592,
        },
    }


@pytest.fixture
def sample_child_host_creation_result():
    """Sample child host creation result for testing."""
    return {
        "message_type": "command_result",
        "command_type": "create_child_host",
        "success": True,
        "result": {
            "child_name": "test-child",
            "child_type": "lxd",
            "status": "running",
            "hostname": "test-child.example.com",
        },
    }


@pytest.fixture
def sample_child_host_delete_result():
    """Sample child host delete result for testing."""
    return {
        "message_type": "command_result",
        "command_type": "delete_child_host",
        "success": True,
        "result": {
            "child_name": "test-child",
            "child_type": "lxd",
        },
    }


@pytest.fixture
def sample_child_host_control_result():
    """Sample child host control (start/stop/restart) result for testing."""
    return {
        "message_type": "command_result",
        "command_type": "start_child_host",
        "success": True,
        "result": {
            "child_name": "test-child",
            "child_type": "lxd",
            "status": "running",
        },
    }
