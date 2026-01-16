"""
Tests for the packages operations API module.

This module tests the package management operation endpoints.
"""

import uuid

import pytest


class TestPackageInstallEndpoint:
    """Test cases for the package install endpoint."""

    def test_install_requires_authentication(self, client):
        """Test that package install requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/packages/install",
            json={"packages": ["nginx"]},
        )
        assert response.status_code in [401, 403, 404]

    def test_install_host_not_found(self, client, auth_headers):
        """Test that install returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/packages/install",
            json={"packages": ["nginx"]},
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestPackageUpdateEndpoint:
    """Test cases for the package update endpoint."""

    def test_update_requires_authentication(self, client):
        """Test that package update requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/packages/update",
            json={"packages": ["nginx"]},
        )
        assert response.status_code in [401, 403, 404]

    def test_update_host_not_found(self, client, auth_headers):
        """Test that update returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/packages/update",
            json={"packages": ["nginx"]},
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestPackageRemoveEndpoint:
    """Test cases for the package remove endpoint."""

    def test_remove_requires_authentication(self, client):
        """Test that package remove requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/packages/remove",
            json={"packages": ["nginx"]},
        )
        assert response.status_code in [401, 403, 404]

    def test_remove_host_not_found(self, client, auth_headers):
        """Test that remove returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/packages/remove",
            json={"packages": ["nginx"]},
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestPackageListEndpoint:
    """Test cases for the package list endpoint."""

    def test_list_requires_authentication(self, client):
        """Test that package list requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/host/{host_id}/packages")
        assert response.status_code in [401, 403, 404]

    def test_list_host_not_found(self, client, auth_headers):
        """Test that list returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/packages",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestPackageSearchEndpoint:
    """Test cases for the package search endpoint."""

    def test_search_requires_authentication(self, client):
        """Test that package search requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/host/{host_id}/packages/search?q=nginx")
        assert response.status_code in [401, 403, 404]
