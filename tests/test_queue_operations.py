"""
Tests for backend/websocket/queue_operations.py module.
Tests core queue operations for message management.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.websocket.queue_enums import Priority, QueueDirection, QueueStatus


class TestQueueOperationsEnqueue:
    """Tests for QueueOperations.enqueue_message method."""

    @patch("backend.websocket.queue_operations.get_db")
    def test_enqueue_message_basic(self, mock_get_db):
        """Test basic message enqueue."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Mock host exists check
        mock_host = MagicMock()
        mock_created_msg = MagicMock()
        mock_created_msg.message_id = "generated-msg-id"
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_host,  # host check
            None,  # duplicate message check
            mock_created_msg,  # verification after commit
        ]

        ops = QueueOperations()
        result = ops.enqueue_message(
            message_type="command",
            message_data={"action": "test"},
            direction=QueueDirection.OUTBOUND,
            host_id="host-123",
        )

        assert result is not None
        mock_db.add.assert_called_once()

    @patch("backend.websocket.queue_operations.get_db")
    def test_enqueue_message_with_custom_id(self, mock_get_db):
        """Test enqueue with custom message ID."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_host = MagicMock()
        mock_created_msg = MagicMock()
        mock_created_msg.message_id = "custom-msg-id"
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_host,  # host check
            None,  # duplicate check
            mock_created_msg,  # verification after commit
        ]
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.enqueue_message(
            message_type="command",
            message_data={},
            direction=QueueDirection.OUTBOUND,
            host_id="host-123",
            message_id="custom-msg-id",
        )

        assert result == "custom-msg-id"

    @patch("backend.websocket.queue_operations.get_db")
    def test_enqueue_message_host_not_found(self, mock_get_db):
        """Test enqueue fails when host not found."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        with pytest.raises(ValueError) as exc_info:
            ops.enqueue_message(
                message_type="command",
                message_data={},
                direction=QueueDirection.OUTBOUND,
                host_id="nonexistent-host",
            )

        assert "not found" in str(exc_info.value)

    @patch("backend.websocket.queue_operations.get_db")
    def test_enqueue_message_duplicate_skipped(self, mock_get_db):
        """Test duplicate message ID is skipped."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_existing = MagicMock()
        mock_existing.status = QueueStatus.PENDING
        # First call for host check, second for duplicate check returns existing
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            MagicMock(),  # host exists
            mock_existing,  # duplicate message exists
        ]
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.enqueue_message(
            message_type="command",
            message_data={},
            direction=QueueDirection.OUTBOUND,
            host_id="host-123",
            message_id="existing-msg-id",
        )

        assert result == "existing-msg-id"
        mock_db.add.assert_not_called()

    def test_enqueue_message_with_provided_db(self):
        """Test enqueue with provided db session."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_host = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_host,  # host check
            None,  # duplicate check
            MagicMock(),  # verification after flush
        ]

        ops = QueueOperations()
        result = ops.enqueue_message(
            message_type="command",
            message_data={},
            direction=QueueDirection.OUTBOUND,
            host_id="host-123",
            db=mock_db,
        )

        assert result is not None
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()  # Caller manages commit


class TestQueueOperationsDequeue:
    """Tests for QueueOperations dequeue methods."""

    @patch("backend.websocket.queue_operations.get_db")
    def test_dequeue_messages_for_host_empty(self, mock_get_db):
        """Test dequeue when no messages available."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.dequeue_messages_for_host(host_id="host-123")

        assert result == []

    @patch("backend.websocket.queue_operations.get_db")
    def test_dequeue_messages_for_host_with_messages(self, mock_get_db):
        """Test dequeue returns pending messages."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg1 = MagicMock()
        mock_msg1.priority = Priority.NORMAL
        mock_msg1.created_at = datetime.now(timezone.utc)
        mock_msg2 = MagicMock()
        mock_msg2.priority = Priority.HIGH
        mock_msg2.created_at = datetime.now(timezone.utc)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_msg1,
            mock_msg2,
        ]
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.dequeue_messages_for_host(host_id="host-123")

        assert len(result) == 2

    @patch("backend.websocket.queue_operations.get_db")
    def test_dequeue_broadcast_messages_empty(self, mock_get_db):
        """Test dequeue broadcast when no messages."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.dequeue_broadcast_messages()

        assert result == []

    def test_dequeue_messages_with_provided_db(self):
        """Test dequeue with provided db session."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )

        ops = QueueOperations()
        result = ops.dequeue_messages_for_host(host_id="host-123", db=mock_db)

        assert result == []
        mock_db.close.assert_not_called()


class TestQueueOperationsMarkProcessing:
    """Tests for QueueOperations.mark_processing method."""

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_processing_success(self, mock_get_db):
        """Test mark_processing succeeds for pending message."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()
        mock_msg.status = QueueStatus.PENDING

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_msg
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_processing("msg-123")

        assert result is True
        assert mock_msg.status == QueueStatus.IN_PROGRESS

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_processing_not_found(self, mock_get_db):
        """Test mark_processing fails when message not found."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_processing("nonexistent-msg")

        assert result is False

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_processing_wrong_status(self, mock_get_db):
        """Test mark_processing fails for non-pending message."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()
        mock_msg.status = QueueStatus.COMPLETED

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_msg
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_processing("msg-123")

        assert result is False


class TestQueueOperationsMarkCompleted:
    """Tests for QueueOperations.mark_completed method."""

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_completed_success(self, mock_get_db):
        """Test mark_completed succeeds."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()
        mock_msg.status = QueueStatus.IN_PROGRESS

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_msg
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_completed("msg-123")

        assert result is True
        assert mock_msg.status == QueueStatus.COMPLETED

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_completed_not_found(self, mock_get_db):
        """Test mark_completed fails when message not found."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_completed("nonexistent-msg")

        assert result is False


class TestQueueOperationsMarkSent:
    """Tests for QueueOperations.mark_sent method."""

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_sent_success(self, mock_get_db):
        """Test mark_sent succeeds."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_msg
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_sent("msg-123")

        assert result is True
        assert mock_msg.status == QueueStatus.SENT

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_sent_not_found(self, mock_get_db):
        """Test mark_sent fails when message not found."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_sent("nonexistent-msg")

        assert result is False


class TestQueueOperationsMarkAcknowledged:
    """Tests for QueueOperations.mark_acknowledged method."""

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_acknowledged_success(self, mock_get_db):
        """Test mark_acknowledged succeeds for sent message."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()
        mock_msg.status = QueueStatus.SENT

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_msg
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_acknowledged("msg-123")

        assert result is True
        assert mock_msg.status == QueueStatus.COMPLETED

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_acknowledged_not_found(self, mock_get_db):
        """Test mark_acknowledged fails when message not found."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_acknowledged("nonexistent-msg")

        assert result is False

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_acknowledged_wrong_status(self, mock_get_db):
        """Test mark_acknowledged for non-sent message."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()
        mock_msg.status = QueueStatus.PENDING

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_msg
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_acknowledged("msg-123")

        assert result is False

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_acknowledged_already_completed(self, mock_get_db):
        """Test mark_acknowledged returns True for already completed."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()
        mock_msg.status = QueueStatus.COMPLETED

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_msg
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_acknowledged("msg-123")

        assert result is True


class TestQueueOperationsMarkFailed:
    """Tests for QueueOperations.mark_failed method."""

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_failed_with_retry(self, mock_get_db):
        """Test mark_failed with retry available."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()
        mock_msg.retry_count = 0
        mock_msg.max_retries = 3

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_msg
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_failed("msg-123", error_message="Test error", retry=True)

        assert result is True
        assert mock_msg.status == QueueStatus.PENDING
        assert mock_msg.retry_count == 1

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_failed_max_retries_reached(self, mock_get_db):
        """Test mark_failed when max retries reached."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()
        mock_msg.retry_count = 2
        mock_msg.max_retries = 3

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_msg
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_failed("msg-123", retry=True)

        assert result is True
        assert mock_msg.status == QueueStatus.FAILED

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_failed_no_retry(self, mock_get_db):
        """Test mark_failed with retry disabled."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()
        mock_msg.retry_count = 0
        mock_msg.max_retries = 3

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_msg
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_failed("msg-123", retry=False)

        assert result is True
        assert mock_msg.status == QueueStatus.FAILED

    @patch("backend.websocket.queue_operations.get_db")
    def test_mark_failed_not_found(self, mock_get_db):
        """Test mark_failed when message not found."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.mark_failed("nonexistent-msg")

        assert result is False


class TestQueueOperationsDeserialize:
    """Tests for QueueOperations.deserialize_message_data method."""

    def test_deserialize_valid_json(self):
        """Test deserialize with valid JSON."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()
        mock_msg.message_data = '{"key": "value"}'
        mock_msg.message_id = "msg-123"

        ops = QueueOperations()
        result = ops.deserialize_message_data(mock_msg)

        assert result == {"key": "value"}

    def test_deserialize_invalid_json(self):
        """Test deserialize with invalid JSON returns empty dict."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()
        mock_msg.message_data = "not valid json"
        mock_msg.message_id = "msg-123"

        ops = QueueOperations()
        result = ops.deserialize_message_data(mock_msg)

        assert result == {}

    def test_deserialize_none_data(self):
        """Test deserialize with None data returns empty dict."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()
        mock_msg.message_data = None
        mock_msg.message_id = "msg-123"

        ops = QueueOperations()
        result = ops.deserialize_message_data(mock_msg)

        assert result == {}


class TestQueueOperationsRetryUnacknowledged:
    """Tests for QueueOperations.retry_unacknowledged_messages method."""

    @patch("backend.websocket.queue_operations.get_db")
    def test_retry_unacknowledged_no_messages(self, mock_get_db):
        """Test retry when no unacknowledged messages."""
        from backend.websocket.queue_operations import QueueOperations

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.retry_unacknowledged_messages(timeout_seconds=60)

        assert result == 0

    @patch("backend.websocket.queue_operations.get_db")
    def test_retry_unacknowledged_with_messages(self, mock_get_db):
        """Test retry with unacknowledged messages."""
        from backend.websocket.queue_operations import QueueOperations

        mock_msg = MagicMock()
        mock_msg.message_id = "msg-123"
        mock_msg.message_data = '{"data": {"command_type": "test"}}'
        mock_msg.started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        mock_msg.status = QueueStatus.SENT
        mock_msg.retry_count = 0
        mock_msg.max_retries = 3

        mock_db = MagicMock()
        # First call for stale messages query
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_msg]
        # Second call for mark_failed lookup
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_msg
        mock_get_db.return_value = iter([mock_db])

        ops = QueueOperations()
        result = ops.retry_unacknowledged_messages(timeout_seconds=60)

        assert result == 1
