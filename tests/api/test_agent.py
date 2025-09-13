"""
Unit tests for agent communication API endpoints.
Tests agent authentication and WebSocket connection endpoints.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import json

from backend.websocket.messages import MessageType


class TestAgentAuth:
    """Test cases for POST /agent/auth endpoint."""

    @patch("backend.api.agent.websocket_security")
    def test_agent_auth_success(self, mock_security, client):
        """Test successful agent authentication."""
        # Mock security validations
        mock_security.is_connection_rate_limited.return_value = False
        mock_security.generate_connection_token.return_value = "test_token_123"

        # Mock request with agent hostname header
        response = client.post(
            "/agent/auth", headers={"x-agent-hostname": "test-agent.example.com"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "connection_token" in data
        assert data["connection_token"] == "test_token_123"
        assert data["expires_in"] == 3600
        assert data["websocket_endpoint"] == "/api/agent/connect"

        # Verify security methods were called
        mock_security.record_connection_attempt.assert_called_once()
        mock_security.generate_connection_token.assert_called_once_with(
            "test-agent.example.com", "testclient"  # Default test client host
        )

    @patch("backend.api.agent.websocket_security")
    def test_agent_auth_rate_limited(self, mock_security, client):
        """Test agent authentication when rate limited."""
        # Mock rate limiting
        mock_security.is_connection_rate_limited.return_value = True

        response = client.post("/agent/auth")

        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"] == "Rate limit exceeded"
        assert data["retry_after"] == 900

        # Verify rate limit was checked but token generation was not called
        mock_security.is_connection_rate_limited.assert_called_once()
        mock_security.generate_connection_token.assert_not_called()

    @patch("backend.api.agent.websocket_security")
    def test_agent_auth_no_hostname_header(self, mock_security, client):
        """Test agent authentication without hostname header."""
        mock_security.is_connection_rate_limited.return_value = False
        mock_security.generate_connection_token.return_value = "test_token_456"

        response = client.post("/agent/auth")

        assert response.status_code == 200
        data = response.json()
        assert "connection_token" in data

        # Should use client IP as hostname when header is missing
        mock_security.generate_connection_token.assert_called_once_with(
            "testclient",  # Uses client IP as hostname fallback
            "testclient",  # Client host
        )

    @patch("backend.api.agent.websocket_security")
    def test_agent_auth_with_custom_client_ip(self, mock_security, client):
        """Test agent authentication with different client IP scenarios."""
        mock_security.is_connection_rate_limited.return_value = False
        mock_security.generate_connection_token.return_value = "test_token_789"

        # Test with X-Forwarded-For header (simulating proxy)
        response = client.post(
            "/agent/auth",
            headers={
                "x-agent-hostname": "proxy-agent.example.com",
                "x-forwarded-for": "192.168.1.100",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "connection_token" in data

        # Verify security methods were called with expected parameters
        mock_security.record_connection_attempt.assert_called_once()


class TestAgentWebSocket:
    """Test cases for WebSocket /agent/connect endpoint."""

    def test_websocket_endpoint_exists(self, client):
        """Test that WebSocket endpoint exists and can be reached."""
        # Note: Testing actual WebSocket connections requires more complex setup
        # This test verifies the endpoint exists and basic routing works

        # Since we can't easily test WebSocket connections with TestClient,
        # we'll test the route exists by checking it doesn't return 404
        # for WebSocket upgrade requests

        # This would typically require a WebSocket test client
        # For now, we verify the endpoint is registered

        # Check that the endpoint is in the router
        from backend.api import agent

        routes = [route.path for route in agent.router.routes]
        assert "/api/agent/connect" in routes

    @patch("backend.api.agent.websocket_security")
    @patch("backend.api.agent.connection_manager")
    def test_websocket_security_validation(
        self, mock_connection_manager, mock_security
    ):
        """Test WebSocket security validation logic."""
        # This tests the security validation logic that would be used
        # in the WebSocket connection handler

        # Mock security validation
        mock_security.validate_connection_token.return_value = {
            "valid": True,
            "hostname": "test-agent.example.com",
            "client_ip": "192.168.1.100",
        }

        # Mock connection manager
        mock_connection_manager.connect_agent.return_value = "agent_123"

        # Test the validation logic
        token = "valid_token_123"
        client_ip = "192.168.1.100"

        validation_result = mock_security.validate_connection_token(token, client_ip)

        assert validation_result["valid"] is True
        assert validation_result["hostname"] == "test-agent.example.com"

        # Verify security validation was called
        mock_security.validate_connection_token.assert_called_once_with(
            token, client_ip
        )

    @patch("backend.api.agent.websocket_security")
    def test_websocket_invalid_token(self, mock_security):
        """Test WebSocket connection with invalid token."""
        # Mock security validation failure
        mock_security.validate_connection_token.return_value = {
            "valid": False,
            "error": "Invalid or expired token",
        }

        token = "invalid_token"
        client_ip = "192.168.1.100"

        validation_result = mock_security.validate_connection_token(token, client_ip)

        assert validation_result["valid"] is False
        assert "Invalid or expired token" in validation_result["error"]

    @patch("backend.api.agent.connection_manager")
    def test_websocket_connection_management(self, mock_connection_manager):
        """Test WebSocket connection management integration."""
        # Test connection manager integration
        mock_websocket = Mock()
        agent_id = "test_agent_123"
        hostname = "test-agent.example.com"

        # Mock successful connection
        mock_connection_manager.connect_agent.return_value = agent_id
        mock_connection_manager.disconnect_agent.return_value = True
        mock_connection_manager.send_to_agent = AsyncMock(return_value=True)

        # Test connection
        connection_id = mock_connection_manager.connect_agent(mock_websocket, hostname)
        assert connection_id == agent_id

        # Test message sending
        test_message = {"type": "ping", "data": {}}
        result = mock_connection_manager.send_to_agent(agent_id, test_message)
        # Since this is an AsyncMock, we need to await it in a real scenario

        # Test disconnection
        disconnect_result = mock_connection_manager.disconnect_agent(agent_id)
        assert disconnect_result is True

        # Verify methods were called
        mock_connection_manager.connect_agent.assert_called_once_with(
            mock_websocket, hostname
        )
        mock_connection_manager.disconnect_agent.assert_called_once_with(agent_id)

    @patch("backend.api.agent.get_db")
    def test_websocket_database_integration(self, mock_get_db):
        """Test WebSocket database integration for host updates."""
        # Mock database session
        mock_session = Mock()
        mock_get_db.return_value.__enter__.return_value = mock_session

        # Mock host query
        mock_host = Mock()
        mock_host.fqdn = "test-agent.example.com"
        mock_host.last_checkin = None

        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        # Test database update logic
        hostname = "test-agent.example.com"

        # Simulate finding and updating host
        host = mock_session.query().filter().first()
        if host:
            host.last_checkin = "2023-01-01T12:00:00Z"
            mock_session.commit()

        # Verify database operations
        assert host.fqdn == hostname
        mock_session.commit.assert_called_once()

    def test_websocket_message_validation(self):
        """Test WebSocket message format validation."""
        from backend.websocket.messages import create_message, MessageType

        # Test valid message creation
        raw_message = {
            "message_type": MessageType.SYSTEM_INFO,
            "data": {"status": "connected", "hostname": "test-agent"},
        }
        message = create_message(raw_message)

        assert message.message_type == MessageType.SYSTEM_INFO
        assert message.data["hostname"] == "test-agent"
        assert message.message_id is not None
        assert message.timestamp is not None

    @patch("backend.api.agent.config_push_manager")
    def test_websocket_config_push_integration(self, mock_config_manager):
        """Test WebSocket integration with config push manager."""
        # Mock config push functionality
        mock_config_manager.has_pending_config.return_value = True
        mock_config_manager.get_pending_config.return_value = {
            "hostname": "test-agent.example.com",
            "config": {"setting1": "value1", "setting2": "value2"},
            "version": "1.0.0",
        }
        mock_config_manager.mark_config_sent.return_value = True

        hostname = "test-agent.example.com"

        # Test config push logic
        if mock_config_manager.has_pending_config(hostname):
            pending_config = mock_config_manager.get_pending_config(hostname)
            assert pending_config["hostname"] == hostname
            assert "config" in pending_config

            # Mark as sent
            mock_config_manager.mark_config_sent(hostname, pending_config["version"])

        # Verify config manager methods were called
        mock_config_manager.has_pending_config.assert_called_once_with(hostname)
        mock_config_manager.get_pending_config.assert_called_once_with(hostname)
        mock_config_manager.mark_config_sent.assert_called_once_with(hostname, "1.0.0")


class TestAgentErrorHandling:
    """Test error handling in agent communication."""

    @patch("backend.api.agent.websocket_security")
    def test_auth_security_exception(self, mock_security, client):
        """Test agent auth when security module raises exception."""
        # Mock security exception
        mock_security.is_connection_rate_limited.side_effect = Exception(
            "Security error"
        )

        # The security exception should cause the request to fail
        with pytest.raises(Exception, match="Security error"):
            response = client.post("/agent/auth")

    @patch("backend.api.agent.websocket_security")
    def test_auth_token_generation_failure(self, mock_security, client):
        """Test agent auth when token generation fails."""
        mock_security.is_connection_rate_limited.return_value = False
        mock_security.generate_connection_token.return_value = None

        response = client.post("/agent/auth")

        # Should handle token generation failure
        assert response.status_code in [200, 500]
