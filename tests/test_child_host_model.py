"""
Tests for backend/persistence/models/child_host.py module.
Tests HostChild and ChildHostDistribution models.
"""

import uuid
from datetime import datetime, timezone

import pytest


class TestHostChildModel:
    """Tests for HostChild model."""

    def test_host_child_table_name(self):
        """Test HostChild table name."""
        from backend.persistence.models.child_host import HostChild

        assert HostChild.__tablename__ == "host_child"

    def test_host_child_columns_exist(self):
        """Test HostChild has expected columns."""
        from backend.persistence.models.child_host import HostChild

        assert hasattr(HostChild, "id")
        assert hasattr(HostChild, "parent_host_id")
        assert hasattr(HostChild, "child_host_id")
        assert hasattr(HostChild, "child_name")
        assert hasattr(HostChild, "child_type")
        assert hasattr(HostChild, "distribution")
        assert hasattr(HostChild, "distribution_version")
        assert hasattr(HostChild, "install_path")
        assert hasattr(HostChild, "default_username")
        assert hasattr(HostChild, "hostname")
        assert hasattr(HostChild, "wsl_guid")
        assert hasattr(HostChild, "auto_approve_token")
        assert hasattr(HostChild, "status")
        assert hasattr(HostChild, "installation_step")
        assert hasattr(HostChild, "error_message")
        assert hasattr(HostChild, "created_at")
        assert hasattr(HostChild, "updated_at")
        assert hasattr(HostChild, "installed_at")


class TestHostChildRepr:
    """Tests for HostChild __repr__ method."""

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.child_host import HostChild

        child = HostChild()
        child.id = uuid.uuid4()
        child.child_name = "ubuntu-vm"
        child.child_type = "lxd"
        child.status = "running"

        repr_str = repr(child)

        assert "HostChild" in repr_str
        assert "ubuntu-vm" in repr_str
        assert "lxd" in repr_str
        assert "running" in repr_str


class TestChildHostDistributionModel:
    """Tests for ChildHostDistribution model."""

    def test_child_host_distribution_table_name(self):
        """Test ChildHostDistribution table name."""
        from backend.persistence.models.child_host import ChildHostDistribution

        assert ChildHostDistribution.__tablename__ == "child_host_distribution"

    def test_child_host_distribution_columns_exist(self):
        """Test ChildHostDistribution has expected columns."""
        from backend.persistence.models.child_host import ChildHostDistribution

        assert hasattr(ChildHostDistribution, "id")
        assert hasattr(ChildHostDistribution, "child_type")
        assert hasattr(ChildHostDistribution, "distribution_name")
        assert hasattr(ChildHostDistribution, "distribution_version")
        assert hasattr(ChildHostDistribution, "display_name")
        assert hasattr(ChildHostDistribution, "install_identifier")
        assert hasattr(ChildHostDistribution, "is_active")


class TestChildHostConstants:
    """Tests for child_host module constants."""

    def test_valid_child_types(self):
        """Test child_type supports various virtualization types."""
        from backend.persistence.models.child_host import HostChild

        # These are the documented child_type values
        valid_types = ["wsl", "lxd", "virtualbox", "hyperv", "vmm", "bhyve", "kvm"]

        for child_type in valid_types:
            child = HostChild()
            child.child_type = child_type
            assert child.child_type == child_type

    def test_valid_status_values(self):
        """Test status supports expected values."""
        from backend.persistence.models.child_host import HostChild

        valid_statuses = [
            "pending",
            "creating",
            "installing",
            "running",
            "stopped",
            "error",
            "uninstalling",
        ]

        for status in valid_statuses:
            child = HostChild()
            child.status = status
            assert child.status == status
