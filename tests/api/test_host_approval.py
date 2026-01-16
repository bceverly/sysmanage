"""
Tests for the host approval API module.

This module tests the host approval, rejection, and OS update request
API endpoints.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.persistence.models import Host, User, HostChild


class TestApproveHostEndpoint:
    """Test cases for the approve_host endpoint."""

    def test_approve_host_requires_authentication(self, client):
        """Test that approve_host requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.put(f"/api/host/{host_id}/approve")
        # Without auth, should be 401 (Unauthorized) or 403 (Forbidden)
        assert response.status_code in [401, 403]

    def test_approve_host_not_found(self, client, auth_headers):
        """Test that approve_host returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.put(f"/api/host/{host_id}/approve", headers=auth_headers)
        # Could be 403 (no permission) or 404 (not found) depending on auth
        assert response.status_code in [401, 403, 404]


class TestRejectHostEndpoint:
    """Test cases for the reject_host endpoint."""

    def test_reject_host_requires_authentication(self, client):
        """Test that reject_host requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.put(f"/api/host/{host_id}/reject")
        # Without auth, should be 401 (Unauthorized) or 403 (Forbidden)
        assert response.status_code in [401, 403]

    def test_reject_host_not_found(self, client, auth_headers):
        """Test that reject_host returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.put(f"/api/host/{host_id}/reject", headers=auth_headers)
        # Could be 401 (no permission) or 404 (not found)
        assert response.status_code in [401, 403, 404]


class TestRequestOsUpdateEndpoint:
    """Test cases for the request_os_version_update endpoint."""

    def test_request_os_update_requires_authentication(self, client):
        """Test that request-os-update requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(f"/api/host/{host_id}/request-os-update")
        # Without auth, should be 401 (Unauthorized) or 403 (Forbidden)
        assert response.status_code in [401, 403]

    def test_request_os_update_not_found(self, client, auth_headers):
        """Test that request-os-update returns 404 for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/request-os-update", headers=auth_headers
        )
        assert response.status_code == 404


class TestRequestUpdatesCheckEndpoint:
    """Test cases for the request_updates_check endpoint."""

    def test_request_updates_check_requires_authentication(self, client):
        """Test that request-updates-check requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.post(f"/api/host/{host_id}/request-updates-check")
        # Without auth, should be 401 (Unauthorized) or 403 (Forbidden)
        assert response.status_code in [401, 403]

    def test_request_updates_check_not_found(self, client, auth_headers):
        """Test that request-updates-check returns 404 for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.post(
            f"/api/host/{host_id}/request-updates-check", headers=auth_headers
        )
        assert response.status_code == 404
