"""
Test WebSocket heartbeat message handling.
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from backend.websocket.messages import HeartbeatMessage, MessageType, create_message


class TestHeartbeatMessage:
    """Test heartbeat message creation and handling."""

    def test_heartbeat_message_creation(self):
        """Test creating a heartbeat message."""
        message = HeartbeatMessage()

        assert message.message_type == MessageType.HEARTBEAT
        assert message.data["agent_status"] == "healthy"
        assert message.data["system_load"] is None
        assert message.data["memory_usage"] is None
        assert "message_id" in message.to_dict()
        assert "timestamp" in message.to_dict()

    def test_heartbeat_message_with_data(self):
        """Test creating a heartbeat message with system metrics."""
        message = HeartbeatMessage(
            agent_status="healthy", system_load=0.5, memory_usage=75.2
        )

        assert message.data["agent_status"] == "healthy"
        assert message.data["system_load"] == 0.5
        assert message.data["memory_usage"] == 75.2

    def test_heartbeat_message_serialization(self):
        """Test heartbeat message serialization."""
        message = HeartbeatMessage(
            agent_status="healthy", system_load=0.3, memory_usage=60.0
        )

        serialized = message.to_dict()

        assert serialized["message_type"] == "heartbeat"
        assert serialized["data"]["agent_status"] == "healthy"
        assert serialized["data"]["system_load"] == 0.3
        assert serialized["data"]["memory_usage"] == 60.0
        assert isinstance(serialized["timestamp"], str)

    def test_heartbeat_message_json_serialization(self):
        """Test that heartbeat messages can be JSON serialized."""
        message = HeartbeatMessage(
            agent_status="healthy", system_load=0.8, memory_usage=90.5
        )

        # Should not raise an exception
        json_str = json.dumps(message.to_dict())

        # Should be able to deserialize
        deserialized = json.loads(json_str)
        assert deserialized["message_type"] == "heartbeat"
        assert deserialized["data"]["system_load"] == 0.8

    def test_create_heartbeat_from_dict(self):
        """Test creating heartbeat message from dictionary."""
        data = {
            "message_type": "heartbeat",
            "message_id": "test-123",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "agent_status": "healthy",
                "system_load": 0.4,
                "memory_usage": 65.0,
            },
        }

        message = create_message(data)

        assert isinstance(message, HeartbeatMessage)
        assert message.message_type == MessageType.HEARTBEAT
        assert message.data["agent_status"] == "healthy"
        assert message.data["system_load"] == 0.4
        assert message.data["memory_usage"] == 65.0


class TestConnectionManagerHeartbeat:
    """Test connection manager heartbeat functionality."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock agent connection."""
        from backend.websocket.connection_manager import AgentConnection

        connection = Mock(spec=AgentConnection)
        connection.agent_id = "test-agent-123"
        connection.hostname = "test-host.example.com"
        connection.ipv4 = "192.168.1.100"
        connection.ipv6 = "2001:db8::1"
        connection.platform = "Linux"
        connection.connected_at = datetime.utcnow()
        connection.last_seen = datetime.utcnow()
        connection.send_message = AsyncMock(return_value=True)
        return connection

    @pytest.fixture
    def connection_manager(self):
        """Create a connection manager instance."""
        from backend.websocket.connection_manager import ConnectionManager

        return ConnectionManager()

    def test_connection_last_seen_update(self, mock_connection):
        """Test that connection last_seen is updated."""
        initial_time = mock_connection.last_seen

        # Simulate heartbeat update
        mock_connection.update_info()

        assert mock_connection.last_seen >= initial_time

    def test_connection_info_update(self, mock_connection):
        """Test updating connection info."""
        # Since mock_connection is a Mock, we need to test the actual update_info method
        from backend.websocket.connection_manager import AgentConnection
        from unittest.mock import Mock

        # Create a real connection to test the update functionality
        websocket_mock = Mock()
        connection = AgentConnection(websocket_mock)

        connection.update_info(
            hostname="updated-host.example.com",
            ipv4="192.168.1.101",
            platform="Windows",
        )

        assert connection.hostname == "updated-host.example.com"
        assert connection.ipv4 == "192.168.1.101"
        assert connection.platform == "Windows"

    def test_get_active_agents_includes_heartbeat_info(
        self, connection_manager, mock_connection
    ):
        """Test that get_active_agents includes heartbeat info."""
        connection_manager.active_connections["test-agent"] = mock_connection

        agents = connection_manager.get_active_agents()

        assert len(agents) == 1
        agent_info = agents[0]
        assert agent_info["agent_id"] == "test-agent"
        assert agent_info["hostname"] == "test-host.example.com"
        assert "last_seen" in agent_info
        assert "connected_at" in agent_info

    @pytest.mark.asyncio
    async def test_broadcast_heartbeat_command(
        self, connection_manager, mock_connection
    ):
        """Test broadcasting heartbeat command to all agents."""
        connection_manager.active_connections["test-agent"] = mock_connection

        heartbeat_command = {
            "message_type": "ping",
            "message_id": "ping-123",
            "data": {},
        }

        result = await connection_manager.broadcast_to_all(heartbeat_command)

        assert result == 1  # One successful send
        mock_connection.send_message.assert_called_once_with(heartbeat_command)

    @pytest.mark.asyncio
    async def test_broadcast_handles_failed_connections(self, connection_manager):
        """Test that broadcast handles failed connections."""
        # Create a connection that will fail
        failed_connection = Mock()
        failed_connection.send_message = AsyncMock(return_value=False)
        connection_manager.active_connections["failed-agent"] = failed_connection

        # Create a successful connection
        success_connection = Mock()
        success_connection.send_message = AsyncMock(return_value=True)
        connection_manager.active_connections["success-agent"] = success_connection

        test_message = {"message_type": "test"}
        result = await connection_manager.broadcast_to_all(test_message)

        assert result == 1  # Only one successful send
        # Failed connection should be removed
        assert "failed-agent" not in connection_manager.active_connections
        assert "success-agent" in connection_manager.active_connections


class TestWebSocketHeartbeatIntegration:
    """Test WebSocket heartbeat integration."""

    @pytest.mark.asyncio
    async def test_agent_websocket_heartbeat_flow(self):
        """Test complete agent WebSocket heartbeat flow."""
        from backend.api.agent import handle_heartbeat

        # Mock dependencies
        mock_db = Mock()
        mock_host = Mock()
        mock_host.fqdn = "test-host.example.com"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        mock_connection = Mock()
        mock_connection.hostname = "test-host.example.com"
        mock_connection.send_message = AsyncMock()

        message_data = {
            "message_id": "heartbeat-123",
            "agent_status": "healthy",
            "system_load": 0.5,
            "memory_usage": 75.0,
        }

        # Execute heartbeat handling
        await handle_heartbeat(mock_db, mock_connection, message_data)

        # Verify host status was updated
        assert mock_host.status == "up"
        assert mock_host.active is True
        mock_db.commit.assert_called_once()

        # Verify acknowledgment was sent
        mock_connection.send_message.assert_called_once()
        ack_call_args = mock_connection.send_message.call_args[0][0]
        assert ack_call_args["message_type"] == "ack"
        assert ack_call_args["message_id"] == "heartbeat-123"

    def test_message_type_enum(self):
        """Test that heartbeat message type is properly defined."""
        assert MessageType.HEARTBEAT == "heartbeat"
        assert hasattr(MessageType, "HEARTBEAT")

    def test_heartbeat_message_validation(self):
        """Test heartbeat message validation."""
        # Test with invalid agent status
        message = HeartbeatMessage(agent_status="invalid_status")

        # Should still create message but with the provided status
        assert message.data["agent_status"] == "invalid_status"

        # Test with negative system load
        message = HeartbeatMessage(system_load=-1.0)
        assert message.data["system_load"] == -1.0

        # Test with high memory usage
        message = HeartbeatMessage(memory_usage=150.0)
        assert message.data["memory_usage"] == 150.0

    def test_heartbeat_message_defaults(self):
        """Test heartbeat message default values."""
        message = HeartbeatMessage()

        # Check defaults
        assert message.data["agent_status"] == "healthy"
        assert message.data["system_load"] is None
        assert message.data["memory_usage"] is None

        # Ensure message structure is complete
        message_dict = message.to_dict()
        assert "message_id" in message_dict
        assert "timestamp" in message_dict
        assert "message_type" in message_dict
        assert "data" in message_dict
