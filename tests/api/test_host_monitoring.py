"""
Tests for the host monitoring API module.

This module tests the host monitoring endpoints.
"""

import uuid

import pytest


class TestHostMonitoringStatusEndpoint:
    """Test cases for the host monitoring status endpoint."""

    def test_status_requires_authentication(self, client):
        """Test that monitoring status requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/host/{host_id}/monitoring")
        assert response.status_code in [401, 403, 404]

    def test_status_host_not_found(self, client, auth_headers):
        """Test that status returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/monitoring",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestMonitoringConfigEndpoint:
    """Test cases for monitoring configuration."""

    def test_config_requires_authentication(self, client):
        """Test that monitoring config requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/host/{host_id}/monitoring/config")
        assert response.status_code in [401, 403, 404]

    def test_update_config_requires_authentication(self, client):
        """Test that updating monitoring config requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.put(
            f"/api/host/{host_id}/monitoring/config",
            json={"enabled": True},
        )
        assert response.status_code in [401, 403, 404]


class TestMonitoringAlertsEndpoint:
    """Test cases for monitoring alerts."""

    def test_alerts_requires_authentication(self, client):
        """Test that monitoring alerts requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/host/{host_id}/monitoring/alerts")
        assert response.status_code in [401, 403, 404]

    def test_alerts_host_not_found(self, client, auth_headers):
        """Test that alerts returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/monitoring/alerts",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]
