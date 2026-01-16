"""
Tests for the message queue enumerations module.

This module tests the QueueStatus, QueueDirection, and Priority classes
that define message queue constants.
"""

import pytest

from backend.websocket.queue_enums import Priority, QueueDirection, QueueStatus


class TestQueueStatus:
    """Test cases for QueueStatus enumeration."""

    def test_pending_status(self):
        """Verify PENDING status value."""
        assert QueueStatus.PENDING == "pending"

    def test_in_progress_status(self):
        """Verify IN_PROGRESS status value."""
        assert QueueStatus.IN_PROGRESS == "in_progress"

    def test_sent_status(self):
        """Verify SENT status value."""
        assert QueueStatus.SENT == "sent"

    def test_completed_status(self):
        """Verify COMPLETED status value."""
        assert QueueStatus.COMPLETED == "completed"

    def test_failed_status(self):
        """Verify FAILED status value."""
        assert QueueStatus.FAILED == "failed"

    def test_expired_status(self):
        """Verify EXPIRED status value."""
        assert QueueStatus.EXPIRED == "expired"

    def test_all_statuses_are_strings(self):
        """Verify all status values are strings."""
        assert isinstance(QueueStatus.PENDING, str)
        assert isinstance(QueueStatus.IN_PROGRESS, str)
        assert isinstance(QueueStatus.SENT, str)
        assert isinstance(QueueStatus.COMPLETED, str)
        assert isinstance(QueueStatus.FAILED, str)
        assert isinstance(QueueStatus.EXPIRED, str)

    def test_statuses_are_lowercase(self):
        """Verify all status values are lowercase."""
        assert QueueStatus.PENDING == QueueStatus.PENDING.lower()
        assert QueueStatus.IN_PROGRESS == QueueStatus.IN_PROGRESS.lower()
        assert QueueStatus.SENT == QueueStatus.SENT.lower()
        assert QueueStatus.COMPLETED == QueueStatus.COMPLETED.lower()
        assert QueueStatus.FAILED == QueueStatus.FAILED.lower()
        assert QueueStatus.EXPIRED == QueueStatus.EXPIRED.lower()


class TestQueueDirection:
    """Test cases for QueueDirection enumeration."""

    def test_outbound_direction(self):
        """Verify OUTBOUND direction value."""
        assert QueueDirection.OUTBOUND == "outbound"

    def test_inbound_direction(self):
        """Verify INBOUND direction value."""
        assert QueueDirection.INBOUND == "inbound"

    def test_directions_are_strings(self):
        """Verify all direction values are strings."""
        assert isinstance(QueueDirection.OUTBOUND, str)
        assert isinstance(QueueDirection.INBOUND, str)

    def test_directions_are_lowercase(self):
        """Verify all direction values are lowercase."""
        assert QueueDirection.OUTBOUND == QueueDirection.OUTBOUND.lower()
        assert QueueDirection.INBOUND == QueueDirection.INBOUND.lower()


class TestPriority:
    """Test cases for Priority enumeration."""

    def test_low_priority(self):
        """Verify LOW priority value."""
        assert Priority.LOW == "low"

    def test_normal_priority(self):
        """Verify NORMAL priority value."""
        assert Priority.NORMAL == "normal"

    def test_high_priority(self):
        """Verify HIGH priority value."""
        assert Priority.HIGH == "high"

    def test_urgent_priority(self):
        """Verify URGENT priority value."""
        assert Priority.URGENT == "urgent"

    def test_priorities_are_strings(self):
        """Verify all priority values are strings."""
        assert isinstance(Priority.LOW, str)
        assert isinstance(Priority.NORMAL, str)
        assert isinstance(Priority.HIGH, str)
        assert isinstance(Priority.URGENT, str)

    def test_priorities_are_lowercase(self):
        """Verify all priority values are lowercase."""
        assert Priority.LOW == Priority.LOW.lower()
        assert Priority.NORMAL == Priority.NORMAL.lower()
        assert Priority.HIGH == Priority.HIGH.lower()
        assert Priority.URGENT == Priority.URGENT.lower()


class TestQueueEnumsUsage:
    """Test cases for practical usage of queue enums."""

    def test_can_use_status_in_dict(self):
        """Test that status can be used as dict values."""
        message = {
            "id": "test-123",
            "status": QueueStatus.PENDING,
        }
        assert message["status"] == "pending"

    def test_can_use_direction_in_dict(self):
        """Test that direction can be used as dict values."""
        message = {
            "id": "test-123",
            "direction": QueueDirection.OUTBOUND,
        }
        assert message["direction"] == "outbound"

    def test_can_use_priority_in_dict(self):
        """Test that priority can be used as dict values."""
        message = {
            "id": "test-123",
            "priority": Priority.HIGH,
        }
        assert message["priority"] == "high"

    def test_can_compare_status_with_string(self):
        """Test that status can be compared with string."""
        status = QueueStatus.COMPLETED
        assert status == "completed"

    def test_can_use_in_conditional(self):
        """Test that enums work in conditional statements."""
        status = QueueStatus.FAILED
        if status == QueueStatus.FAILED:
            result = "error"
        else:
            result = "ok"
        assert result == "error"
