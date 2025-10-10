"""
Comprehensive unit tests for backend.websocket.queue_maintenance module.
Tests QueueMaintenance class methods for cleanup, deletion, and expiration.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.persistence.models import Host, MessageQueue
from backend.websocket.queue_enums import QueueDirection, QueueStatus
from backend.websocket.queue_maintenance import QueueMaintenance


class TestCleanupOldMessages:
    """Test cases for cleanup_old_messages method."""

    def test_cleanup_old_completed_messages(self, session):
        """Test cleanup of old completed messages."""
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

        # Create old completed message (8 days ago)
        old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=8)
        old_message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.COMPLETED,
            priority="normal",
            message_type="heartbeat",
            message_data='{"test": "data"}',
            created_at=old_time,
            completed_at=old_time,
        )
        session.add(old_message)

        # Create recent completed message (should not be deleted)
        recent_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=1
        )
        recent_message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.COMPLETED,
            priority="normal",
            message_type="heartbeat",
            message_data='{"test": "data"}',
            created_at=recent_time,
            completed_at=recent_time,
        )
        session.add(recent_message)
        session.commit()

        maintenance = QueueMaintenance()
        deleted_count = maintenance.cleanup_old_messages(
            older_than_days=7, keep_failed=True, db=session
        )

        # Note: The cleanup method might return count but not commit when session is provided
        # Let's commit to ensure changes are persisted
        session.commit()

        assert deleted_count >= 1

        # Verify old message was deleted but recent one remains
        remaining = (
            session.query(MessageQueue)
            .filter_by(message_id=recent_message.message_id)
            .first()
        )
        assert remaining is not None

        # Verify old message is gone
        old_remaining = (
            session.query(MessageQueue)
            .filter_by(message_id=old_message.message_id)
            .first()
        )
        assert old_remaining is None

    def test_cleanup_with_keep_failed_true(self, session):
        """Test cleanup keeps failed messages when keep_failed=True."""
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

        # Create old failed message
        old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=8)
        failed_message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.FAILED,
            priority="normal",
            message_type="test_message",
            message_data='{"test": "data"}',
            created_at=old_time,
            completed_at=old_time,
        )
        session.add(failed_message)
        session.commit()

        maintenance = QueueMaintenance()
        deleted_count = maintenance.cleanup_old_messages(
            older_than_days=7, keep_failed=True, db=session
        )

        assert deleted_count == 0

        # Verify failed message still exists
        remaining = session.query(MessageQueue).all()
        assert len(remaining) == 1

    def test_cleanup_with_keep_failed_false(self, session):
        """Test cleanup removes failed messages when keep_failed=False."""
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

        # Create old failed message
        old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=8)
        failed_message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.FAILED,
            priority="normal",
            message_type="test_message",
            message_data='{"test": "data"}',
            created_at=old_time,
            completed_at=old_time,
        )
        session.add(failed_message)
        session.commit()

        maintenance = QueueMaintenance()
        deleted_count = maintenance.cleanup_old_messages(
            older_than_days=7, keep_failed=False, db=session
        )

        # Commit to ensure changes are persisted
        session.commit()

        assert deleted_count >= 1

        # Verify message was deleted
        failed_remaining = (
            session.query(MessageQueue)
            .filter_by(message_id=failed_message.message_id)
            .first()
        )
        assert failed_remaining is None

    def test_cleanup_no_old_messages(self, session):
        """Test cleanup when there are no old messages."""
        maintenance = QueueMaintenance()
        deleted_count = maintenance.cleanup_old_messages(
            older_than_days=7, keep_failed=True, db=session
        )

        assert deleted_count == 0


class TestDeleteMessagesForHost:
    """Test cases for delete_messages_for_host method."""

    def test_delete_all_messages_for_host(self, session):
        """Test deleting all messages for a specific host."""
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
                    message_type="heartbeat",
                    message_data='{"test": "data"}',
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                session.add(message)
        session.commit()

        maintenance = QueueMaintenance()
        deleted_count = maintenance.delete_messages_for_host(host1.id, db=session)

        assert deleted_count == 3

        # Verify only host2 messages remain
        remaining = session.query(MessageQueue).all()
        assert len(remaining) == 3
        for msg in remaining:
            assert msg.host_id == host2.id

    def test_delete_messages_for_nonexistent_host(self, session):
        """Test deleting messages for host with no messages."""
        nonexistent_host_id = str(uuid4())

        maintenance = QueueMaintenance()
        deleted_count = maintenance.delete_messages_for_host(
            nonexistent_host_id, db=session
        )

        assert deleted_count == 0


class TestExpireOldMessages:
    """Test cases for expire_old_messages method."""

    def test_expire_old_pending_messages(self, session):
        """Test expiring old pending messages."""
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

        # Create old pending message (61 minutes ago - should expire with default 60min timeout)
        old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=61
        )
        old_message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            priority="normal",
            message_type="test_message",
            message_data='{"test": "data"}',
            created_at=old_time,
        )
        session.add(old_message)
        session.commit()

        maintenance = QueueMaintenance()
        expired_count = maintenance.expire_old_messages(db=session)

        assert expired_count == 1

        # Verify message was marked as expired
        message = (
            session.query(MessageQueue)
            .filter_by(message_id=old_message.message_id)
            .first()
        )
        assert message.status == QueueStatus.EXPIRED
        assert message.expired_at is not None

    def test_expire_old_in_progress_messages(self, session):
        """Test expiring old IN_PROGRESS messages."""
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

        # Create old IN_PROGRESS message
        old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=61
        )
        old_message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.IN_PROGRESS,
            priority="normal",
            message_type="test_message",
            message_data='{"test": "data"}',
            created_at=old_time,
            started_at=old_time,
        )
        session.add(old_message)
        session.commit()

        maintenance = QueueMaintenance()
        expired_count = maintenance.expire_old_messages(db=session)

        assert expired_count == 1

        # Verify message was marked as expired
        message = (
            session.query(MessageQueue)
            .filter_by(message_id=old_message.message_id)
            .first()
        )
        assert message.status == QueueStatus.EXPIRED

    def test_expire_does_not_touch_completed_messages(self, session):
        """Test that completed messages are not expired."""
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

        # Create old completed message
        old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=61
        )
        completed_message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.COMPLETED,
            priority="normal",
            message_type="test_message",
            message_data='{"test": "data"}',
            created_at=old_time,
            completed_at=old_time,
        )
        session.add(completed_message)
        session.commit()

        maintenance = QueueMaintenance()
        expired_count = maintenance.expire_old_messages(db=session)

        assert expired_count == 0

        # Verify message status unchanged
        message = (
            session.query(MessageQueue)
            .filter_by(message_id=completed_message.message_id)
            .first()
        )
        assert message.status == QueueStatus.COMPLETED

    def test_expire_no_old_messages(self, session):
        """Test expiration when there are no old messages."""
        maintenance = QueueMaintenance()
        expired_count = maintenance.expire_old_messages(db=session)

        assert expired_count == 0


class TestDeleteFailedMessages:
    """Test cases for delete_failed_messages method."""

    def test_delete_specific_failed_messages(self, session):
        """Test deleting specific failed messages by ID."""
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

        # Create failed messages
        failed_message1 = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.FAILED,
            priority="normal",
            message_type="test_message",
            message_data='{"test": "data"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(failed_message1)
        session.commit()

        failed_message2 = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.FAILED,
            priority="normal",
            message_type="test_message",
            message_data='{"test": "data"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(failed_message2)
        session.commit()

        maintenance = QueueMaintenance()
        deleted_count = maintenance.delete_failed_messages(
            [failed_message1.message_id], db=session
        )

        assert deleted_count == 1

        # Verify only first message was deleted
        remaining = session.query(MessageQueue).all()
        assert len(remaining) == 1
        assert remaining[0].message_id == failed_message2.message_id

    def test_delete_expired_messages(self, session):
        """Test deleting expired messages."""
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
            expired_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(expired_message)
        session.commit()

        maintenance = QueueMaintenance()
        deleted_count = maintenance.delete_failed_messages(
            [expired_message.message_id], db=session
        )

        assert deleted_count == 1

        # Verify message was deleted
        remaining = session.query(MessageQueue).all()
        assert len(remaining) == 0

    def test_delete_does_not_remove_pending_messages(self, session):
        """Test that pending messages are not deleted."""
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

        # Create pending message
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
        session.add(pending_message)
        session.commit()

        maintenance = QueueMaintenance()
        deleted_count = maintenance.delete_failed_messages(
            [pending_message.message_id], db=session
        )

        assert deleted_count == 0

        # Verify message still exists
        remaining = session.query(MessageQueue).all()
        assert len(remaining) == 1

    def test_delete_nonexistent_message_ids(self, session):
        """Test deleting with non-existent message IDs."""
        maintenance = QueueMaintenance()
        deleted_count = maintenance.delete_failed_messages(
            [str(uuid4()), str(uuid4())], db=session
        )

        assert deleted_count == 0
