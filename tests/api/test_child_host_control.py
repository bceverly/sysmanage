"""
Tests for the child host control API module.

This module tests the child host start, stop, and restart
API endpoints with focus on authentication and basic endpoint behavior.
"""

import uuid


class TestStartChildHostEndpoint:
    """Test cases for the start_child_host endpoint."""

    def test_start_child_requires_authentication(self, client):
        """Test that start_child_host requires authentication."""
        host_id = str(uuid.uuid4())
        child_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/children/{child_id}/start"
        )
        assert response.status_code in [401, 403, 404]

    def test_start_child_parent_not_found(self, client, auth_headers):
        """Test that start returns error for non-existent parent."""
        host_id = str(uuid.uuid4())
        child_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/children/{child_id}/start",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestStopChildHostEndpoint:
    """Test cases for the stop_child_host endpoint."""

    def test_stop_child_requires_authentication(self, client):
        """Test that stop_child_host requires authentication."""
        host_id = str(uuid.uuid4())
        child_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/children/{child_id}/stop"
        )
        assert response.status_code in [401, 403, 404]

    def test_stop_child_parent_not_found(self, client, auth_headers):
        """Test that stop returns error for non-existent parent."""
        host_id = str(uuid.uuid4())
        child_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/children/{child_id}/stop",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestRestartChildHostEndpoint:
    """Test cases for the restart_child_host endpoint."""

    def test_restart_child_requires_authentication(self, client):
        """Test that restart_child_host requires authentication."""
        host_id = str(uuid.uuid4())
        child_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/children/{child_id}/restart"
        )
        assert response.status_code in [401, 403, 404]

    def test_restart_child_parent_not_found(self, client, auth_headers):
        """Test that restart returns error for non-existent parent."""
        host_id = str(uuid.uuid4())
        child_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/children/{child_id}/restart",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]
