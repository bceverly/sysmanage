"""
Tests for backend/websocket/queue_operations.py module.
Tests core queue operations including enqueue, dequeue, and status updates.
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


class TestQueueOperationsEnqueue:
    """Tests for QueueOperations.enqueue_message method."""

    def test_enqueue_generates_message_id(self):
        """Test that message ID is generated if not provided."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueDirection

        ops = QueueOperations()
        mock_db = MagicMock()

        # First filter call returns None (no existing message)
        # Second filter call returns the verification message
        mock_verification_msg = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # No duplicate check
            mock_verification_msg,  # Verification after flush
        ]

        result = ops.enqueue_message(
            message_type="test",
            message_data={"key": "value"},
            direction=QueueDirection.OUTBOUND,
            db=mock_db,
        )

        assert result is not None
        assert len(result) == 36  # UUID length with dashes

    def test_enqueue_uses_provided_message_id(self):
        """Test that provided message ID is used."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueDirection

        ops = QueueOperations()
        mock_db = MagicMock()

        # Set up filter to return None for duplicate check, then message for verification
        mock_verification_msg = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # No duplicate message
            mock_verification_msg,  # Verification after flush
        ]

        result = ops.enqueue_message(
            message_type="test",
            message_data={"key": "value"},
            direction=QueueDirection.OUTBOUND,
            message_id="custom-id-123",
            db=mock_db,
        )

        assert result == "custom-id-123"

    def test_enqueue_validates_host_id(self):
        """Test that host ID is validated."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueDirection

        ops = QueueOperations()
        mock_db = MagicMock()
        # Host not found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError) as exc_info:
            ops.enqueue_message(
                message_type="test",
                message_data={"key": "value"},
                direction=QueueDirection.OUTBOUND,
                host_id="nonexistent-host",
                db=mock_db,
            )

        assert "not found" in str(exc_info.value)

    def test_enqueue_skips_duplicate_message_id(self):
        """Test that duplicate message IDs are skipped."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueDirection

        ops = QueueOperations()
        mock_db = MagicMock()

        existing_message = MagicMock()
        existing_message.status = "pending"

        # First filter is for host validation (return host)
        mock_host = MagicMock()
        # Second filter is for duplicate message ID check
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_host,  # Host validation passes
            existing_message,  # Duplicate message ID found
        ]

        result = ops.enqueue_message(
            message_type="test",
            message_data={"key": "value"},
            direction=QueueDirection.OUTBOUND,
            host_id="host-123",
            message_id="duplicate-id",
            db=mock_db,
        )

        assert result == "duplicate-id"
        mock_db.add.assert_not_called()

    def test_enqueue_converts_enum_to_string(self):
        """Test that enums are converted to string values."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueDirection, Priority

        ops = QueueOperations()
        mock_db = MagicMock()

        # Set up filter to return None for duplicate check, then message for verification
        mock_verification_msg = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # No duplicate message
            mock_verification_msg,  # Verification after flush
        ]

        result = ops.enqueue_message(
            message_type="test",
            message_data={"key": "value"},
            direction=QueueDirection.OUTBOUND,
            priority=Priority.HIGH,
            db=mock_db,
        )

        # Should successfully enqueue
        assert result is not None
        mock_db.add.assert_called_once()


class TestQueueOperationsDequeue:
    """Tests for QueueOperations.dequeue_messages_for_host method."""

    def test_dequeue_returns_pending_messages(self):
        """Test that pending messages are returned."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueDirection

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_message.priority = "normal"
        mock_message.created_at = datetime.now()

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_message
        ]

        result = ops.dequeue_messages_for_host(
            host_id="host-123", direction=QueueDirection.OUTBOUND, db=mock_db
        )

        assert len(result) == 1
        assert result[0] == mock_message

    def test_dequeue_respects_limit(self):
        """Test that limit is respected."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueDirection

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )

        ops.dequeue_messages_for_host(
            host_id="host-123",
            direction=QueueDirection.OUTBOUND,
            limit=5,
            db=mock_db,
        )

        # Check limit was passed
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.assert_called_with(
            5
        )

    def test_dequeue_sorts_by_priority(self):
        """Test that messages are sorted by priority."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueDirection, Priority

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_normal = MagicMock()
        mock_normal.priority = Priority.NORMAL
        mock_normal.created_at = datetime.now()

        mock_high = MagicMock()
        mock_high.priority = Priority.HIGH
        mock_high.created_at = datetime.now()

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_normal,
            mock_high,
        ]

        result = ops.dequeue_messages_for_host(
            host_id="host-123",
            direction=QueueDirection.OUTBOUND,
            priority_order=True,
            db=mock_db,
        )

        # High priority should be first
        assert result[0] == mock_high
        assert result[1] == mock_normal


class TestQueueOperationsDequeueBroadcast:
    """Tests for QueueOperations.dequeue_broadcast_messages method."""

    def test_dequeue_broadcast_returns_messages(self):
        """Test that broadcast messages are returned."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueDirection

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_message
        ]

        result = ops.dequeue_broadcast_messages(
            direction=QueueDirection.OUTBOUND, db=mock_db
        )

        assert len(result) == 1
        assert result[0] == mock_message


class TestQueueOperationsMarkProcessing:
    """Tests for QueueOperations.mark_processing method."""

    def test_mark_processing_success(self):
        """Test successfully marking message as processing."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueStatus

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_message.status = QueueStatus.PENDING
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_message
        )

        result = ops.mark_processing("msg-123", db=mock_db)

        assert result is True
        assert mock_message.status == QueueStatus.IN_PROGRESS
        assert mock_message.started_at is not None
        mock_db.flush.assert_called_once()

    def test_mark_processing_message_not_found(self):
        """Test marking nonexistent message."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()
        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        result = ops.mark_processing("nonexistent-msg", db=mock_db)

        assert result is False

    def test_mark_processing_wrong_status(self):
        """Test marking message with wrong status."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueStatus

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_message.status = QueueStatus.COMPLETED
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_message
        )

        result = ops.mark_processing("msg-123", db=mock_db)

        assert result is False

    def test_mark_processing_handles_exception(self):
        """Test exception handling in mark_processing."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()
        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.side_effect = Exception(
            "Database error"
        )

        result = ops.mark_processing("msg-123", db=mock_db)

        assert result is False


class TestQueueOperationsMarkCompleted:
    """Tests for QueueOperations.mark_completed method."""

    def test_mark_completed_success(self):
        """Test successfully marking message as completed."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueStatus

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_message
        )

        result = ops.mark_completed("msg-123", db=mock_db)

        assert result is True
        assert mock_message.status == QueueStatus.COMPLETED
        assert mock_message.completed_at is not None

    def test_mark_completed_message_not_found(self):
        """Test marking nonexistent message as completed."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()
        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        result = ops.mark_completed("nonexistent-msg", db=mock_db)

        assert result is False

    def test_mark_completed_handles_exception(self):
        """Test exception handling in mark_completed."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()
        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.side_effect = Exception(
            "Database error"
        )

        result = ops.mark_completed("msg-123", db=mock_db)

        assert result is False


class TestQueueOperationsMarkSent:
    """Tests for QueueOperations.mark_sent method."""

    def test_mark_sent_success(self):
        """Test successfully marking message as sent."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueStatus

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_message
        )

        result = ops.mark_sent("msg-123", db=mock_db)

        assert result is True
        assert mock_message.status == QueueStatus.SENT
        assert mock_message.started_at is not None

    def test_mark_sent_message_not_found(self):
        """Test marking nonexistent message as sent."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()
        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        result = ops.mark_sent("nonexistent-msg", db=mock_db)

        assert result is False

    def test_mark_sent_handles_exception(self):
        """Test exception handling in mark_sent."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()
        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.side_effect = Exception(
            "Database error"
        )

        result = ops.mark_sent("msg-123", db=mock_db)

        assert result is False


class TestQueueOperationsMarkAcknowledged:
    """Tests for QueueOperations.mark_acknowledged method."""

    def test_mark_acknowledged_success(self):
        """Test successfully marking sent message as acknowledged."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueStatus

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_message.status = QueueStatus.SENT
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_message
        )

        result = ops.mark_acknowledged("msg-123", db=mock_db)

        assert result is True
        assert mock_message.status == QueueStatus.COMPLETED
        assert mock_message.completed_at is not None

    def test_mark_acknowledged_message_not_found(self):
        """Test acknowledging nonexistent message."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()
        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        result = ops.mark_acknowledged("nonexistent-msg", db=mock_db)

        assert result is False

    def test_mark_acknowledged_wrong_status(self):
        """Test acknowledging message not in SENT status."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueStatus

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_message.status = QueueStatus.PENDING
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_message
        )

        result = ops.mark_acknowledged("msg-123", db=mock_db)

        assert result is False

    def test_mark_acknowledged_already_completed(self):
        """Test acknowledging already completed message returns True."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueStatus

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_message.status = QueueStatus.COMPLETED
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_message
        )

        result = ops.mark_acknowledged("msg-123", db=mock_db)

        assert result is True

    def test_mark_acknowledged_handles_exception(self):
        """Test exception handling in mark_acknowledged."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()
        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.side_effect = Exception(
            "Database error"
        )

        result = ops.mark_acknowledged("msg-123", db=mock_db)

        assert result is False


class TestQueueOperationsMarkFailed:
    """Tests for QueueOperations.mark_failed method."""

    def test_mark_failed_with_retry(self):
        """Test marking message as failed with retry available."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueStatus

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_message.retry_count = 0
        mock_message.max_retries = 3
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_message
        )

        result = ops.mark_failed("msg-123", error_message="Test error", db=mock_db)

        assert result is True
        assert mock_message.status == QueueStatus.PENDING
        assert mock_message.retry_count == 1
        assert mock_message.error_message == "Test error"
        assert mock_message.scheduled_at is not None

    def test_mark_failed_max_retries_reached(self):
        """Test marking message as permanently failed."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueStatus

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_message.retry_count = 2
        mock_message.max_retries = 3
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_message
        )

        result = ops.mark_failed("msg-123", error_message="Final error", db=mock_db)

        assert result is True
        assert mock_message.status == QueueStatus.FAILED
        assert mock_message.retry_count == 3

    def test_mark_failed_no_retry(self):
        """Test marking message as failed without retry."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueStatus

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_message.retry_count = 0
        mock_message.max_retries = 3
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_message
        )

        result = ops.mark_failed(
            "msg-123", error_message="No retry error", retry=False, db=mock_db
        )

        assert result is True
        assert mock_message.status == QueueStatus.FAILED

    def test_mark_failed_message_not_found(self):
        """Test marking nonexistent message as failed."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()
        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        result = ops.mark_failed("nonexistent-msg", db=mock_db)

        assert result is False

    def test_mark_failed_handles_exception(self):
        """Test exception handling in mark_failed."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()
        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.side_effect = Exception(
            "Database error"
        )

        result = ops.mark_failed("msg-123", db=mock_db)

        assert result is False


class TestQueueOperationsRetryUnacknowledged:
    """Tests for QueueOperations.retry_unacknowledged_messages method."""

    def test_retry_unacknowledged_success(self):
        """Test retrying unacknowledged messages."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueStatus

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_message.message_id = "stale-msg"
        mock_message.started_at = datetime.now() - timedelta(minutes=5)
        mock_message.message_data = json.dumps({"data": {"command_type": "test"}})
        mock_message.retry_count = 0
        mock_message.max_retries = 3
        mock_message.status = QueueStatus.SENT

        # First query for stale messages, second for mark_failed
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_message]
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_message
        )

        result = ops.retry_unacknowledged_messages(timeout_seconds=60, db=mock_db)

        assert result == 1

    def test_retry_unacknowledged_no_stale_messages(self):
        """Test when no stale messages exist."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = ops.retry_unacknowledged_messages(timeout_seconds=60, db=mock_db)

        assert result == 0

    def test_retry_unacknowledged_create_child_host(self):
        """Test retry logging for create_child_host command."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueStatus

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_message.message_id = "child-create-msg"
        mock_message.started_at = datetime.now() - timedelta(minutes=5)
        mock_message.message_data = json.dumps(
            {
                "data": {
                    "command_type": "create_child_host",
                    "parameters": {"distribution": "ubuntu"},
                }
            }
        )
        mock_message.retry_count = 0
        mock_message.max_retries = 3
        mock_message.status = QueueStatus.SENT

        mock_db.query.return_value.filter.return_value.all.return_value = [mock_message]
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_message
        )

        result = ops.retry_unacknowledged_messages(timeout_seconds=60, db=mock_db)

        assert result == 1

    def test_retry_unacknowledged_handles_exception(self):
        """Test exception handling in retry_unacknowledged_messages."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.side_effect = Exception(
            "Database error"
        )

        result = ops.retry_unacknowledged_messages(timeout_seconds=60, db=mock_db)

        assert result == 0


class TestQueueOperationsDeserialize:
    """Tests for QueueOperations.deserialize_message_data method."""

    def test_deserialize_valid_json(self):
        """Test deserializing valid JSON data."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()

        mock_message = MagicMock()
        mock_message.message_data = '{"key": "value", "number": 42}'
        mock_message.message_id = "msg-123"

        result = ops.deserialize_message_data(mock_message)

        assert result == {"key": "value", "number": 42}

    def test_deserialize_invalid_json(self):
        """Test deserializing invalid JSON data."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()

        mock_message = MagicMock()
        mock_message.message_data = "not valid json"
        mock_message.message_id = "msg-123"

        result = ops.deserialize_message_data(mock_message)

        assert result == {}

    def test_deserialize_none_data(self):
        """Test deserializing None data."""
        from backend.websocket.queue_operations import QueueOperations

        ops = QueueOperations()

        mock_message = MagicMock()
        mock_message.message_data = None
        mock_message.message_id = "msg-123"

        result = ops.deserialize_message_data(mock_message)

        assert result == {}


class TestQueueOperationsWithSelfManagedSession:
    """Tests for queue operations that manage their own database session."""

    def test_enqueue_with_self_managed_session(self):
        """Test enqueue with self-managed session."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueDirection

        ops = QueueOperations()
        mock_db = MagicMock()

        # Set up filter to return None for duplicate check, then message for verification
        mock_verification_msg = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # No duplicate message
            mock_verification_msg,  # Verification after commit
        ]

        with patch("backend.websocket.queue_operations.get_db") as mock_get_db:
            mock_get_db.return_value = iter([mock_db])

            result = ops.enqueue_message(
                message_type="test",
                message_data={"key": "value"},
                direction=QueueDirection.OUTBOUND,
            )

        assert result is not None
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    def test_mark_processing_with_self_managed_session(self):
        """Test mark_processing with self-managed session."""
        from backend.websocket.queue_operations import QueueOperations
        from backend.websocket.queue_enums import QueueStatus

        ops = QueueOperations()
        mock_db = MagicMock()

        mock_message = MagicMock()
        mock_message.status = QueueStatus.PENDING
        mock_db.query.return_value.filter_by.return_value.first.return_value = (
            mock_message
        )

        with patch("backend.websocket.queue_operations.get_db") as mock_get_db:
            mock_get_db.return_value = iter([mock_db])

            result = ops.mark_processing("msg-123")

        assert result is True
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()
