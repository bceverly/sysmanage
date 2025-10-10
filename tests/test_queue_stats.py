"""
Comprehensive unit tests for backend.websocket.queue_stats module.
Tests QueueStats class methods for statistics and monitoring.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.persistence.models import Host, MessageQueue
from backend.websocket.queue_enums import QueueDirection, QueueStatus
from backend.websocket.queue_stats import QueueStats


class TestGetQueueStats:
    """Test cases for get_queue_stats method."""

    def test_get_stats_all_messages(self, session):
        """Test getting statistics for all messages."""
        host = Host(
            id=str(uuid4()),
            fqdn="test-host.example.com",
            ipv4="192.168.1.100",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host)
        session.commit()

        # Create messages with different statuses
        statuses = [
            QueueStatus.PENDING,
            QueueStatus.PENDING,
            QueueStatus.IN_PROGRESS,
            QueueStatus.COMPLETED,
            QueueStatus.COMPLETED,
            QueueStatus.COMPLETED,
            QueueStatus.FAILED,
        ]

        for status in statuses:
            message = MessageQueue(
                message_id=str(uuid4()),
                host_id=host.id,
                direction=QueueDirection.INBOUND,
                status=status,
                priority="normal",
                message_type="test_message",
                message_data='{"test": "data"}',
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            session.add(message)
        session.commit()

        stats_manager = QueueStats()
        stats = stats_manager.get_queue_stats(db=session)

        assert stats["total"] == 7
        assert stats["pending"] == 2
        assert stats["in_progress"] == 1
        assert stats["completed"] == 3
        assert stats["failed"] == 1

    def test_get_stats_filtered_by_host(self, session):
        """Test getting statistics filtered by host ID."""
        host1 = Host(
            id=str(uuid4()),
            fqdn="host1.example.com",
            ipv4="192.168.1.100",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host1)
        session.commit()

        host2 = Host(
            id=str(uuid4()),
            fqdn="host2.example.com",
            ipv4="192.168.1.101",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host2)
        session.commit()

        # Create messages for both hosts
        for host in [host1, host2]:
            for i in range(3):
                message = MessageQueue(
                    message_id=str(uuid4()),
                    host_id=host.id,
                    direction=QueueDirection.INBOUND,
                    status=QueueStatus.PENDING,
                    priority="normal",
                    message_type="test_message",
                    message_data='{"test": "data"}',
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                session.add(message)
        session.commit()

        stats_manager = QueueStats()
        stats = stats_manager.get_queue_stats(host_id=host1.id, db=session)

        assert stats["total"] == 3
        assert stats["host_id"] == host1.id
        assert stats["pending"] == 3

    def test_get_stats_filtered_by_direction(self, session):
        """Test getting statistics filtered by direction."""
        host = Host(
            id=str(uuid4()),
            fqdn="test-host.example.com",
            ipv4="192.168.1.100",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host)
        session.commit()

        # Create inbound and outbound messages
        for direction in [
            QueueDirection.INBOUND,
            QueueDirection.INBOUND,
            QueueDirection.OUTBOUND,
        ]:
            message = MessageQueue(
                message_id=str(uuid4()),
                host_id=host.id,
                direction=direction,
                status=QueueStatus.PENDING,
                priority="normal",
                message_type="test_message",
                message_data='{"test": "data"}',
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            session.add(message)
        session.commit()

        stats_manager = QueueStats()
        stats = stats_manager.get_queue_stats(
            direction=QueueDirection.INBOUND, db=session
        )

        assert stats["total"] == 2
        assert stats["direction"] == "inbound"

    def test_get_stats_filtered_by_host_and_direction(self, session):
        """Test getting statistics filtered by both host and direction."""
        host = Host(
            id=str(uuid4()),
            fqdn="test-host.example.com",
            ipv4="192.168.1.100",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host)
        session.commit()

        # Create messages
        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            priority="normal",
            message_type="test_message",
            message_data='{"test": "data"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        stats_manager = QueueStats()
        stats = stats_manager.get_queue_stats(
            host_id=host.id, direction=QueueDirection.INBOUND, db=session
        )

        assert stats["total"] == 1
        assert stats["host_id"] == host.id
        assert stats["direction"] == "inbound"

    def test_get_stats_no_messages(self, session):
        """Test getting statistics when no messages exist."""
        stats_manager = QueueStats()
        stats = stats_manager.get_queue_stats(db=session)

        assert stats["total"] == 0
        assert stats["pending"] == 0
        assert stats["in_progress"] == 0
        assert stats["completed"] == 0
        assert stats["failed"] == 0


class TestGetFailedMessages:
    """Test cases for get_failed_messages method."""

    def test_get_failed_messages_returns_failed(self, session):
        """Test getting failed messages."""
        host = Host(
            id=str(uuid4()),
            fqdn="test-host.example.com",
            ipv4="192.168.1.100",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host)
        session.commit()

        # Create failed and pending messages
        failed_message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.FAILED,
            priority="normal",
            message_type="test_message",
            message_data='{"test": "data"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        pending_message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            priority="normal",
            message_type="test_message",
            message_data='{"test": "data"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(failed_message)
        session.add(pending_message)
        session.commit()

        stats_manager = QueueStats()
        failed_messages = stats_manager.get_failed_messages(db=session)

        assert len(failed_messages) == 1
        assert failed_messages[0].status == QueueStatus.FAILED

    def test_get_failed_messages_returns_expired(self, session):
        """Test getting expired messages."""
        host = Host(
            id=str(uuid4()),
            fqdn="test-host.example.com",
            ipv4="192.168.1.100",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host)
        session.commit()

        # Create expired message
        expired_message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.EXPIRED,
            priority="normal",
            message_type="test_message",
            message_data='{"test": "data"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(expired_message)
        session.commit()

        stats_manager = QueueStats()
        failed_messages = stats_manager.get_failed_messages(db=session)

        assert len(failed_messages) == 1
        assert failed_messages[0].status == QueueStatus.EXPIRED

    def test_get_failed_messages_respects_limit(self, session):
        """Test that limit parameter works correctly."""
        host = Host(
            id=str(uuid4()),
            fqdn="test-host.example.com",
            ipv4="192.168.1.100",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host)
        session.commit()

        # Create 5 failed messages
        for i in range(5):
            message = MessageQueue(
                message_id=str(uuid4()),
                host_id=host.id,
                direction=QueueDirection.INBOUND,
                status=QueueStatus.FAILED,
                priority="normal",
                message_type="test_message",
                message_data='{"test": "data"}',
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            session.add(message)
        session.commit()

        stats_manager = QueueStats()
        failed_messages = stats_manager.get_failed_messages(limit=3, db=session)

        assert len(failed_messages) == 3

    def test_get_failed_messages_no_failures(self, session):
        """Test getting failed messages when none exist."""
        stats_manager = QueueStats()
        failed_messages = stats_manager.get_failed_messages(db=session)

        assert len(failed_messages) == 0
