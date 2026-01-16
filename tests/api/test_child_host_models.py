"""
Tests for the child host models module.

This module tests the Pydantic models for child host API endpoints.
"""

import pytest
from pydantic import ValidationError

from backend.api.child_host_models import (
    CreateChildHostRequest,
    CreateWslChildHostRequest,
    EnableWslRequest,
    ChildHostResponse,
    DistributionResponse,
    DistributionDetailResponse,
    CreateDistributionRequest,
    UpdateDistributionRequest,
    VirtualizationSupportResponse,
    ConfigureKvmNetworkingRequest,
)


class TestCreateChildHostRequest:
    """Test cases for CreateChildHostRequest model."""

    def test_valid_request(self):
        """Test creating a valid request."""
        request = CreateChildHostRequest(
            child_type="wsl",
            distribution_id="123e4567-e89b-12d3-a456-426614174000",
            hostname="test-host",
            username="testuser",
            password="testpass123",
        )
        assert request.child_type == "wsl"
        assert request.hostname == "test-host"
        assert request.username == "testuser"
        assert request.auto_approve is False

    def test_with_optional_fields(self):
        """Test request with optional fields."""
        request = CreateChildHostRequest(
            child_type="lxd",
            distribution_id="123",
            hostname="test",
            username="user",
            password="pass",
            install_path="/custom/path",
            auto_approve=True,
        )
        assert request.install_path == "/custom/path"
        assert request.auto_approve is True

    def test_missing_required_fields(self):
        """Test that missing required fields raise validation error."""
        with pytest.raises(ValidationError):
            CreateChildHostRequest(
                child_type="wsl",
                # Missing other required fields
            )


class TestCreateWslChildHostRequest:
    """Test cases for CreateWslChildHostRequest model."""

    def test_valid_wsl_request(self):
        """Test creating a valid WSL request."""
        request = CreateWslChildHostRequest(
            distribution="Ubuntu-22.04",
            hostname="wsl-host",
            username="wsluser",
            password="wslpass",
        )
        assert request.child_type == "wsl"
        assert request.distribution == "Ubuntu-22.04"
        assert request.memory == "2G"  # Default
        assert request.cpus == 2  # Default

    def test_kvm_request_with_all_fields(self):
        """Test KVM request with all fields."""
        request = CreateWslChildHostRequest(
            child_type="kvm",
            distribution="debian12",
            hostname="kvm-host",
            username="kvmuser",
            password="kvmpass",
            root_password="rootpass",
            vm_name="test-vm",
            memory="4G",
            disk_size="50G",
            cpus=4,
            auto_approve=True,
        )
        assert request.child_type == "kvm"
        assert request.vm_name == "test-vm"
        assert request.memory == "4G"
        assert request.disk_size == "50G"
        assert request.cpus == 4

    def test_lxd_request(self):
        """Test LXD container request."""
        request = CreateWslChildHostRequest(
            child_type="lxd",
            distribution="ubuntu:22.04",
            hostname="lxd-host",
            username="lxduser",
            password="lxdpass",
            container_name="my-container",
        )
        assert request.child_type == "lxd"
        assert request.container_name == "my-container"


class TestEnableWslRequest:
    """Test cases for EnableWslRequest model."""

    def test_empty_request(self):
        """Test that empty request is valid (placeholder model)."""
        request = EnableWslRequest()
        assert request is not None


class TestChildHostResponse:
    """Test cases for ChildHostResponse model."""

    def test_valid_response(self):
        """Test creating a valid response."""
        response = ChildHostResponse(
            id="123e4567-e89b-12d3-a456-426614174000",
            parent_host_id="456e7890-e89b-12d3-a456-426614174000",
            child_name="test-child",
            child_type="wsl",
            status="running",
            created_at="2024-01-01T00:00:00Z",
        )
        assert response.id == "123e4567-e89b-12d3-a456-426614174000"
        assert response.child_name == "test-child"
        assert response.status == "running"

    def test_with_optional_fields(self):
        """Test response with all optional fields."""
        response = ChildHostResponse(
            id="123",
            parent_host_id="456",
            child_host_id="789",
            child_name="child",
            child_type="lxd",
            distribution="Ubuntu",
            distribution_version="22.04",
            hostname="child.local",
            status="stopped",
            installation_step="configuring",
            error_message=None,
            created_at="2024-01-01T00:00:00Z",
            installed_at="2024-01-02T00:00:00Z",
        )
        assert response.child_host_id == "789"
        assert response.distribution == "Ubuntu"
        assert response.installed_at == "2024-01-02T00:00:00Z"


class TestDistributionResponse:
    """Test cases for DistributionResponse model."""

    def test_valid_response(self):
        """Test creating a valid distribution response."""
        response = DistributionResponse(
            id="123",
            child_type="wsl",
            distribution_name="Ubuntu",
            distribution_version="22.04",
            display_name="Ubuntu 22.04 LTS",
            is_active=True,
        )
        assert response.distribution_name == "Ubuntu"
        assert response.display_name == "Ubuntu 22.04 LTS"
        assert response.is_active is True


class TestDistributionDetailResponse:
    """Test cases for DistributionDetailResponse model."""

    def test_valid_detail_response(self):
        """Test creating a valid detail response."""
        response = DistributionDetailResponse(
            id="123",
            child_type="lxd",
            distribution_name="Debian",
            distribution_version="12",
            display_name="Debian 12 Bookworm",
            is_active=True,
            agent_install_method="apt",
            notes="Stable release",
        )
        assert response.distribution_name == "Debian"
        assert response.agent_install_method == "apt"
        assert response.notes == "Stable release"


class TestCreateDistributionRequest:
    """Test cases for CreateDistributionRequest model."""

    def test_valid_request(self):
        """Test creating a valid distribution request."""
        request = CreateDistributionRequest(
            child_type="kvm",
            distribution_name="Fedora",
            distribution_version="39",
            display_name="Fedora 39",
        )
        assert request.distribution_name == "Fedora"
        assert request.is_active is True  # Default

    def test_with_all_fields(self):
        """Test request with all optional fields."""
        request = CreateDistributionRequest(
            child_type="vmm",
            distribution_name="OpenBSD",
            distribution_version="7.4",
            display_name="OpenBSD 7.4",
            install_identifier="openbsd74",
            executable_name="vmctl",
            agent_install_method="pkg_add",
            agent_install_commands="pkg_add sysmanage-agent",
            is_active=True,
            min_agent_version="1.0.0",
            notes="OpenBSD release",
        )
        assert request.install_identifier == "openbsd74"
        assert request.min_agent_version == "1.0.0"


class TestUpdateDistributionRequest:
    """Test cases for UpdateDistributionRequest model."""

    def test_empty_update(self):
        """Test empty update request (all optional)."""
        request = UpdateDistributionRequest()
        assert request.child_type is None
        assert request.distribution_name is None

    def test_partial_update(self):
        """Test partial update request."""
        request = UpdateDistributionRequest(
            is_active=False,
            notes="Deprecated",
        )
        assert request.is_active is False
        assert request.notes == "Deprecated"
        assert request.distribution_name is None


class TestVirtualizationSupportResponse:
    """Test cases for VirtualizationSupportResponse model."""

    def test_valid_response(self):
        """Test creating a valid response."""
        response = VirtualizationSupportResponse(
            supported_types=["wsl", "kvm"],
            wsl_enabled=True,
            wsl_version=2,
            requires_reboot=False,
        )
        assert "wsl" in response.supported_types
        assert "kvm" in response.supported_types
        assert response.wsl_enabled is True
        assert response.wsl_version == 2

    def test_minimal_response(self):
        """Test response with minimal fields."""
        response = VirtualizationSupportResponse(
            supported_types=["lxd"],
        )
        assert response.supported_types == ["lxd"]
        assert response.requires_reboot is False  # Default

    def test_empty_supported_types(self):
        """Test response with no supported types."""
        response = VirtualizationSupportResponse(
            supported_types=[],
        )
        assert response.supported_types == []


class TestConfigureKvmNetworkingRequest:
    """Test cases for ConfigureKvmNetworkingRequest model."""

    def test_default_nat_mode(self):
        """Test default NAT mode."""
        request = ConfigureKvmNetworkingRequest()
        assert request.mode == "nat"
        assert request.network_name is None
        assert request.bridge is None

    def test_bridged_mode(self):
        """Test bridged mode configuration."""
        request = ConfigureKvmNetworkingRequest(
            mode="bridged",
            bridge="br0",
        )
        assert request.mode == "bridged"
        assert request.bridge == "br0"

    def test_nat_with_custom_network(self):
        """Test NAT mode with custom network name."""
        request = ConfigureKvmNetworkingRequest(
            mode="nat",
            network_name="mynetwork",
        )
        assert request.network_name == "mynetwork"
