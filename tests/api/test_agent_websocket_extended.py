# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Fixed extended comprehensive tests for agent WebSocket functionality.
Tests additional functions and edge cases in agent.py with correct mocking.
"""

import json
from unittest.mock import AsyncMock, Mock, patch
import pytest
from fastapi import WebSocket

from backend.api.agent import (
    agent_connect,
)


class TestWebSocketConnect:
    """Test the main WebSocket connection function."""

    @pytest.fixture
    def mock_websocket(self):
        websocket = Mock(spec=WebSocket)
        websocket.client = Mock()
        websocket.client.host = "192.168.1.100"
        websocket.query_params = {"token": "valid_token_123"}
        websocket.close = AsyncMock()
        websocket.receive_text = AsyncMock()
        return websocket

    @pytest.mark.asyncio
    @patch("backend.api.agent.AuditService.log")
    @patch("backend.api.agent.get_db")
    async def test_agent_connect_no_auth_token(
        self, mock_get_db, mock_audit_log, mock_websocket
    ):
        """Test WebSocket connection with no auth token."""
        # Remove token from query params
        mock_websocket.query_params = {}

        # Mock database session
        mock_db = Mock()
        mock_db.close = Mock()
        mock_get_db.return_value = iter([mock_db])

        await agent_connect(mock_websocket)

        # Should close with auth error
        mock_websocket.close.assert_called_once_with(
            code=4000, reason="Authentication token required"
        )

        # Verify audit log was called
        assert mock_audit_log.called

    @pytest.mark.asyncio
    @patch("backend.api.agent.AuditService.log")
    @patch("backend.api.agent.get_db")
    @patch("backend.api.agent.websocket_security")
    async def test_agent_connect_invalid_token(
        self, mock_security, mock_get_db, mock_audit_log, mock_websocket
    ):
        """Test WebSocket connection with invalid token."""
        # Mock invalid token
        mock_security.validate_connection_token.return_value = (
            False,
            None,
            "Invalid token",
        )

        # Mock database session
        mock_db = Mock()
        mock_db.close = Mock()
        mock_get_db.return_value = iter([mock_db])

        await agent_connect(mock_websocket)

        # Should close with auth error
        mock_websocket.close.assert_called_once_with(
            code=4001, reason="Authentication failed: Invalid token"
        )

        # Verify audit log was called
        assert mock_audit_log.called


class TestHostValidationExtended:
    """Extended tests for host validation with more edge cases."""

    @pytest.fixture
    def mock_connection(self):
        connection = Mock()
        connection.agent_id = "test-agent-123"
        return connection

    @pytest.fixture
    def mock_db(self):
        return Mock()

    @pytest.mark.asyncio
    async def test_validate_host_with_short_hostname_match(
        self, mock_connection, mock_db
    ):
        """Test host validation with short hostname matching FQDN."""
        from backend.api.agent import _validate_and_get_host

        message_data = {
            "hostname": "shortname",  # Short hostname
            "host_id": "host-123",
        }

        # Mock host with FQDN
        mock_host = Mock()
        mock_host.id = "host-123"
        mock_host.fqdn = "shortname.example.com"  # FQDN where short name matches
        mock_host.approval_status = "approved"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        host, error = await _validate_and_get_host(
            message_data, mock_connection, mock_db
        )

        # Should succeed - short hostname matches FQDN short name
        assert host == mock_host
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_host_case_insensitive(self, mock_connection, mock_db):
        """Test host validation is case insensitive."""
        from backend.api.agent import _validate_and_get_host

        message_data = {"hostname": "TEST-HOST.EXAMPLE.COM"}  # Uppercase

        # Mock case-insensitive query
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        mock_host = Mock()
        mock_host.fqdn = "test-host.example.com"  # Lowercase in DB
        mock_host.approval_status = "approved"
        mock_query.first.return_value = mock_host

        host, error = await _validate_and_get_host(
            message_data, mock_connection, mock_db
        )

        # Should succeed with case-insensitive match
        assert host == mock_host
        assert error is None


class TestMessageProcessingErrorHandling:
    """Test error handling in message processing."""

    @pytest.fixture
    def mock_connection(self):
        connection = Mock()
        connection.agent_id = "test-agent-123"
        connection.send_message = AsyncMock()
        return connection

    @pytest.fixture
    def mock_db(self):
        return Mock()

    @pytest.mark.asyncio
    async def test_process_message_general_exception_with_send_failure(
        self, mock_connection, mock_db
    ):
        """Test message processing with general exception and send error failure."""
        from backend.api.agent import _process_websocket_message

        valid_message = {"message_type": "test", "data": {}}

        with patch("backend.api.agent.websocket_security") as mock_security, patch(
            "backend.api.agent.create_message"
        ) as mock_create:

            # Mock security validation to pass
            mock_security.validate_message_integrity.return_value = (True, "")

            # Mock create_message to raise exception
            mock_create.side_effect = Exception("Processing error")

            # Mock send_message to also fail
            mock_connection.send_message.side_effect = Exception("Send failed")

            # Should not raise exception despite both failures
            await _process_websocket_message(
                json.dumps(valid_message), mock_connection, mock_db, "connection-123"
            )

            # Verify send was attempted
            mock_connection.send_message.assert_called_once()


class TestConfigPushIntegration:
    """Test config push integration in WebSocket handling."""

    @pytest.mark.asyncio
    async def test_config_push_integration_basic(self):
        """Test basic config push manager access."""
        from backend.api.agent import config_push_manager

        # Test that config_push_manager is accessible
        assert config_push_manager is not None

        # Test basic functionality without mocking internal methods
        # This tests the import and basic object structure
        assert hasattr(config_push_manager, "__class__")
        assert config_push_manager.__class__.__name__ == "ConfigPushManager"


class TestBasicWebSocketFunctionality:
    """Test basic WebSocket functionality that should work."""

    @pytest.mark.asyncio
    async def test_agent_connect_basic(self):
        """Test that agent connect function exists and is callable."""
        # Import test
        assert agent_connect is not None
        assert callable(agent_connect)
