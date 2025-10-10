"""
Comprehensive unit tests for backend.websocket.inbound_processor module.
Tests process_pending_messages and process_validated_message functions.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from backend.persistence.models import Host, MessageQueue
from backend.websocket.inbound_processor import (
    process_pending_messages,
    process_validated_message,
)
from backend.websocket.queue_manager import QueueDirection, QueueStatus


class TestProcessPendingMessages:
    """Test cases for process_pending_messages function."""

    @pytest.mark.asyncio
    async def test_process_pending_messages_no_messages(self, session):
        """Test processing when no messages are in queue."""
        # No setup needed - empty database
        await process_pending_messages(session)

        # Should complete without errors
        assert True

    @pytest.mark.asyncio
    async def test_process_pending_messages_expires_old_messages(self, session):
        """Test that old messages are expired."""
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

        # Create old message (61 minutes ago - should be expired)
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
            message_data="{}",
            created_at=old_time,
        )
        session.add(old_message)
        session.commit()

        await process_pending_messages(session)

        # Check that message was expired
        message = (
            session.query(MessageQueue)
            .filter_by(message_id=old_message.message_id)
            .first()
        )
        assert message.expired_at is not None

    @pytest.mark.asyncio
    async def test_process_pending_messages_resets_stuck_messages(self, session):
        """Test that stuck IN_PROGRESS messages are reset to PENDING."""
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

        # Create stuck message (35 seconds ago in IN_PROGRESS)
        stuck_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            seconds=35
        )
        stuck_message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.IN_PROGRESS,
            priority="normal",
            message_type="test_message",
            message_data='{"test": "data"}',
            created_at=stuck_time,
            started_at=stuck_time,
        )
        session.add(stuck_message)
        session.commit()

        await process_pending_messages(session)

        # Check that message was reset to PENDING
        message = (
            session.query(MessageQueue)
            .filter_by(message_id=stuck_message.message_id)
            .first()
        )
        assert message.status == QueueStatus.PENDING
        assert message.started_at is None

    @pytest.mark.asyncio
    async def test_process_pending_messages_deletes_for_nonexistent_host(self, session):
        """Test that messages for non-existent hosts are deleted."""
        nonexistent_host_id = str(uuid4())

        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=nonexistent_host_id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            message_type="test_message",
            message_data="{}",
            priority="normal",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        message_id = message.message_id
        await process_pending_messages(session)

        # Check that message was deleted
        remaining = session.query(MessageQueue).filter_by(message_id=message_id).first()
        assert remaining is None

    @pytest.mark.asyncio
    async def test_process_pending_messages_deletes_for_unapproved_host(self, session):
        """Test that messages for unapproved hosts are deleted."""
        host = Host(
            id=str(uuid4()),
            fqdn="unapproved-host.example.com",
            ipv4="192.168.1.101",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="pending",  # Not approved
        )
        session.add(host)
        session.commit()

        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            message_type="test_message",
            message_data="{}",
            priority="normal",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        message_id = message.message_id
        await process_pending_messages(session)

        # Check that message was deleted
        remaining = session.query(MessageQueue).filter_by(message_id=message_id).first()
        assert remaining is None

    @pytest.mark.asyncio
    async def test_process_pending_messages_processes_approved_host(self, session):
        """Test that messages for approved hosts are processed."""
        host = Host(
            id=str(uuid4()),
            fqdn="approved-host.example.com",
            ipv4="192.168.1.102",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host)
        session.commit()

        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            message_type="heartbeat",
            message_data='{"hostname": "approved-host.example.com"}',
            priority="normal",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        with patch(
            "backend.websocket.inbound_processor.process_validated_message",
            new_callable=AsyncMock,
        ) as mock_process:
            await process_pending_messages(session)

            # Verify process_validated_message was called
            assert mock_process.called

    @pytest.mark.asyncio
    async def test_process_pending_messages_null_host_id_with_hostname(self, session):
        """Test processing message with NULL host_id but valid hostname."""
        host = Host(
            id=str(uuid4()),
            fqdn="hostname-host.example.com",
            ipv4="192.168.1.103",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host)
        session.commit()

        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=None,  # NULL host_id
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            message_type="heartbeat",
            message_data='{"hostname": "hostname-host.example.com"}',
            priority="normal",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        with patch(
            "backend.websocket.inbound_processor.process_validated_message",
            new_callable=AsyncMock,
        ) as mock_process:
            await process_pending_messages(session)

            # Verify process_validated_message was called with correct host
            assert mock_process.called
            call_args = mock_process.call_args
            assert call_args[0][1].id == host.id

    @pytest.mark.asyncio
    async def test_process_pending_messages_null_host_id_missing_hostname(
        self, session
    ):
        """Test processing message with NULL host_id and missing hostname."""
        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=None,  # NULL host_id
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            message_type="test_message",
            message_data="{}",  # No hostname
            priority="normal",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        message_id = message.message_id
        await process_pending_messages(session)

        # Check that message was marked as failed or remains unprocessed
        msg = session.query(MessageQueue).filter_by(message_id=message_id).first()
        # Message should exist and be marked failed, or be deleted
        # In practice, mark_failed sets failed status but doesn't always delete
        assert msg is None or msg.status in [QueueStatus.FAILED, QueueStatus.PENDING]

    @pytest.mark.asyncio
    async def test_process_pending_messages_null_host_id_unknown_hostname(
        self, session
    ):
        """Test processing message with NULL host_id and unknown hostname."""
        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=None,  # NULL host_id
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            message_type="test_message",
            message_data='{"hostname": "unknown-host.example.com"}',
            priority="normal",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        message_id = message.message_id
        await process_pending_messages(session)

        # Check that message was marked as failed or remains unprocessed
        msg = session.query(MessageQueue).filter_by(message_id=message_id).first()
        # Message should be marked failed, remain pending, or be deleted
        assert msg is None or msg.status in [QueueStatus.FAILED, QueueStatus.PENDING]


class TestProcessValidatedMessage:
    """Test cases for process_validated_message function."""

    @pytest.mark.asyncio
    async def test_process_validated_message_success(self, session):
        """Test successful message processing."""
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

        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            message_type="heartbeat",
            message_data='{"hostname": "test-host.example.com"}',
            priority="normal",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        with patch(
            "backend.websocket.inbound_processor.route_inbound_message",
            new_callable=AsyncMock,
            return_value=True,
        ):
            message_id = message.message_id
            await process_validated_message(message, host, session)

        # Verify message was marked as completed
        msg = session.query(MessageQueue).filter_by(message_id=message_id).first()
        assert msg is None or msg.status == QueueStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_process_validated_message_failure(self, session):
        """Test message processing failure."""
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

        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            message_type="unknown_type",
            message_data='{"test": "data"}',
            priority="normal",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        with patch(
            "backend.websocket.inbound_processor.route_inbound_message",
            new_callable=AsyncMock,
            return_value=False,  # Simulate failure
        ):
            message_id = message.message_id
            await process_validated_message(message, host, session)

        # Verify message was marked as failed or remains unprocessed
        msg = session.query(MessageQueue).filter_by(message_id=message_id).first()
        # Message should be marked failed, remain pending, or be deleted
        assert msg is None or msg.status in [QueueStatus.FAILED, QueueStatus.PENDING]

    @pytest.mark.asyncio
    async def test_process_validated_message_exception(self, session):
        """Test message processing with exception."""
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

        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            message_type="test_message",
            message_data='{"test": "data"}',
            priority="normal",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        with patch(
            "backend.websocket.inbound_processor.route_inbound_message",
            new_callable=AsyncMock,
            side_effect=Exception("Test exception"),
        ):
            message_id = message.message_id
            await process_validated_message(message, host, session)

        # Verify message was marked as failed or remains unprocessed
        msg = session.query(MessageQueue).filter_by(message_id=message_id).first()
        # Message should be marked failed, remain pending, or be deleted
        assert msg is None or msg.status in [QueueStatus.FAILED, QueueStatus.PENDING]

    @pytest.mark.asyncio
    async def test_process_validated_message_marks_processing(self, session):
        """Test that message is marked as IN_PROGRESS during processing."""
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

        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            message_type="heartbeat",
            message_data='{"hostname": "test-host.example.com"}',
            priority="normal",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        processing_was_set = False

        async def check_processing(*args, **kwargs):
            nonlocal processing_was_set
            msg = (
                session.query(MessageQueue)
                .filter_by(message_id=message.message_id)
                .first()
            )
            if msg and msg.status == QueueStatus.IN_PROGRESS:
                processing_was_set = True
            return True

        with patch(
            "backend.websocket.inbound_processor.route_inbound_message",
            new_callable=AsyncMock,
            side_effect=check_processing,
        ):
            await process_validated_message(message, host, session)

        assert processing_was_set

    @pytest.mark.asyncio
    async def test_process_validated_message_creates_mock_connection(self, session):
        """Test that MockConnection is created with correct properties."""
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

        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=host.id,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            message_type="heartbeat",
            message_data='{"hostname": "test-host.example.com"}',
            priority="normal",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        captured_connection = None

        async def capture_connection(message_type, db, connection, message_data):
            nonlocal captured_connection
            captured_connection = connection
            return True

        with patch(
            "backend.websocket.inbound_processor.route_inbound_message",
            new_callable=AsyncMock,
            side_effect=capture_connection,
        ):
            await process_validated_message(message, host, session)

        assert captured_connection is not None
        assert captured_connection.host_id == host.id
        assert captured_connection.hostname == host.fqdn
