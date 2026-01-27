"""
Tests for the diagnostics API module.

This module tests the system diagnostics endpoints.
"""

import uuid


class TestDiagnosticsEndpoint:
    """Test cases for the diagnostics endpoint."""

    def test_diagnostics_requires_authentication(self, client):
        """Test that diagnostics requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/host/{host_id}/diagnostics")
        assert response.status_code in [401, 403, 404]

    def test_diagnostics_host_not_found(self, client, auth_headers):
        """Test that diagnostics returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/diagnostics",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestRequestDiagnosticsEndpoint:
    """Test cases for requesting diagnostics."""

    def test_request_requires_authentication(self, client):
        """Test that requesting diagnostics requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(f"/api/host/{host_id}/request-diagnostics")
        assert response.status_code in [401, 403, 404]

    def test_request_host_not_found(self, client, auth_headers):
        """Test that request returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/request-diagnostics",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestDiagnosticsHistory:
    """Test cases for diagnostics history."""

    def test_history_requires_authentication(self, client):
        """Test that diagnostics history requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/host/{host_id}/diagnostics/history")
        assert response.status_code in [401, 403, 404]

    def test_history_host_not_found(self, client, auth_headers):
        """Test that history returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/diagnostics/history",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]
