"""
Comprehensive tests for backend/api/host_utils.py module.
Tests utility functions for host management operations.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from backend.api import host_utils
from backend.persistence import models


class MockHost:
    """Mock host object for testing."""

    def __init__(
        self,
        host_id="550e8400-e29b-41d4-a716-446655440001",
        fqdn="test.example.com",
        approval_status="approved",
    ):
        self.id = host_id
        self.fqdn = fqdn
        self.approval_status = approval_status
        self.ipv4 = "192.168.1.100"
        self.ipv6 = "::1"
        self.last_access = datetime.now(timezone.utc)
        self.active = True
        self.status = "up"
        self.host_token = None  # For secure token support


class MockStorageDevice:
    """Mock storage device object for testing."""

    def __init__(
        self,
        device_id="550e8400-e29b-41d4-a716-446655440001",
        name="/dev/sda1",
        host_id="550e8400-e29b-41d4-a716-446655440001",
    ):
        self.id = device_id
        self.device_name = name  # Match actual model field name
        self.host_id = host_id
        self.mount_point = "/"
        self.filesystem = "ext4"  # Match actual model field name
        self.device_type = "disk"
        self.total_size_bytes = 1000000000000  # 1TB - Match actual model field name
        self.used_size_bytes = 500000000000  # 500GB - Match actual model field name
        self.available_size_bytes = (
            500000000000  # 500GB - Match actual model field name
        )
        self.last_updated = datetime.now(timezone.utc)  # Match actual model field name
        # Legacy compatibility fields for tests that expect old names
        self.name = name
        self.device_path = "/dev/sda1"
        self.file_system = "ext4"
        self.capacity_bytes = 1000000000000  # 1TB
        self.used_bytes = 500000000000  # 500GB
        self.available_bytes = 500000000000  # 500GB
        self.is_physical = True
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class MockNetworkInterface:
    """Mock network interface object for testing."""

    def __init__(
        self,
        interface_id="550e8400-e29b-41d4-a716-446655440002",
        interface_name="eth0",
        host_id="550e8400-e29b-41d4-a716-446655440001",
    ):
        self.id = interface_id
        self.interface_name = interface_name
        self.host_id = host_id
        self.interface_type = "ethernet"
        self.hardware_type = "physical"
        self.mac_address = "00:11:22:33:44:55"
        self.ipv4_address = "192.168.1.100"
        self.ipv6_address = "::1"
        self.netmask = "255.255.255.0"
        self.broadcast = "192.168.1.255"
        self.mtu = 1500
        self.is_up = True
        self.speed_mbps = 1000
        self.last_updated = datetime.now(timezone.utc)
        # For backward compatibility
        self.is_active = self.is_up


class MockUserAccount:
    """Mock user account object for testing."""

    def __init__(
        self,
        user_id="550e8400-e29b-41d4-a716-446655440003",
        username="testuser",
        host_id="550e8400-e29b-41d4-a716-446655440001",
    ):
        self.id = user_id
        self.username = username
        self.host_id = host_id
        self.full_name = "Test User"
        self.home_directory = "/home/testuser"
        self.shell = "/bin/bash"
        self.user_id = 1000
        self.group_id = 1000
        self.uid = 1000
        self.is_system_user = False
        self.is_active = True
        self.last_login = datetime.now(timezone.utc)
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class MockUserGroup:
    """Mock user group object for testing."""

    def __init__(
        self,
        group_id="550e8400-e29b-41d4-a716-446655440004",
        group_name="testgroup",
        host_id="550e8400-e29b-41d4-a716-446655440001",
    ):
        self.id = group_id
        self.group_name = group_name
        self.host_id = host_id
        self.gid = 1000
        self.is_system_group = False
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class MockUserGroupMembership:
    """Mock user group membership object for testing."""

    def __init__(
        self,
        user_account_id="550e8400-e29b-41d4-a716-446655440003",
        user_group_id="550e8400-e29b-41d4-a716-446655440004",
    ):
        self.user_account_id = user_account_id
        self.user_group_id = user_group_id


class MockSoftwarePackage:
    """Mock software package object for testing."""

    def __init__(
        self,
        package_id="550e8400-e29b-41d4-a716-446655440005",
        package_name="testpkg",
        host_id="550e8400-e29b-41d4-a716-446655440001",
    ):
        self.id = package_id
        self.package_name = package_name
        self.host_id = host_id
        self.package_version = "1.0.0"
        self.package_description = "Test package"
        self.package_manager = "apt"
        self.source = "ubuntu"
        self.architecture = "amd64"
        self.size_bytes = 1024000
        self.install_date = datetime.now(timezone.utc)
        self.vendor = "Test Vendor"
        self.category = "utilities"
        self.license = "GPL"
        self.bundle_id = None
        self.app_store_id = None
        self.install_path = "/usr/bin/testpkg"
        self.is_system_package = False
        self.is_user_installed = True
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.software_updated_at = datetime.now(timezone.utc)


class MockUbuntuProInfo:
    """Mock Ubuntu Pro info object for testing."""

    def __init__(self, host_id="550e8400-e29b-41d4-a716-446655440001"):
        self.id = "550e8400-e29b-41d4-a716-446655440006"
        self.host_id = host_id
        self.available = True
        self.attached = True
        self.subscription_name = "27.13.6"
        self.expires = datetime(2025, 12, 31, tzinfo=timezone.utc)
        self.account_name = "Test Account"
        self.contract_name = "Test Contract"
        self.tech_support_level = "essential"


class MockUbuntuProService:
    """Mock Ubuntu Pro service object for testing."""

    def __init__(self, ubuntu_pro_info_id=1, service_name="esm-infra"):
        self.ubuntu_pro_info_id = ubuntu_pro_info_id
        self.service_name = service_name
        self.description = "Expanded Security Maintenance for Infrastructure"
        self.available = True
        self.status = "enabled"
        self.entitled = "true"


class TestGetHostById:
    """Test get_host_by_id function."""

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_by_id_success(self, mock_get_engine, mock_sessionmaker):
        """Test successful host retrieval by ID."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        result = host_utils.get_host_by_id(1)

        assert result == mock_host
        mock_session.query.assert_called_once_with(models.Host)

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_by_id_not_found(self, mock_get_engine, mock_sessionmaker):
        """Test host not found by ID."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            host_utils.get_host_by_id(999)

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)


class TestGetHostByFqdn:
    """Test get_host_by_fqdn function."""

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_by_fqdn_success(self, mock_get_engine, mock_sessionmaker):
        """Test successful host retrieval by FQDN."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(fqdn="test.example.com")
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        result = host_utils.get_host_by_fqdn("test.example.com")

        assert result == mock_host
        mock_session.query.assert_called_once_with(models.Host)

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_by_fqdn_not_found(self, mock_get_engine, mock_sessionmaker):
        """Test host not found by FQDN."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            host_utils.get_host_by_fqdn("nonexistent.example.com")

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)


class TestValidateHostApprovalStatus:
    """Test validate_host_approval_status function."""

    def test_validate_host_approval_status_approved(self):
        """Test validation with approved host."""
        mock_host = MockHost(approval_status="approved")

        # Should not raise exception
        host_utils.validate_host_approval_status(mock_host)

    def test_validate_host_approval_status_pending(self):
        """Test validation with pending host."""
        mock_host = MockHost(approval_status="pending")

        with pytest.raises(HTTPException) as exc_info:
            host_utils.validate_host_approval_status(mock_host)

        assert exc_info.value.status_code == 400
        assert "Host is not approved" in str(exc_info.value.detail)

    def test_validate_host_approval_status_rejected(self):
        """Test validation with rejected host."""
        mock_host = MockHost(approval_status="rejected")

        with pytest.raises(HTTPException) as exc_info:
            host_utils.validate_host_approval_status(mock_host)

        assert exc_info.value.status_code == 400
        assert "Host is not approved" in str(exc_info.value.detail)


class TestGetHostStorageDevices:
    """Test get_host_storage_devices function."""

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_storage_devices_success(self, mock_get_engine, mock_sessionmaker):
        """Test successful storage devices retrieval."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_device = MockStorageDevice()

        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_device
        ]

        result = host_utils.get_host_storage_devices(1)

        assert len(result) == 1
        device = result[0]
        assert device["id"] == mock_device.id
        assert device["name"] == mock_device.device_name
        assert device["mount_point"] == mock_device.mount_point
        assert device["file_system"] == mock_device.filesystem
        assert device["device_type"] == "physical"  # /dev/sda1 should be physical
        assert device["is_physical"] == True  # New field we added
        assert device["capacity_bytes"] == mock_device.total_size_bytes
        assert device["used_bytes"] == mock_device.used_size_bytes
        assert device["available_bytes"] == mock_device.available_size_bytes
        assert device["size_gb"] == 931.32  # 1TB in GB
        assert device["used_gb"] == 465.66  # 500GB in GB
        assert device["available_gb"] == 465.66  # 500GB in GB
        assert device["usage_percent"] == 50.0

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_storage_devices_host_not_found(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test storage devices retrieval with nonexistent host."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            host_utils.get_host_storage_devices(999)

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_storage_devices_empty(self, mock_get_engine, mock_sessionmaker):
        """Test storage devices retrieval with no devices."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_session.query.return_value.filter.return_value.all.return_value = []

        result = host_utils.get_host_storage_devices(1)

        assert result == []

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_storage_devices_none_values(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test storage devices with None values."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_device = MockStorageDevice()
        # Set both new and legacy field names to None
        mock_device.total_size_bytes = None
        mock_device.used_size_bytes = None
        mock_device.available_size_bytes = None
        mock_device.capacity_bytes = None
        mock_device.used_bytes = None
        mock_device.available_bytes = None
        mock_device.last_updated = None
        mock_device.created_at = None
        mock_device.updated_at = None

        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_device
        ]

        result = host_utils.get_host_storage_devices(1)

        assert len(result) == 1
        device = result[0]
        # Check the actual field names returned by the function
        assert device["capacity_bytes"] is None
        assert device["used_bytes"] is None
        assert device["available_bytes"] is None
        assert device["last_updated"] is None
        assert device["size_gb"] == 0
        assert device["used_gb"] == 0
        assert device["available_gb"] == 0
        assert device["usage_percent"] == 0


class TestGetHostNetworkInterfaces:
    """Test get_host_network_interfaces function."""

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_network_interfaces_success(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test successful network interfaces retrieval."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_interface = MockNetworkInterface()

        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_interface
        ]

        result = host_utils.get_host_network_interfaces(1)

        assert len(result) == 1
        interface = result[0]
        assert interface["id"] == mock_interface.id
        assert interface["name"] == mock_interface.interface_name
        assert interface["interface_type"] == mock_interface.interface_type
        assert interface["mac_address"] == mock_interface.mac_address
        assert interface["ipv4_address"] == mock_interface.ipv4_address
        assert interface["is_up"] == mock_interface.is_up

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_network_interfaces_host_not_found(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test network interfaces retrieval with nonexistent host."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            host_utils.get_host_network_interfaces(999)

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)


class TestGetHostUserAccounts:
    """Test get_host_user_accounts function."""

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_user_accounts_success(self, mock_get_engine, mock_sessionmaker):
        """Test successful user accounts retrieval."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_user = MockUserAccount()

        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_user
        ]

        result = host_utils.get_host_user_accounts(1)

        assert len(result) == 1
        user = result[0]
        assert user["id"] == mock_user.id
        assert user["username"] == mock_user.username
        assert user["full_name"] == mock_user.full_name
        assert user["home_directory"] == mock_user.home_directory
        assert user["is_system_user"] == mock_user.is_system_user

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_user_accounts_host_not_found(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test user accounts retrieval with nonexistent host."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            host_utils.get_host_user_accounts(999)

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)


class TestGetHostUsersWithGroups:
    """Test get_host_users_with_groups function."""

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_users_with_groups_success(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test successful users with groups retrieval."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_user = MockUserAccount()
        mock_group = MockUserGroup()
        mock_membership = MockUserGroupMembership()

        # Setup query return values
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_user
        ]
        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = [
            (mock_membership, mock_group)
        ]

        result = host_utils.get_host_users_with_groups(1)

        assert len(result) == 1
        user = result[0]
        assert user["id"] == mock_user.id
        assert user["username"] == mock_user.username
        assert user["uid"] == mock_user.uid
        assert user["groups"] == [mock_group.group_name]

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_users_with_groups_host_not_found(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test users with groups retrieval with nonexistent host."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            host_utils.get_host_users_with_groups(999)

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)


class TestGetHostUserGroups:
    """Test get_host_user_groups function."""

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_user_groups_success(self, mock_get_engine, mock_sessionmaker):
        """Test successful user groups retrieval."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_group = MockUserGroup()
        mock_user = MockUserAccount()
        mock_membership = MockUserGroupMembership()

        # Setup query return values
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_group
        ]
        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = [
            (mock_membership, mock_user)
        ]

        result = host_utils.get_host_user_groups(1)

        assert len(result) == 1
        group = result[0]
        assert group["id"] == mock_group.id
        assert group["group_name"] == mock_group.group_name
        assert group["gid"] == mock_group.gid
        assert group["users"] == [mock_user.username]

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_user_groups_host_not_found(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test user groups retrieval with nonexistent host."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            host_utils.get_host_user_groups(999)

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)


class TestGetHostSoftwarePackages:
    """Test get_host_software_packages function."""

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_software_packages_success(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test successful software packages retrieval."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_package = MockSoftwarePackage()

        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_package
        ]

        result = host_utils.get_host_software_packages(1)

        assert len(result) == 1
        package = result[0]
        assert package["id"] == mock_package.id
        assert package["package_name"] == mock_package.package_name
        assert package["version"] == mock_package.package_version
        assert package["package_manager"] == mock_package.package_manager
        assert package["is_system_package"] == mock_package.is_system_package

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_software_packages_host_not_found(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test software packages retrieval with nonexistent host."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            host_utils.get_host_software_packages(999)

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)


class TestUpdateHostTimestamp:
    """Test update_host_timestamp function."""

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_update_host_timestamp_success(self, mock_get_engine, mock_sessionmaker):
        """Test successful timestamp update."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        # Should not raise exception
        host_utils.update_host_timestamp(1, "last_access")

        mock_session.commit.assert_called_once()

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_update_host_timestamp_host_not_found(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test timestamp update with nonexistent host."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None

        # Should not raise exception, just do nothing
        host_utils.update_host_timestamp(999, "last_access")

        mock_session.commit.assert_not_called()


class TestUpdateOrCreateHost:
    """Test update_or_create_host async function."""

    @pytest.mark.asyncio
    async def test_update_existing_host(self):
        """Test updating existing host."""
        mock_session = Mock()
        mock_host = MockHost(fqdn="test.example.com")
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        result = await host_utils.update_or_create_host(
            mock_session, "test.example.com", "192.168.1.100", "::1"
        )

        assert result == mock_host
        assert mock_host.ipv4 == "192.168.1.100"
        assert mock_host.ipv6 == "::1"
        assert mock_host.active is True
        assert mock_host.status == "up"
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once_with(mock_host)

    @pytest.mark.asyncio
    async def test_create_new_host(self):
        """Test creating new host."""
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = await host_utils.update_or_create_host(
            mock_session, "new.example.com", "192.168.1.200", "::2"
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_host_with_ipv4_only(self):
        """Test creating new host with IPv4 only."""
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = await host_utils.update_or_create_host(
            mock_session, "ipv4only.example.com", "192.168.1.200"
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()


class TestGetHostUbuntuProInfo:
    """Test get_host_ubuntu_pro_info function."""

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_ubuntu_pro_info_success(self, mock_get_engine, mock_sessionmaker):
        """Test successful Ubuntu Pro info retrieval."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_pro_info = MockUbuntuProInfo()
        mock_service = MockUbuntuProService()

        mock_session.query.return_value.filter.return_value.first.side_effect = [
            mock_host,  # First call for host
            mock_pro_info,  # Second call for ubuntu pro info
        ]
        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_service
        ]

        result = host_utils.get_host_ubuntu_pro_info(1)

        assert result["available"] == mock_pro_info.available
        assert result["attached"] == mock_pro_info.attached
        assert result["version"] == mock_pro_info.subscription_name
        assert result["account_name"] == mock_pro_info.account_name
        assert result["contract_name"] == mock_pro_info.contract_name
        assert result["tech_support_level"] == mock_pro_info.tech_support_level
        assert len(result["services"]) == 1
        assert result["services"][0]["name"] == mock_service.service_name
        assert result["services"][0]["status"] == mock_service.status

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_ubuntu_pro_info_host_not_found(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test Ubuntu Pro info retrieval with nonexistent host."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            host_utils.get_host_ubuntu_pro_info(999)

        assert exc_info.value.status_code == 404
        assert "Host not found" in str(exc_info.value.detail)

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_ubuntu_pro_info_no_data(self, mock_get_engine, mock_sessionmaker):
        """Test Ubuntu Pro info retrieval with no Pro data."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_session.query.return_value.filter.return_value.first.side_effect = [
            mock_host,  # First call for host
            None,  # Second call for ubuntu pro info
        ]

        result = host_utils.get_host_ubuntu_pro_info(1)

        assert result["available"] is False
        assert result["attached"] is False
        assert result["version"] is None
        assert result["expires"] is None
        assert result["account_name"] is None
        assert result["contract_name"] is None
        assert result["tech_support_level"] is None
        assert result["services"] == []

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_get_host_ubuntu_pro_info_no_services(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test Ubuntu Pro info retrieval with no services."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_pro_info = MockUbuntuProInfo()

        mock_session.query.return_value.filter.return_value.first.side_effect = [
            mock_host,  # First call for host
            mock_pro_info,  # Second call for ubuntu pro info
        ]
        mock_session.query.return_value.filter.return_value.all.return_value = []

        result = host_utils.get_host_ubuntu_pro_info(1)

        assert result["available"] == mock_pro_info.available
        assert result["attached"] == mock_pro_info.attached
        assert len(result["services"]) == 0


class TestHostUtilsIntegration:
    """Integration tests for host utils functionality."""

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_storage_device_calculations(self, mock_get_engine, mock_sessionmaker):
        """Test storage device size calculations are correct."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_device = MockStorageDevice()
        mock_device.total_size_bytes = 1000000000000  # 1TB
        mock_device.used_size_bytes = 250000000000  # 250GB
        mock_device.available_size_bytes = 750000000000  # 750GB

        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_device
        ]

        result = host_utils.get_host_storage_devices(1)

        device = result[0]
        assert device["size_gb"] == 931.32  # 1TB in binary GB
        assert device["used_gb"] == 232.83  # 250GB in binary GB
        assert device["available_gb"] == 698.49  # 750GB in binary GB
        assert device["usage_percent"] == 25.0  # 25% usage

    @patch("backend.api.host_utils.sessionmaker")
    @patch("backend.api.host_utils.db.get_engine")
    def test_multiple_storage_devices(self, mock_get_engine, mock_sessionmaker):
        """Test handling multiple storage devices."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_host = MockHost(host_id=1)
        mock_device1 = MockStorageDevice(device_id=1, name="/dev/sda1")
        mock_device2 = MockStorageDevice(device_id=2, name="/dev/sdb1")

        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_device1,
            mock_device2,
        ]

        result = host_utils.get_host_storage_devices(1)

        assert len(result) == 2
        assert result[0]["name"] == "/dev/sda1"
        assert result[1]["name"] == "/dev/sdb1"

    def test_validate_host_approval_multiple_statuses(self):
        """Test validation with various approval statuses."""
        approved_host = MockHost(approval_status="approved")
        pending_host = MockHost(approval_status="pending")
        rejected_host = MockHost(approval_status="rejected")
        unknown_host = MockHost(approval_status="unknown_status")

        # Only approved should pass
        host_utils.validate_host_approval_status(approved_host)

        # All others should fail
        for host in [pending_host, rejected_host, unknown_host]:
            with pytest.raises(HTTPException):
                host_utils.validate_host_approval_status(host)
