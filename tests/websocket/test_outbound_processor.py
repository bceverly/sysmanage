"""
Comprehensive unit tests for WebSocket outbound message processor.
Tests processing and sending of messages from server to agents.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch, MagicMock

import pytest

from backend.websocket.outbound_processor import (
    process_outbound_message,
    send_command_to_agent,
)
from backend.websocket.queue_manager import QueueDirection, QueueStatus


class TestProcessOutboundMessage:
    """Test process_outbound_message function."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return Mock()

    @pytest.fixture
    def mock_host(self):
        """Create mock host object."""
        host = Mock()
        host.id = 123  # Use integer as expected by logging
        host.fqdn = "test-host.example.com"
        host.approval_status = "approved"
        return host

    @pytest.fixture
    def mock_message(self):
        """Create mock message object."""
        message = Mock()
        message.message_id = "msg-123"
        message.message_type = "command"
        message.host_id = 123  # Integer
        return message

    @pytest.mark.asyncio
    async def test_process_outbound_message_command_success(
        self, mock_db, mock_host, mock_message
    ):
        """Test successful command message processing."""
        command_data = {
            "message_type": "command",
            "data": {"command_type": "execute_shell", "parameters": {"cmd": "ls"}},
        }

        with patch(
            "backend.websocket.outbound_processor.server_queue_manager"
        ) as mock_qm, patch(
            "backend.websocket.outbound_processor.send_command_to_agent"
        ) as mock_send:
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.return_value = command_data
            mock_send.return_value = True

            await process_outbound_message(mock_message, mock_host, mock_db)

            mock_qm.mark_processing.assert_called_once()
            mock_qm.mark_sent.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_outbound_message_command_failure(
        self, mock_db, mock_host, mock_message
    ):
        """Test command message processing when send fails."""
        command_data = {
            "message_type": "command",
            "data": {"command_type": "execute_shell"},
        }

        with patch(
            "backend.websocket.outbound_processor.server_queue_manager"
        ) as mock_qm, patch(
            "backend.websocket.outbound_processor.send_command_to_agent"
        ) as mock_send:
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.return_value = command_data
            mock_send.return_value = False  # Send fails

            await process_outbound_message(mock_message, mock_host, mock_db)

            mock_qm.mark_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_outbound_message_cannot_mark_processing(
        self, mock_db, mock_host, mock_message
    ):
        """Test handling when message cannot be marked as processing."""
        with patch(
            "backend.websocket.outbound_processor.server_queue_manager"
        ) as mock_qm:
            mock_qm.mark_processing.return_value = False

            await process_outbound_message(mock_message, mock_host, mock_db)

            mock_qm.deserialize_message_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_outbound_message_unknown_type(
        self, mock_db, mock_host, mock_message
    ):
        """Test handling unknown message type."""
        mock_message.message_type = "unknown_type"

        with patch(
            "backend.websocket.outbound_processor.server_queue_manager"
        ) as mock_qm:
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.return_value = {}

            await process_outbound_message(mock_message, mock_host, mock_db)

            # Unknown type should not call mark_sent
            mock_qm.mark_sent.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_outbound_message_exception(
        self, mock_db, mock_host, mock_message
    ):
        """Test handling exceptions during processing."""
        with patch(
            "backend.websocket.outbound_processor.server_queue_manager"
        ) as mock_qm:
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.side_effect = Exception(
                "Deserialization error"
            )

            await process_outbound_message(mock_message, mock_host, mock_db)

            mock_qm.mark_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_outbound_message_create_child_host_logging(
        self, mock_db, mock_host, mock_message
    ):
        """Test special logging for create_child_host commands."""
        command_data = {
            "message_type": "command",
            "data": {
                "command_type": "create_child_host",
                "parameters": {
                    "distribution": "ubuntu-22.04",
                    "vm_name": "test-vm",
                    "child_type": "kvm",
                    "hostname": "test-vm.example.com",
                },
            },
        }

        with patch(
            "backend.websocket.outbound_processor.server_queue_manager"
        ) as mock_qm, patch(
            "backend.websocket.outbound_processor.send_command_to_agent"
        ) as mock_send, patch(
            "backend.websocket.outbound_processor.logger"
        ) as mock_logger:
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.return_value = command_data
            mock_send.return_value = True

            await process_outbound_message(mock_message, mock_host, mock_db)

            # Should log with child host details
            assert mock_logger.info.called


class TestSendCommandToAgent:
    """Test send_command_to_agent function."""

    @pytest.fixture
    def mock_host(self):
        """Create mock host object."""
        host = Mock()
        host.id = 123  # Integer
        host.fqdn = "test-host.example.com"
        return host

    @pytest.mark.asyncio
    async def test_send_command_to_agent_success(self, mock_host):
        """Test successful command sending."""
        command_data = {
            "message_type": "command",
            "data": {"command_type": "execute_shell"},
        }

        with patch(
            "backend.websocket.connection_manager.connection_manager"
        ) as mock_cm:
            mock_cm.send_to_host = AsyncMock(return_value=True)

            result = await send_command_to_agent(
                command_data, mock_host, "queue-msg-123"
            )

            assert result is True
            mock_cm.send_to_host.assert_called_once()
            # Verify queue_message_id was added to message
            call_args = mock_cm.send_to_host.call_args[0]
            assert call_args[1]["queue_message_id"] == "queue-msg-123"

    @pytest.mark.asyncio
    async def test_send_command_to_agent_failure(self, mock_host):
        """Test command sending failure."""
        command_data = {
            "message_type": "command",
            "data": {"command_type": "execute_shell"},
        }

        with patch(
            "backend.websocket.connection_manager.connection_manager"
        ) as mock_cm:
            mock_cm.send_to_host = AsyncMock(return_value=False)

            result = await send_command_to_agent(
                command_data, mock_host, "queue-msg-123"
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_command_to_agent_exception(self, mock_host):
        """Test command sending with exception."""
        command_data = {
            "message_type": "command",
            "data": {"command_type": "execute_shell"},
        }

        with patch(
            "backend.websocket.connection_manager.connection_manager"
        ) as mock_cm:
            mock_cm.send_to_host = AsyncMock(side_effect=Exception("Connection error"))

            result = await send_command_to_agent(
                command_data, mock_host, "queue-msg-123"
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_command_preserves_data(self, mock_host):
        """Test that command data is preserved and copied."""
        original_command_data = {
            "message_type": "command",
            "message_id": "cmd-123",
            "data": {
                "command_type": "install_package",
                "parameters": {"package": "vim"},
            },
        }

        with patch(
            "backend.websocket.connection_manager.connection_manager"
        ) as mock_cm:
            mock_cm.send_to_host = AsyncMock(return_value=True)

            await send_command_to_agent(
                original_command_data, mock_host, "queue-msg-123"
            )

            # Original should not be modified
            assert "queue_message_id" not in original_command_data

            # Sent message should have queue_message_id
            call_args = mock_cm.send_to_host.call_args[0]
            sent_message = call_args[1]
            assert sent_message["queue_message_id"] == "queue-msg-123"
            assert sent_message["message_type"] == "command"
            assert sent_message["message_id"] == "cmd-123"


class TestOutboundProcessorIntegration:
    """Integration tests for outbound processor."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return Mock()

    @pytest.mark.asyncio
    async def test_full_command_flow(self, mock_db):
        """Test complete command sending flow."""
        mock_host = Mock()
        mock_host.id = 123
        mock_host.fqdn = "test-host.example.com"
        mock_host.approval_status = "approved"

        mock_message = Mock()
        mock_message.message_id = "msg-123"
        mock_message.message_type = "command"
        mock_message.host_id = 123

        command_data = {
            "message_type": "command",
            "message_id": "cmd-123",
            "data": {
                "command_type": "execute_shell",
                "parameters": {"cmd": "echo hello"},
            },
        }

        with patch(
            "backend.websocket.outbound_processor.server_queue_manager"
        ) as mock_qm, patch(
            "backend.websocket.connection_manager.connection_manager"
        ) as mock_cm:
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.return_value = command_data
            mock_cm.send_to_host = AsyncMock(return_value=True)

            await process_outbound_message(mock_message, mock_host, mock_db)

            # Verify complete flow
            mock_qm.mark_processing.assert_called_once()
            mock_qm.deserialize_message_data.assert_called_once()
            mock_cm.send_to_host.assert_called_once()
            mock_qm.mark_sent.assert_called_once()

    @pytest.mark.asyncio
    async def test_command_with_retry_on_failure(self, mock_db):
        """Test command handling when connection fails."""
        mock_host = Mock()
        mock_host.id = 123
        mock_host.fqdn = "test-host.example.com"
        mock_host.approval_status = "approved"

        mock_message = Mock()
        mock_message.message_id = "msg-123"
        mock_message.message_type = "command"
        mock_message.host_id = 123

        command_data = {
            "message_type": "command",
            "data": {"command_type": "execute_shell"},
        }

        with patch(
            "backend.websocket.outbound_processor.server_queue_manager"
        ) as mock_qm, patch(
            "backend.websocket.connection_manager.connection_manager"
        ) as mock_cm:
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.return_value = command_data
            mock_cm.send_to_host = AsyncMock(return_value=False)  # Connection fails

            await process_outbound_message(mock_message, mock_host, mock_db)

            # Should be marked as failed
            mock_qm.mark_failed.assert_called_once()
            # mark_sent should NOT be called
            mock_qm.mark_sent.assert_not_called()


class TestOutboundProcessorModuleImports:
    """Test module-level functionality and imports."""

    def test_process_outbound_message_is_async(self):
        """Test that process_outbound_message is an async function."""
        import asyncio

        assert asyncio.iscoroutinefunction(process_outbound_message)

    def test_send_command_to_agent_is_async(self):
        """Test that send_command_to_agent is an async function."""
        import asyncio

        assert asyncio.iscoroutinefunction(send_command_to_agent)

    def test_queue_status_enum(self):
        """Test QueueStatus enum is properly accessible."""
        assert hasattr(QueueStatus, "PENDING")
        assert hasattr(QueueStatus, "IN_PROGRESS")
        assert hasattr(QueueStatus, "SENT")
        assert hasattr(QueueStatus, "COMPLETED")
        assert hasattr(QueueStatus, "FAILED")
