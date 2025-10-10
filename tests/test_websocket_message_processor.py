"""
Unit tests for backend.websocket.message_processor module.
Tests the MessageProcessor class and MockConnection class.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.websocket.message_processor import MessageProcessor
from backend.websocket.mock_connection import MockConnection
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

    @patch(
        "backend.websocket.message_processor.process_outbound_messages",
        new_callable=AsyncMock,
    )
    @patch(
        "backend.websocket.message_processor.process_pending_messages",
        new_callable=AsyncMock,
    )
    @patch("backend.websocket.message_processor.get_db")
    async def test_process_pending_messages_success(
        self, mock_get_db, mock_inbound, mock_outbound
    ):
        """Test successful _process_pending_messages."""
        processor = MessageProcessor()
        mock_db = Mock()
        # Ensure commit and close are callable
        mock_db.commit = Mock()
        mock_db.close = Mock()
        mock_get_db.return_value = iter([mock_db])

        # Mock inbound and outbound processors to do nothing
        mock_inbound.return_value = None
        mock_outbound.return_value = None

        await processor._process_pending_messages()

        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()
        mock_inbound.assert_called_once_with(mock_db)
        mock_outbound.assert_called_once_with(mock_db)

    @patch(
        "backend.websocket.message_processor.process_pending_messages",
        new_callable=AsyncMock,
    )
    @patch("backend.websocket.message_processor.get_db")
    async def test_process_pending_messages_exception(self, mock_get_db, mock_inbound):
        """Test _process_pending_messages with exception."""
        processor = MessageProcessor()
        mock_db = Mock()
        mock_db.rollback = Mock()
        mock_db.close = Mock()
        mock_get_db.return_value = iter([mock_db])

        # Make inbound processor raise an exception
        mock_inbound.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await processor._process_pending_messages()

        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    # Tests for methods that have been moved to other modules
    # These tests have been removed as the methods are no longer part of MessageProcessor
    # The functionality is now tested in the individual module tests


class TestMockConnection:
    """Test cases for MockConnection class."""

    def test_init(self):
        """Test MockConnection initialization."""
        conn = MockConnection(host_id=123)

        assert conn.host_id == 123
        assert conn.hostname is None
        assert conn.is_mock_connection is True

    @patch("backend.websocket.mock_connection.logger")
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

    # Integration tests have been removed as the detailed processing logic
    # has been moved to separate modules (inbound_processor, outbound_processor)
    # These modules should have their own dedicated test files
