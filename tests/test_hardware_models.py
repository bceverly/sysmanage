"""
Tests for backend/persistence/models/hardware.py module.
Tests StorageDevice and NetworkInterface models.
"""

import uuid
from datetime import datetime, timezone

import pytest


class TestStorageDeviceModel:
    """Tests for StorageDevice model."""

    def test_storage_device_table_name(self):
        """Test StorageDevice table name."""
        from backend.persistence.models.hardware import StorageDevice

        assert StorageDevice.__tablename__ == "storage_device"

    def test_storage_device_columns_exist(self):
        """Test StorageDevice has expected columns."""
        from backend.persistence.models.hardware import StorageDevice

        assert hasattr(StorageDevice, "id")
        assert hasattr(StorageDevice, "host_id")
        assert hasattr(StorageDevice, "device_name")
        assert hasattr(StorageDevice, "device_type")
        assert hasattr(StorageDevice, "mount_point")
        assert hasattr(StorageDevice, "filesystem")
        assert hasattr(StorageDevice, "total_size_bytes")
        assert hasattr(StorageDevice, "used_size_bytes")
        assert hasattr(StorageDevice, "available_size_bytes")
        assert hasattr(StorageDevice, "device_details")
        assert hasattr(StorageDevice, "last_updated")

    def test_storage_device_repr(self):
        """Test StorageDevice __repr__ format."""
        from backend.persistence.models.hardware import StorageDevice

        device = StorageDevice()
        device.id = uuid.uuid4()
        device.device_name = "/dev/sda1"
        device.host_id = uuid.uuid4()

        repr_str = repr(device)

        assert "StorageDevice" in repr_str
        assert "/dev/sda1" in repr_str


class TestNetworkInterfaceModel:
    """Tests for NetworkInterface model."""

    def test_network_interface_table_name(self):
        """Test NetworkInterface table name."""
        from backend.persistence.models.hardware import NetworkInterface

        assert NetworkInterface.__tablename__ == "network_interface"

    def test_network_interface_columns_exist(self):
        """Test NetworkInterface has expected columns."""
        from backend.persistence.models.hardware import NetworkInterface

        assert hasattr(NetworkInterface, "id")
        assert hasattr(NetworkInterface, "host_id")
        assert hasattr(NetworkInterface, "interface_name")
        assert hasattr(NetworkInterface, "interface_type")
        assert hasattr(NetworkInterface, "mac_address")
        assert hasattr(NetworkInterface, "ipv4_address")
        assert hasattr(NetworkInterface, "ipv6_address")
        assert hasattr(NetworkInterface, "netmask")
        assert hasattr(NetworkInterface, "broadcast")
        assert hasattr(NetworkInterface, "mtu")
        assert hasattr(NetworkInterface, "speed_mbps")
        assert hasattr(NetworkInterface, "is_up")
        assert hasattr(NetworkInterface, "interface_details")
        assert hasattr(NetworkInterface, "last_updated")

    def test_network_interface_repr(self):
        """Test NetworkInterface __repr__ format."""
        from backend.persistence.models.hardware import NetworkInterface

        iface = NetworkInterface()
        iface.id = uuid.uuid4()
        iface.interface_name = "eth0"
        iface.host_id = uuid.uuid4()

        repr_str = repr(iface)

        assert "NetworkInterface" in repr_str
        assert "eth0" in repr_str
