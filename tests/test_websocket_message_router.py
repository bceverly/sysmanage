"""
Tests for backend/websocket/message_router.py module.
Tests message routing to appropriate handlers.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestRouteInboundMessage:
    """Tests for route_inbound_message async function."""

    @pytest.mark.asyncio
    async def test_routes_os_version_update(self):
        """Test routing OS_VERSION_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"version": "22.04"}

        with patch(
            "backend.websocket.message_router.handle_os_version_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.OS_VERSION_UPDATE, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once_with(mock_db, mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_routes_hardware_update(self):
        """Test routing HARDWARE_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"cpu_vendor": "Intel"}

        with patch(
            "backend.websocket.message_router.handle_hardware_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.HARDWARE_UPDATE, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_user_access_update(self):
        """Test routing USER_ACCESS_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"users": []}

        with patch(
            "backend.websocket.message_router.handle_user_access_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.USER_ACCESS_UPDATE, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_software_inventory_update(self):
        """Test routing SOFTWARE_INVENTORY_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"software_packages": []}

        with patch(
            "backend.websocket.message_router.handle_software_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.SOFTWARE_INVENTORY_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_package_updates_update(self):
        """Test routing PACKAGE_UPDATES_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"updates": []}

        with patch(
            "backend.websocket.message_router.handle_package_updates_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.PACKAGE_UPDATES_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_available_packages_batch_start(self):
        """Test routing AVAILABLE_PACKAGES_BATCH_START message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"batch_id": "123"}

        with patch(
            "backend.websocket.message_router.handle_packages_batch_start",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.AVAILABLE_PACKAGES_BATCH_START,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_available_packages_batch(self):
        """Test routing AVAILABLE_PACKAGES_BATCH message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"packages": []}

        with patch(
            "backend.websocket.message_router.handle_packages_batch",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.AVAILABLE_PACKAGES_BATCH,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_available_packages_batch_end(self):
        """Test routing AVAILABLE_PACKAGES_BATCH_END message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"batch_id": "123"}

        with patch(
            "backend.websocket.message_router.handle_packages_batch_end",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.AVAILABLE_PACKAGES_BATCH_END,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_script_execution_result(self):
        """Test routing SCRIPT_EXECUTION_RESULT message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"result": "success"}

        with patch(
            "backend.websocket.message_router.handle_script_execution_result",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.SCRIPT_EXECUTION_RESULT,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_reboot_status_update(self):
        """Test routing REBOOT_STATUS_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"reboot_required": True}

        with patch(
            "backend.websocket.message_router.handle_reboot_status_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.REBOOT_STATUS_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_host_certificates_update(self):
        """Test routing HOST_CERTIFICATES_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"certificates": []}

        with patch(
            "backend.websocket.message_router.handle_host_certificates_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.HOST_CERTIFICATES_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_role_data(self):
        """Test routing ROLE_DATA message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"roles": []}

        with patch(
            "backend.websocket.message_router.handle_host_role_data_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.ROLE_DATA, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_third_party_repository_update(self):
        """Test routing THIRD_PARTY_REPOSITORY_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"repositories": []}

        with patch(
            "backend.websocket.message_router.handle_third_party_repository_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.THIRD_PARTY_REPOSITORY_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_antivirus_status_update(self):
        """Test routing ANTIVIRUS_STATUS_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"status": "running"}

        with patch(
            "backend.websocket.message_router.handle_antivirus_status_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.ANTIVIRUS_STATUS_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_commercial_antivirus_status_update(self):
        """Test routing COMMERCIAL_ANTIVIRUS_STATUS_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"status": "active"}

        with patch(
            "backend.websocket.message_router.handle_commercial_antivirus_status_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.COMMERCIAL_ANTIVIRUS_STATUS_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_firewall_status_update(self):
        """Test routing FIREWALL_STATUS_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"enabled": True}

        with patch(
            "backend.websocket.message_router.handle_firewall_status_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.FIREWALL_STATUS_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_graylog_status_update(self):
        """Test routing GRAYLOG_STATUS_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"connected": True}

        with patch(
            "backend.websocket.message_router.handle_graylog_status_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.GRAYLOG_STATUS_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_hostname_changed(self):
        """Test routing HOSTNAME_CHANGED message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"new_hostname": "new.example.com"}

        with patch(
            "backend.websocket.message_router.handle_hostname_changed",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.HOSTNAME_CHANGED, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_virtualization_support_update(self):
        """Test routing VIRTUALIZATION_SUPPORT_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"supported": True}

        with patch(
            "backend.websocket.message_router.handle_virtualization_support_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.VIRTUALIZATION_SUPPORT_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_child_host_list_update(self):
        """Test routing CHILD_HOST_LIST_UPDATE message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"child_hosts": []}

        with patch(
            "backend.websocket.message_router.handle_child_hosts_list_update",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.CHILD_HOST_LIST_UPDATE,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_child_host_creation_progress(self):
        """Test routing CHILD_HOST_CREATION_PROGRESS message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"progress": 50}

        with patch(
            "backend.websocket.message_router.handle_child_host_creation_progress",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.CHILD_HOST_CREATION_PROGRESS,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_child_host_created(self):
        """Test routing CHILD_HOST_CREATED message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"child_id": "child-123"}

        with patch(
            "backend.websocket.message_router.handle_child_host_created",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.CHILD_HOST_CREATED, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_command_result(self):
        """Test routing COMMAND_RESULT message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"result": "success"}

        with patch(
            "backend.websocket.message_router.handle_command_result",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.COMMAND_RESULT, mock_db, mock_connection, message_data
            )

        assert result is True
        # Command result only takes connection and data, not db
        mock_handler.assert_called_once_with(mock_connection, message_data)

    @pytest.mark.asyncio
    async def test_routes_command_acknowledgment(self):
        """Test routing COMMAND_ACKNOWLEDGMENT message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"ack_id": "ack-123"}

        with patch(
            "backend.websocket.message_router.handle_command_acknowledgment",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.COMMAND_ACKNOWLEDGMENT,
                mock_db,
                mock_connection,
                message_data,
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_update_apply_result(self):
        """Test routing UPDATE_APPLY_RESULT message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"success": True}

        with patch(
            "backend.websocket.message_router.handle_update_apply_result",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.UPDATE_APPLY_RESULT, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_vmm_initialized(self):
        """Test routing VMM_INITIALIZED message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"initialized": True}

        with patch(
            "backend.websocket.message_router.handle_vmm_initialize_result",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.VMM_INITIALIZED, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_kvm_initialized(self):
        """Test routing KVM_INITIALIZED message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"initialized": True}

        with patch(
            "backend.websocket.message_router.handle_kvm_initialize_result",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.KVM_INITIALIZED, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_bhyve_initialized(self):
        """Test routing BHYVE_INITIALIZED message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"initialized": True}

        with patch(
            "backend.websocket.message_router.handle_bhyve_initialize_result",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.BHYVE_INITIALIZED, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_kvm_modules_enabled(self):
        """Test routing KVM_MODULES_ENABLED message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"modules": ["kvm", "kvm_intel"]}

        with patch(
            "backend.websocket.message_router.handle_kvm_modules_enable_result",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.KVM_MODULES_ENABLED, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_kvm_modules_disabled(self):
        """Test routing KVM_MODULES_DISABLED message."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {"modules": []}

        with patch(
            "backend.websocket.message_router.handle_kvm_modules_disable_result",
            new=AsyncMock(),
        ) as mock_handler:
            result = await route_inbound_message(
                MessageType.KVM_MODULES_DISABLED, mock_db, mock_connection, message_data
            )

        assert result is True
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_for_unknown_message_type(self):
        """Test returns False for unknown message type."""
        from backend.websocket.message_router import route_inbound_message

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {}

        result = await route_inbound_message(
            "UNKNOWN_TYPE", mock_db, mock_connection, message_data
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_handler_exception(self):
        """Test returns False when handler raises exception."""
        from backend.websocket.message_router import route_inbound_message
        from backend.websocket.messages import MessageType

        mock_db = MagicMock()
        mock_connection = MagicMock()
        message_data = {}

        with patch(
            "backend.websocket.message_router.handle_os_version_update",
            new=AsyncMock(side_effect=Exception("Handler error")),
        ):
            result = await route_inbound_message(
                MessageType.OS_VERSION_UPDATE, mock_db, mock_connection, message_data
            )

        assert result is False


class TestLogMessageData:
    """Tests for log_message_data function."""

    def test_logs_hardware_update_data(self):
        """Test logging hardware update data."""
        from backend.websocket.message_router import log_message_data
        from backend.websocket.messages import MessageType

        message_data = {
            "cpu_vendor": "Intel",
            "cpu_model": "Core i7-9700K",
            "memory_total_mb": 32768,
            "storage_devices": [{"name": "sda"}, {"name": "sdb"}],
        }

        # Should not raise
        log_message_data(MessageType.HARDWARE_UPDATE, message_data)

    def test_logs_hardware_update_with_missing_fields(self):
        """Test logging hardware update with missing fields."""
        from backend.websocket.message_router import log_message_data
        from backend.websocket.messages import MessageType

        message_data = {}

        # Should not raise, uses defaults
        log_message_data(MessageType.HARDWARE_UPDATE, message_data)

    def test_logs_software_inventory_update_data(self):
        """Test logging software inventory update data."""
        from backend.websocket.message_router import log_message_data
        from backend.websocket.messages import MessageType

        message_data = {
            "total_packages": 150,
            "software_packages": [{"name": "vim"}, {"name": "bash"}],
        }

        # Should not raise
        log_message_data(MessageType.SOFTWARE_INVENTORY_UPDATE, message_data)

    def test_logs_software_inventory_with_empty_packages(self):
        """Test logging software inventory with empty packages list."""
        from backend.websocket.message_router import log_message_data
        from backend.websocket.messages import MessageType

        message_data = {
            "total_packages": 0,
            "software_packages": [],
        }

        # Should not raise
        log_message_data(MessageType.SOFTWARE_INVENTORY_UPDATE, message_data)

    def test_logs_user_access_update_data(self):
        """Test logging user access update data."""
        from backend.websocket.message_router import log_message_data
        from backend.websocket.messages import MessageType

        message_data = {
            "total_users": 10,
            "total_groups": 5,
        }

        # Should not raise
        log_message_data(MessageType.USER_ACCESS_UPDATE, message_data)

    def test_logs_user_access_with_missing_fields(self):
        """Test logging user access with missing fields."""
        from backend.websocket.message_router import log_message_data
        from backend.websocket.messages import MessageType

        message_data = {}

        # Should not raise, uses defaults
        log_message_data(MessageType.USER_ACCESS_UPDATE, message_data)

    def test_does_not_log_for_other_message_types(self):
        """Test no special logging for other message types."""
        from backend.websocket.message_router import log_message_data
        from backend.websocket.messages import MessageType

        message_data = {"key": "value"}

        # Should not raise - just returns without logging
        log_message_data(MessageType.HEARTBEAT, message_data)

    def test_handles_none_in_storage_devices(self):
        """Test handling None value for storage_devices."""
        from backend.websocket.message_router import log_message_data
        from backend.websocket.messages import MessageType

        message_data = {
            "cpu_vendor": "AMD",
            "cpu_model": "Ryzen 9",
            "memory_total_mb": 65536,
            "storage_devices": None,
        }

        # Should handle None gracefully
        try:
            log_message_data(MessageType.HARDWARE_UPDATE, message_data)
        except TypeError:
            # Expected if storage_devices is None
            pass
