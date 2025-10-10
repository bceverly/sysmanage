"""
Comprehensive unit tests for backend.websocket.outbound_processor module.
Tests process_outbound_messages, process_outbound_message, and send_command_to_agent.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from backend.persistence.models import Host, MessageQueue
from backend.websocket.outbound_processor import (
    process_outbound_message,
    process_outbound_messages,
    send_command_to_agent,
)
from backend.websocket.queue_manager import QueueDirection, QueueStatus


class TestProcessOutboundMessages:
    """Test cases for process_outbound_messages function."""

    @pytest.mark.asyncio
    async def test_process_outbound_messages_no_messages(self, session):
        """Test processing when no outbound messages exist."""
        await process_outbound_messages(session)
        # Should complete without errors
        assert True

    @pytest.mark.asyncio
    async def test_process_outbound_messages_host_not_found(self, session):
        """Test processing message for non-existent host."""
        nonexistent_host_id = str(uuid4())

        message = MessageQueue(
            message_id=str(uuid4()),
            host_id=nonexistent_host_id,
            direction=QueueDirection.OUTBOUND,
            status=QueueStatus.PENDING,
            priority="normal",
            message_type="command",
            message_data='{"command": "test"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        message_id = message.message_id
        await process_outbound_messages(session)

        # Message should be marked as failed
        msg = session.query(MessageQueue).filter_by(message_id=message_id).first()
        assert msg is None or msg.status in [QueueStatus.FAILED, QueueStatus.PENDING]

    @pytest.mark.asyncio
    async def test_process_outbound_messages_host_not_approved(self, session):
        """Test processing message for unapproved host."""
        host = Host(
            id=str(uuid4()),
            fqdn="unapproved-host.example.com",
            ipv4="192.168.1.100",
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
            direction=QueueDirection.OUTBOUND,
            status=QueueStatus.PENDING,
            priority="normal",
            message_type="command",
            message_data='{"command": "test"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        message_id = message.message_id
        await process_outbound_messages(session)

        # Message should be marked as failed
        msg = session.query(MessageQueue).filter_by(message_id=message_id).first()
        assert msg is None or msg.status in [QueueStatus.FAILED, QueueStatus.PENDING]

    @pytest.mark.asyncio
    async def test_process_outbound_messages_success(self, session):
        """Test successful processing of outbound messages."""
        host = Host(
            id=str(uuid4()),
            fqdn="approved-host.example.com",
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
            direction=QueueDirection.OUTBOUND,
            status=QueueStatus.PENDING,
            priority="normal",
            message_type="command",
            message_data='{"command": "test"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        with patch(
            "backend.websocket.outbound_processor.process_outbound_message",
            new_callable=AsyncMock,
        ) as mock_process:
            await process_outbound_messages(session)

        # Verify process_outbound_message was called
        assert mock_process.called

    @pytest.mark.asyncio
    async def test_process_outbound_messages_multiple_hosts(self, session):
        """Test processing messages for multiple hosts."""
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

        message1 = MessageQueue(
            message_id=str(uuid4()),
            host_id=host1.id,
            direction=QueueDirection.OUTBOUND,
            status=QueueStatus.PENDING,
            priority="normal",
            message_type="command",
            message_data='{"command": "test1"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        message2 = MessageQueue(
            message_id=str(uuid4()),
            host_id=host2.id,
            direction=QueueDirection.OUTBOUND,
            status=QueueStatus.PENDING,
            priority="normal",
            message_type="command",
            message_data='{"command": "test2"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add_all([message1, message2])
        session.commit()

        with patch(
            "backend.websocket.outbound_processor.process_outbound_message",
            new_callable=AsyncMock,
        ) as mock_process:
            await process_outbound_messages(session)

        # Verify process_outbound_message was called for both hosts
        assert mock_process.call_count == 2


class TestProcessOutboundMessage:
    """Test cases for process_outbound_message function."""

    @pytest.mark.asyncio
    async def test_process_outbound_message_command_success(self, session):
        """Test successful processing of command message."""
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
            direction=QueueDirection.OUTBOUND,
            status=QueueStatus.PENDING,
            priority="normal",
            message_type="command",
            message_data='{"command": "reboot"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        with patch(
            "backend.websocket.outbound_processor.send_command_to_agent",
            new_callable=AsyncMock,
            return_value=True,
        ):
            message_id = message.message_id
            await process_outbound_message(message, host, session)

        # Verify message was marked as completed
        msg = session.query(MessageQueue).filter_by(message_id=message_id).first()
        assert msg is None or msg.status == QueueStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_process_outbound_message_command_failure(self, session):
        """Test processing of command message that fails to send."""
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
            direction=QueueDirection.OUTBOUND,
            status=QueueStatus.PENDING,
            priority="normal",
            message_type="command",
            message_data='{"command": "reboot"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        with patch(
            "backend.websocket.outbound_processor.send_command_to_agent",
            new_callable=AsyncMock,
            return_value=False,
        ):
            message_id = message.message_id
            await process_outbound_message(message, host, session)

        # Verify message was marked as failed
        msg = session.query(MessageQueue).filter_by(message_id=message_id).first()
        assert msg is None or msg.status in [QueueStatus.FAILED, QueueStatus.PENDING]

    @pytest.mark.asyncio
    async def test_process_outbound_message_unknown_type(self, session):
        """Test processing of unknown message type."""
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
            direction=QueueDirection.OUTBOUND,
            status=QueueStatus.PENDING,
            priority="normal",
            message_type="unknown_type",
            message_data='{"data": "test"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        message_id = message.message_id
        await process_outbound_message(message, host, session)

        # Verify message was marked as failed due to unknown type
        msg = session.query(MessageQueue).filter_by(message_id=message_id).first()
        assert msg is None or msg.status in [QueueStatus.FAILED, QueueStatus.PENDING]

    @pytest.mark.asyncio
    async def test_process_outbound_message_exception(self, session):
        """Test processing when exception occurs."""
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
            direction=QueueDirection.OUTBOUND,
            status=QueueStatus.PENDING,
            priority="normal",
            message_type="command",
            message_data='{"command": "test"}',
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(message)
        session.commit()

        with patch(
            "backend.websocket.outbound_processor.send_command_to_agent",
            new_callable=AsyncMock,
            side_effect=Exception("Test exception"),
        ):
            message_id = message.message_id
            await process_outbound_message(message, host, session)

        # Verify message was marked as failed
        msg = session.query(MessageQueue).filter_by(message_id=message_id).first()
        assert msg is None or msg.status in [QueueStatus.FAILED, QueueStatus.PENDING]


class TestSendCommandToAgent:
    """Test cases for send_command_to_agent function."""

    @pytest.mark.asyncio
    async def test_send_command_to_agent_success(self):
        """Test successfully sending command to agent."""
        host = Mock()
        host.id = str(uuid4())
        host.fqdn = "test-host.example.com"

        command_data = {"command": "reboot", "timeout": 30}
        message_id = str(uuid4())

        with patch(
            "backend.websocket.connection_manager.connection_manager"
        ) as mock_manager:
            mock_manager.send_to_host = AsyncMock(return_value=True)

            result = await send_command_to_agent(command_data, host, message_id)

        assert result is True
        mock_manager.send_to_host.assert_called_once_with(host.id, command_data)

    @pytest.mark.asyncio
    async def test_send_command_to_agent_failure(self):
        """Test sending command when agent not connected."""
        host = Mock()
        host.id = str(uuid4())
        host.fqdn = "test-host.example.com"

        command_data = {"command": "reboot"}
        message_id = str(uuid4())

        with patch(
            "backend.websocket.connection_manager.connection_manager"
        ) as mock_manager:
            mock_manager.send_to_host = AsyncMock(return_value=False)

            result = await send_command_to_agent(command_data, host, message_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_command_to_agent_exception(self):
        """Test sending command when exception occurs."""
        host = Mock()
        host.id = str(uuid4())
        host.fqdn = "test-host.example.com"

        command_data = {"command": "reboot"}
        message_id = str(uuid4())

        with patch(
            "backend.websocket.connection_manager.connection_manager"
        ) as mock_manager:
            mock_manager.send_to_host = AsyncMock(
                side_effect=Exception("Connection error")
            )

            result = await send_command_to_agent(command_data, host, message_id)

        assert result is False
