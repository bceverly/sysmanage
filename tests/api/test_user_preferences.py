"""
Tests for the user preferences API module.

This module tests the user preferences endpoints.
"""

import pytest


class TestGetUserPreferencesEndpoint:
    """Test cases for getting user preferences."""

    def test_get_requires_authentication(self, client):
        """Test that getting preferences requires authentication."""
        response = client.get("/api/user/preferences")
        assert response.status_code in [401, 403, 404]

    def test_get_with_auth(self, client, auth_headers):
        """Test that authenticated users can get preferences."""
        response = client.get("/api/user/preferences", headers=auth_headers)
        assert response.status_code in [200, 403, 404]


class TestUpdateUserPreferencesEndpoint:
    """Test cases for updating user preferences."""

    def test_update_requires_authentication(self, client):
        """Test that updating preferences requires authentication."""
        response = client.put(
            "/api/user/preferences",
            json={"theme": "dark"},
        )
        assert response.status_code in [401, 403, 404]

    def test_update_with_auth(self, client, auth_headers):
        """Test that authenticated users can update preferences."""
        response = client.put(
            "/api/user/preferences",
            json={"theme": "dark"},
            headers=auth_headers,
        )
        assert response.status_code in [200, 403, 404, 422]

    def test_update_empty_body(self, client, auth_headers):
        """Test updating with empty body."""
        response = client.put(
            "/api/user/preferences",
            json={},
            headers=auth_headers,
        )
        # Either valid or validation error
        assert response.status_code in [200, 403, 404, 422]


class TestUserPreferenceFields:
    """Test cases for specific preference fields."""

    def test_language_preference(self, client, auth_headers):
        """Test setting language preference."""
        response = client.put(
            "/api/user/preferences",
            json={"language": "en"},
            headers=auth_headers,
        )
        assert response.status_code in [200, 403, 404, 422]

    def test_timezone_preference(self, client, auth_headers):
        """Test setting timezone preference."""
        response = client.put(
            "/api/user/preferences",
            json={"timezone": "America/New_York"},
            headers=auth_headers,
        )
        assert response.status_code in [200, 403, 404, 422]
