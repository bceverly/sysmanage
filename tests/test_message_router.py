"""
Comprehensive unit tests for backend.websocket.message_router module.
Tests route_inbound_message and log_message_data functions.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.websocket.message_router import log_message_data, route_inbound_message
from backend.websocket.messages import MessageType


class TestRouteInboundMessage:
    """Test cases for route_inbound_message function."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return Mock()

    @pytest.fixture
    def mock_connection(self):
        """Create a mock connection."""
        connection = Mock()
        connection.host_id = "test-host-id"
        connection.hostname = "test-host"
        return connection

    @pytest.mark.asyncio
    async def test_route_os_version_update(self, mock_db, mock_connection):
        """Test routing OS version update message."""
        message_data = {"os_name": "Ubuntu", "os_version": "22.04"}

        with patch(
            "backend.websocket.message_router.handle_os_version_update",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.OS_VERSION_UPDATE, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_hardware_update(self, mock_db, mock_connection):
        """Test routing hardware update message."""
        message_data = {"cpu_vendor": "Intel", "cpu_model": "i7"}

        with patch(
            "backend.websocket.message_router.handle_hardware_update",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.HARDWARE_UPDATE, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_user_access_update(self, mock_db, mock_connection):
        """Test routing user access update message."""
        message_data = {"users": [], "groups": []}

        with patch(
            "backend.websocket.message_router.handle_user_access_update",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.USER_ACCESS_UPDATE, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_software_inventory_update(self, mock_db, mock_connection):
        """Test routing software inventory update message."""
        message_data = {"software_packages": []}

        with patch(
            "backend.websocket.message_router.handle_software_update",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.SOFTWARE_INVENTORY_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_package_updates_update(self, mock_db, mock_connection):
        """Test routing package updates update message."""
        message_data = {"available_updates": []}

        with patch(
            "backend.websocket.message_router.handle_package_updates_update",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.PACKAGE_UPDATES_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_packages_batch_start(self, mock_db, mock_connection):
        """Test routing packages batch start message."""
        message_data = {"os_name": "Ubuntu", "os_version": "22.04"}

        with patch(
            "backend.websocket.message_router.handle_packages_batch_start",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.AVAILABLE_PACKAGES_BATCH_START,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_packages_batch(self, mock_db, mock_connection):
        """Test routing packages batch message."""
        message_data = {"packages": [], "batch_number": 1}

        with patch(
            "backend.websocket.message_router.handle_packages_batch",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.AVAILABLE_PACKAGES_BATCH,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_packages_batch_end(self, mock_db, mock_connection):
        """Test routing packages batch end message."""
        message_data = {"total_batches": 5}

        with patch(
            "backend.websocket.message_router.handle_packages_batch_end",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.AVAILABLE_PACKAGES_BATCH_END,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_script_execution_result(self, mock_db, mock_connection):
        """Test routing script execution result message."""
        message_data = {"script_id": "123", "exit_code": 0}

        with patch(
            "backend.websocket.message_router.handle_script_execution_result",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.SCRIPT_EXECUTION_RESULT,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_reboot_status_update(self, mock_db, mock_connection):
        """Test routing reboot status update message."""
        message_data = {"status": "completed"}

        with patch(
            "backend.websocket.message_router.handle_reboot_status_update",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.REBOOT_STATUS_UPDATE, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_host_certificates_update(self, mock_db, mock_connection):
        """Test routing host certificates update message."""
        message_data = {"certificates": []}

        with patch(
            "backend.websocket.message_router.handle_host_certificates_update",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.HOST_CERTIFICATES_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_role_data(self, mock_db, mock_connection):
        """Test routing role data message."""
        message_data = {"roles": []}

        with patch(
            "backend.websocket.message_router.handle_host_role_data_update",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.ROLE_DATA, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_third_party_repository_update(self, mock_db, mock_connection):
        """Test routing third-party repository update message."""
        message_data = {"repositories": []}

        with patch(
            "backend.websocket.message_router.handle_third_party_repository_update",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.THIRD_PARTY_REPOSITORY_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_antivirus_status_update(self, mock_db, mock_connection):
        """Test routing antivirus status update message."""
        message_data = {"software_name": "Windows Defender"}

        with patch(
            "backend.websocket.message_router.handle_antivirus_status_update",
            new_callable=AsyncMock,
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.ANTIVIRUS_STATUS_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_unknown_message_type(self, mock_db, mock_connection):
        """Test routing unknown message type."""
        message_data = {}

        with patch("backend.websocket.message_router.logger") as mock_logger:
            result = await route_inbound_message(
                "unknown_message_type", mock_db, mock_connection, message_data
            )

        assert result is False
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_message_handler_exception(self, mock_db, mock_connection):
        """Test routing when handler raises exception."""
        message_data = {}

        with patch(
            "backend.websocket.message_router.handle_hardware_update",
            new_callable=AsyncMock,
            side_effect=Exception("Handler error"),
        ), patch("backend.websocket.message_router.logger") as mock_logger:
            result = await route_inbound_message(
                MessageType.HARDWARE_UPDATE, mock_db, mock_connection, message_data
            )

        assert result is False
        mock_logger.error.assert_called_once()


class TestLogMessageData:
    """Test cases for log_message_data function."""

    def test_log_hardware_update(self):
        """Test logging hardware update message data."""
        message_data = {
            "cpu_vendor": "Intel",
            "cpu_model": "Core i7-9700K",
            "memory_total_mb": 16384,
            "storage_devices": [{"name": "sda", "size": "500GB"}],
        }

        with patch("backend.websocket.message_router.logger") as mock_logger:
            log_message_data(MessageType.HARDWARE_UPDATE, message_data)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0]
        assert "Intel" in str(call_args)
        assert "Core i7-9700K" in str(call_args)
        assert "16384" in str(call_args)

    def test_log_hardware_update_missing_fields(self):
        """Test logging hardware update with missing fields."""
        message_data = {}

        with patch("backend.websocket.message_router.logger") as mock_logger:
            log_message_data(MessageType.HARDWARE_UPDATE, message_data)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0]
        assert "N/A" in str(call_args)

    def test_log_software_inventory_update(self):
        """Test logging software inventory update message data."""
        message_data = {
            "total_packages": 500,
            "software_packages": [
                {"package_name": "nginx", "version": "1.18.0"},
                {"package_name": "python3", "version": "3.10.0"},
            ],
        }

        with patch("backend.websocket.message_router.logger") as mock_logger:
            log_message_data(MessageType.SOFTWARE_INVENTORY_UPDATE, message_data)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0]
        assert "500" in str(call_args)

    def test_log_software_inventory_update_empty_packages(self):
        """Test logging software inventory with empty packages."""
        message_data = {"total_packages": 0, "software_packages": []}

        with patch("backend.websocket.message_router.logger") as mock_logger:
            log_message_data(MessageType.SOFTWARE_INVENTORY_UPDATE, message_data)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0]
        assert "None" in str(call_args)

    def test_log_user_access_update(self):
        """Test logging user access update message data."""
        message_data = {"total_users": 25, "total_groups": 10}

        with patch("backend.websocket.message_router.logger") as mock_logger:
            log_message_data(MessageType.USER_ACCESS_UPDATE, message_data)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0]
        assert "25" in str(call_args)
        assert "10" in str(call_args)

    def test_log_user_access_update_missing_fields(self):
        """Test logging user access update with missing fields."""
        message_data = {}

        with patch("backend.websocket.message_router.logger") as mock_logger:
            log_message_data(MessageType.USER_ACCESS_UPDATE, message_data)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0]
        assert "0" in str(call_args)

    def test_log_other_message_types(self):
        """Test logging other message types (no specific logging)."""
        message_data = {"some_field": "some_value"}

        with patch("backend.websocket.message_router.logger") as mock_logger:
            log_message_data(MessageType.OS_VERSION_UPDATE, message_data)

        # Should not call logger for message types without specific logging
        mock_logger.info.assert_not_called()
