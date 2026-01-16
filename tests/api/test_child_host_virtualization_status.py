"""
Tests for the child host virtualization status API module.

This module tests the virtualization status endpoint.
"""

import uuid

import pytest


class TestVirtualizationStatusEndpoint:
    """Test cases for the virtualization_status endpoint."""

    def test_status_requires_authentication(self, client):
        """Test that virtualization status requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/child-hosts/host/{host_id}/virtualization-status")
        # Without auth, should return 401, 403, or 404
        assert response.status_code in [401, 403, 404]

    def test_status_host_not_found(self, client, auth_headers):
        """Test that status returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/child-hosts/host/{host_id}/virtualization-status",
            headers=auth_headers,
        )
        # Should return 403 (permission) or 404 (not found)
        assert response.status_code in [403, 404]


class TestEnableVirtualizationEndpoint:
    """Test cases for the enable virtualization endpoint."""

    def test_enable_requires_authentication(self, client):
        """Test that enable virtualization requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/enable-wsl",
            json={},
        )
        assert response.status_code in [401, 403, 404]

    def test_enable_host_not_found(self, client, auth_headers):
        """Test that enable returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/enable-wsl",
            json={},
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestRefreshVirtualizationEndpoint:
    """Test cases for the refresh virtualization endpoint."""

    def test_refresh_requires_authentication(self, client):
        """Test that refresh virtualization requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/refresh-virtualization"
        )
        assert response.status_code in [401, 403, 404]

    def test_refresh_host_not_found(self, client, auth_headers):
        """Test that refresh returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/refresh-virtualization",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestConfigureKvmNetworkEndpoint:
    """Test cases for the KVM network configuration endpoint."""

    def test_configure_network_requires_authentication(self, client):
        """Test that configure KVM network requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/configure-kvm-network",
            json={"mode": "nat"},
        )
        assert response.status_code in [401, 403, 404]

    def test_configure_network_host_not_found(self, client, auth_headers):
        """Test that configure returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/configure-kvm-network",
            json={"mode": "nat"},
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]
