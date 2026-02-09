"""
Comprehensive unit tests for WebSocket message routing.
Tests message routing to appropriate handlers based on message type.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.websocket.message_router import route_inbound_message, log_message_data
from backend.websocket.messages import MessageType


class TestRouteInboundMessage:
    """Test route_inbound_message function."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return Mock()

    @pytest.fixture
    def mock_connection(self):
        """Create mock connection object."""
        connection = Mock()
        connection.host_id = "test-host-id"
        connection.hostname = "test-host.example.com"
        return connection

    @pytest.mark.asyncio
    async def test_route_os_version_update(self, mock_db, mock_connection):
        """Test routing OS_VERSION_UPDATE message."""
        message_data = {
            "hostname": "test-host.example.com",
            "os_name": "Ubuntu",
            "os_version": "22.04",
        }

        with patch(
            "backend.websocket.message_router.handle_os_version_update"
        ) as mock_handler:
            mock_handler.return_value = None

            result = await route_inbound_message(
                MessageType.OS_VERSION_UPDATE, mock_db, mock_connection, message_data
            )

            assert result is True
            mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_hardware_update(self, mock_db, mock_connection):
        """Test routing HARDWARE_UPDATE message."""
        message_data = {
            "hostname": "test-host.example.com",
            "cpu_vendor": "Intel",
            "cpu_model": "Core i7",
            "memory_total_mb": 16384,
        }

        with patch(
            "backend.websocket.message_router.handle_hardware_update"
        ) as mock_handler:
            mock_handler.return_value = None

            result = await route_inbound_message(
                MessageType.HARDWARE_UPDATE, mock_db, mock_connection, message_data
            )

            assert result is True
            mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_user_access_update(self, mock_db, mock_connection):
        """Test routing USER_ACCESS_UPDATE message."""
        message_data = {
            "hostname": "test-host.example.com",
            "users": [{"username": "testuser"}],
            "groups": [{"group_name": "testgroup"}],
        }

        with patch(
            "backend.websocket.message_router.handle_user_access_update"
        ) as mock_handler:
            mock_handler.return_value = None

            result = await route_inbound_message(
                MessageType.USER_ACCESS_UPDATE, mock_db, mock_connection, message_data
            )

            assert result is True
            mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_software_inventory_update(self, mock_db, mock_connection):
        """Test routing SOFTWARE_INVENTORY_UPDATE message."""
        message_data = {
            "hostname": "test-host.example.com",
            "software_packages": [{"package_name": "vim", "version": "8.2"}],
        }

        with patch(
            "backend.websocket.message_router.handle_software_update"
        ) as mock_handler:
            mock_handler.return_value = None

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
        """Test routing PACKAGE_UPDATES_UPDATE message."""
        message_data = {
            "hostname": "test-host.example.com",
            "updates": [{"package": "vim", "new_version": "8.3"}],
        }

        with patch(
            "backend.websocket.message_router.handle_package_updates_update"
        ) as mock_handler:
            mock_handler.return_value = None

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
        """Test routing AVAILABLE_PACKAGES_BATCH_START message."""
        message_data = {
            "hostname": "test-host.example.com",
            "batch_id": "batch-123",
            "total_packages": 100,
        }

        with patch(
            "backend.websocket.message_router.handle_packages_batch_start"
        ) as mock_handler:
            mock_handler.return_value = None

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
        """Test routing AVAILABLE_PACKAGES_BATCH message."""
        message_data = {
            "hostname": "test-host.example.com",
            "batch_id": "batch-123",
            "packages": [{"name": "vim"}],
        }

        with patch(
            "backend.websocket.message_router.handle_packages_batch"
        ) as mock_handler:
            mock_handler.return_value = None

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
        """Test routing AVAILABLE_PACKAGES_BATCH_END message."""
        message_data = {
            "hostname": "test-host.example.com",
            "batch_id": "batch-123",
        }

        with patch(
            "backend.websocket.message_router.handle_packages_batch_end"
        ) as mock_handler:
            mock_handler.return_value = None

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
        """Test routing SCRIPT_EXECUTION_RESULT message."""
        message_data = {
            "hostname": "test-host.example.com",
            "execution_id": "exec-123",
            "exit_code": 0,
            "output": "Script completed",
        }

        with patch(
            "backend.websocket.message_router.handle_script_execution_result"
        ) as mock_handler:
            mock_handler.return_value = None

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
        """Test routing REBOOT_STATUS_UPDATE message."""
        message_data = {
            "hostname": "test-host.example.com",
            "reboot_required": True,
        }

        with patch(
            "backend.websocket.message_router.handle_reboot_status_update"
        ) as mock_handler:
            mock_handler.return_value = None

            result = await route_inbound_message(
                MessageType.REBOOT_STATUS_UPDATE, mock_db, mock_connection, message_data
            )

            assert result is True
            mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_command_result(self, mock_db, mock_connection):
        """Test routing COMMAND_RESULT message."""
        message_data = {
            "command_id": "cmd-123",
            "success": True,
            "result": {"stdout": "output"},
        }

        with patch(
            "backend.websocket.message_router.handle_command_result"
        ) as mock_handler:
            mock_handler.return_value = None

            result = await route_inbound_message(
                MessageType.COMMAND_RESULT, mock_db, mock_connection, message_data
            )

            assert result is True
            mock_handler.assert_called_once_with(mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_command_acknowledgment(self, mock_db, mock_connection):
        """Test routing COMMAND_ACKNOWLEDGMENT message."""
        message_data = {
            "command_id": "cmd-123",
            "acknowledged": True,
        }

        with patch(
            "backend.websocket.message_router.handle_command_acknowledgment"
        ) as mock_handler:
            mock_handler.return_value = None

            result = await route_inbound_message(
                MessageType.COMMAND_ACKNOWLEDGMENT,
                mock_db,
                mock_connection,
                message_data,
            )

            assert result is True
            mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_update_apply_result(self, mock_db, mock_connection):
        """Test routing UPDATE_APPLY_RESULT message."""
        message_data = {
            "update_id": "update-123",
            "success": True,
        }

        with patch(
            "backend.websocket.message_router.handle_update_apply_result"
        ) as mock_handler:
            mock_handler.return_value = None

            result = await route_inbound_message(
                MessageType.UPDATE_APPLY_RESULT, mock_db, mock_connection, message_data
            )

            assert result is True
            mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_firewall_status_update(self, mock_db, mock_connection):
        """Test routing FIREWALL_STATUS_UPDATE message."""
        message_data = {
            "hostname": "test-host.example.com",
            "firewall_enabled": True,
        }

        with patch(
            "backend.websocket.message_router.handle_firewall_status_update"
        ) as mock_handler:
            mock_handler.return_value = None

            result = await route_inbound_message(
                MessageType.FIREWALL_STATUS_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

            assert result is True
            mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_antivirus_status_update(self, mock_db, mock_connection):
        """Test routing ANTIVIRUS_STATUS_UPDATE message."""
        message_data = {
            "hostname": "test-host.example.com",
            "antivirus_installed": True,
        }

        with patch(
            "backend.websocket.message_router.handle_antivirus_status_update"
        ) as mock_handler:
            mock_handler.return_value = None

            result = await route_inbound_message(
                MessageType.ANTIVIRUS_STATUS_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

            assert result is True
            mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_hostname_changed(self, mock_db, mock_connection):
        """Test routing HOSTNAME_CHANGED message."""
        message_data = {
            "old_hostname": "old-host.example.com",
            "new_hostname": "new-host.example.com",
        }

        with patch(
            "backend.websocket.message_router.handle_hostname_changed"
        ) as mock_handler:
            mock_handler.return_value = None

            result = await route_inbound_message(
                MessageType.HOSTNAME_CHANGED, mock_db, mock_connection, message_data
            )

            assert result is True
            mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_virtualization_support_update(self, mock_db, mock_connection):
        """Test routing VIRTUALIZATION_SUPPORT_UPDATE message."""
        message_data = {
            "hostname": "test-host.example.com",
            "virtualization_enabled": True,
        }

        with patch(
            "backend.websocket.message_router.handle_virtualization_support_update"
        ) as mock_handler:
            mock_handler.return_value = None

            result = await route_inbound_message(
                MessageType.VIRTUALIZATION_SUPPORT_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

            assert result is True
            mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_child_host_list_update(self, mock_db, mock_connection):
        """Test routing CHILD_HOST_LIST_UPDATE message."""
        message_data = {
            "hostname": "test-host.example.com",
            "child_hosts": [{"name": "vm1"}],
        }

        with patch(
            "backend.websocket.message_router.handle_child_hosts_list_update"
        ) as mock_handler:
            mock_handler.return_value = None

            result = await route_inbound_message(
                MessageType.CHILD_HOST_LIST_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

            assert result is True
            mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_route_unknown_message_type(self, mock_db, mock_connection):
        """Test routing unknown message type returns False."""
        message_data = {"data": "test"}

        result = await route_inbound_message(
            "unknown_message_type", mock_db, mock_connection, message_data
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_route_handler_exception(self, mock_db, mock_connection):
        """Test routing handles handler exceptions gracefully."""
        message_data = {
            "hostname": "test-host.example.com",
        }

        with patch(
            "backend.websocket.message_router.handle_os_version_update"
        ) as mock_handler:
            mock_handler.side_effect = Exception("Handler error")

            result = await route_inbound_message(
                MessageType.OS_VERSION_UPDATE, mock_db, mock_connection, message_data
            )

            assert result is False


class TestLogMessageData:
    """Test log_message_data function."""

    def test_log_hardware_update_data(self):
        """Test logging hardware update message data."""
        message_data = {
            "cpu_vendor": "Intel",
            "cpu_model": "Core i7",
            "memory_total_mb": 16384,
            "storage_devices": [{"name": "sda"}, {"name": "sdb"}],
        }

        # Should not raise
        log_message_data(MessageType.HARDWARE_UPDATE, message_data)

    def test_log_software_inventory_update_data(self):
        """Test logging software inventory update message data."""
        message_data = {
            "total_packages": 250,
            "software_packages": [{"package_name": "vim"}, {"package_name": "git"}],
        }

        # Should not raise
        log_message_data(MessageType.SOFTWARE_INVENTORY_UPDATE, message_data)

    def test_log_software_inventory_empty_packages(self):
        """Test logging software inventory with empty packages list."""
        message_data = {
            "total_packages": 0,
            "software_packages": [],
        }

        # Should not raise
        log_message_data(MessageType.SOFTWARE_INVENTORY_UPDATE, message_data)

    def test_log_user_access_update_data(self):
        """Test logging user access update message data."""
        message_data = {
            "total_users": 10,
            "total_groups": 5,
        }

        # Should not raise
        log_message_data(MessageType.USER_ACCESS_UPDATE, message_data)

    def test_log_other_message_type(self):
        """Test logging other message types (no special logging)."""
        message_data = {
            "some_field": "some_value",
        }

        # Should not raise
        log_message_data(MessageType.HEARTBEAT, message_data)

    def test_log_missing_fields(self):
        """Test logging with missing expected fields."""
        message_data = {}

        # Should not raise even with missing fields
        log_message_data(MessageType.HARDWARE_UPDATE, message_data)
        log_message_data(MessageType.SOFTWARE_INVENTORY_UPDATE, message_data)
        log_message_data(MessageType.USER_ACCESS_UPDATE, message_data)
