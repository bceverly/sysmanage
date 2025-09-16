"""
Tests for WebSocket connection manager.
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from backend.websocket.connection_manager import AgentConnection, ConnectionManager


class TestAgentConnection:
    """Test AgentConnection class."""

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock websocket."""
        mock_ws = Mock()
        mock_ws.send_text = AsyncMock()
        return mock_ws

    def test_agent_connection_creation(self, mock_websocket):
        """Test creating an agent connection."""
        conn = AgentConnection(mock_websocket, "test-agent-123")

        assert conn.websocket == mock_websocket
        assert conn.agent_id == "test-agent-123"
        assert conn.hostname is None
        assert conn.ipv4 is None
        assert conn.ipv6 is None
        assert conn.platform is None
        assert conn.connected_at is not None
        assert conn.last_seen is not None

    def test_agent_connection_auto_id(self, mock_websocket):
        """Test auto-generation of agent ID."""
        conn = AgentConnection(mock_websocket)

        assert conn.agent_id is not None
        assert len(conn.agent_id) > 0

    @pytest.mark.asyncio
    async def test_send_message_success(self, mock_websocket):
        """Test successful message sending."""
        conn = AgentConnection(mock_websocket, "test-agent")
        message = {"test": "data"}

        result = await conn.send_message(message)

        assert result is True
        mock_websocket.send_text.assert_called_once_with('{"test": "data"}')

    @pytest.mark.asyncio
    async def test_send_message_failure(self, mock_websocket):
        """Test message sending failure."""
        mock_websocket.send_text.side_effect = Exception("Connection error")
        conn = AgentConnection(mock_websocket, "test-agent")

        result = await conn.send_message({"test": "data"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_connection_closed(self, mock_websocket):
        """Test message sending with ConnectionClosed exception."""
        from websockets.exceptions import ConnectionClosed

        mock_websocket.send_text.side_effect = ConnectionClosed(None, None)
        conn = AgentConnection(mock_websocket, "test-agent")
        conn.hostname = "test-host"  # Set hostname for logging

        result = await conn.send_message({"test": "data"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_os_error(self, mock_websocket):
        """Test message sending with OSError exception."""
        mock_websocket.send_text.side_effect = OSError("Network error")
        conn = AgentConnection(mock_websocket, "test-agent")
        conn.hostname = "test-host"  # Set hostname for logging

        result = await conn.send_message({"test": "data"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_runtime_error(self, mock_websocket):
        """Test message sending with RuntimeError exception."""
        mock_websocket.send_text.side_effect = RuntimeError("Runtime error")
        conn = AgentConnection(mock_websocket, "test-agent")
        conn.hostname = "test-host"  # Set hostname for logging

        result = await conn.send_message({"test": "data"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_type_error(self, mock_websocket):
        """Test message sending with TypeError (protocol error)."""
        mock_websocket.send_text.side_effect = TypeError("Invalid type")
        conn = AgentConnection(mock_websocket, "test-agent")
        conn.hostname = "test-host"  # Set hostname for logging

        result = await conn.send_message({"test": "data"})

        assert result is True  # Protocol errors don't trigger disconnection

    @pytest.mark.asyncio
    async def test_send_message_value_error(self, mock_websocket):
        """Test message sending with ValueError (protocol error)."""
        mock_websocket.send_text.side_effect = ValueError("Invalid value")
        conn = AgentConnection(mock_websocket, "test-agent")
        conn.hostname = "test-host"  # Set hostname for logging

        result = await conn.send_message({"test": "data"})

        assert result is True  # Protocol errors don't trigger disconnection

    def test_update_info(self, mock_websocket):
        """Test updating agent information."""
        conn = AgentConnection(mock_websocket, "test-agent")
        original_last_seen = conn.last_seen

        # Wait a bit to ensure timestamp changes
        import time

        time.sleep(0.001)

        conn.update_info(
            hostname="test.example.com", ipv4="192.168.1.1", platform="Linux"
        )

        assert conn.hostname == "test.example.com"
        assert conn.ipv4 == "192.168.1.1"
        assert conn.platform == "Linux"
        assert conn.last_seen > original_last_seen


class TestConnectionManager:
    """Test ConnectionManager class."""

    @pytest.fixture
    def manager(self):
        """Create a fresh connection manager."""
        return ConnectionManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock websocket."""
        mock_ws = Mock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()
        return mock_ws

    @pytest.mark.asyncio
    async def test_connect_agent(self, manager, mock_websocket):
        """Test connecting a new agent."""
        connection = await manager.connect(mock_websocket, "test-agent-123")

        assert connection.agent_id == "test-agent-123"
        assert connection.websocket == mock_websocket
        assert "test-agent-123" in manager.active_connections
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_agent_auto_id(self, manager, mock_websocket):
        """Test connecting agent with auto-generated ID."""
        connection = await manager.connect(mock_websocket)

        assert connection.agent_id is not None
        assert connection.agent_id in manager.active_connections

    def test_disconnect_agent(self, manager, mock_websocket):
        """Test disconnecting an agent."""
        # Manually add a connection
        connection = AgentConnection(mock_websocket, "test-agent-123")
        connection.hostname = "test.example.com"
        manager.active_connections["test-agent-123"] = connection
        manager.hostname_to_agent["test.example.com"] = "test-agent-123"

        manager.disconnect("test-agent-123")

        # Use explicit checking for security
        assert manager.active_connections.get("test-agent-123") is None
        assert manager.hostname_to_agent.get("test.example.com") is None

    def test_register_agent(self, manager, mock_websocket):
        """Test registering agent details."""
        connection = AgentConnection(mock_websocket, "test-agent-123")
        manager.active_connections["test-agent-123"] = connection

        result = manager.register_agent(
            "test-agent-123", "test.example.com", "192.168.1.1", "2001:db8::1", "Linux"
        )

        assert result == connection
        assert connection.hostname == "test.example.com"
        assert connection.ipv4 == "192.168.1.1"
        assert connection.ipv6 == "2001:db8::1"
        assert connection.platform == "Linux"
        assert manager.hostname_to_agent["test.example.com"] == "test-agent-123"

    def test_register_nonexistent_agent(self, manager):
        """Test registering details for non-existent agent."""
        result = manager.register_agent(
            "nonexistent-agent", "test.example.com", "192.168.1.1"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_send_to_agent_success(self, manager, mock_websocket):
        """Test sending message to specific agent."""
        connection = AgentConnection(mock_websocket, "test-agent-123")
        manager.active_connections["test-agent-123"] = connection

        result = await manager.send_to_agent("test-agent-123", {"test": "message"})

        assert result is True
        mock_websocket.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_to_agent_not_found(self, manager):
        """Test sending message to non-existent agent."""
        result = await manager.send_to_agent("nonexistent-agent", {"test": "message"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_to_hostname(self, manager, mock_websocket):
        """Test sending message by hostname."""
        connection = AgentConnection(mock_websocket, "test-agent-123")
        connection.hostname = "test.example.com"
        manager.active_connections["test-agent-123"] = connection
        manager.hostname_to_agent["test.example.com"] = "test-agent-123"

        result = await manager.send_to_hostname("test.example.com", {"test": "message"})

        assert result is True
        mock_websocket.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_to_hostname_not_found(self, manager):
        """Test sending message to unknown hostname."""
        result = await manager.send_to_hostname("unknown.host.com", {"test": "message"})

        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast_to_all(self, manager):
        """Test broadcasting to all agents."""
        # Create multiple mock websockets
        ws1 = Mock()
        ws1.send_text = AsyncMock()
        ws2 = Mock()
        ws2.send_text = AsyncMock()
        ws3 = Mock()
        ws3.send_text = AsyncMock(side_effect=Exception("Connection failed"))

        # Add connections
        manager.active_connections["agent1"] = AgentConnection(ws1, "agent1")
        manager.active_connections["agent2"] = AgentConnection(ws2, "agent2")
        manager.active_connections["agent3"] = AgentConnection(ws3, "agent3")

        result = await manager.broadcast_to_all({"broadcast": "message"})

        assert result == 2  # Two successful sends
        assert "agent3" not in manager.active_connections  # Failed connection removed
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_to_platform(self, manager):
        """Test broadcasting to specific platform."""
        ws1 = Mock()
        ws1.send_text = AsyncMock()
        ws2 = Mock()
        ws2.send_text = AsyncMock()
        ws3 = Mock()
        ws3.send_text = AsyncMock()

        # Add connections with different platforms
        conn1 = AgentConnection(ws1, "agent1")
        conn1.platform = "Linux"
        conn2 = AgentConnection(ws2, "agent2")
        conn2.platform = "Linux"
        conn3 = AgentConnection(ws3, "agent3")
        conn3.platform = "Windows"

        manager.active_connections["agent1"] = conn1
        manager.active_connections["agent2"] = conn2
        manager.active_connections["agent3"] = conn3

        result = await manager.broadcast_to_platform("Linux", {"platform": "message"})

        assert result == 2  # Two Linux agents
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()
        ws3.send_text.assert_not_called()  # Windows agent not called

    def test_get_active_agents(self, manager, mock_websocket):
        """Test getting list of active agents."""
        conn1 = AgentConnection(mock_websocket, "agent1")
        conn1.hostname = "host1.com"
        conn1.platform = "Linux"

        conn2 = AgentConnection(mock_websocket, "agent2")
        conn2.hostname = "host2.com"
        conn2.platform = "Windows"

        manager.active_connections["agent1"] = conn1
        manager.active_connections["agent2"] = conn2

        agents = manager.get_active_agents()

        assert len(agents) == 2
        assert any(
            a["agent_id"] == "agent1" and a["hostname"] == "host1.com" for a in agents
        )
        assert any(
            a["agent_id"] == "agent2" and a["hostname"] == "host2.com" for a in agents
        )

    def test_get_agent_by_hostname(self, manager, mock_websocket):
        """Test getting agent by hostname."""
        conn = AgentConnection(mock_websocket, "test-agent")
        conn.hostname = "test.example.com"
        conn.platform = "Linux"

        manager.active_connections["test-agent"] = conn
        manager.hostname_to_agent["test.example.com"] = "test-agent"

        agent_info = manager.get_agent_by_hostname("test.example.com")

        assert agent_info is not None
        assert agent_info["agent_id"] == "test-agent"
        assert agent_info["hostname"] == "test.example.com"
        assert agent_info["platform"] == "Linux"

    def test_get_agent_by_hostname_not_found(self, manager):
        """Test getting non-existent agent by hostname."""
        agent_info = manager.get_agent_by_hostname("nonexistent.com")

        assert agent_info is None
