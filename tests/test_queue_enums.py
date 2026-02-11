"""
Tests for backend/websocket/queue_enums.py module.
Tests message queue enumerations.
"""

import pytest


class TestQueueStatus:
    """Tests for QueueStatus class."""

    def test_pending_status(self):
        """Test PENDING status value."""
        from backend.websocket.queue_enums import QueueStatus

        assert QueueStatus.PENDING == "pending"

    def test_in_progress_status(self):
        """Test IN_PROGRESS status value."""
        from backend.websocket.queue_enums import QueueStatus

        assert QueueStatus.IN_PROGRESS == "in_progress"

    def test_sent_status(self):
        """Test SENT status value."""
        from backend.websocket.queue_enums import QueueStatus

        assert QueueStatus.SENT == "sent"

    def test_completed_status(self):
        """Test COMPLETED status value."""
        from backend.websocket.queue_enums import QueueStatus

        assert QueueStatus.COMPLETED == "completed"

    def test_failed_status(self):
        """Test FAILED status value."""
        from backend.websocket.queue_enums import QueueStatus

        assert QueueStatus.FAILED == "failed"

    def test_expired_status(self):
        """Test EXPIRED status value."""
        from backend.websocket.queue_enums import QueueStatus

        assert QueueStatus.EXPIRED == "expired"

    def test_all_statuses_are_strings(self):
        """Test all status values are strings."""
        from backend.websocket.queue_enums import QueueStatus

        statuses = [
            QueueStatus.PENDING,
            QueueStatus.IN_PROGRESS,
            QueueStatus.SENT,
            QueueStatus.COMPLETED,
            QueueStatus.FAILED,
            QueueStatus.EXPIRED,
        ]
        for status in statuses:
            assert isinstance(status, str)

    def test_all_statuses_are_unique(self):
        """Test all status values are unique."""
        from backend.websocket.queue_enums import QueueStatus

        statuses = [
            QueueStatus.PENDING,
            QueueStatus.IN_PROGRESS,
            QueueStatus.SENT,
            QueueStatus.COMPLETED,
            QueueStatus.FAILED,
            QueueStatus.EXPIRED,
        ]
        assert len(statuses) == len(set(statuses))


class TestQueueDirection:
    """Tests for QueueDirection class."""

    def test_outbound_direction(self):
        """Test OUTBOUND direction value."""
        from backend.websocket.queue_enums import QueueDirection

        assert QueueDirection.OUTBOUND == "outbound"

    def test_inbound_direction(self):
        """Test INBOUND direction value."""
        from backend.websocket.queue_enums import QueueDirection

        assert QueueDirection.INBOUND == "inbound"

    def test_directions_are_strings(self):
        """Test direction values are strings."""
        from backend.websocket.queue_enums import QueueDirection

        assert isinstance(QueueDirection.OUTBOUND, str)
        assert isinstance(QueueDirection.INBOUND, str)

    def test_directions_are_different(self):
        """Test directions are different values."""
        from backend.websocket.queue_enums import QueueDirection

        assert QueueDirection.OUTBOUND != QueueDirection.INBOUND


class TestPriority:
    """Tests for Priority class."""

    def test_low_priority(self):
        """Test LOW priority value."""
        from backend.websocket.queue_enums import Priority

        assert Priority.LOW == "low"

    def test_normal_priority(self):
        """Test NORMAL priority value."""
        from backend.websocket.queue_enums import Priority

        assert Priority.NORMAL == "normal"

    def test_high_priority(self):
        """Test HIGH priority value."""
        from backend.websocket.queue_enums import Priority

        assert Priority.HIGH == "high"

    def test_urgent_priority(self):
        """Test URGENT priority value."""
        from backend.websocket.queue_enums import Priority

        assert Priority.URGENT == "urgent"

    def test_all_priorities_are_strings(self):
        """Test all priority values are strings."""
        from backend.websocket.queue_enums import Priority

        priorities = [
            Priority.LOW,
            Priority.NORMAL,
            Priority.HIGH,
            Priority.URGENT,
        ]
        for priority in priorities:
            assert isinstance(priority, str)

    def test_all_priorities_are_unique(self):
        """Test all priority values are unique."""
        from backend.websocket.queue_enums import Priority

        priorities = [
            Priority.LOW,
            Priority.NORMAL,
            Priority.HIGH,
            Priority.URGENT,
        ]
        assert len(priorities) == len(set(priorities))


class TestEnumsUsability:
    """Tests for enum usability in comparisons and lookups."""

    def test_status_comparison(self):
        """Test status values can be compared."""
        from backend.websocket.queue_enums import QueueStatus

        status = "pending"
        assert status == QueueStatus.PENDING
        assert status != QueueStatus.COMPLETED

    def test_direction_in_list(self):
        """Test directions work in list lookups."""
        from backend.websocket.queue_enums import QueueDirection

        valid_directions = [QueueDirection.INBOUND, QueueDirection.OUTBOUND]
        assert "inbound" in valid_directions
        assert "outbound" in valid_directions
        assert "unknown" not in valid_directions

    def test_priority_dict_key(self):
        """Test priorities can be used as dictionary keys."""
        from backend.websocket.queue_enums import Priority

        priority_weights = {
            Priority.LOW: 1,
            Priority.NORMAL: 2,
            Priority.HIGH: 3,
            Priority.URGENT: 4,
        }

        assert priority_weights["low"] == 1
        assert priority_weights[Priority.NORMAL] == 2
