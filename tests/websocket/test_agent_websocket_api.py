"""
Comprehensive unit tests for the agent WebSocket API.
Tests WebSocket connection handling, message processing, and authentication.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch, MagicMock

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from backend.api.agent import (
    agent_connect,
    authenticate_agent,
    _process_websocket_message,
    _handle_message_by_type,
    _validate_and_get_host,
    _handle_system_info_message,
)
from backend.websocket.messages import MessageType


class TestAuthenticateAgent:
    """Test agent authentication endpoint."""

    @pytest.mark.asyncio
    async def test_authenticate_agent_success(self):
        """Test successful agent authentication."""
        mock_request = Mock()
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {"x-agent-hostname": "test-host.example.com"}

        with patch("backend.api.agent.websocket_security") as mock_security:
            mock_security.is_connection_rate_limited.return_value = False
            mock_security.generate_connection_token.return_value = "test-token-abc123"

            result = await authenticate_agent(mock_request)

            assert "connection_token" in result
            assert result["connection_token"] == "test-token-abc123"
            assert result["expires_in"] == 3600
            assert result["websocket_endpoint"] == "/api/agent/connect"

    @pytest.mark.asyncio
    async def test_authenticate_agent_rate_limited(self):
        """Test agent authentication when rate limited."""
        mock_request = Mock()
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.100"

        with patch("backend.api.agent.websocket_security") as mock_security:
            mock_security.is_connection_rate_limited.return_value = True

            result = await authenticate_agent(mock_request)

            assert "error" in result
            assert result["retry_after"] == 900

    @pytest.mark.asyncio
    async def test_authenticate_agent_no_hostname_header(self):
        """Test authentication uses IP when no hostname header."""
        mock_request = Mock()
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {}  # No x-agent-hostname header

        with patch("backend.api.agent.websocket_security") as mock_security:
            mock_security.is_connection_rate_limited.return_value = False
            mock_security.generate_connection_token.return_value = "test-token"

            await authenticate_agent(mock_request)

            # Should use IP as hostname fallback
            mock_security.generate_connection_token.assert_called_once_with(
                "192.168.1.100", "192.168.1.100"
            )


class TestAgentConnect:
    """Test agent WebSocket connection endpoint."""

    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket."""
        ws = AsyncMock(spec=WebSocket)
        ws.client = Mock()
        ws.client.host = "192.168.1.100"
        ws.query_params = {"token": "valid-token"}
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.receive_text = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_agent_connect_no_token(self, mock_websocket):
        """Test connection attempt without authentication token."""
        mock_websocket.query_params = {}  # No token

        with patch("backend.api.agent.get_db") as mock_get_db, patch(
            "backend.api.agent.AuditService"
        ) as mock_audit:
            mock_db = Mock()
            mock_db.close = Mock()
            mock_get_db.return_value = iter([mock_db])

            await agent_connect(mock_websocket)

            mock_websocket.close.assert_called_once_with(
                code=4000, reason="Authentication token required"
            )

    @pytest.mark.asyncio
    async def test_agent_connect_invalid_token(self, mock_websocket):
        """Test connection attempt with invalid token."""
        with patch("backend.api.agent.get_db") as mock_get_db, patch(
            "backend.api.agent.websocket_security"
        ) as mock_security, patch("backend.api.agent.AuditService") as mock_audit:
            mock_db = Mock()
            mock_db.close = Mock()
            mock_get_db.return_value = iter([mock_db])
            mock_security.validate_connection_token.return_value = (
                False,
                None,
                "Invalid token signature",
            )

            await agent_connect(mock_websocket)

            mock_websocket.close.assert_called_once()
            close_args = mock_websocket.close.call_args
            assert close_args[1]["code"] == 4001

    @pytest.mark.asyncio
    async def test_agent_connect_valid_token_then_disconnect(self, mock_websocket):
        """Test valid connection that then disconnects."""
        mock_websocket.receive_text.side_effect = WebSocketDisconnect()

        with patch("backend.api.agent.get_db") as mock_get_db, patch(
            "backend.api.agent.websocket_security"
        ) as mock_security, patch("backend.api.agent.connection_manager") as mock_cm:
            mock_db = Mock()
            mock_db.close = Mock()
            mock_get_db.return_value = iter([mock_db])
            mock_security.validate_connection_token.return_value = (
                True,
                "conn-123",
                "Valid",
            )

            mock_connection = Mock()
            mock_connection.agent_id = "agent-123"
            mock_cm.connect = AsyncMock(return_value=mock_connection)

            await agent_connect(mock_websocket)

            mock_cm.disconnect.assert_called_once_with("agent-123")
            mock_db.close.assert_called_once()


class TestProcessWebSocketMessage:
    """Test _process_websocket_message function."""

    @pytest.fixture
    def mock_connection(self):
        """Create mock connection."""
        conn = Mock()
        conn.agent_id = "agent-123"
        conn.hostname = "test-host.example.com"
        conn.send_message = AsyncMock()
        return conn

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return Mock()

    @pytest.mark.asyncio
    async def test_process_valid_heartbeat_message(self, mock_connection, mock_db):
        """Test processing valid heartbeat message."""
        message = {
            "message_type": "heartbeat",
            "message_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {"status": "healthy"},
        }

        with patch("backend.api.agent.websocket_security") as mock_security, patch(
            "backend.api.agent._handle_message_by_type"
        ) as mock_handler:
            mock_security.validate_message_integrity.return_value = (True, "")
            mock_handler.return_value = None

            await _process_websocket_message(
                json.dumps(message), mock_connection, mock_db, "conn-123"
            )

            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_invalid_json(self, mock_connection, mock_db):
        """Test processing invalid JSON."""
        invalid_json = "{ not valid json"

        await _process_websocket_message(
            invalid_json, mock_connection, mock_db, "conn-123"
        )

        mock_connection.send_message.assert_called_once()
        error_msg = mock_connection.send_message.call_args[0][0]
        assert error_msg["message_type"] == "error"
        # Error message format uses "error_type" not "error_code"
        assert "json" in error_msg["error_type"].lower()

    @pytest.mark.asyncio
    async def test_process_failed_validation(self, mock_connection, mock_db):
        """Test processing message that fails validation."""
        message = {
            "message_type": "heartbeat",
            "message_id": "short",  # Invalid ID
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        with patch("backend.api.agent.websocket_security") as mock_security:
            mock_security.validate_message_integrity.return_value = (
                False,
                "Invalid message_id format",
            )

            await _process_websocket_message(
                json.dumps(message), mock_connection, mock_db, "conn-123"
            )

            mock_connection.send_message.assert_called_once()
            error_msg = mock_connection.send_message.call_args[0][0]
            assert error_msg["message_type"] == "error"

    @pytest.mark.asyncio
    async def test_process_system_info_handled_immediately(
        self, mock_connection, mock_db
    ):
        """Test that SYSTEM_INFO messages are handled immediately."""
        message = {
            "message_type": "system_info",
            "message_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {"hostname": "test-host.example.com"},
        }

        with patch("backend.api.agent.websocket_security") as mock_security, patch(
            "backend.api.agent._handle_message_by_type"
        ) as mock_handler:
            mock_security.validate_message_integrity.return_value = (True, "")
            mock_handler.return_value = None

            await _process_websocket_message(
                json.dumps(message), mock_connection, mock_db, "conn-123"
            )

            # Should call handler, not enqueue
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_other_messages_queued(self, mock_connection, mock_db):
        """Test that non-heartbeat/system_info messages are queued."""
        message = {
            "message_type": "hardware_update",
            "message_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {"cpu_vendor": "Intel"},
        }

        with patch("backend.api.agent.websocket_security") as mock_security, patch(
            "backend.api.agent._enqueue_inbound_message"
        ) as mock_enqueue:
            mock_security.validate_message_integrity.return_value = (True, "")

            await _process_websocket_message(
                json.dumps(message), mock_connection, mock_db, "conn-123"
            )

            mock_enqueue.assert_called_once()


class TestHandleMessageByType:
    """Test _handle_message_by_type function."""

    @pytest.fixture
    def mock_connection(self):
        """Create mock connection."""
        conn = Mock()
        conn.agent_id = "agent-123"
        conn.hostname = "test-host.example.com"
        conn.send_message = AsyncMock()
        return conn

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return Mock()

    @pytest.mark.asyncio
    async def test_handle_system_info(self, mock_connection, mock_db):
        """Test handling SYSTEM_INFO message."""
        message = Mock()
        message.message_type = MessageType.SYSTEM_INFO
        message.data = {"hostname": "test-host.example.com"}

        with patch("backend.api.agent.handle_system_info") as mock_handler:
            mock_handler.return_value = {"status": "success"}

            await _handle_message_by_type(message, mock_connection, mock_db)

            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_heartbeat(self, mock_connection, mock_db):
        """Test handling HEARTBEAT message."""
        message = Mock()
        message.message_type = MessageType.HEARTBEAT
        message.message_id = "msg-123"
        message.data = {"status": "healthy"}

        with patch("backend.api.agent.handle_heartbeat") as mock_handler:
            mock_handler.return_value = None

            await _handle_message_by_type(message, mock_connection, mock_db)

            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_unexpected_type_logs_warning(self, mock_connection, mock_db):
        """Test handling unexpected message type logs warning."""
        message = Mock()
        message.message_type = "unexpected_type"
        message.data = {}

        with patch("backend.api.agent.logger") as mock_logger:
            await _handle_message_by_type(message, mock_connection, mock_db)

            mock_logger.warning.assert_called_once()


class TestValidateAndGetHost:
    """Test _validate_and_get_host function."""

    @pytest.fixture
    def mock_connection(self):
        """Create mock connection."""
        conn = Mock()
        conn.agent_id = "agent-123"
        conn.hostname = "test-host.example.com"
        conn.ipv4 = "192.168.1.100"
        conn.ipv6 = None
        return conn

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = Mock()
        db.query = Mock()
        db.expire_all = Mock()
        db.flush = Mock()
        return db

    @pytest.mark.asyncio
    async def test_validate_host_success_by_hostname(self, mock_connection, mock_db):
        """Test successful host validation by hostname."""
        mock_host = Mock()
        mock_host.id = "host-123"
        mock_host.fqdn = "test-host.example.com"
        mock_host.approval_status = "approved"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        message_data = {"hostname": "test-host.example.com"}

        host, error = await _validate_and_get_host(
            message_data, mock_connection, mock_db
        )

        assert host == mock_host
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_host_success_by_host_id(self, mock_connection, mock_db):
        """Test successful host validation by host_id."""
        mock_host = Mock()
        mock_host.id = "host-123"
        mock_host.fqdn = "test-host.example.com"
        mock_host.approval_status = "approved"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        message_data = {"host_id": "host-123", "hostname": "test-host.example.com"}

        host, error = await _validate_and_get_host(
            message_data, mock_connection, mock_db
        )

        assert host == mock_host
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_host_missing_identifiers(self, mock_connection, mock_db):
        """Test validation fails with missing hostname and host_id."""
        mock_connection.hostname = None
        mock_connection.ipv4 = None
        mock_connection.ipv6 = None

        message_data = {}  # No hostname or host_id

        with patch("backend.api.agent.AuditService"):
            host, error = await _validate_and_get_host(
                message_data, mock_connection, mock_db
            )

            assert host is None
            assert error is not None
            # ErrorMessage uses _error_code attribute
            assert error._error_code == "missing_host_info"

    @pytest.mark.asyncio
    async def test_validate_host_not_registered(self, mock_connection, mock_db):
        """Test validation fails for unregistered host."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        message_data = {"hostname": "unknown-host.example.com"}

        with patch("backend.api.agent.AuditService"):
            host, error = await _validate_and_get_host(
                message_data, mock_connection, mock_db
            )

            assert host is None
            assert error is not None
            assert error._error_code == "host_not_registered"

    @pytest.mark.asyncio
    async def test_validate_host_not_approved(self, mock_connection, mock_db):
        """Test validation fails for unapproved host."""
        mock_host = Mock()
        mock_host.id = "host-123"
        mock_host.fqdn = "test-host.example.com"
        mock_host.approval_status = "pending"  # Not approved

        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        message_data = {"hostname": "test-host.example.com"}

        with patch("backend.api.agent.AuditService"):
            host, error = await _validate_and_get_host(
                message_data, mock_connection, mock_db
            )

            assert host is None
            assert error is not None
            assert error._error_code == "host_not_approved"


class TestHandleSystemInfoMessage:
    """Test _handle_system_info_message function."""

    @pytest.fixture
    def mock_connection(self):
        """Create mock connection."""
        conn = Mock()
        conn.agent_id = "agent-123"
        conn.hostname = "test-host.example.com"
        conn.send_message = AsyncMock()
        return conn

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return Mock()

    @pytest.mark.asyncio
    async def test_handle_system_info_success(self, mock_connection, mock_db):
        """Test successful system info handling."""
        message = Mock()
        message.data = {
            "hostname": "test-host.example.com",
            "os_name": "Ubuntu",
            "os_version": "22.04",
        }

        with patch("backend.api.agent.handle_system_info") as mock_handler:
            mock_handler.return_value = {"message_type": "registration_success"}

            await _handle_system_info_message(message, mock_connection, mock_db)

            mock_handler.assert_called_once()
            mock_connection.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_system_info_no_response(self, mock_connection, mock_db):
        """Test system info handling when handler returns None."""
        message = Mock()
        message.data = {"hostname": "test-host.example.com"}

        with patch("backend.api.agent.handle_system_info") as mock_handler:
            mock_handler.return_value = None

            await _handle_system_info_message(message, mock_connection, mock_db)

            mock_handler.assert_called_once()
            mock_connection.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_system_info_exception(self, mock_connection, mock_db):
        """Test system info handling with exception."""
        message = Mock()
        message.data = {"hostname": "test-host.example.com"}

        with patch("backend.api.agent.handle_system_info") as mock_handler:
            mock_handler.side_effect = Exception("Handler error")

            with pytest.raises(Exception, match="Handler error"):
                await _handle_system_info_message(message, mock_connection, mock_db)


class TestAgentWebSocketAPIModuleImports:
    """Test module-level functionality and imports."""

    def test_agent_connect_is_async(self):
        """Test that agent_connect is an async function."""
        import asyncio

        assert asyncio.iscoroutinefunction(agent_connect)

    def test_authenticate_agent_is_async(self):
        """Test that authenticate_agent is an async function."""
        import asyncio

        assert asyncio.iscoroutinefunction(authenticate_agent)

    def test_process_websocket_message_is_async(self):
        """Test that _process_websocket_message is an async function."""
        import asyncio

        assert asyncio.iscoroutinefunction(_process_websocket_message)

    def test_handle_message_by_type_is_async(self):
        """Test that _handle_message_by_type is an async function."""
        import asyncio

        assert asyncio.iscoroutinefunction(_handle_message_by_type)

    def test_validate_and_get_host_is_async(self):
        """Test that _validate_and_get_host is an async function."""
        import asyncio

        assert asyncio.iscoroutinefunction(_validate_and_get_host)
