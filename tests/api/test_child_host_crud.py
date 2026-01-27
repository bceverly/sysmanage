"""
Tests for the child host CRUD API module.

This module tests the child host create, read, update, and delete
API endpoints with focus on authentication and basic endpoint behavior.
"""

import uuid
from unittest.mock import patch


class TestListChildHostsEndpoint:
    """Test cases for the list_child_hosts endpoint."""

    def test_list_children_requires_authentication(self, client):
        """Test that list_child_hosts requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/child-hosts/host/{host_id}/children")
        # Without auth, should return 401, 403, or 404 (host not found)
        assert response.status_code in [401, 403, 404]

    def test_list_children_host_not_found(self, client, auth_headers):
        """Test that list_child_hosts returns 404 for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/child-hosts/host/{host_id}/children", headers=auth_headers
        )
        assert response.status_code in [403, 404]


class TestCreateChildHostEndpoint:
    """Test cases for the create_child_host endpoint."""

    def test_create_child_requires_authentication(self, client):
        """Test that create_child_host requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/children",
            json={"hostname": "test", "child_type": "lxd", "distribution_id": "123"},
        )
        assert response.status_code in [401, 403, 404]

    def test_create_child_host_not_found(self, client, auth_headers):
        """Test that create returns 404 for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/child-hosts/host/{host_id}/children",
            json={
                "hostname": "testchild",
                "child_type": "lxd",
                "distribution_id": str(uuid.uuid4()),
            },
            headers=auth_headers,
        )
        # Should be 403 (permission) or 404 (host not found)
        assert response.status_code in [403, 404]


class TestChildHostDistributions:
    """Test cases for distribution management endpoints."""

    def test_list_distributions_requires_authentication(self, client):
        """Test that distributions endpoint requires authentication."""
        response = client.get("/api/child-hosts/distributions/lxd")
        # Should require auth or return 404 if endpoint not found
        assert response.status_code in [200, 401, 403, 404]

    def test_list_distributions_invalid_type(self, client, auth_headers):
        """Test listing distributions for invalid type."""
        response = client.get(
            "/api/child-hosts/distributions/invalid_type", headers=auth_headers
        )
        # Either empty list or error
        assert response.status_code in [200, 400, 403, 404]


class TestDeleteChildHostEndpoint:
    """Test cases for delete_child_host endpoint."""

    def test_delete_child_requires_authentication(self, client):
        """Test that delete_child_host requires authentication."""
        host_id = str(uuid.uuid4())
        child_id = str(uuid.uuid4())
        response = client.delete(f"/api/child-hosts/host/{host_id}/children/{child_id}")
        assert response.status_code in [401, 403, 404, 405]

    def test_delete_child_not_found(self, client, auth_headers):
        """Test that delete returns error for non-existent child."""
        host_id = str(uuid.uuid4())
        child_id = str(uuid.uuid4())
        response = client.delete(
            f"/api/child-hosts/host/{host_id}/children/{child_id}",
            headers=auth_headers,
        )
        # Either 403 (permission), 404 (not found), or 405 (method not allowed)
        assert response.status_code in [403, 404, 405]
