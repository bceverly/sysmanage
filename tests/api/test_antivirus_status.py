"""
Tests for the antivirus status API module.

This module tests the antivirus status endpoints.
"""

import uuid


class TestAntivirusStatusEndpoint:
    """Test cases for the antivirus status endpoint."""

    def test_status_requires_authentication(self, client):
        """Test that antivirus status requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/host/{host_id}/antivirus-status")
        assert response.status_code in [401, 403, 404]

    def test_status_host_not_found(self, client, auth_headers):
        """Test that status returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/antivirus-status",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestAntivirusScanEndpoint:
    """Test cases for the antivirus scan endpoint."""

    def test_scan_requires_authentication(self, client):
        """Test that antivirus scan requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(f"/api/host/{host_id}/antivirus-scan")
        assert response.status_code in [401, 403, 404]

    def test_scan_host_not_found(self, client, auth_headers):
        """Test that scan returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/antivirus-scan",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestAntivirusUpdateEndpoint:
    """Test cases for the antivirus update endpoint."""

    def test_update_requires_authentication(self, client):
        """Test that antivirus update requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(f"/api/host/{host_id}/antivirus-update")
        assert response.status_code in [401, 403, 404]

    def test_update_host_not_found(self, client, auth_headers):
        """Test that update returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/antivirus-update",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]
