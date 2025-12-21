"""
Quick additional tests for backend/websocket/queue_manager.py module.
Covers basic functionality to improve coverage.
"""

import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from backend.websocket.queue_manager import (
    Priority,
    QueueDirection,
    QueueStatus,
    ServerMessageQueueManager,
)


class MockMessageQueue:
    """Mock message queue object."""

    def __init__(self, message_id="test-123", status=QueueStatus.PENDING):
        self.message_id = message_id
        self.status = status
        self.message_data = '{"test": "data"}'
        self.host_id = 1
        self.priority = Priority.NORMAL
        self.direction = QueueDirection.OUTBOUND
        self.message_type = "command"
        self.created_at = datetime.now(timezone.utc)
        self.retry_count = 0
        self.max_retries = 3


class MockHost:
    """Mock host object."""

    def __init__(self, host_id=1):
        self.id = host_id
        self.fqdn = "test.example.com"


class TestServerMessageQueueManager:
    """Test ServerMessageQueueManager basic functionality."""

    def test_init(self):
        """Test manager initialization."""
        manager = ServerMessageQueueManager()
        assert manager is not None

    @patch("backend.websocket.queue_operations.get_db")
    def test_enqueue_message_basic(self, mock_get_db):
        """Test basic message enqueuing."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])

        # Create mock message for verification query
        mock_message = MockMessageQueue()

        # Query order:
        # 1. Host validation (MockHost)
        # 2. Duplicate message_id check (None - no duplicate)
        # 3. Verification after commit (MockMessageQueue)
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            MockHost(),
            None,
            mock_message,
        ]

        manager = ServerMessageQueueManager()

        message_id = manager.enqueue_message(
            message_type="test",
            message_data={"test": "data"},
            direction=QueueDirection.OUTBOUND,
            host_id=1,
        )

        assert isinstance(message_id, str)
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("backend.websocket.queue_operations.get_db")
    def test_enqueue_message_no_host_id(self, mock_get_db):
        """Test message enqueuing without host ID (broadcast)."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])

        # Create mock message for verification query
        mock_message = MockMessageQueue()

        # Query order (no host_id means no host validation):
        # 1. Duplicate message_id check (None - no duplicate)
        # 2. Verification after commit (MockMessageQueue)
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,
            mock_message,
        ]

        manager = ServerMessageQueueManager()

        message_id = manager.enqueue_message(
            message_type="broadcast",
            message_data={"test": "broadcast"},
            direction=QueueDirection.OUTBOUND,
        )

        assert isinstance(message_id, str)
        mock_db.add.assert_called_once()

    @patch("backend.websocket.queue_operations.get_db")
    def test_enqueue_message_invalid_host(self, mock_get_db):
        """Test message enqueuing with invalid host ID."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.first.return_value = None

        manager = ServerMessageQueueManager()

        with pytest.raises(ValueError) as exc_info:
            manager.enqueue_message(
                message_type="test",
                message_data={"test": "data"},
                direction=QueueDirection.OUTBOUND,
                host_id=999,
            )

        assert "not found" in str(exc_info.value)

    def test_mark_processing_not_found(self):
        """Test marking non-existent message as processing."""
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        manager = ServerMessageQueueManager()
        result = manager.mark_processing("nonexistent", mock_db)

        assert result is False

    def test_deserialize_message_data_success(self):
        """Test successful message data deserialization."""
        mock_message = MockMessageQueue()
        mock_message.message_data = '{"test": "value", "number": 42}'

        manager = ServerMessageQueueManager()
        result = manager.deserialize_message_data(mock_message)

        assert result == {"test": "value", "number": 42}

    def test_deserialize_message_data_invalid_json(self):
        """Test message data deserialization with invalid JSON."""
        mock_message = MockMessageQueue()
        mock_message.message_data = "invalid json{"

        manager = ServerMessageQueueManager()
        result = manager.deserialize_message_data(mock_message)

        assert result == {}

    def test_enum_classes(self):
        """Test enum class constants."""
        assert QueueStatus.PENDING == "pending"
        assert QueueStatus.IN_PROGRESS == "in_progress"
        assert QueueStatus.COMPLETED == "completed"
        assert QueueStatus.FAILED == "failed"
        assert QueueStatus.EXPIRED == "expired"

        assert QueueDirection.OUTBOUND == "outbound"
        assert QueueDirection.INBOUND == "inbound"

        assert Priority.LOW == "low"
        assert Priority.NORMAL == "normal"
        assert Priority.HIGH == "high"
        assert Priority.URGENT == "urgent"


class TestQueueManagerIntegration:
    """Integration tests for queue manager."""

    def test_enum_string_conversion(self):
        """Test that enums work with string values."""
        manager = ServerMessageQueueManager()

        # Test with enum values
        with patch("backend.websocket.queue_operations.get_db") as mock_get_db:
            mock_db = Mock()
            mock_get_db.return_value = iter([mock_db])

            # Create mock message for verification query
            mock_message = MockMessageQueue()

            # Query order:
            # 1. Host validation (MockHost)
            # 2. Duplicate message_id check (None - no duplicate)
            # 3. Verification after commit (MockMessageQueue)
            mock_db.query.return_value.filter.return_value.first.side_effect = [
                MockHost(),
                None,
                mock_message,
            ]

            message_id = manager.enqueue_message(
                message_type="test",
                message_data={"test": "data"},
                direction=QueueDirection.OUTBOUND,  # Enum value
                priority=Priority.HIGH,  # Enum value
                host_id=1,
            )

            assert isinstance(message_id, str)
