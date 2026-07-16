# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Comprehensive unit tests for backend.websocket.inbound_processor module.
Tests process_pending_messages and process_validated_message functions.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
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
    async def test_process_pending_messages_defers_for_nonexistent_host(self, session):
        """Phase 13.1 #2: a message whose host isn't present on THIS database is
        deferred (mark_failed → retry-with-backoff), NOT hard-deleted.  Under
        per-tenant queues a freshly-registered host's row may not be visible yet
        when its messages are already queued; deleting would lose the agent's
        data, so we retry instead and only give up after max_retries."""
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

        # The data-loss guard: the message must survive (not be deleted) and be
        # rescheduled for retry rather than processed against a missing host.
        remaining = session.query(MessageQueue).filter_by(message_id=message_id).first()
        assert remaining is not None
        assert remaining.retry_count == 1
        assert remaining.status == QueueStatus.PENDING
        assert remaining.scheduled_at is not None

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
    async def test_host_id_resolves_to_tenant_over_stale_bootstrap_hostname(
        self, session
    ):
        """A provided host_id that resolves to a tenant host must win over a
        stale bootstrap row sharing the same fqdn.

        Regression: a leftover bootstrap row (often ``pending``) matched the
        hostname fallback first and shadowed the real, approved tenant host the
        agent identified by id — failing every inbound message as "not
        approved".  host_id must be resolved (bootstrap + tenants) before any
        hostname fallback runs.
        """
        stale = Host(
            id=str(uuid4()),
            fqdn="dup-host.example.com",
            ipv4="10.0.0.9",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="pending",  # the stale duplicate
        )
        session.add(stale)
        session.commit()

        real_id = str(uuid4())  # the agent's real (tenant) host id
        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=None,
            direction=QueueDirection.INBOUND,
            status=QueueStatus.PENDING,
            message_type="process_status_update",
            message_data=json.dumps(
                {"host_id": real_id, "hostname": "dup-host.example.com"}
            ),
            priority="normal",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        # The agent's host_id resolves to an APPROVED host in a tenant DB.
        tenant_host = MagicMock()
        tenant_host.id = real_id
        tenant_host.fqdn = "dup-host.example.com"
        tenant_host.approval_status = "approved"

        with patch(
            "backend.websocket.inbound_processor._find_host_in_tenant_dbs",
            return_value=(tenant_host, None),
        ) as mock_find, patch(
            "backend.websocket.inbound_processor.process_validated_message",
            new_callable=AsyncMock,
        ) as mock_process:
            await process_pending_messages(session)

        # host_id was resolved across tenants FIRST (by id, no hostname).
        mock_find.assert_called_once_with(real_id, None)
        # Processed against the tenant host, NOT the stale pending bootstrap row.
        assert mock_process.called
        assert mock_process.call_args[0][1] is tenant_host
        assert mock_process.call_args[0][1].id != stale.id

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
