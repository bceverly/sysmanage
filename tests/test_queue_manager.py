"""
Tests for backend/websocket/queue_manager.py module.
Tests server-side message queue manager.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.websocket.queue_enums import Priority, QueueDirection, QueueStatus


class TestServerMessageQueueManagerInit:
    """Tests for ServerMessageQueueManager initialization."""

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_init_creates_components(self, mock_ops, mock_maintenance, mock_stats):
        """Test that initialization creates all components."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        manager = ServerMessageQueueManager()

        mock_ops.assert_called_once()
        mock_maintenance.assert_called_once()
        mock_stats.assert_called_once()


class TestServerMessageQueueManagerEnqueue:
    """Tests for ServerMessageQueueManager enqueue operations."""

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_enqueue_message_delegates(self, mock_ops, mock_maint, mock_stats):
        """Test enqueue_message delegates to operations component."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_ops_instance = MagicMock()
        mock_ops_instance.enqueue_message.return_value = "msg-123"
        mock_ops.return_value = mock_ops_instance

        manager = ServerMessageQueueManager()
        result = manager.enqueue_message(
            message_type="command",
            message_data={"action": "test"},
            direction=QueueDirection.OUTBOUND,
            host_id="host-123",
        )

        assert result == "msg-123"
        mock_ops_instance.enqueue_message.assert_called_once()


class TestServerMessageQueueManagerDequeue:
    """Tests for ServerMessageQueueManager dequeue operations."""

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_dequeue_messages_for_host_delegates(
        self, mock_ops, mock_maint, mock_stats
    ):
        """Test dequeue_messages_for_host delegates to operations."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_ops_instance = MagicMock()
        mock_ops_instance.dequeue_messages_for_host.return_value = []
        mock_ops.return_value = mock_ops_instance

        manager = ServerMessageQueueManager()
        result = manager.dequeue_messages_for_host(host_id="host-123")

        assert result == []
        mock_ops_instance.dequeue_messages_for_host.assert_called_once()

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_dequeue_broadcast_messages_delegates(
        self, mock_ops, mock_maint, mock_stats
    ):
        """Test dequeue_broadcast_messages delegates to operations."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_ops_instance = MagicMock()
        mock_ops_instance.dequeue_broadcast_messages.return_value = []
        mock_ops.return_value = mock_ops_instance

        manager = ServerMessageQueueManager()
        result = manager.dequeue_broadcast_messages()

        assert result == []
        mock_ops_instance.dequeue_broadcast_messages.assert_called_once()


class TestServerMessageQueueManagerStatus:
    """Tests for ServerMessageQueueManager status operations."""

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_mark_processing_delegates(self, mock_ops, mock_maint, mock_stats):
        """Test mark_processing delegates to operations."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_ops_instance = MagicMock()
        mock_ops_instance.mark_processing.return_value = True
        mock_ops.return_value = mock_ops_instance

        manager = ServerMessageQueueManager()
        result = manager.mark_processing("msg-123")

        assert result is True
        mock_ops_instance.mark_processing.assert_called_once_with(
            message_id="msg-123", db=None
        )

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_mark_completed_delegates(self, mock_ops, mock_maint, mock_stats):
        """Test mark_completed delegates to operations."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_ops_instance = MagicMock()
        mock_ops_instance.mark_completed.return_value = True
        mock_ops.return_value = mock_ops_instance

        manager = ServerMessageQueueManager()
        result = manager.mark_completed("msg-123")

        assert result is True

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_mark_failed_delegates(self, mock_ops, mock_maint, mock_stats):
        """Test mark_failed delegates to operations."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_ops_instance = MagicMock()
        mock_ops_instance.mark_failed.return_value = True
        mock_ops.return_value = mock_ops_instance

        manager = ServerMessageQueueManager()
        result = manager.mark_failed("msg-123", error_message="Test error")

        assert result is True

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_mark_sent_delegates(self, mock_ops, mock_maint, mock_stats):
        """Test mark_sent delegates to operations."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_ops_instance = MagicMock()
        mock_ops_instance.mark_sent.return_value = True
        mock_ops.return_value = mock_ops_instance

        manager = ServerMessageQueueManager()
        result = manager.mark_sent("msg-123")

        assert result is True

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_mark_acknowledged_delegates(self, mock_ops, mock_maint, mock_stats):
        """Test mark_acknowledged delegates to operations."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_ops_instance = MagicMock()
        mock_ops_instance.mark_acknowledged.return_value = True
        mock_ops.return_value = mock_ops_instance

        manager = ServerMessageQueueManager()
        result = manager.mark_acknowledged("msg-123")

        assert result is True


class TestServerMessageQueueManagerMaintenance:
    """Tests for ServerMessageQueueManager maintenance operations."""

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_cleanup_old_messages_delegates(self, mock_ops, mock_maint, mock_stats):
        """Test cleanup_old_messages delegates to maintenance."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_maint_instance = MagicMock()
        mock_maint_instance.cleanup_old_messages.return_value = 5
        mock_maint.return_value = mock_maint_instance

        manager = ServerMessageQueueManager()
        result = manager.cleanup_old_messages(older_than_days=7)

        assert result == 5
        mock_maint_instance.cleanup_old_messages.assert_called_once()

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_delete_messages_for_host_delegates(self, mock_ops, mock_maint, mock_stats):
        """Test delete_messages_for_host delegates to maintenance."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_maint_instance = MagicMock()
        mock_maint_instance.delete_messages_for_host.return_value = 3
        mock_maint.return_value = mock_maint_instance

        manager = ServerMessageQueueManager()
        result = manager.delete_messages_for_host("host-123")

        assert result == 3

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_expire_old_messages_delegates(self, mock_ops, mock_maint, mock_stats):
        """Test expire_old_messages delegates to maintenance."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_maint_instance = MagicMock()
        mock_maint_instance.expire_old_messages.return_value = 2
        mock_maint.return_value = mock_maint_instance

        manager = ServerMessageQueueManager()
        result = manager.expire_old_messages()

        assert result == 2

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_delete_failed_messages_delegates(self, mock_ops, mock_maint, mock_stats):
        """Test delete_failed_messages delegates to maintenance."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_maint_instance = MagicMock()
        mock_maint_instance.delete_failed_messages.return_value = 2
        mock_maint.return_value = mock_maint_instance

        manager = ServerMessageQueueManager()
        result = manager.delete_failed_messages(["msg-1", "msg-2"])

        assert result == 2


class TestServerMessageQueueManagerStats:
    """Tests for ServerMessageQueueManager statistics operations."""

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_get_queue_stats_delegates(self, mock_ops, mock_maint, mock_stats):
        """Test get_queue_stats delegates to stats component."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_stats_instance = MagicMock()
        mock_stats_instance.get_queue_stats.return_value = {"total": 10}
        mock_stats.return_value = mock_stats_instance

        manager = ServerMessageQueueManager()
        result = manager.get_queue_stats()

        assert result == {"total": 10}
        mock_stats_instance.get_queue_stats.assert_called_once()

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_get_failed_messages_delegates(self, mock_ops, mock_maint, mock_stats):
        """Test get_failed_messages delegates to stats component."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_stats_instance = MagicMock()
        mock_stats_instance.get_failed_messages.return_value = []
        mock_stats.return_value = mock_stats_instance

        manager = ServerMessageQueueManager()
        result = manager.get_failed_messages(limit=50)

        assert result == []


class TestServerMessageQueueManagerOther:
    """Tests for other ServerMessageQueueManager methods."""

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_deserialize_message_data_delegates(self, mock_ops, mock_maint, mock_stats):
        """Test deserialize_message_data delegates to operations."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_ops_instance = MagicMock()
        mock_ops_instance.deserialize_message_data.return_value = {"data": "value"}
        mock_ops.return_value = mock_ops_instance

        manager = ServerMessageQueueManager()
        mock_message = MagicMock()
        result = manager.deserialize_message_data(mock_message)

        assert result == {"data": "value"}

    @patch("backend.websocket.queue_manager.QueueStats")
    @patch("backend.websocket.queue_manager.QueueMaintenance")
    @patch("backend.websocket.queue_manager.QueueOperations")
    def test_retry_unacknowledged_messages_delegates(
        self, mock_ops, mock_maint, mock_stats
    ):
        """Test retry_unacknowledged_messages delegates to operations."""
        from backend.websocket.queue_manager import ServerMessageQueueManager

        mock_ops_instance = MagicMock()
        mock_ops_instance.retry_unacknowledged_messages.return_value = 3
        mock_ops.return_value = mock_ops_instance

        manager = ServerMessageQueueManager()
        result = manager.retry_unacknowledged_messages(timeout_seconds=60)

        assert result == 3


class TestGlobalInstance:
    """Tests for global server_queue_manager instance."""

    def test_global_instance_exists(self):
        """Test that global server_queue_manager instance exists."""
        from backend.websocket.queue_manager import server_queue_manager

        assert server_queue_manager is not None

    def test_global_instance_type(self):
        """Test that global instance is correct type."""
        from backend.websocket.queue_manager import (
            ServerMessageQueueManager,
            server_queue_manager,
        )

        assert isinstance(server_queue_manager, ServerMessageQueueManager)
