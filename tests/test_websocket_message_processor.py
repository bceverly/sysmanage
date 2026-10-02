# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Unit tests for backend.websocket.message_processor module.
Tests the MessageProcessor class and MockConnection class.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.websocket.message_processor import MessageProcessor
from backend.websocket.mock_connection import MockConnection


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
        mock_logger.info.assert_any_call("Message processor started")

    @patch("backend.websocket.message_processor.logger")
    @patch("builtins.print")
    async def test_start_when_already_running(self, mock_print, mock_logger):
        """Test start() when processor is already running."""
        processor = MessageProcessor()
        processor.running = True

        await processor.start()

        mock_logger.info.assert_any_call("Message processor already running")

    async def test_stop(self):
        """Test stop() method."""
        processor = MessageProcessor()
        processor.running = True

        processor.stop()

        assert processor.running is False

    @patch("backend.websocket.message_processor.config")
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
        self, mock_get_db, mock_inbound, mock_outbound, mock_config
    ):
        """Test successful _process_pending_messages (collapsed → bootstrap only)."""
        mock_config.is_multitenancy_enabled.return_value = False
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
        # Inbound runs on the worker thread with its OWN session, bound to
        # the same database (Phase 22.2); outbound stays on this session.
        mock_inbound.assert_called_once()
        worker_session = mock_inbound.call_args.args[0]
        assert worker_session is not mock_db
        assert worker_session.get_bind() is mock_db.get_bind.return_value
        mock_outbound.assert_called_once_with(mock_db)

    @patch("backend.websocket.message_processor.config")
    @patch(
        "backend.websocket.message_processor.process_pending_messages",
        new_callable=AsyncMock,
    )
    @patch("backend.websocket.message_processor.get_db")
    async def test_process_pending_messages_exception(
        self, mock_get_db, mock_inbound, mock_config
    ):
        """A drain error is ISOLATED (logged + rolled back), not re-raised --
        Phase 13.1 #2 per-DB isolation."""
        mock_config.is_multitenancy_enabled.return_value = False
        processor = MessageProcessor()
        mock_db = Mock()
        mock_db.rollback = Mock()
        mock_db.close = Mock()
        mock_get_db.return_value = iter([mock_db])

        # Make inbound processor raise an exception
        mock_inbound.side_effect = Exception("Database error")

        # Does NOT raise -- contained to this DB.
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


@pytest.mark.asyncio
async def test_a_backlog_brings_the_loop_straight_back():
    """Phase 22.2: a drain that stopped on its time budget with work waiting
    is followed by the short pause, not the full interval."""
    processor = MessageProcessor()
    pauses = []
    results = iter([True, False])

    async def drain():
        try:
            return next(results)
        except StopIteration:
            processor.stop()
            return False

    async def fake_sleep(seconds):
        pauses.append(seconds)

    with patch.object(processor, "_process_pending_messages", side_effect=drain), patch(
        "backend.websocket.message_processor.asyncio.sleep", side_effect=fake_sleep
    ):
        await processor.start()
    assert pauses[:2] == [processor.busy_interval, processor.process_interval]
