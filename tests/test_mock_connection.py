"""
Tests for backend/websocket/mock_connection.py module.
Tests mock WebSocket connection for queue processing.
"""

import pytest


class TestMockConnectionInit:
    """Tests for MockConnection initialization."""

    def test_init_sets_host_id(self):
        """Test initialization sets host_id."""
        from backend.websocket.mock_connection import MockConnection

        conn = MockConnection(host_id="host-123")

        assert conn.host_id == "host-123"

    def test_init_sets_hostname_to_none(self):
        """Test initialization sets hostname to None."""
        from backend.websocket.mock_connection import MockConnection

        conn = MockConnection(host_id="host-456")

        assert conn.hostname is None

    def test_init_sets_is_mock_connection_flag(self):
        """Test initialization sets is_mock_connection flag to True."""
        from backend.websocket.mock_connection import MockConnection

        conn = MockConnection(host_id="host-789")

        assert conn.is_mock_connection is True


class TestMockConnectionSendMessage:
    """Tests for MockConnection.send_message method."""

    @pytest.mark.asyncio
    async def test_send_message_is_async(self):
        """Test send_message is an async method."""
        from backend.websocket.mock_connection import MockConnection

        conn = MockConnection(host_id="host-123")
        message = {"message_type": "test", "data": "value"}

        # Should not raise any exception
        await conn.send_message(message)

    @pytest.mark.asyncio
    async def test_send_message_accepts_any_message(self):
        """Test send_message accepts any dictionary message."""
        from backend.websocket.mock_connection import MockConnection

        conn = MockConnection(host_id="host-123")

        # Various message formats
        await conn.send_message({"message_type": "status"})
        await conn.send_message({"type": "data", "payload": {"key": "value"}})
        await conn.send_message({})

    @pytest.mark.asyncio
    async def test_send_message_no_side_effects(self):
        """Test send_message doesn't modify the connection state."""
        from backend.websocket.mock_connection import MockConnection

        conn = MockConnection(host_id="host-123")
        original_host_id = conn.host_id
        original_hostname = conn.hostname
        original_is_mock = conn.is_mock_connection

        await conn.send_message({"message_type": "test"})

        assert conn.host_id == original_host_id
        assert conn.hostname == original_hostname
        assert conn.is_mock_connection == original_is_mock


class TestMockConnectionAttributes:
    """Tests for MockConnection attributes."""

    def test_hostname_is_settable(self):
        """Test hostname attribute can be set."""
        from backend.websocket.mock_connection import MockConnection

        conn = MockConnection(host_id="host-123")
        conn.hostname = "test-hostname"

        assert conn.hostname == "test-hostname"

    def test_host_id_is_string(self):
        """Test host_id is stored as provided."""
        from backend.websocket.mock_connection import MockConnection

        conn = MockConnection(host_id="12345")

        assert isinstance(conn.host_id, str)
        assert conn.host_id == "12345"


class TestMockConnectionUsage:
    """Tests for typical MockConnection usage patterns."""

    @pytest.mark.asyncio
    async def test_multiple_messages(self):
        """Test sending multiple messages."""
        from backend.websocket.mock_connection import MockConnection

        conn = MockConnection(host_id="host-123")

        # Send multiple messages
        for i in range(5):
            await conn.send_message({"message_type": f"message-{i}"})

        # Should complete without issues
        assert conn.host_id == "host-123"

    def test_is_mock_flag_identifies_mock(self):
        """Test is_mock_connection flag can be used to identify mock connections."""
        from backend.websocket.mock_connection import MockConnection

        conn = MockConnection(host_id="host-123")

        # This flag allows handlers to skip certain operations
        if conn.is_mock_connection:
            # Would skip last_access updates, etc.
            pass

        assert conn.is_mock_connection is True
