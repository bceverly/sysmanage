"""
Comprehensive unit tests for WebSocket inbound message processor.
Tests processing of messages received from agents.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch, MagicMock

import pytest

from backend.websocket.inbound_processor import (
    process_validated_message,
)
from backend.websocket.queue_manager import QueueDirection, QueueStatus


class TestProcessValidatedMessage:
    """Test process_validated_message function."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return Mock()

    @pytest.fixture
    def mock_host(self):
        """Create mock host object."""
        host = Mock()
        host.id = "host-123"
        host.fqdn = "test-host.example.com"
        host.approval_status = "approved"
        return host

    @pytest.fixture
    def mock_message(self):
        """Create mock message object."""
        message = Mock()
        message.message_id = "msg-123"
        message.message_type = "heartbeat"
        message.host_id = "host-123"
        return message

    @pytest.mark.asyncio
    async def test_process_validated_message_success(
        self, mock_db, mock_host, mock_message
    ):
        """Test successful message processing."""
        message_data = {"hostname": "test-host.example.com", "status": "healthy"}

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_qm, patch(
            "backend.websocket.inbound_processor.route_inbound_message"
        ) as mock_route, patch(
            "backend.websocket.inbound_processor.log_message_data"
        ):
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.return_value = message_data
            mock_route.return_value = True

            await process_validated_message(mock_message, mock_host, mock_db)

            mock_qm.mark_processing.assert_called_once_with("msg-123", db=mock_db)
            mock_qm.mark_completed.assert_called_once_with("msg-123", db=mock_db)

    @pytest.mark.asyncio
    async def test_process_validated_message_routing_fails(
        self, mock_db, mock_host, mock_message
    ):
        """Test message processing when routing fails."""
        message_data = {"hostname": "test-host.example.com"}

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_qm, patch(
            "backend.websocket.inbound_processor.route_inbound_message"
        ) as mock_route, patch(
            "backend.websocket.inbound_processor.log_message_data"
        ):
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.return_value = message_data
            mock_route.return_value = False  # Routing fails

            await process_validated_message(mock_message, mock_host, mock_db)

            mock_qm.mark_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_validated_message_cannot_mark_processing(
        self, mock_db, mock_host, mock_message
    ):
        """Test handling when message cannot be marked as processing."""
        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_qm:
            mock_qm.mark_processing.return_value = False  # Cannot mark

            await process_validated_message(mock_message, mock_host, mock_db)

            # Should not attempt to deserialize or route
            mock_qm.deserialize_message_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_validated_message_exception(
        self, mock_db, mock_host, mock_message
    ):
        """Test handling of exceptions during processing."""
        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_qm, patch(
            "backend.websocket.inbound_processor.route_inbound_message"
        ) as mock_route, patch(
            "backend.websocket.inbound_processor.log_message_data"
        ):
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.return_value = {}
            mock_route.side_effect = Exception("Processing error")

            await process_validated_message(mock_message, mock_host, mock_db)

            mock_qm.mark_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_validated_message_hardware_update(self, mock_db, mock_host):
        """Test processing hardware update message."""
        mock_message = Mock()
        mock_message.message_id = "msg-hw-123"
        mock_message.message_type = "hardware_update"
        mock_message.host_id = "host-123"

        message_data = {
            "hostname": "test-host.example.com",
            "cpu_vendor": "Intel",
            "cpu_model": "Core i7",
            "memory_total_mb": 16384,
            "storage_devices": [{"name": "sda", "size": 1000000}],
        }

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_qm, patch(
            "backend.websocket.inbound_processor.route_inbound_message"
        ) as mock_route, patch(
            "backend.websocket.inbound_processor.log_message_data"
        ) as mock_log:
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.return_value = message_data
            mock_route.return_value = True

            await process_validated_message(mock_message, mock_host, mock_db)

            # Verify log_message_data was called for hardware update
            mock_log.assert_called_once_with("hardware_update", message_data)
            mock_qm.mark_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_validated_message_creates_mock_connection(
        self, mock_db, mock_host, mock_message
    ):
        """Test that processing creates proper mock connection with host info."""
        message_data = {"hostname": "test-host.example.com"}

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_qm, patch(
            "backend.websocket.inbound_processor.route_inbound_message"
        ) as mock_route, patch(
            "backend.websocket.inbound_processor.log_message_data"
        ), patch(
            "backend.websocket.inbound_processor.MockConnection"
        ) as mock_conn_class:
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.return_value = message_data
            mock_route.return_value = True

            mock_conn = Mock()
            mock_conn_class.return_value = mock_conn

            await process_validated_message(mock_message, mock_host, mock_db)

            # Verify MockConnection was created with host_id
            mock_conn_class.assert_called_once_with(mock_host.id)
            # Verify hostname was set
            assert mock_conn.hostname == mock_host.fqdn


class TestProcessValidatedMessageIntegration:
    """Integration tests for process_validated_message."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return Mock()

    @pytest.fixture
    def mock_host(self):
        """Create mock host object."""
        host = Mock()
        host.id = "host-123"
        host.fqdn = "test-host.example.com"
        host.approval_status = "approved"
        return host

    @pytest.mark.asyncio
    async def test_full_message_flow(self, mock_db, mock_host):
        """Test complete message processing flow."""
        mock_message = Mock()
        mock_message.message_id = "msg-123"
        mock_message.message_type = "software_inventory_update"
        mock_message.host_id = "host-123"

        message_data = {
            "hostname": "test-host.example.com",
            "total_packages": 250,
            "software_packages": [{"package_name": "vim"}, {"package_name": "git"}],
        }

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_qm, patch(
            "backend.websocket.inbound_processor.route_inbound_message"
        ) as mock_route, patch(
            "backend.websocket.inbound_processor.log_message_data"
        ):
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.return_value = message_data
            mock_route.return_value = True

            await process_validated_message(mock_message, mock_host, mock_db)

            # Verify complete flow
            mock_qm.mark_processing.assert_called_once()
            mock_qm.deserialize_message_data.assert_called_once()
            mock_route.assert_called_once()
            mock_qm.mark_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_with_large_data(self, mock_db, mock_host):
        """Test processing message with large data payload."""
        mock_message = Mock()
        mock_message.message_id = "msg-large-123"
        mock_message.message_type = "software_inventory_update"
        mock_message.host_id = "host-123"

        # Create large message data
        message_data = {
            "hostname": "test-host.example.com",
            "total_packages": 5000,
            "software_packages": [
                {"package_name": f"package-{i}", "version": f"1.0.{i}"}
                for i in range(100)
            ],
        }

        with patch(
            "backend.websocket.inbound_processor.server_queue_manager"
        ) as mock_qm, patch(
            "backend.websocket.inbound_processor.route_inbound_message"
        ) as mock_route, patch(
            "backend.websocket.inbound_processor.log_message_data"
        ):
            mock_qm.mark_processing.return_value = True
            mock_qm.deserialize_message_data.return_value = message_data
            mock_route.return_value = True

            await process_validated_message(mock_message, mock_host, mock_db)

            mock_qm.mark_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_various_message_types(self, mock_db, mock_host):
        """Test processing various message types."""
        message_types = [
            "heartbeat",
            "hardware_update",
            "software_inventory_update",
            "user_access_update",
            "os_version_update",
            "package_updates_update",
            "firewall_status_update",
        ]

        for msg_type in message_types:
            mock_message = Mock()
            mock_message.message_id = f"msg-{msg_type}"
            mock_message.message_type = msg_type
            mock_message.host_id = "host-123"

            with patch(
                "backend.websocket.inbound_processor.server_queue_manager"
            ) as mock_qm, patch(
                "backend.websocket.inbound_processor.route_inbound_message"
            ) as mock_route, patch(
                "backend.websocket.inbound_processor.log_message_data"
            ):
                mock_qm.mark_processing.return_value = True
                mock_qm.deserialize_message_data.return_value = {"hostname": "test"}
                mock_route.return_value = True

                await process_validated_message(mock_message, mock_host, mock_db)

                # Each message type should be processed successfully
                mock_qm.mark_completed.assert_called()


class TestInboundProcessorModuleImports:
    """Test module-level functionality and imports."""

    def test_process_validated_message_is_async(self):
        """Test that process_validated_message is an async function."""
        import asyncio

        assert asyncio.iscoroutinefunction(process_validated_message)

    def test_queue_status_values(self):
        """Test QueueStatus enum values are accessible."""
        assert hasattr(QueueStatus, "PENDING")
        assert hasattr(QueueStatus, "IN_PROGRESS")
        assert hasattr(QueueStatus, "COMPLETED")
        assert hasattr(QueueStatus, "FAILED")

    def test_queue_direction_values(self):
        """Test QueueDirection enum values are accessible."""
        assert hasattr(QueueDirection, "INBOUND")
        assert hasattr(QueueDirection, "OUTBOUND")
