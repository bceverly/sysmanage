"""
Tests for backend/websocket/queue_maintenance.py module.
Tests queue maintenance operations for cleanup, expiration, and deletion.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.websocket.queue_enums import QueueStatus


class TestQueueMaintenanceCleanupOldMessages:
    """Tests for QueueMaintenance.cleanup_old_messages method."""

    def test_cleanup_old_messages_with_provided_db(self):
        """Test cleanup with provided db session."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_db = MagicMock()
        mock_messages = [MagicMock(), MagicMock()]
        mock_db.query.return_value.filter.return_value.all.return_value = mock_messages

        maintenance = QueueMaintenance()
        result = maintenance.cleanup_old_messages(older_than_days=7, db=mock_db)

        assert result == 2
        mock_db.commit.assert_not_called()  # Caller manages commit
        assert mock_db.delete.call_count == 2

    def test_cleanup_old_messages_with_keep_failed_false(self):
        """Test cleanup including failed messages."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_db = MagicMock()
        mock_messages = [MagicMock()]
        mock_db.query.return_value.filter.return_value.union.return_value.all.return_value = (
            mock_messages
        )

        maintenance = QueueMaintenance()
        result = maintenance.cleanup_old_messages(
            older_than_days=7, keep_failed=False, db=mock_db
        )

        assert result == 1

    @patch("backend.websocket.queue_maintenance.get_db")
    def test_cleanup_old_messages_without_db(self, mock_get_db):
        """Test cleanup creates and commits its own db session."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.all.return_value = []

        maintenance = QueueMaintenance()
        result = maintenance.cleanup_old_messages(older_than_days=7)

        assert result == 0
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("backend.websocket.queue_maintenance.get_db")
    def test_cleanup_old_messages_error_handling(self, mock_get_db):
        """Test cleanup handles errors gracefully."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.side_effect = Exception("Database error")

        maintenance = QueueMaintenance()
        result = maintenance.cleanup_old_messages(older_than_days=7)

        assert result == 0
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()


class TestQueueMaintenanceDeleteMessagesForHost:
    """Tests for QueueMaintenance.delete_messages_for_host method."""

    def test_delete_messages_for_host_with_provided_db(self):
        """Test delete messages with provided db session."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 5

        maintenance = QueueMaintenance()
        result = maintenance.delete_messages_for_host("host-123", db=mock_db)

        assert result == 5
        mock_db.commit.assert_not_called()  # Caller manages commit

    @patch("backend.websocket.queue_maintenance.get_db")
    def test_delete_messages_for_host_without_db(self, mock_get_db):
        """Test delete creates and commits its own db session."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.count.return_value = 3

        maintenance = QueueMaintenance()
        result = maintenance.delete_messages_for_host("host-456")

        assert result == 3
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("backend.websocket.queue_maintenance.get_db")
    def test_delete_messages_for_host_error_handling(self, mock_get_db):
        """Test delete handles errors gracefully."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.side_effect = Exception("Database error")

        maintenance = QueueMaintenance()
        result = maintenance.delete_messages_for_host("host-789")

        assert result == 0
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()


class TestQueueMaintenanceExpireOldMessages:
    """Tests for QueueMaintenance.expire_old_messages method."""

    @patch("backend.config.config.config")
    def test_expire_old_messages_with_provided_db(self, mock_config):
        """Test expire with provided db session."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_config.get.return_value = {"expiration_timeout_minutes": 60}

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 3
        mock_db.query.return_value.filter.return_value.update.return_value = None

        maintenance = QueueMaintenance()
        result = maintenance.expire_old_messages(db=mock_db)

        assert result == 3
        mock_db.commit.assert_not_called()  # Caller manages commit

    @patch("backend.config.config.config")
    def test_expire_old_messages_none_to_expire(self, mock_config):
        """Test expire when no messages need expiration."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_config.get.return_value = {}

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 0

        maintenance = QueueMaintenance()
        result = maintenance.expire_old_messages(db=mock_db)

        assert result == 0

    @patch("backend.config.config.config")
    @patch("backend.websocket.queue_maintenance.get_db")
    def test_expire_old_messages_without_db(self, mock_get_db, mock_config):
        """Test expire creates and commits its own db session."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_config.get.return_value = {"expiration_timeout_minutes": 30}

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.count.return_value = 2
        mock_db.query.return_value.filter.return_value.update.return_value = None

        maintenance = QueueMaintenance()
        result = maintenance.expire_old_messages()

        assert result == 2
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("backend.config.config.config")
    @patch("backend.websocket.queue_maintenance.get_db")
    def test_expire_old_messages_error_handling(self, mock_get_db, mock_config):
        """Test expire handles errors gracefully."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_config.get.return_value = {}

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.side_effect = Exception("Database error")

        maintenance = QueueMaintenance()
        result = maintenance.expire_old_messages()

        assert result == 0
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()


class TestQueueMaintenanceDeleteFailedMessages:
    """Tests for QueueMaintenance.delete_failed_messages method."""

    def test_delete_failed_messages_with_provided_db(self):
        """Test delete failed messages with provided db session."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 4

        maintenance = QueueMaintenance()
        result = maintenance.delete_failed_messages(
            ["msg-1", "msg-2", "msg-3", "msg-4"], db=mock_db
        )

        assert result == 4
        mock_db.commit.assert_not_called()  # Caller manages commit

    def test_delete_failed_messages_empty_list(self):
        """Test delete with empty message list."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 0

        maintenance = QueueMaintenance()
        result = maintenance.delete_failed_messages([], db=mock_db)

        assert result == 0

    @patch("backend.websocket.queue_maintenance.get_db")
    def test_delete_failed_messages_without_db(self, mock_get_db):
        """Test delete creates and commits its own db session."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.count.return_value = 2

        maintenance = QueueMaintenance()
        result = maintenance.delete_failed_messages(["msg-1", "msg-2"])

        assert result == 2
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("backend.websocket.queue_maintenance.get_db")
    def test_delete_failed_messages_error_handling(self, mock_get_db):
        """Test delete handles errors gracefully."""
        from backend.websocket.queue_maintenance import QueueMaintenance

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.side_effect = Exception("Database error")

        maintenance = QueueMaintenance()
        result = maintenance.delete_failed_messages(["msg-1"])

        assert result == 0
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()
