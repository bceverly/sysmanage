"""
Unit tests for backend.websocket.message_processor module.
Tests the MessageProcessor class and MockConnection class.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.websocket.message_processor import MessageProcessor, MockConnection
from backend.websocket.messages import MessageType
from backend.websocket.queue_manager import QueueDirection, QueueStatus


class TestMessageProcessor:
    """Test cases for MessageProcessor class."""

    def test_init(self):
        """Test MessageProcessor initialization."""
        processor = MessageProcessor()
        assert processor.running is False
        assert processor.process_interval == 1.0

    @patch("backend.websocket.message_processor.logger")
    @patch("builtins.print")
    async def test_start_when_not_running(self, mock_print, mock_logger):
        """Test start() when processor is not running."""
        processor = MessageProcessor()

        # Mock the processing loop to stop after one iteration
        with patch.object(processor, "_process_pending_messages") as mock_process:
            # Start the processor but stop it quickly
            start_task = asyncio.create_task(processor.start())
            await asyncio.sleep(0.1)  # Let it start
            processor.stop()

            try:
                await asyncio.wait_for(start_task, timeout=2.0)
            except asyncio.TimeoutError:
                start_task.cancel()

        # Verify logger calls
        mock_logger.info.assert_any_call("DEBUG: MessageProcessor.start() called")
        mock_logger.info.assert_any_call("Message processor started")

    @patch("backend.websocket.message_processor.logger")
    @patch("builtins.print")
    async def test_start_when_already_running(self, mock_print, mock_logger):
        """Test start() when processor is already running."""
        processor = MessageProcessor()
        processor.running = True

        await processor.start()

        mock_logger.info.assert_any_call(
            "DEBUG: MessageProcessor already running, returning early"
        )

    async def test_stop(self):
        """Test stop() method."""
        processor = MessageProcessor()
        processor.running = True

        processor.stop()

        assert processor.running is False

    @patch("backend.websocket.message_processor.get_db")
    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_process_pending_messages_success(
        self, mock_queue_manager, mock_get_db
    ):
        """Test successful _process_pending_messages."""
        processor = MessageProcessor()
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])

        # Mock queue manager methods
        mock_queue_manager.expire_old_messages.return_value = 2
        mock_queue_manager.delete_messages_for_host.return_value = 1

        # Mock database queries to return empty lists
        mock_db.query.return_value.filter.return_value.all.return_value = (
            []
        )  # No stuck messages
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = (
            []
        )

        with patch.object(processor, "_process_outbound_messages") as mock_outbound:
            await processor._process_pending_messages()

        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()
        mock_outbound.assert_called_once()

    @patch("backend.websocket.message_processor.get_db")
    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_process_pending_messages_exception(
        self, mock_queue_manager, mock_get_db
    ):
        """Test _process_pending_messages with exception."""
        processor = MessageProcessor()
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])

        # Make expire_old_messages raise an exception
        mock_queue_manager.expire_old_messages.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await processor._process_pending_messages()

        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_process_message_success(self, mock_queue_manager):
        """Test successful _process_message."""
        processor = MessageProcessor()
        mock_db = Mock()

        mock_message = Mock()
        mock_message.message_id = "msg_123"
        mock_message.message_type = MessageType.OS_VERSION_UPDATE
        mock_message.host_id = 1

        mock_queue_manager.mark_processing.return_value = True
        mock_queue_manager.deserialize_message_data.return_value = {
            "hostname": "test.local"
        }

        with patch(
            "backend.websocket.message_processor.handle_os_version_update"
        ) as mock_handler:
            mock_handler.return_value = None  # Async function returns None
            await processor._process_message(mock_message, mock_db)

        mock_queue_manager.mark_processing.assert_called_once_with(
            "msg_123", db=mock_db
        )
        mock_queue_manager.mark_completed.assert_called_once_with("msg_123", db=mock_db)

    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_process_message_unknown_type(self, mock_queue_manager):
        """Test _process_message with unknown message type."""
        processor = MessageProcessor()
        mock_db = Mock()

        mock_message = Mock()
        mock_message.message_id = "msg_123"
        mock_message.message_type = "UNKNOWN_TYPE"
        mock_message.host_id = 1

        mock_queue_manager.mark_processing.return_value = True
        mock_queue_manager.deserialize_message_data.return_value = {
            "hostname": "test.local"
        }

        await processor._process_message(mock_message, mock_db)

        mock_queue_manager.mark_failed.assert_called_once_with(
            "msg_123", error_message="Unknown message type", db=mock_db
        )

    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_process_message_mark_processing_fails(self, mock_queue_manager):
        """Test _process_message when mark_processing fails."""
        processor = MessageProcessor()
        mock_db = Mock()

        mock_message = Mock()
        mock_message.message_id = "msg_123"

        mock_queue_manager.mark_processing.return_value = False

        await processor._process_message(mock_message, mock_db)

        # Should return early without processing
        mock_queue_manager.deserialize_message_data.assert_not_called()

    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_process_validated_message_success(self, mock_queue_manager):
        """Test successful _process_validated_message."""
        processor = MessageProcessor()
        mock_db = Mock()

        mock_message = Mock()
        mock_message.message_id = "msg_123"
        mock_message.message_type = MessageType.HARDWARE_UPDATE

        mock_host = Mock()
        mock_host.id = 1
        mock_host.fqdn = "test.local"

        mock_queue_manager.mark_processing.return_value = True
        mock_queue_manager.deserialize_message_data.return_value = {
            "cpu_vendor": "Intel",
            "cpu_model": "Core i7",
            "memory_total_mb": 16384,
            "storage_devices": [{"name": "sda"}],
        }

        with patch(
            "backend.websocket.message_processor.handle_hardware_update"
        ) as mock_handler:
            await processor._process_validated_message(mock_message, mock_host, mock_db)

        mock_queue_manager.mark_completed.assert_called_once_with("msg_123", db=mock_db)

    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_process_validated_message_script_execution(self, mock_queue_manager):
        """Test _process_validated_message with script execution result."""
        processor = MessageProcessor()
        mock_db = Mock()

        mock_message = Mock()
        mock_message.message_id = "msg_123"
        mock_message.message_type = MessageType.SCRIPT_EXECUTION_RESULT

        mock_host = Mock()
        mock_host.id = 1
        mock_host.fqdn = "test.local"

        mock_queue_manager.mark_processing.return_value = True
        mock_queue_manager.deserialize_message_data.return_value = {
            "execution_id": "exec_123",
            "exit_code": 0,
            "stdout": "Success",
        }

        with patch(
            "backend.websocket.message_processor.handle_script_execution_result"
        ) as mock_handler:
            await processor._process_validated_message(mock_message, mock_host, mock_db)

        mock_queue_manager.mark_completed.assert_called_once_with("msg_123", db=mock_db)

    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_process_validated_message_exception(self, mock_queue_manager):
        """Test _process_validated_message with exception."""
        processor = MessageProcessor()
        mock_db = Mock()

        mock_message = Mock()
        mock_message.message_id = "msg_123"
        mock_message.message_type = MessageType.OS_VERSION_UPDATE

        mock_host = Mock()
        mock_host.id = 1
        mock_host.fqdn = "test.local"

        mock_queue_manager.mark_processing.return_value = True
        mock_queue_manager.deserialize_message_data.side_effect = Exception(
            "Deserialization error"
        )

        await processor._process_validated_message(mock_message, mock_host, mock_db)

        mock_queue_manager.mark_failed.assert_called_once_with(
            "msg_123", error_message="Deserialization error", db=mock_db
        )

    async def test_process_outbound_messages_success(self):
        """Test successful _process_outbound_messages."""
        processor = MessageProcessor()
        mock_db = Mock()

        # Mock outbound messages query
        mock_message = Mock()
        mock_message.host_id = 1
        mock_message.message_id = "msg_123"

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_message
        ]

        # Mock host query
        mock_host = Mock()
        mock_host.id = 1
        mock_host.approval_status = "approved"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        with patch.object(processor, "_process_outbound_message") as mock_process:
            await processor._process_outbound_messages(mock_db)

        mock_process.assert_called_once_with(mock_message, mock_host, mock_db)

    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_process_outbound_messages_host_not_found(self, mock_queue_manager):
        """Test _process_outbound_messages when host not found."""
        processor = MessageProcessor()
        mock_db = Mock()

        mock_message = Mock()
        mock_message.host_id = 1
        mock_message.message_id = "msg_123"

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_message
        ]
        mock_db.query.return_value.filter.return_value.first.return_value = (
            None  # Host not found
        )

        await processor._process_outbound_messages(mock_db)

        mock_queue_manager.mark_failed.assert_called_once_with(
            "msg_123", "Host not found", db=mock_db
        )

    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_process_outbound_message_command_success(self, mock_queue_manager):
        """Test successful _process_outbound_message with command type."""
        processor = MessageProcessor()
        mock_db = Mock()

        mock_message = Mock()
        mock_message.message_id = "msg_123"
        mock_message.message_type = "command"

        mock_host = Mock()
        mock_host.fqdn = "test.local"

        mock_queue_manager.mark_processing.return_value = True
        mock_queue_manager.deserialize_message_data.return_value = {"command": "ls -la"}

        with patch.object(
            processor, "_send_command_to_agent", return_value=True
        ) as mock_send:
            await processor._process_outbound_message(mock_message, mock_host, mock_db)

        mock_queue_manager.mark_completed.assert_called_once_with("msg_123", db=mock_db)

    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_process_outbound_message_unknown_type(self, mock_queue_manager):
        """Test _process_outbound_message with unknown message type."""
        processor = MessageProcessor()
        mock_db = Mock()

        mock_message = Mock()
        mock_message.message_id = "msg_123"
        mock_message.message_type = "unknown_type"

        mock_host = Mock()
        mock_host.fqdn = "test.local"

        mock_queue_manager.mark_processing.return_value = True
        mock_queue_manager.deserialize_message_data.return_value = {}

        await processor._process_outbound_message(mock_message, mock_host, mock_db)

        mock_queue_manager.mark_failed.assert_called_once_with(
            "msg_123", "Failed to send message to agent", db=mock_db
        )

    @patch("backend.websocket.connection_manager.connection_manager")
    @patch("backend.websocket.messages.create_command_message")
    async def test_send_command_to_agent_script_execution(
        self, mock_create_message, mock_connection_manager
    ):
        """Test _send_command_to_agent with script execution command."""
        processor = MessageProcessor()

        command_data = {"execution_id": "exec_123", "script": "echo hello"}
        mock_host = Mock()
        mock_host.id = 1
        mock_host.fqdn = "test.local"
        message_id = "msg_123"

        mock_create_message.return_value = {"type": "execute_script"}
        mock_connection_manager.send_to_host = AsyncMock(return_value=True)

        result = await processor._send_command_to_agent(
            command_data, mock_host, message_id
        )

        assert result is True
        mock_create_message.assert_called_once_with("execute_script", command_data)
        mock_connection_manager.send_to_host.assert_called_once()

    @patch("backend.websocket.connection_manager.connection_manager")
    @patch("backend.websocket.messages.create_command_message")
    async def test_send_command_to_agent_generic_command(
        self, mock_create_message, mock_connection_manager
    ):
        """Test _send_command_to_agent with generic command."""
        processor = MessageProcessor()

        command_data = {"command": "ls -la"}
        mock_host = Mock()
        mock_host.id = 1
        mock_host.fqdn = "test.local"
        message_id = "msg_123"

        mock_create_message.return_value = {"type": "generic_command"}
        mock_connection_manager.send_to_host = AsyncMock(return_value=True)

        result = await processor._send_command_to_agent(
            command_data, mock_host, message_id
        )

        assert result is True
        mock_create_message.assert_called_once_with("generic_command", command_data)

    @patch("backend.websocket.connection_manager.connection_manager")
    @patch("backend.websocket.messages.create_command_message")
    async def test_send_command_to_agent_connection_failure(
        self, mock_create_message, mock_connection_manager
    ):
        """Test _send_command_to_agent when connection fails."""
        processor = MessageProcessor()

        command_data = {"command": "ls -la"}
        mock_host = Mock()
        mock_host.id = 1
        mock_host.fqdn = "test.local"
        message_id = "msg_123"

        mock_create_message.return_value = {"type": "generic_command"}
        mock_connection_manager.send_to_host = AsyncMock(return_value=False)

        result = await processor._send_command_to_agent(
            command_data, mock_host, message_id
        )

        assert result is False

    @patch("backend.websocket.connection_manager.connection_manager")
    @patch("backend.websocket.messages.create_command_message")
    async def test_send_command_to_agent_exception(
        self, mock_create_message, mock_connection_manager
    ):
        """Test _send_command_to_agent with exception."""
        processor = MessageProcessor()

        command_data = {"command": "ls -la"}
        mock_host = Mock()
        mock_host.id = 1
        mock_host.fqdn = "test.local"
        message_id = "msg_123"

        mock_create_message.side_effect = Exception("Network error")

        result = await processor._send_command_to_agent(
            command_data, mock_host, message_id
        )

        assert result is False


class TestMockConnection:
    """Test cases for MockConnection class."""

    def test_init(self):
        """Test MockConnection initialization."""
        conn = MockConnection(host_id=123)

        assert conn.host_id == 123
        assert conn.hostname is None
        assert conn.is_mock_connection is True

    @patch("backend.websocket.message_processor.logger")
    async def test_send_message(self, mock_logger):
        """Test send_message method."""
        conn = MockConnection(host_id=123)

        message = {"message_type": "test_message", "data": "test"}
        await conn.send_message(message)

        mock_logger.debug.assert_called_once()


class TestGlobalMessageProcessor:
    """Test cases for global message processor instance."""

    def test_global_instance_exists(self):
        """Test that global message processor instance exists."""
        from backend.websocket.message_processor import message_processor

        assert message_processor is not None
        assert isinstance(message_processor, MessageProcessor)


class TestMessageProcessorIntegration:
    """Integration test cases for MessageProcessor with mocked dependencies."""

    @patch("backend.websocket.message_processor.get_db")
    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_pending_messages_with_stuck_messages(
        self, mock_queue_manager, mock_get_db
    ):
        """Test processing with stuck IN_PROGRESS messages."""
        processor = MessageProcessor()
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])

        # Mock stuck messages - message started 35 seconds ago (stuck threshold is 30 seconds)
        old_time = datetime(2023, 1, 1, 11, 59, 25, tzinfo=timezone.utc)
        mock_stuck_msg = Mock()
        mock_stuck_msg.message_id = "stuck_123"
        mock_stuck_msg.status = QueueStatus.IN_PROGRESS
        mock_stuck_msg.started_at = old_time

        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_stuck_msg
        ]
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = (
            []
        )

        mock_queue_manager.expire_old_messages.return_value = 0

        with patch.object(processor, "_process_outbound_messages"):
            await processor._process_pending_messages()

        # Verify stuck message was reset
        assert mock_stuck_msg.status == QueueStatus.PENDING
        assert mock_stuck_msg.started_at is None
        mock_db.commit.assert_called()

    @patch("backend.websocket.message_processor.get_db")
    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_pending_messages_with_unapproved_host(
        self, mock_queue_manager, mock_get_db
    ):
        """Test processing messages for unapproved host."""
        processor = MessageProcessor()
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])

        # Mock host with unapproved status
        mock_host = Mock()
        mock_host.id = 1
        mock_host.fqdn = "test.local"
        mock_host.approval_status = "pending"

        # Mock queries
        mock_db.query.return_value.filter.return_value.all.return_value = (
            []
        )  # No stuck messages
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = [
            (1,)
        ]
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = (
            []
        )  # No null host messages
        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        mock_queue_manager.expire_old_messages.return_value = 0
        mock_queue_manager.delete_messages_for_host.return_value = 5

        with patch.object(processor, "_process_outbound_messages"):
            await processor._process_pending_messages()

        mock_queue_manager.delete_messages_for_host.assert_called_once_with(
            1, db=mock_db
        )

    @patch("backend.websocket.message_processor.get_db")
    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_pending_messages_with_null_host_id(
        self, mock_queue_manager, mock_get_db
    ):
        """Test processing messages with NULL host_id."""
        processor = MessageProcessor()
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])

        # Mock message with NULL host_id
        mock_message = Mock()
        mock_message.message_id = "null_host_123"
        mock_message.host_id = None

        # Mock approved host
        mock_host = Mock()
        mock_host.id = 1
        mock_host.fqdn = "test.local"
        mock_host.approval_status = "approved"

        # Mock queries
        mock_db.query.return_value.filter.return_value.all.return_value = (
            []
        )  # No stuck messages
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = (
            []
        )  # No host messages
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            mock_message
        ]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        mock_queue_manager.expire_old_messages.return_value = 0
        mock_queue_manager.deserialize_message_data.return_value = {
            "hostname": "test.local"
        }

        with patch.object(processor, "_process_outbound_messages"):
            with patch.object(
                processor, "_process_validated_message"
            ) as mock_process_validated:
                await processor._process_pending_messages()

        mock_process_validated.assert_called_once_with(mock_message, mock_host, mock_db)

    @patch("backend.websocket.message_processor.get_db")
    @patch("backend.websocket.message_processor.server_queue_manager")
    async def test_pending_messages_null_host_missing_hostname(
        self, mock_queue_manager, mock_get_db
    ):
        """Test processing NULL host_id messages without hostname."""
        processor = MessageProcessor()
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])

        # Mock message with NULL host_id
        mock_message = Mock()
        mock_message.message_id = "null_host_123"
        mock_message.host_id = None

        # Mock queries
        mock_db.query.return_value.filter.return_value.all.return_value = (
            []
        )  # No stuck messages
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = (
            []
        )  # No host messages
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            mock_message
        ]

        mock_queue_manager.expire_old_messages.return_value = 0
        mock_queue_manager.deserialize_message_data.return_value = {}  # No hostname

        with patch.object(processor, "_process_outbound_messages"):
            await processor._process_pending_messages()

        mock_queue_manager.mark_failed.assert_called_once_with(
            "null_host_123", "Missing hostname in message data", db=mock_db
        )
