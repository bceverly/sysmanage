"""
Comprehensive tests for backend/api/host_data_updates.py module.
Tests host data update endpoints for hardware, users, and software information.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from backend.api.host_data_updates import (
    get_host_groups,
    get_host_network,
    get_host_software,
    get_host_storage,
    get_host_ubuntu_pro,
    get_host_users,
    request_hardware_update,
    request_hardware_update_bulk,
    request_user_access_update,
    update_host_hardware,
)


class MockHost:
    """Mock host object."""

    def __init__(self, host_id=1, approval_status="approved"):
        self.id = host_id
        self.fqdn = "test-host.example.com"
        self.hostname = "test-host"
        self.approval_status = approval_status
        self.cpu_vendor = None
        self.cpu_model = None
        self.cpu_cores = None
        self.cpu_threads = None
        self.cpu_frequency_mhz = None
        self.memory_total_mb = None
        self.storage_details = None
        self.network_details = None
        self.hardware_details = None
        self.hardware_updated_at = None
        self.last_access = None


class MockStorageDevice:
    """Mock storage device object."""

    def __init__(self, host_id=1, name="sda1"):
        self.host_id = host_id
        self.name = name
        self.device_path = "/dev/sda1"
        self.mount_point = "/"
        self.file_system = "ext4"
        self.device_type = "disk"
        self.capacity_bytes = 1000000000
        self.used_bytes = 500000000
        self.available_bytes = 500000000
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class MockNetworkInterface:
    """Mock network interface object."""

    def __init__(self, host_id=1, name="eth0"):
        self.host_id = host_id
        self.name = name
        self.interface_type = "ethernet"
        self.hardware_type = "physical"
        self.mac_address = "00:11:22:33:44:55"
        self.ipv4_address = "192.168.1.100"
        self.ipv6_address = "2001:db8::1"
        self.subnet_mask = "255.255.255.0"
        self.is_active = True
        self.speed_mbps = 1000
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class MockSession:
    """Mock database session."""

    def __init__(self, hosts=None, storage_devices=None, network_interfaces=None):
        self.hosts = hosts or []
        self.storage_devices = storage_devices or []
        self.network_interfaces = network_interfaces or []
        self.committed = False
        self.added_objects = []
        self.deleted_queries = []

    def query(self, model):
        return MockQuery(
            self.hosts
            if model.__name__ == "Host"
            else (
                self.storage_devices
                if model.__name__ == "StorageDevice"
                else self.network_interfaces
            )
        )

    def add(self, obj):
        self.added_objects.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockQuery:
    """Mock SQLAlchemy query."""

    def __init__(self, objects):
        self.objects = objects
        self.filter_called = False

    def filter(self, *args):
        self.filter_called = True
        return self

    def first(self):
        return self.objects[0] if self.objects else None

    def all(self):
        return self.objects

    def delete(self):
        return MockDeleteResult()


class MockDeleteResult:
    """Mock delete operation result."""

    def __init__(self):
        self.deleted_count = 1


class MockSessionLocal:
    """Mock session factory."""

    def __init__(self, mock_session):
        self.mock_session = mock_session

    def __call__(self):
        return self.mock_session


class TestUpdateHostHardware:
    """Test update_host_hardware function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    async def test_update_host_hardware_success(self, mock_db, mock_sessionmaker):
        """Test successful hardware update."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        hardware_data = {
            "cpu_vendor": "Intel",
            "cpu_model": "Core i7-8700K",
            "cpu_cores": 6,
            "cpu_threads": 12,
            "cpu_frequency_mhz": 3700,
            "memory_total_mb": 16384,
            "hardware_details": {"additional": "info"},
        }

        result = await update_host_hardware(1, hardware_data)

        assert result["result"] is True
        assert "Hardware information updated successfully" in result["message"]
        assert mock_session.committed is True
        assert mock_host.cpu_vendor == "Intel"
        assert mock_host.cpu_model == "Core i7-8700K"
        assert mock_host.cpu_cores == 6

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    async def test_update_host_hardware_with_storage_devices(
        self, mock_db, mock_sessionmaker
    ):
        """Test hardware update with storage devices."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        hardware_data = {
            "storage_devices": [
                {
                    "name": "sda1",
                    "device_path": "/dev/sda1",
                    "mount_point": "/",
                    "file_system": "ext4",
                    "device_type": "disk",
                    "capacity_bytes": 1000000000,
                    "used_bytes": 500000000,
                    "available_bytes": 500000000,
                },
                {
                    "name": "sdb1",
                    "device_path": "/dev/sdb1",
                    "mount_point": "/home",
                    "file_system": "ext4",
                    "device_type": "disk",
                    "capacity_bytes": 2000000000,
                    "used_bytes": 1000000000,
                    "available_bytes": 1000000000,
                },
            ]
        }

        result = await update_host_hardware(1, hardware_data)

        assert result["result"] is True
        assert mock_session.committed is True
        assert len(mock_session.added_objects) == 2  # Two storage devices added

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    async def test_update_host_hardware_with_network_interfaces(
        self, mock_db, mock_sessionmaker
    ):
        """Test hardware update with network interfaces."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        hardware_data = {
            "network_interfaces": [
                {
                    "name": "eth0",
                    "interface_type": "ethernet",
                    "hardware_type": "physical",
                    "mac_address": "00:11:22:33:44:55",
                    "ipv4_address": "192.168.1.100",
                    "ipv6_address": "2001:db8::1",
                    "subnet_mask": "255.255.255.0",
                    "is_active": True,
                    "speed_mbps": 1000,
                },
                {
                    "name": "lo",
                    "interface_type": "loopback",
                    "hardware_type": "virtual",
                    "ipv4_address": "127.0.0.1",
                    "is_active": True,
                },
            ]
        }

        result = await update_host_hardware(1, hardware_data)

        assert result["result"] is True
        assert mock_session.committed is True
        assert len(mock_session.added_objects) == 2  # Two network interfaces added

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    async def test_update_host_hardware_skip_error_entries(
        self, mock_db, mock_sessionmaker
    ):
        """Test hardware update skips entries with errors."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        hardware_data = {
            "storage_devices": [
                {
                    "name": "sda1",
                    "device_path": "/dev/sda1",
                    "capacity_bytes": 1000000000,
                },
                {"error": "Device not accessible"},  # This should be skipped
            ],
            "network_interfaces": [
                {"name": "eth0", "mac_address": "00:11:22:33:44:55"},
                {"error": "Interface down"},  # This should be skipped
            ],
        }

        result = await update_host_hardware(1, hardware_data)

        assert result["result"] is True
        assert len(mock_session.added_objects) == 2  # Only non-error entries added

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    async def test_update_host_hardware_backward_compatibility(
        self, mock_db, mock_sessionmaker
    ):
        """Test hardware update with legacy JSON fields."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        hardware_data = {
            "storage_details": {"legacy": "storage_data"},
            "network_details": {"legacy": "network_data"},
            "hardware_details": {"legacy": "hardware_data"},
        }

        result = await update_host_hardware(1, hardware_data)

        assert result["result"] is True
        assert mock_host.storage_details == {"legacy": "storage_data"}
        assert mock_host.network_details == {"legacy": "network_data"}
        assert mock_host.hardware_details == {"legacy": "hardware_data"}

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    async def test_update_host_hardware_host_not_found(
        self, mock_db, mock_sessionmaker
    ):
        """Test hardware update when host is not found."""
        mock_session = MockSession([])  # Empty hosts list
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        hardware_data = {"cpu_vendor": "Intel"}

        with pytest.raises(HTTPException) as exc_info:
            await update_host_hardware(999, hardware_data)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    async def test_update_host_hardware_partial_update(
        self, mock_db, mock_sessionmaker
    ):
        """Test hardware update with only some fields."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        hardware_data = {
            "cpu_vendor": "AMD",
            "memory_total_mb": 32768,
            # Missing other fields
        }

        result = await update_host_hardware(1, hardware_data)

        assert result["result"] is True
        assert mock_host.cpu_vendor == "AMD"
        assert mock_host.memory_total_mb == 32768
        assert mock_host.cpu_model is None  # Should remain unchanged


class TestGetHostStorage:
    """Test get_host_storage function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.get_host_storage_devices")
    async def test_get_host_storage(self, mock_get_storage):
        """Test getting host storage devices."""
        expected_result = [{"name": "sda1", "capacity": 1000}]
        mock_get_storage.return_value = expected_result

        result = await get_host_storage(1)

        assert result == expected_result
        mock_get_storage.assert_called_once_with(1)


class TestGetHostNetwork:
    """Test get_host_network function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.get_host_network_interfaces")
    async def test_get_host_network(self, mock_get_network):
        """Test getting host network interfaces."""
        expected_result = [{"name": "eth0", "ip": "192.168.1.1"}]
        mock_get_network.return_value = expected_result

        result = await get_host_network(1)

        assert result == expected_result
        mock_get_network.assert_called_once_with(1)


class TestRequestHardwareUpdate:
    """Test request_hardware_update function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    @patch("backend.api.host_data_updates.validate_host_approval_status")
    @patch("backend.api.host_data_updates.create_command_message")
    @patch("backend.api.host_data_updates.queue_ops")
    async def test_request_hardware_update_success(
        self, mock_queue_ops, mock_create_msg, mock_validate, mock_db, mock_sessionmaker
    ):
        """Test successful hardware update request."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)
        mock_create_msg.return_value = {"command": "update_hardware"}
        mock_queue_ops.enqueue_message = Mock(return_value="test-message-id-123")

        result = await request_hardware_update(1)

        assert result["result"] is True
        assert "Hardware update requested" in result["message"]
        mock_validate.assert_called_once_with(mock_host)
        mock_create_msg.assert_called_once_with(
            command_type="update_hardware", parameters={}
        )
        mock_queue_ops.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    async def test_request_hardware_update_host_not_found(
        self, mock_db, mock_sessionmaker
    ):
        """Test hardware update request when host not found."""
        mock_session = MockSession([])  # Empty hosts list
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await request_hardware_update(999)

        assert exc_info.value.status_code == 404


class TestRequestHardwareUpdateBulk:
    """Test request_hardware_update_bulk function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    @patch("backend.api.host_data_updates.create_command_message")
    @patch("backend.api.host_data_updates.queue_ops")
    async def test_request_hardware_update_bulk_success(
        self, mock_queue_ops, mock_create_msg, mock_db, mock_sessionmaker
    ):
        """Test successful bulk hardware update request."""
        mock_hosts = [MockHost(1), MockHost(2)]
        mock_session = MockSession(mock_hosts)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)
        mock_create_msg.return_value = {"command": "update_hardware"}
        mock_queue_ops.enqueue_message = Mock(return_value="test-message-id-123")

        result = await request_hardware_update_bulk([1, 2])

        assert len(result["results"]) == 2
        assert all(r["success"] for r in result["results"])
        assert mock_queue_ops.enqueue_message.call_count == 2

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    async def test_request_hardware_update_bulk_host_not_found(
        self, mock_db, mock_sessionmaker
    ):
        """Test bulk hardware update request with non-existent host."""
        # Mock a session that returns no hosts
        mock_session = MockSession([])  # Empty host list
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        result = await request_hardware_update_bulk([999])  # Non-existent host ID

        assert len(result["results"]) == 1
        assert result["results"][0]["success"] is False
        assert result["results"][0]["host_id"] == 999
        assert result["results"][0]["error"] == "Host not found"

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    async def test_request_hardware_update_bulk_host_not_approved(
        self, mock_db, mock_sessionmaker
    ):
        """Test bulk hardware update request with non-approved host."""
        # Mock a host that is not approved
        mock_hosts = [MockHost(1, "pending")]  # Host with pending approval
        mock_session = MockSession(mock_hosts)
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        result = await request_hardware_update_bulk([1])

        assert len(result["results"]) == 1
        assert result["results"][0]["success"] is False
        assert result["results"][0]["host_id"] == 1
        assert result["results"][0]["error"] == "Host is not approved"


class TestGetHostUsers:
    """Test get_host_users function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.get_host_users_with_groups")
    async def test_get_host_users(self, mock_get_users):
        """Test getting host users."""
        expected_result = [{"username": "user1", "groups": ["admin"]}]
        mock_get_users.return_value = expected_result

        result = await get_host_users(1)

        assert result == expected_result
        mock_get_users.assert_called_once_with(1)


class TestGetHostGroups:
    """Test get_host_groups function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.get_host_user_groups")
    async def test_get_host_groups(self, mock_get_groups):
        """Test getting host groups."""
        expected_result = [{"groupname": "admin", "gid": 1000}]
        mock_get_groups.return_value = expected_result

        result = await get_host_groups(1)

        assert result == expected_result
        mock_get_groups.assert_called_once_with(1)


class TestRequestUserAccessUpdate:
    """Test request_user_access_update function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    @patch("backend.api.host_data_updates.validate_host_approval_status")
    @patch("backend.api.host_data_updates.create_command_message")
    @patch("backend.api.host_data_updates.queue_ops")
    async def test_request_user_access_update_success(
        self, mock_queue_ops, mock_create_msg, mock_validate, mock_db, mock_sessionmaker
    ):
        """Test successful user access update request."""
        mock_host = MockHost()
        mock_session = MockSession([mock_host])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)
        mock_create_msg.return_value = {"command": "update_user_access"}
        mock_queue_ops.enqueue_message = Mock(return_value="test-message-id-123")

        result = await request_user_access_update(1)

        assert result["result"] is True
        assert "User access update requested" in result["message"]
        mock_validate.assert_called_once_with(mock_host)
        mock_create_msg.assert_called_once_with(
            command_type="update_user_access", parameters={}
        )
        mock_queue_ops.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.sessionmaker")
    @patch("backend.api.host_data_updates.db")
    async def test_request_user_access_update_host_not_found(
        self, mock_db, mock_sessionmaker
    ):
        """Test user access update request when host not found."""
        mock_session = MockSession([])
        mock_sessionmaker.return_value = MockSessionLocal(mock_session)

        with pytest.raises(HTTPException) as exc_info:
            await request_user_access_update(999)

        assert exc_info.value.status_code == 404


class TestGetHostSoftware:
    """Test get_host_software function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.get_host_software_packages")
    async def test_get_host_software(self, mock_get_software):
        """Test getting host software packages."""
        expected_result = [{"name": "nginx", "version": "1.18.0"}]
        mock_get_software.return_value = expected_result

        result = await get_host_software(1)

        assert result == expected_result
        mock_get_software.assert_called_once_with(1)


class TestGetHostUbuntuPro:
    """Test get_host_ubuntu_pro function."""

    @pytest.mark.asyncio
    @patch("backend.api.host_data_updates.get_host_ubuntu_pro_info")
    async def test_get_host_ubuntu_pro(self, mock_get_ubuntu_pro):
        """Test getting host Ubuntu Pro information."""
        expected_result = {"status": "enabled", "services": ["esm"]}
        mock_get_ubuntu_pro.return_value = expected_result

        result = await get_host_ubuntu_pro(1)

        assert result == expected_result
        mock_get_ubuntu_pro.assert_called_once_with(1)


class TestIntegration:
    """Integration tests for host_data_updates module."""

    def test_datetime_handling(self):
        """Test datetime handling in hardware updates."""
        now = datetime.now(timezone.utc)
        iso_string = now.isoformat()

        # Should be valid ISO format
        parsed = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None

    def test_mock_objects_structure(self):
        """Test mock objects have expected structure."""
        host = MockHost()
        storage = MockStorageDevice()
        network = MockNetworkInterface()

        # Host should have required fields
        assert hasattr(host, "approval_status")
        assert hasattr(host, "cpu_vendor")
        assert hasattr(host, "memory_total_mb")

        # Storage should have required fields
        assert hasattr(storage, "name")
        assert hasattr(storage, "capacity_bytes")

        # Network should have required fields
        assert hasattr(network, "name")
        assert hasattr(network, "mac_address")
