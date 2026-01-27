"""
Tests for the firewall status API module.

This module tests the firewall status endpoints.
"""

import uuid


class TestFirewallStatusEndpoint:
    """Test cases for the firewall status endpoint."""

    def test_status_requires_authentication(self, client):
        """Test that firewall status requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/host/{host_id}/firewall-status")
        assert response.status_code in [401, 403, 404]

    def test_status_host_not_found(self, client, auth_headers):
        """Test that status returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/firewall-status",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestFirewallEnableEndpoint:
    """Test cases for the firewall enable endpoint."""

    def test_enable_requires_authentication(self, client):
        """Test that enable firewall requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(f"/api/host/{host_id}/firewall-enable")
        assert response.status_code in [401, 403, 404]

    def test_enable_host_not_found(self, client, auth_headers):
        """Test that enable returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/firewall-enable",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestFirewallDisableEndpoint:
    """Test cases for the firewall disable endpoint."""

    def test_disable_requires_authentication(self, client):
        """Test that disable firewall requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(f"/api/host/{host_id}/firewall-disable")
        assert response.status_code in [401, 403, 404]

    def test_disable_host_not_found(self, client, auth_headers):
        """Test that disable returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/firewall-disable",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]
