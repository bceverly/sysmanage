"""
Tests for backend/websocket/message_processor.py module.
Tests background message processing for SysManage.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMessageProcessorInit:
    """Tests for MessageProcessor initialization."""

    def test_init_defaults(self):
        """Test initialization sets correct defaults."""
        from backend.websocket.message_processor import MessageProcessor

        processor = MessageProcessor()

        assert processor.running is False
        assert processor.process_interval == 1.0


class TestMessageProcessorStart:
    """Tests for MessageProcessor.start method."""

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """Test start returns early if already running."""
        from backend.websocket.message_processor import MessageProcessor

        processor = MessageProcessor()
        processor.running = True

        await processor.start()

        # Should return immediately without changing state
        assert processor.running is True

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self):
        """Test start sets running flag."""
        from backend.websocket.message_processor import MessageProcessor

        processor = MessageProcessor()
        processor.process_interval = 0.01  # Short interval for test

        # Run for a brief moment then stop
        async def stop_after_delay():
            await asyncio.sleep(0.05)
            processor.stop()

        with patch.object(
            processor, "_process_pending_messages", new_callable=AsyncMock
        ):
            # Start both tasks
            await asyncio.gather(processor.start(), stop_after_delay())

        assert processor.running is False  # Stopped after test

    @pytest.mark.asyncio
    async def test_start_handles_exception_in_processing(self):
        """Test start continues after processing exception."""
        from backend.websocket.message_processor import MessageProcessor

        processor = MessageProcessor()
        processor.process_interval = 0.01

        call_count = 0

        async def mock_process():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Test error")

        async def stop_after_delay():
            await asyncio.sleep(0.05)
            processor.stop()

        with patch.object(
            processor, "_process_pending_messages", side_effect=mock_process
        ):
            await asyncio.gather(processor.start(), stop_after_delay())

        # Should have called process multiple times despite first error
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_start_handles_cancelled_error(self):
        """Test start handles CancelledError gracefully."""
        from backend.websocket.message_processor import MessageProcessor

        processor = MessageProcessor()
        processor.process_interval = 1.0

        with patch.object(
            processor, "_process_pending_messages", new_callable=AsyncMock
        ):
            task = asyncio.create_task(processor.start())
            await asyncio.sleep(0.01)
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                _ = await task  # assignment placates py/ineffectual-statement

        assert processor.running is False


class TestMessageProcessorStop:
    """Tests for MessageProcessor.stop method."""

    def test_stop_sets_flag_false(self):
        """Test stop sets running flag to False."""
        from backend.websocket.message_processor import MessageProcessor

        processor = MessageProcessor()
        processor.running = True

        processor.stop()

        assert processor.running is False


class TestMessageProcessorProcessPendingMessages:
    """Tests for MessageProcessor._process_pending_messages method."""

    @patch("backend.websocket.message_processor.config")
    @patch("backend.websocket.message_processor.server_queue_manager")
    @patch("backend.websocket.message_processor.process_outbound_messages")
    @patch("backend.websocket.message_processor.process_pending_messages")
    @patch("backend.websocket.message_processor.get_db")
    @pytest.mark.asyncio
    async def test_process_pending_messages_success(
        self,
        mock_get_db,
        mock_process_inbound,
        mock_process_outbound,
        mock_queue_manager,
        mock_config,
    ):
        """Test successful message processing (collapsed mode → bootstrap DB only)."""
        from backend.websocket.message_processor import MessageProcessor

        mock_config.is_multitenancy_enabled.return_value = False
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_process_inbound.return_value = None
        mock_process_outbound.return_value = None
        mock_queue_manager.retry_unacknowledged_messages.return_value = 0

        processor = MessageProcessor()
        await processor._process_pending_messages()

        mock_process_inbound.assert_called_once_with(mock_db)
        mock_process_outbound.assert_called_once_with(mock_db)
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("backend.websocket.message_processor.config")
    @patch("backend.websocket.message_processor.server_queue_manager")
    @patch("backend.websocket.message_processor.process_outbound_messages")
    @patch("backend.websocket.message_processor.process_pending_messages")
    @patch("backend.websocket.message_processor.get_db")
    @pytest.mark.asyncio
    async def test_process_pending_messages_with_retries(
        self,
        mock_get_db,
        mock_process_inbound,
        mock_process_outbound,
        mock_queue_manager,
        mock_config,
    ):
        """Test message processing with retry scheduling."""
        from backend.websocket.message_processor import MessageProcessor

        mock_config.is_multitenancy_enabled.return_value = False
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_process_inbound.return_value = None
        mock_process_outbound.return_value = None
        mock_queue_manager.retry_unacknowledged_messages.return_value = 5

        processor = MessageProcessor()
        await processor._process_pending_messages()

        mock_queue_manager.retry_unacknowledged_messages.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("backend.websocket.message_processor.config")
    @patch("backend.websocket.message_processor.server_queue_manager")
    @patch("backend.websocket.message_processor.process_outbound_messages")
    @patch("backend.websocket.message_processor.process_pending_messages")
    @patch("backend.websocket.message_processor.get_db")
    @pytest.mark.asyncio
    async def test_process_pending_messages_rollback_on_error(
        self,
        mock_get_db,
        mock_process_inbound,
        mock_process_outbound,
        mock_queue_manager,
        mock_config,
    ):
        """A failure draining one DB is ISOLATED (logged + rolled back), NOT
        re-raised — Phase 13.1 #2 per-DB isolation so one tenant can't stall the
        others or the cycle."""
        from backend.websocket.message_processor import MessageProcessor

        mock_config.is_multitenancy_enabled.return_value = False
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_process_inbound.side_effect = Exception("Processing error")

        processor = MessageProcessor()

        # Does NOT raise — the error is contained to this DB.
        await processor._process_pending_messages()

        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("backend.websocket.message_processor.resolve_engine")
    @patch("backend.websocket.message_processor.sessionmaker")
    @patch("backend.websocket.message_processor.config")
    @patch("backend.websocket.message_processor.server_queue_manager")
    @patch("backend.websocket.message_processor.process_outbound_messages")
    @patch("backend.websocket.message_processor.process_pending_messages")
    @patch("backend.websocket.message_processor.get_db")
    @pytest.mark.asyncio
    async def test_fans_out_over_bootstrap_plus_each_tenant(
        self,
        mock_get_db,
        mock_process_inbound,
        mock_process_outbound,
        mock_queue_manager,
        mock_config,
        mock_sessionmaker,
        mock_resolve_engine,
    ):
        """Phase 13.1 #2: with MT enabled and provisioned tenants, the processors
        run once per DB — bootstrap + each tenant — each on its own session."""
        from backend.websocket.message_processor import MessageProcessor

        mock_config.is_multitenancy_enabled.return_value = True
        bootstrap_db = MagicMock(name="bootstrap")
        mock_get_db.return_value = iter([bootstrap_db])
        mock_queue_manager.retry_unacknowledged_messages.return_value = 0

        # Two provisioned tenants, each yielding a distinct session.
        tenant_a, tenant_b = MagicMock(name="tenantA"), MagicMock(name="tenantB")
        mock_resolve_engine.side_effect = [
            MagicMock(name="engA"),
            MagicMock(name="engB"),
        ]
        mock_sessionmaker.side_effect = [
            MagicMock(return_value=tenant_a),
            MagicMock(return_value=tenant_b),
        ]

        processor = MessageProcessor()
        with patch.object(
            processor, "_provisioned_tenant_ids", return_value=["t-a", "t-b"]
        ):
            await processor._process_pending_messages()

        # Processed bootstrap + both tenant DBs (3 sessions), each committed/closed.
        processed = {c.args[0] for c in mock_process_inbound.call_args_list}
        assert processed == {bootstrap_db, tenant_a, tenant_b}
        for db in (bootstrap_db, tenant_a, tenant_b):
            db.commit.assert_called_once()
            db.close.assert_called_once()


class TestGlobalInstance:
    """Tests for global message_processor instance."""

    def test_global_instance_exists(self):
        """Test that global message_processor instance exists."""
        from backend.websocket.message_processor import message_processor

        assert message_processor is not None

    def test_global_instance_type(self):
        """Test that global instance is correct type."""
        from backend.websocket.message_processor import (
            MessageProcessor,
            message_processor,
        )

        assert isinstance(message_processor, MessageProcessor)
