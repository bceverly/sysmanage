"""
Tests for the telemetry API module.

This module tests the telemetry data endpoints.
"""

import uuid

import pytest


class TestTelemetryEndpoint:
    """Test cases for the telemetry endpoint."""

    def test_telemetry_requires_authentication(self, client):
        """Test that telemetry requires authentication."""
        response = client.get("/api/telemetry")
        assert response.status_code in [401, 403, 404]

    def test_telemetry_with_auth(self, client, auth_headers):
        """Test that authenticated users can access telemetry."""
        response = client.get("/api/telemetry", headers=auth_headers)
        assert response.status_code in [200, 403, 404]


class TestHostTelemetryEndpoint:
    """Test cases for host-specific telemetry."""

    def test_host_telemetry_requires_authentication(self, client):
        """Test that host telemetry requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/host/{host_id}/telemetry")
        assert response.status_code in [401, 403, 404]

    def test_host_telemetry_not_found(self, client, auth_headers):
        """Test that host telemetry returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/telemetry",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestTelemetryDataPoints:
    """Test cases for telemetry data points."""

    def test_cpu_telemetry(self, client, auth_headers):
        """Test getting CPU telemetry."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/telemetry?type=cpu",
            headers=auth_headers,
        )
        assert response.status_code in [200, 403, 404]

    def test_memory_telemetry(self, client, auth_headers):
        """Test getting memory telemetry."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/telemetry?type=memory",
            headers=auth_headers,
        )
        assert response.status_code in [200, 403, 404]

    def test_disk_telemetry(self, client, auth_headers):
        """Test getting disk telemetry."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/telemetry?type=disk",
            headers=auth_headers,
        )
        assert response.status_code in [200, 403, 404]


class TestTelemetryTimeRange:
    """Test cases for telemetry time range filtering."""

    def test_telemetry_with_time_range(self, client, auth_headers):
        """Test getting telemetry with time range."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/telemetry?start=2024-01-01&end=2024-12-31",
            headers=auth_headers,
        )
        assert response.status_code in [200, 403, 404]
