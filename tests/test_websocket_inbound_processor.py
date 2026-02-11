"""
Tests for backend/websocket/inbound_processor.py module.
Tests inbound message processing for the WebSocket queue.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock


class TestProcessPendingMessages:
    """Tests for process_pending_messages async function."""

    @pytest.mark.asyncio
    async def test_expires_old_messages(self):
        """Test that old messages are expired."""
        from backend.websocket.inbound_processor import process_pending_messages

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = (
            []
        )

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.expire_old_messages.return_value = 5

            await process_pending_messages(mock_db)

        mock_queue.expire_old_messages.assert_called_once_with(mock_db)

    @pytest.mark.asyncio
    async def test_resets_stuck_messages(self):
        """Test that stuck IN_PROGRESS messages are reset to PENDING."""
        from backend.websocket.inbound_processor import process_pending_messages
        from backend.websocket.queue_manager import QueueStatus

        mock_stuck_message = MagicMock()
        mock_stuck_message.message_id = "stuck-123"

        mock_db = MagicMock()
        # First call returns stuck messages
        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_stuck_message
        ]
        # Second call returns no host IDs
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = (
            []
        )

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.expire_old_messages.return_value = 0

            await process_pending_messages(mock_db)

        # Check message was reset
        assert mock_stuck_message.status == QueueStatus.PENDING
        assert mock_stuck_message.started_at is None
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_deletes_messages_for_nonexistent_host(self):
        """Test that messages for non-existent hosts are deleted."""
        from backend.websocket.inbound_processor import process_pending_messages

        mock_db = MagicMock()
        # No stuck messages
        mock_db.query.return_value.filter.return_value.all.return_value = []
        # One host with pending messages
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = [
            ("host-123",)
        ]
        # Host lookup returns None (not found)
        mock_db.query.return_value.filter.return_value.first.return_value = None
        # No null host messages
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = (
            []
        )

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.expire_old_messages.return_value = 0
            mock_queue.delete_messages_for_host.return_value = 3

            await process_pending_messages(mock_db)

        mock_queue.delete_messages_for_host.assert_called()

    @pytest.mark.asyncio
    async def test_deletes_messages_for_unapproved_host(self):
        """Test that messages for unapproved hosts are deleted."""
        from backend.websocket.inbound_processor import process_pending_messages

        mock_host = MagicMock()
        mock_host.id = "host-123"
        mock_host.fqdn = "test.example.com"
        mock_host.approval_status = "pending"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = [
            ("host-123",)
        ]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.expire_old_messages.return_value = 0
            mock_queue.delete_messages_for_host.return_value = 2

            await process_pending_messages(mock_db)

        mock_queue.delete_messages_for_host.assert_called()

    @pytest.mark.asyncio
    async def test_processes_messages_for_approved_host(self):
        """Test that messages for approved hosts are processed."""
        from backend.websocket.inbound_processor import process_pending_messages

        mock_host = MagicMock()
        mock_host.id = "host-123"
        mock_host.fqdn = "test.example.com"
        mock_host.approval_status = "approved"

        mock_message = MagicMock()
        mock_message.message_id = "msg-456"
        mock_message.message_type = "TEST"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = [
            ("host-123",)
        ]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.expire_old_messages.return_value = 0
            mock_queue.dequeue_messages_for_host.return_value = [mock_message]
            mock_queue.mark_processing.return_value = True
            mock_queue.deserialize_message_data.return_value = {"key": "value"}

            with patch(
                "backend.websocket.inbound_processor.route_inbound_message",
                new=AsyncMock(return_value=True),
            ):
                with patch("backend.websocket.inbound_processor.log_message_data"):
                    await process_pending_messages(mock_db)

            mock_queue.dequeue_messages_for_host.assert_called()
            mock_queue.mark_completed.assert_called()


class TestProcessValidatedMessage:
    """Tests for process_validated_message async function."""

    @pytest.mark.asyncio
    async def test_marks_message_processing(self):
        """Test that message is marked as processing."""
        from backend.websocket.inbound_processor import process_validated_message

        mock_message = MagicMock()
        mock_message.message_id = "msg-123"
        mock_message.message_type = "TEST"

        mock_host = MagicMock()
        mock_host.id = "host-456"
        mock_host.fqdn = "test.example.com"

        mock_db = MagicMock()

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_processing.return_value = True
            mock_queue.deserialize_message_data.return_value = {"data": "test"}

            with patch(
                "backend.websocket.inbound_processor.route_inbound_message",
                new=AsyncMock(return_value=True),
            ):
                with patch("backend.websocket.inbound_processor.log_message_data"):
                    await process_validated_message(mock_message, mock_host, mock_db)

            mock_queue.mark_processing.assert_called_once_with("msg-123", db=mock_db)

    @pytest.mark.asyncio
    async def test_returns_early_if_cannot_mark_processing(self):
        """Test that processing stops if message cannot be marked."""
        from backend.websocket.inbound_processor import process_validated_message

        mock_message = MagicMock()
        mock_message.message_id = "msg-123"
        mock_message.message_type = "TEST"

        mock_host = MagicMock()
        mock_host.id = "host-456"
        mock_host.fqdn = "test.example.com"

        mock_db = MagicMock()

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_processing.return_value = False

            await process_validated_message(mock_message, mock_host, mock_db)

            # Should not call deserialize if marking failed
            mock_queue.deserialize_message_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_marks_completed_on_success(self):
        """Test that message is marked completed on successful routing."""
        from backend.websocket.inbound_processor import process_validated_message

        mock_message = MagicMock()
        mock_message.message_id = "msg-123"
        mock_message.message_type = "TEST"

        mock_host = MagicMock()
        mock_host.id = "host-456"
        mock_host.fqdn = "test.example.com"

        mock_db = MagicMock()

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_processing.return_value = True
            mock_queue.deserialize_message_data.return_value = {"data": "test"}

            with patch(
                "backend.websocket.inbound_processor.route_inbound_message",
                new=AsyncMock(return_value=True),
            ):
                with patch("backend.websocket.inbound_processor.log_message_data"):
                    await process_validated_message(mock_message, mock_host, mock_db)

            mock_queue.mark_completed.assert_called_once_with("msg-123", db=mock_db)

    @pytest.mark.asyncio
    async def test_marks_failed_on_routing_failure(self):
        """Test that message is marked failed when routing fails."""
        from backend.websocket.inbound_processor import process_validated_message

        mock_message = MagicMock()
        mock_message.message_id = "msg-123"
        mock_message.message_type = "UNKNOWN"

        mock_host = MagicMock()
        mock_host.id = "host-456"
        mock_host.fqdn = "test.example.com"

        mock_db = MagicMock()

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_processing.return_value = True
            mock_queue.deserialize_message_data.return_value = {"data": "test"}

            with patch(
                "backend.websocket.inbound_processor.route_inbound_message",
                new=AsyncMock(return_value=False),
            ):
                with patch("backend.websocket.inbound_processor.log_message_data"):
                    await process_validated_message(mock_message, mock_host, mock_db)

            mock_queue.mark_failed.assert_called_once()
            call_args = mock_queue.mark_failed.call_args
            assert call_args[0][0] == "msg-123"
            assert "Unknown message type" in call_args[1]["error_message"]

    @pytest.mark.asyncio
    async def test_handles_exception_during_processing(self):
        """Test that exceptions are caught and message marked failed."""
        from backend.websocket.inbound_processor import process_validated_message

        mock_message = MagicMock()
        mock_message.message_id = "msg-123"
        mock_message.message_type = "TEST"

        mock_host = MagicMock()
        mock_host.id = "host-456"
        mock_host.fqdn = "test.example.com"

        mock_db = MagicMock()

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_processing.return_value = True
            mock_queue.deserialize_message_data.side_effect = Exception(
                "Deserialization error"
            )

            await process_validated_message(mock_message, mock_host, mock_db)

            mock_queue.mark_failed.assert_called_once()
            call_args = mock_queue.mark_failed.call_args
            assert "Deserialization error" in call_args[1]["error_message"]

    @pytest.mark.asyncio
    async def test_creates_mock_connection(self):
        """Test that MockConnection is created with correct host info."""
        from backend.websocket.inbound_processor import process_validated_message

        mock_message = MagicMock()
        mock_message.message_id = "msg-123"
        mock_message.message_type = "TEST"

        mock_host = MagicMock()
        mock_host.id = "host-456"
        mock_host.fqdn = "test.example.com"

        mock_db = MagicMock()

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_processing.return_value = True
            mock_queue.deserialize_message_data.return_value = {"data": "test"}

            with patch(
                "backend.websocket.inbound_processor.route_inbound_message",
                new=AsyncMock(return_value=True),
            ) as mock_route:
                with patch("backend.websocket.inbound_processor.log_message_data"):
                    await process_validated_message(mock_message, mock_host, mock_db)

                # Check route_inbound_message was called with MockConnection
                call_args = mock_route.call_args
                mock_connection = call_args[0][2]
                assert mock_connection.hostname == "test.example.com"


class TestProcessSystemInfoMessage:
    """Tests for process_system_info_message async function."""

    @pytest.mark.asyncio
    async def test_marks_message_processing(self):
        """Test that SYSTEM_INFO message is marked as processing."""
        from backend.websocket.inbound_processor import process_system_info_message

        mock_message = MagicMock()
        mock_message.message_id = "sysinfo-123"

        mock_db = MagicMock()

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_processing.return_value = True
            mock_queue.deserialize_message_data.return_value = {
                "_connection_info": {
                    "agent_id": "agent-1",
                    "hostname": "new-host.example.com",
                    "ipv4": "192.168.1.100",
                    "ipv6": "::1",
                    "platform": "linux",
                }
            }

            with patch(
                "backend.api.message_handlers.handle_system_info",
                new=AsyncMock(return_value={}),
            ):
                await process_system_info_message(mock_message, mock_db)

            mock_queue.mark_processing.assert_called_once_with(
                "sysinfo-123", db=mock_db
            )

    @pytest.mark.asyncio
    async def test_returns_early_if_cannot_mark_processing(self):
        """Test that processing stops if message cannot be marked."""
        from backend.websocket.inbound_processor import process_system_info_message

        mock_message = MagicMock()
        mock_message.message_id = "sysinfo-123"

        mock_db = MagicMock()

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_processing.return_value = False

            await process_system_info_message(mock_message, mock_db)

            mock_queue.deserialize_message_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_mock_connection_with_connection_info(self):
        """Test that MockConnection is created with connection info."""
        from backend.websocket.inbound_processor import process_system_info_message

        mock_message = MagicMock()
        mock_message.message_id = "sysinfo-123"

        mock_db = MagicMock()

        connection_info = {
            "agent_id": "agent-1",
            "hostname": "new-host.example.com",
            "ipv4": "192.168.1.100",
            "ipv6": "2001:db8::1",
            "platform": "linux",
        }

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_processing.return_value = True
            mock_queue.deserialize_message_data.return_value = {
                "_connection_info": connection_info
            }

            with patch(
                "backend.api.message_handlers.handle_system_info",
                new=AsyncMock(return_value={}),
            ) as mock_handler:
                await process_system_info_message(mock_message, mock_db)

                # Check handler was called with MockConnection
                call_args = mock_handler.call_args
                mock_connection = call_args[0][1]
                assert mock_connection.agent_id == "agent-1"
                assert mock_connection.hostname == "new-host.example.com"
                assert mock_connection.ipv4 == "192.168.1.100"
                assert mock_connection.ipv6 == "2001:db8::1"
                assert mock_connection.platform == "linux"

    @pytest.mark.asyncio
    async def test_marks_completed_on_success(self):
        """Test that message is marked completed on success."""
        from backend.websocket.inbound_processor import process_system_info_message

        mock_message = MagicMock()
        mock_message.message_id = "sysinfo-123"

        mock_db = MagicMock()

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_processing.return_value = True
            mock_queue.deserialize_message_data.return_value = {"_connection_info": {}}

            with patch(
                "backend.api.message_handlers.handle_system_info",
                new=AsyncMock(return_value={}),
            ):
                await process_system_info_message(mock_message, mock_db)

            mock_queue.mark_completed.assert_called_once_with("sysinfo-123", db=mock_db)

    @pytest.mark.asyncio
    async def test_handles_exception_during_processing(self):
        """Test that exceptions are caught and message marked failed."""
        from backend.websocket.inbound_processor import process_system_info_message

        mock_message = MagicMock()
        mock_message.message_id = "sysinfo-123"

        mock_db = MagicMock()

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_processing.return_value = True
            mock_queue.deserialize_message_data.return_value = {"_connection_info": {}}

            with patch(
                "backend.api.message_handlers.handle_system_info",
                new=AsyncMock(side_effect=Exception("Handler error")),
            ):
                await process_system_info_message(mock_message, mock_db)

            mock_queue.mark_failed.assert_called_once()
            call_args = mock_queue.mark_failed.call_args
            assert "Handler error" in call_args[1]["error_message"]

    @pytest.mark.asyncio
    async def test_handles_empty_connection_info(self):
        """Test handling of empty connection info dict."""
        from backend.websocket.inbound_processor import process_system_info_message

        mock_message = MagicMock()
        mock_message.message_id = "sysinfo-123"

        mock_db = MagicMock()

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_processing.return_value = True
            mock_queue.deserialize_message_data.return_value = {}

            with patch(
                "backend.api.message_handlers.handle_system_info",
                new=AsyncMock(return_value={}),
            ) as mock_handler:
                await process_system_info_message(mock_message, mock_db)

                # Handler should still be called
                mock_handler.assert_called_once()
                mock_queue.mark_completed.assert_called_once()


class TestNullHostIdMessages:
    """Tests for handling messages with NULL host_id."""

    @pytest.mark.asyncio
    async def test_processes_system_info_without_host_lookup(self):
        """Test that SYSTEM_INFO messages skip host lookup."""
        from backend.websocket.inbound_processor import process_pending_messages
        from backend.websocket.messages import MessageType

        mock_message = MagicMock()
        mock_message.message_id = "sysinfo-456"
        mock_message.message_type = MessageType.SYSTEM_INFO
        mock_message.host_id = None

        mock_db = MagicMock()
        # No stuck messages
        mock_db.query.return_value.filter.return_value.all.return_value = []
        # No host IDs with pending
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = (
            []
        )
        # One null-host message
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            mock_message
        ]

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.expire_old_messages.return_value = 0
            mock_queue.mark_processing.return_value = True
            mock_queue.deserialize_message_data.return_value = {"_connection_info": {}}

            with patch(
                "backend.api.message_handlers.handle_system_info",
                new=AsyncMock(return_value={}),
            ):
                await process_pending_messages(mock_db)

            mock_queue.mark_completed.assert_called()

    @pytest.mark.asyncio
    async def test_marks_failed_when_hostname_and_host_id_missing(self):
        """Test that messages without hostname or host_id are marked failed."""
        from backend.websocket.inbound_processor import process_pending_messages
        from backend.websocket.messages import MessageType

        mock_message = MagicMock()
        mock_message.message_id = "msg-789"
        mock_message.message_type = MessageType.HEARTBEAT
        mock_message.host_id = None

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            mock_message
        ]

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.expire_old_messages.return_value = 0
            mock_queue.deserialize_message_data.return_value = {}

            await process_pending_messages(mock_db)

            mock_queue.mark_failed.assert_called()
            call_args = mock_queue.mark_failed.call_args
            assert "Missing hostname and host_id" in call_args[1].get(
                "error_message", call_args[0][1]
            )

    @pytest.mark.asyncio
    async def test_looks_up_host_by_hostname(self):
        """Test that host is looked up by hostname."""
        from backend.websocket.inbound_processor import process_pending_messages
        from backend.websocket.messages import MessageType

        mock_message = MagicMock()
        mock_message.message_id = "msg-789"
        mock_message.message_type = MessageType.HEARTBEAT
        mock_message.host_id = None

        mock_host = MagicMock()
        mock_host.id = "found-host-123"
        mock_host.fqdn = "found.example.com"
        mock_host.approval_status = "approved"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            mock_message
        ]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.expire_old_messages.return_value = 0
            mock_queue.deserialize_message_data.return_value = {
                "hostname": "found.example.com"
            }
            mock_queue.mark_processing.return_value = True

            with patch(
                "backend.websocket.inbound_processor.route_inbound_message",
                new=AsyncMock(return_value=True),
            ):
                with patch("backend.websocket.inbound_processor.log_message_data"):
                    await process_pending_messages(mock_db)

            mock_queue.mark_completed.assert_called()

    @pytest.mark.asyncio
    async def test_marks_failed_for_unapproved_host_null_host_id(self):
        """Test that unapproved host messages are marked failed."""
        from backend.websocket.inbound_processor import process_pending_messages
        from backend.websocket.messages import MessageType

        mock_message = MagicMock()
        mock_message.message_id = "msg-789"
        mock_message.message_type = MessageType.HEARTBEAT
        mock_message.host_id = None

        mock_host = MagicMock()
        mock_host.id = "unapproved-host"
        mock_host.fqdn = "pending.example.com"
        mock_host.approval_status = "pending"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            mock_message
        ]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.expire_old_messages.return_value = 0
            mock_queue.deserialize_message_data.return_value = {
                "hostname": "pending.example.com"
            }

            await process_pending_messages(mock_db)

            mock_queue.mark_failed.assert_called()
            call_args = mock_queue.mark_failed.call_args
            assert "not approved" in str(call_args)

    @pytest.mark.asyncio
    async def test_handles_exception_in_null_host_processing(self):
        """Test exception handling in null host_id processing."""
        from backend.websocket.inbound_processor import process_pending_messages
        from backend.websocket.messages import MessageType

        mock_message = MagicMock()
        mock_message.message_id = "msg-error"
        mock_message.message_type = MessageType.HEARTBEAT
        mock_message.host_id = None

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            mock_message
        ]

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.expire_old_messages.return_value = 0
            mock_queue.deserialize_message_data.side_effect = Exception("Parse error")

            await process_pending_messages(mock_db)

            mock_queue.mark_failed.assert_called()
            call_args = mock_queue.mark_failed.call_args
            assert "Processing error" in str(call_args)

    @pytest.mark.asyncio
    async def test_extracts_hostname_from_connection_info(self):
        """Test hostname extraction from _connection_info."""
        from backend.websocket.inbound_processor import process_pending_messages
        from backend.websocket.messages import MessageType

        mock_message = MagicMock()
        mock_message.message_id = "msg-conn"
        mock_message.message_type = MessageType.HEARTBEAT
        mock_message.host_id = None

        mock_host = MagicMock()
        mock_host.id = "host-conn"
        mock_host.fqdn = "conn.example.com"
        mock_host.approval_status = "approved"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            mock_message
        ]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.expire_old_messages.return_value = 0
            mock_queue.deserialize_message_data.return_value = {
                "_connection_info": {"hostname": "conn.example.com"}
            }
            mock_queue.mark_processing.return_value = True

            with patch(
                "backend.websocket.inbound_processor.route_inbound_message",
                new=AsyncMock(return_value=True),
            ):
                with patch("backend.websocket.inbound_processor.log_message_data"):
                    await process_pending_messages(mock_db)

            mock_queue.mark_completed.assert_called()

    @pytest.mark.asyncio
    async def test_looks_up_host_by_host_id_first(self):
        """Test that host_id lookup takes priority over hostname."""
        from backend.websocket.inbound_processor import process_pending_messages
        from backend.websocket.messages import MessageType

        mock_message = MagicMock()
        mock_message.message_id = "msg-id-lookup"
        mock_message.message_type = MessageType.HEARTBEAT
        mock_message.host_id = None

        mock_host = MagicMock()
        mock_host.id = "host-by-id"
        mock_host.fqdn = "byid.example.com"
        mock_host.approval_status = "approved"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            mock_message
        ]
        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_queue:
            mock_queue.expire_old_messages.return_value = 0
            mock_queue.deserialize_message_data.return_value = {
                "host_id": "host-by-id",
                "hostname": "wrong.example.com",
            }
            mock_queue.mark_processing.return_value = True

            with patch(
                "backend.websocket.inbound_processor.route_inbound_message",
                new=AsyncMock(return_value=True),
            ):
                with patch("backend.websocket.inbound_processor.log_message_data"):
                    await process_pending_messages(mock_db)

            # Message should be processed
            mock_queue.mark_completed.assert_called()
