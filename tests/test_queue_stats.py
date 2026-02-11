"""
Tests for backend/websocket/queue_stats.py module.
Tests queue statistics and monitoring operations.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.websocket.queue_enums import QueueDirection, QueueStatus


class TestQueueStatsGetQueueStats:
    """Tests for QueueStats.get_queue_stats method."""

    @patch("backend.websocket.queue_stats.get_db")
    def test_get_queue_stats_empty(self, mock_get_db):
        """Test get_queue_stats with no messages."""
        from backend.websocket.queue_stats import QueueStats

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.all.return_value = []
        mock_get_db.return_value = iter([mock_db])

        stats_service = QueueStats()
        result = stats_service.get_queue_stats()

        assert result["total"] == 0
        assert result["pending"] == 0
        assert result["in_progress"] == 0
        assert result["completed"] == 0
        assert result["failed"] == 0

    @patch("backend.websocket.queue_stats.get_db")
    def test_get_queue_stats_with_messages(self, mock_get_db):
        """Test get_queue_stats with various message statuses."""
        from backend.websocket.queue_stats import QueueStats

        # Create mock messages with different statuses
        mock_pending = MagicMock()
        mock_pending.status = QueueStatus.PENDING
        mock_in_progress = MagicMock()
        mock_in_progress.status = QueueStatus.IN_PROGRESS
        mock_completed = MagicMock()
        mock_completed.status = QueueStatus.COMPLETED
        mock_failed = MagicMock()
        mock_failed.status = QueueStatus.FAILED

        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [
            mock_pending,
            mock_in_progress,
            mock_completed,
            mock_failed,
        ]
        mock_get_db.return_value = iter([mock_db])

        stats_service = QueueStats()
        result = stats_service.get_queue_stats()

        assert result["total"] == 4
        assert result["pending"] == 1
        assert result["in_progress"] == 1
        assert result["completed"] == 1
        assert result["failed"] == 1

    @patch("backend.websocket.queue_stats.get_db")
    def test_get_queue_stats_with_host_filter(self, mock_get_db):
        """Test get_queue_stats with host_id filter."""
        from backend.websocket.queue_stats import QueueStats

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_get_db.return_value = iter([mock_db])

        stats_service = QueueStats()
        result = stats_service.get_queue_stats(host_id="host-123")

        assert result["host_id"] == "host-123"
        mock_db.query.return_value.filter.assert_called()

    @patch("backend.websocket.queue_stats.get_db")
    def test_get_queue_stats_with_direction_filter(self, mock_get_db):
        """Test get_queue_stats with direction filter."""
        from backend.websocket.queue_stats import QueueStats

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_get_db.return_value = iter([mock_db])

        stats_service = QueueStats()
        result = stats_service.get_queue_stats(direction=QueueDirection.INBOUND)

        assert result["direction"] == QueueDirection.INBOUND
        mock_db.query.return_value.filter.assert_called()

    @patch("backend.websocket.queue_stats.get_db")
    def test_get_queue_stats_with_string_direction(self, mock_get_db):
        """Test get_queue_stats with string direction filter."""
        from backend.websocket.queue_stats import QueueStats

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_get_db.return_value = iter([mock_db])

        stats_service = QueueStats()
        result = stats_service.get_queue_stats(direction="inbound")

        assert result["direction"] == "inbound"

    def test_get_queue_stats_with_provided_db(self):
        """Test get_queue_stats with provided db session."""
        from backend.websocket.queue_stats import QueueStats

        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = []

        stats_service = QueueStats()
        result = stats_service.get_queue_stats(db=mock_db)

        assert result["total"] == 0
        # DB should not be closed when provided
        mock_db.close.assert_not_called()


class TestQueueStatsGetFailedMessages:
    """Tests for QueueStats.get_failed_messages method."""

    @patch("backend.websocket.queue_stats.get_db")
    def test_get_failed_messages_empty(self, mock_get_db):
        """Test get_failed_messages with no failed messages."""
        from backend.websocket.queue_stats import QueueStats

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value = mock_query
        mock_get_db.return_value = iter([mock_db])

        stats_service = QueueStats()
        result = stats_service.get_failed_messages()

        assert result == []

    @patch("backend.websocket.queue_stats.get_db")
    def test_get_failed_messages_with_messages(self, mock_get_db):
        """Test get_failed_messages returns failed/expired messages."""
        from backend.websocket.queue_stats import QueueStats

        mock_msg1 = MagicMock()
        mock_msg2 = MagicMock()

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_msg1,
            mock_msg2,
        ]
        mock_db.query.return_value = mock_query
        mock_get_db.return_value = iter([mock_db])

        stats_service = QueueStats()
        result = stats_service.get_failed_messages()

        assert len(result) == 2

    @patch("backend.websocket.queue_stats.get_db")
    def test_get_failed_messages_with_limit(self, mock_get_db):
        """Test get_failed_messages respects limit parameter."""
        from backend.websocket.queue_stats import QueueStats

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value = mock_query
        mock_get_db.return_value = iter([mock_db])

        stats_service = QueueStats()
        stats_service.get_failed_messages(limit=50)

        mock_query.filter.return_value.order_by.return_value.limit.assert_called_with(
            50
        )

    def test_get_failed_messages_with_provided_db(self):
        """Test get_failed_messages with provided db session."""
        from backend.websocket.queue_stats import QueueStats

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value = mock_query

        stats_service = QueueStats()
        result = stats_service.get_failed_messages(db=mock_db)

        assert result == []
        # DB should not be closed when provided
        mock_db.close.assert_not_called()

    @patch("backend.websocket.queue_stats.get_db")
    def test_get_failed_messages_exception_handling(self, mock_get_db):
        """Test get_failed_messages handles exceptions gracefully."""
        from backend.websocket.queue_stats import QueueStats

        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Database error")
        mock_get_db.return_value = iter([mock_db])

        stats_service = QueueStats()
        result = stats_service.get_failed_messages()

        # Should return empty list on error
        assert result == []
