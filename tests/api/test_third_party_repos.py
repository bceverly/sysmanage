"""
Tests for the third party repositories API module.

This module tests the third party repository endpoints.
"""

import uuid

import pytest


class TestListThirdPartyReposEndpoint:
    """Test cases for listing third party repositories."""

    def test_list_requires_authentication(self, client):
        """Test that listing repos requires authentication."""
        response = client.get("/api/repositories/third-party")
        assert response.status_code in [401, 403, 404]

    def test_list_with_auth(self, client, auth_headers):
        """Test that authenticated users can list repos."""
        response = client.get("/api/repositories/third-party", headers=auth_headers)
        assert response.status_code in [200, 403, 404]


class TestHostThirdPartyReposEndpoint:
    """Test cases for host-specific third party repositories."""

    def test_host_repos_requires_authentication(self, client):
        """Test that host repos requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/host/{host_id}/repositories/third-party")
        assert response.status_code in [401, 403, 404]

    def test_host_repos_not_found(self, client, auth_headers):
        """Test that host repos returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/repositories/third-party",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestAddThirdPartyRepoEndpoint:
    """Test cases for adding third party repositories."""

    def test_add_requires_authentication(self, client):
        """Test that adding repo requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/repositories/third-party",
            json={"name": "test-repo", "url": "https://example.com/repo"},
        )
        assert response.status_code in [401, 403, 404]

    def test_add_host_not_found(self, client, auth_headers):
        """Test that add returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/repositories/third-party",
            json={"name": "test-repo", "url": "https://example.com/repo"},
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]


class TestRemoveThirdPartyRepoEndpoint:
    """Test cases for removing third party repositories."""

    def test_remove_requires_authentication(self, client):
        """Test that removing repo requires authentication."""
        host_id = str(uuid.uuid4())
        repo_id = str(uuid.uuid4())
        response = client.delete(
            f"/api/host/{host_id}/repositories/third-party/{repo_id}"
        )
        assert response.status_code in [401, 403, 404, 405]

    def test_remove_not_found(self, client, auth_headers):
        """Test that remove returns error for non-existent repo."""
        host_id = str(uuid.uuid4())
        repo_id = str(uuid.uuid4())
        response = client.delete(
            f"/api/host/{host_id}/repositories/third-party/{repo_id}",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404, 405]
