"""
Comprehensive unit tests for WebSocket connection manager.
Tests connection handling, message routing, and connection lifecycle.
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch, MagicMock

import pytest
from fastapi import WebSocket
from websockets.exceptions import ConnectionClosed

from backend.websocket.connection_manager import (
    AgentConnection,
    ConnectionManager,
    connection_manager,
)


class TestAgentConnection:
    """Test AgentConnection class functionality."""

    def test_agent_connection_initialization_default(self):
        """Test AgentConnection with default agent_id."""
        mock_ws = Mock(spec=WebSocket)
        connection = AgentConnection(mock_ws)

        assert connection.websocket == mock_ws
        assert connection.agent_id is not None
        assert len(connection.agent_id) == 36  # UUID format
        assert connection.hostname is None
        assert connection.ipv4 is None
        assert connection.ipv6 is None
        assert connection.platform is None
        assert connection.pending_commands == []
        assert isinstance(connection.connected_at, datetime)
        assert isinstance(connection.last_seen, datetime)

    def test_agent_connection_initialization_with_agent_id(self):
        """Test AgentConnection with provided agent_id."""
        mock_ws = Mock(spec=WebSocket)
        connection = AgentConnection(mock_ws, agent_id="custom-agent-123")

        assert connection.agent_id == "custom-agent-123"

    def test_update_info_updates_all_fields(self):
        """Test update_info updates all provided fields."""
        mock_ws = Mock(spec=WebSocket)
        connection = AgentConnection(mock_ws)
        initial_last_seen = connection.last_seen

        connection.update_info(
            hostname="test-host.example.com",
            ipv4="192.168.1.100",
            ipv6="2001:db8::1",
            platform="Linux",
        )

        assert connection.hostname == "test-host.example.com"
        assert connection.ipv4 == "192.168.1.100"
        assert connection.ipv6 == "2001:db8::1"
        assert connection.platform == "Linux"
        assert connection.last_seen >= initial_last_seen

    def test_update_info_partial_update(self):
        """Test update_info with partial fields."""
        mock_ws = Mock(spec=WebSocket)
        connection = AgentConnection(mock_ws)
        connection.hostname = "original-host"
        connection.ipv4 = "10.0.0.1"

        connection.update_info(ipv4="192.168.1.100")

        assert connection.hostname == "original-host"  # Unchanged
        assert connection.ipv4 == "192.168.1.100"  # Updated
        assert connection.ipv6 is None  # Still None
        assert connection.platform is None  # Still None

    def test_update_info_with_none_values(self):
        """Test update_info preserves existing values when None passed."""
        mock_ws = Mock(spec=WebSocket)
        connection = AgentConnection(mock_ws)
        connection.hostname = "existing-host"

        connection.update_info(hostname=None, ipv4="192.168.1.100")

        assert connection.hostname == "existing-host"  # Not overwritten
        assert connection.ipv4 == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        """Test successful message sending."""
        mock_ws = AsyncMock(spec=WebSocket)
        connection = AgentConnection(mock_ws)

        message = {"message_type": "test", "data": {"key": "value"}}
        result = await connection.send_message(message)

        assert result is True
        mock_ws.send_text.assert_called_once_with(json.dumps(message))

    @pytest.mark.asyncio
    async def test_send_message_connection_closed(self):
        """Test send_message returns False when connection closed."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_text.side_effect = ConnectionClosed(None, None)
        connection = AgentConnection(mock_ws)

        result = await connection.send_message({"test": "message"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_os_error(self):
        """Test send_message returns False on OSError."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_text.side_effect = OSError("Connection reset")
        connection = AgentConnection(mock_ws)

        result = await connection.send_message({"test": "message"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_runtime_error(self):
        """Test send_message returns False on RuntimeError."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_text.side_effect = RuntimeError("WebSocket error")
        connection = AgentConnection(mock_ws)

        result = await connection.send_message({"test": "message"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_type_error_stays_connected(self):
        """Test send_message returns True on TypeError (protocol error)."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_text.side_effect = TypeError("Invalid message type")
        connection = AgentConnection(mock_ws)

        result = await connection.send_message({"test": "message"})

        # Protocol errors don't disconnect
        assert result is True

    @pytest.mark.asyncio
    async def test_send_message_value_error_stays_connected(self):
        """Test send_message returns True on ValueError (protocol error)."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_text.side_effect = ValueError("Invalid value")
        connection = AgentConnection(mock_ws)

        result = await connection.send_message({"test": "message"})

        assert result is True

    @pytest.mark.asyncio
    async def test_send_message_connection_related_error(self):
        """Test send_message returns False on connection-related errors."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_text.side_effect = Exception("Connection timeout error")
        connection = AgentConnection(mock_ws)

        result = await connection.send_message({"test": "message"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_unknown_error_stays_connected(self):
        """Test send_message returns True on unknown non-connection errors."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_text.side_effect = Exception("Some unrelated error")
        connection = AgentConnection(mock_ws)

        result = await connection.send_message({"test": "message"})

        # Unknown errors default to staying connected
        assert result is True


class TestConnectionManager:
    """Test ConnectionManager class functionality."""

    def test_connection_manager_initialization(self):
        """Test ConnectionManager initializes correctly."""
        manager = ConnectionManager()

        assert manager.active_connections == {}
        assert manager.hostname_to_agent == {}
        assert isinstance(manager._command_queue, asyncio.Queue)

    @pytest.mark.asyncio
    async def test_connect_creates_connection(self):
        """Test connect creates and stores connection."""
        manager = ConnectionManager()
        mock_ws = AsyncMock(spec=WebSocket)

        connection = await manager.connect(mock_ws)

        assert connection is not None
        assert connection.agent_id in manager.active_connections
        mock_ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_agent_id(self):
        """Test connect with provided agent_id."""
        manager = ConnectionManager()
        mock_ws = AsyncMock(spec=WebSocket)

        connection = await manager.connect(mock_ws, agent_id="specific-agent-id")

        assert connection.agent_id == "specific-agent-id"
        assert "specific-agent-id" in manager.active_connections

    def test_disconnect_removes_connection(self):
        """Test disconnect removes connection and hostname mapping."""
        manager = ConnectionManager()
        mock_connection = Mock(spec=AgentConnection)
        mock_connection.hostname = "test-host.example.com"
        mock_connection.agent_id = "agent-123"

        manager.active_connections["agent-123"] = mock_connection
        manager.hostname_to_agent["test-host.example.com"] = "agent-123"

        manager.disconnect("agent-123")

        assert "agent-123" not in manager.active_connections
        assert "test-host.example.com" not in manager.hostname_to_agent

    def test_disconnect_nonexistent_agent(self):
        """Test disconnect with nonexistent agent_id does not raise."""
        manager = ConnectionManager()

        # Should not raise
        manager.disconnect("nonexistent-agent")

    def test_disconnect_without_hostname(self):
        """Test disconnect when connection has no hostname."""
        manager = ConnectionManager()
        mock_connection = Mock(spec=AgentConnection)
        mock_connection.hostname = None
        mock_connection.agent_id = "agent-123"

        manager.active_connections["agent-123"] = mock_connection

        manager.disconnect("agent-123")

        assert "agent-123" not in manager.active_connections

    def test_register_agent_success(self):
        """Test register_agent updates connection and creates hostname mapping."""
        manager = ConnectionManager()
        mock_ws = Mock(spec=WebSocket)
        connection = AgentConnection(mock_ws, agent_id="agent-123")
        manager.active_connections["agent-123"] = connection

        result = manager.register_agent(
            agent_id="agent-123",
            hostname="test-host.example.com",
            ipv4="192.168.1.100",
            ipv6="2001:db8::1",
            platform="Linux",
        )

        assert result == connection
        assert connection.hostname == "test-host.example.com"
        assert connection.ipv4 == "192.168.1.100"
        assert connection.ipv6 == "2001:db8::1"
        assert connection.platform == "Linux"
        assert manager.hostname_to_agent["test-host.example.com"] == "agent-123"

    def test_register_agent_nonexistent_connection(self):
        """Test register_agent with nonexistent agent_id returns None."""
        manager = ConnectionManager()

        result = manager.register_agent(
            agent_id="nonexistent-agent",
            hostname="test-host.example.com",
        )

        assert result is None

    def test_register_agent_without_hostname(self):
        """Test register_agent without hostname doesn't create mapping."""
        manager = ConnectionManager()
        mock_ws = Mock(spec=WebSocket)
        connection = AgentConnection(mock_ws, agent_id="agent-123")
        manager.active_connections["agent-123"] = connection

        result = manager.register_agent(
            agent_id="agent-123",
            hostname=None,
            ipv4="192.168.1.100",
        )

        assert result == connection
        assert "test-host.example.com" not in manager.hostname_to_agent

    @pytest.mark.asyncio
    async def test_send_to_agent_success(self):
        """Test send_to_agent sends message to correct agent."""
        manager = ConnectionManager()
        mock_ws = AsyncMock(spec=WebSocket)
        connection = AgentConnection(mock_ws, agent_id="agent-123")
        connection.send_message = AsyncMock(return_value=True)
        manager.active_connections["agent-123"] = connection

        message = {"message_type": "test"}
        result = await manager.send_to_agent("agent-123", message)

        assert result is True
        connection.send_message.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_send_to_agent_nonexistent(self):
        """Test send_to_agent returns False for nonexistent agent."""
        manager = ConnectionManager()

        result = await manager.send_to_agent("nonexistent-agent", {"test": "message"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_to_hostname_exact_match(self):
        """Test send_to_hostname with exact hostname match."""
        manager = ConnectionManager()
        mock_ws = AsyncMock(spec=WebSocket)
        connection = AgentConnection(mock_ws, agent_id="agent-123")
        connection.send_message = AsyncMock(return_value=True)
        manager.active_connections["agent-123"] = connection
        manager.hostname_to_agent["test-host.example.com"] = "agent-123"

        message = {"message_type": "test"}
        result = await manager.send_to_hostname("test-host.example.com", message)

        assert result is True
        connection.send_message.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_send_to_hostname_case_insensitive(self):
        """Test send_to_hostname with case-insensitive match."""
        manager = ConnectionManager()
        mock_ws = AsyncMock(spec=WebSocket)
        connection = AgentConnection(mock_ws, agent_id="agent-123")
        connection.send_message = AsyncMock(return_value=True)
        manager.active_connections["agent-123"] = connection
        manager.hostname_to_agent["test-host.example.com"] = "agent-123"

        message = {"message_type": "test"}
        result = await manager.send_to_hostname("TEST-HOST.EXAMPLE.COM", message)

        assert result is True

    @pytest.mark.asyncio
    async def test_send_to_hostname_not_found(self):
        """Test send_to_hostname returns False when hostname not found."""
        manager = ConnectionManager()

        result = await manager.send_to_hostname("unknown-host", {"test": "message"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_to_host_success(self):
        """Test send_to_host sends to host by database ID."""
        manager = ConnectionManager()
        mock_ws = AsyncMock(spec=WebSocket)
        connection = AgentConnection(mock_ws, agent_id="agent-123")
        connection.send_message = AsyncMock(return_value=True)
        manager.active_connections["agent-123"] = connection
        manager.hostname_to_agent["test-host.example.com"] = "agent-123"

        # Mock the database query
        mock_host = Mock()
        mock_host.fqdn = "test-host.example.com"

        with patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker, patch(
            "backend.persistence.db.get_engine"
        ):
            mock_session = MagicMock()
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=False)
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )
            mock_sessionmaker.return_value.return_value = mock_session

            result = await manager.send_to_host("host-id-123", {"test": "message"})

            assert result is True

    @pytest.mark.asyncio
    async def test_send_to_host_not_found(self):
        """Test send_to_host returns False when host not found."""
        manager = ConnectionManager()

        with patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker, patch(
            "backend.persistence.db.get_engine"
        ):
            mock_session = MagicMock()
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=False)
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )
            mock_sessionmaker.return_value.return_value = mock_session

            result = await manager.send_to_host("nonexistent-host", {"test": "message"})

            assert result is False

    @pytest.mark.asyncio
    async def test_broadcast_to_all_success(self):
        """Test broadcast_to_all sends to all connected agents."""
        manager = ConnectionManager()

        for i in range(3):
            mock_ws = AsyncMock(spec=WebSocket)
            connection = AgentConnection(mock_ws, agent_id=f"agent-{i}")
            connection.send_message = AsyncMock(return_value=True)
            manager.active_connections[f"agent-{i}"] = connection

        message = {"message_type": "broadcast"}
        result = await manager.broadcast_to_all(message)

        assert result == 3

    @pytest.mark.asyncio
    async def test_broadcast_to_all_with_failures(self):
        """Test broadcast_to_all handles failed sends and removes failed connections."""
        manager = ConnectionManager()

        # Create successful connection
        mock_ws_success = AsyncMock(spec=WebSocket)
        success_conn = AgentConnection(mock_ws_success, agent_id="success-agent")
        success_conn.send_message = AsyncMock(return_value=True)
        success_conn.hostname = "success-host"
        manager.active_connections["success-agent"] = success_conn

        # Create failing connection
        mock_ws_fail = AsyncMock(spec=WebSocket)
        fail_conn = AgentConnection(mock_ws_fail, agent_id="fail-agent")
        fail_conn.send_message = AsyncMock(return_value=False)
        fail_conn.hostname = "fail-host"
        manager.active_connections["fail-agent"] = fail_conn
        manager.hostname_to_agent["fail-host"] = "fail-agent"

        result = await manager.broadcast_to_all({"test": "message"})

        assert result == 1
        assert "success-agent" in manager.active_connections
        assert "fail-agent" not in manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_to_platform_success(self):
        """Test broadcast_to_platform sends to agents of specific platform."""
        manager = ConnectionManager()

        # Create Linux agents
        for i in range(2):
            mock_ws = AsyncMock(spec=WebSocket)
            connection = AgentConnection(mock_ws, agent_id=f"linux-agent-{i}")
            connection.platform = "Linux"
            connection.send_message = AsyncMock(return_value=True)
            manager.active_connections[f"linux-agent-{i}"] = connection

        # Create Windows agent
        mock_ws = AsyncMock(spec=WebSocket)
        win_conn = AgentConnection(mock_ws, agent_id="windows-agent")
        win_conn.platform = "Windows"
        win_conn.send_message = AsyncMock(return_value=True)
        manager.active_connections["windows-agent"] = win_conn

        result = await manager.broadcast_to_platform("Linux", {"test": "message"})

        assert result == 2
        # Windows agent should not have received message
        win_conn.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_to_platform_with_failures(self):
        """Test broadcast_to_platform handles failures."""
        manager = ConnectionManager()

        mock_ws = AsyncMock(spec=WebSocket)
        connection = AgentConnection(mock_ws, agent_id="fail-agent")
        connection.platform = "Linux"
        connection.hostname = "fail-host"
        connection.send_message = AsyncMock(return_value=False)
        manager.active_connections["fail-agent"] = connection
        manager.hostname_to_agent["fail-host"] = "fail-agent"

        result = await manager.broadcast_to_platform("Linux", {"test": "message"})

        assert result == 0
        assert "fail-agent" not in manager.active_connections

    def test_get_active_agents(self):
        """Test get_active_agents returns all agent details."""
        manager = ConnectionManager()

        mock_ws = Mock(spec=WebSocket)
        connection = AgentConnection(mock_ws, agent_id="agent-123")
        connection.hostname = "test-host.example.com"
        connection.ipv4 = "192.168.1.100"
        connection.ipv6 = "2001:db8::1"
        connection.platform = "Linux"
        manager.active_connections["agent-123"] = connection

        agents = manager.get_active_agents()

        assert len(agents) == 1
        agent = agents[0]
        assert agent["agent_id"] == "agent-123"
        assert agent["hostname"] == "test-host.example.com"
        assert agent["ipv4"] == "192.168.1.100"
        assert agent["ipv6"] == "2001:db8::1"
        assert agent["platform"] == "Linux"
        assert "connected_at" in agent
        assert "last_seen" in agent

    def test_get_active_agents_empty(self):
        """Test get_active_agents with no connections."""
        manager = ConnectionManager()

        agents = manager.get_active_agents()

        assert agents == []

    def test_get_agent_by_hostname_found(self):
        """Test get_agent_by_hostname returns agent details."""
        manager = ConnectionManager()

        mock_ws = Mock(spec=WebSocket)
        connection = AgentConnection(mock_ws, agent_id="agent-123")
        connection.hostname = "test-host.example.com"
        connection.ipv4 = "192.168.1.100"
        connection.platform = "Linux"
        manager.active_connections["agent-123"] = connection
        manager.hostname_to_agent["test-host.example.com"] = "agent-123"

        agent = manager.get_agent_by_hostname("test-host.example.com")

        assert agent is not None
        assert agent["agent_id"] == "agent-123"
        assert agent["hostname"] == "test-host.example.com"

    def test_get_agent_by_hostname_not_found(self):
        """Test get_agent_by_hostname returns None when not found."""
        manager = ConnectionManager()

        agent = manager.get_agent_by_hostname("unknown-host")

        assert agent is None

    def test_get_agent_by_hostname_stale_mapping(self):
        """Test get_agent_by_hostname returns None when connection is missing."""
        manager = ConnectionManager()
        # Create stale mapping without actual connection
        manager.hostname_to_agent["stale-host"] = "nonexistent-agent"

        agent = manager.get_agent_by_hostname("stale-host")

        assert agent is None


class TestGlobalConnectionManager:
    """Test the global connection_manager instance."""

    def test_global_instance_exists(self):
        """Test that global connection_manager instance exists."""
        assert connection_manager is not None
        assert isinstance(connection_manager, ConnectionManager)

    def test_global_instance_has_required_methods(self):
        """Test global instance has all required methods."""
        required_methods = [
            "connect",
            "disconnect",
            "register_agent",
            "send_to_agent",
            "send_to_hostname",
            "send_to_host",
            "broadcast_to_all",
            "broadcast_to_platform",
            "get_active_agents",
            "get_agent_by_hostname",
        ]

        for method in required_methods:
            assert hasattr(connection_manager, method)
            assert callable(getattr(connection_manager, method))
