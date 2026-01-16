"""
Tests for the mock connection module.

This module tests the MockConnection class used for queue processing.
"""

import uuid

import pytest

from backend.websocket.mock_connection import MockConnection


class TestMockConnectionInit:
    """Test cases for MockConnection initialization."""

    def test_init_with_host_id(self):
        """Test that MockConnection initializes with host_id."""
        host_id = str(uuid.uuid4())
        conn = MockConnection(host_id)
        assert conn.host_id == host_id

    def test_hostname_is_none_by_default(self):
        """Test that hostname is None by default."""
        conn = MockConnection("test-host-id")
        assert conn.hostname is None

    def test_is_mock_connection_flag(self):
        """Test that is_mock_connection flag is True."""
        conn = MockConnection("test-host-id")
        assert conn.is_mock_connection is True


class TestMockConnectionSendMessage:
    """Test cases for MockConnection.send_message."""

    @pytest.mark.asyncio
    async def test_send_message_does_not_raise(self):
        """Test that send_message doesn't raise any errors."""
        conn = MockConnection("test-host-id")
        message = {"message_type": "test", "data": "test data"}
        # Should not raise
        await conn.send_message(message)

    @pytest.mark.asyncio
    async def test_send_message_handles_empty_message(self):
        """Test that send_message handles empty messages."""
        conn = MockConnection("test-host-id")
        await conn.send_message({})

    @pytest.mark.asyncio
    async def test_send_message_handles_complex_message(self):
        """Test that send_message handles complex message structures."""
        conn = MockConnection("test-host-id")
        message = {
            "message_type": "command_result",
            "data": {
                "nested": {"deep": {"value": 123}},
                "list": [1, 2, 3],
            },
        }
        await conn.send_message(message)


class TestMockConnectionUsage:
    """Test cases for MockConnection usage patterns."""

    def test_can_modify_hostname(self):
        """Test that hostname can be set after creation."""
        conn = MockConnection("test-host-id")
        conn.hostname = "my-test-host.example.com"
        assert conn.hostname == "my-test-host.example.com"

    def test_host_id_is_string(self):
        """Test that host_id is stored as provided."""
        host_id = str(uuid.uuid4())
        conn = MockConnection(host_id)
        assert isinstance(conn.host_id, str)
        assert conn.host_id == host_id

    def test_can_be_used_as_connection_substitute(self):
        """Test that MockConnection has the expected interface."""
        conn = MockConnection("host-123")
        # Should have the attributes expected by message handlers
        assert hasattr(conn, "host_id")
        assert hasattr(conn, "hostname")
        assert hasattr(conn, "send_message")
        assert hasattr(conn, "is_mock_connection")
