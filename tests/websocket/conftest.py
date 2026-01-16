"""
Pytest configuration for WebSocket tests.

This conftest inherits fixtures from the parent tests/conftest.py.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

# Import fixtures from parent conftest - pytest will auto-discover them
# These fixtures are available: engine, db_session, session, mock_config


@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection for testing."""
    ws = AsyncMock()
    ws.host_id = "test-host-id"
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.close = AsyncMock()
    ws.accept = AsyncMock()
    return ws


@pytest.fixture
def mock_connection():
    """Mock connection object with host_id attribute."""
    connection = MagicMock()
    connection.host_id = "test-host-id"
    connection.websocket = AsyncMock()
    return connection


@pytest.fixture
def sample_command_message():
    """Sample command message for testing."""
    return {
        "message_type": "command",
        "command_id": "test-command-id",
        "command_type": "test_command",
        "parameters": {"param1": "value1"},
    }


@pytest.fixture
def sample_command_result():
    """Sample command result message for testing."""
    return {
        "message_type": "command_result",
        "command_id": "test-command-id",
        "command_type": "test_command",
        "success": True,
        "result": {"status": "completed"},
    }
