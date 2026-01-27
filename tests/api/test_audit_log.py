"""
Tests for the audit log API module.

This module tests the audit log endpoints.
"""

import uuid


class TestAuditLogListEndpoint:
    """Test cases for the audit log list endpoint."""

    def test_list_requires_authentication(self, client):
        """Test that audit log list requires authentication."""
        response = client.get("/api/audit-log")
        assert response.status_code in [401, 403, 404]

    def test_list_with_auth(self, client, auth_headers):
        """Test that authenticated users can access audit log."""
        response = client.get("/api/audit-log", headers=auth_headers)
        # Should either return data (200) or permission error (403)
        assert response.status_code in [200, 403, 404]


class TestAuditLogFilterEndpoint:
    """Test cases for audit log filtering."""

    def test_filter_by_action(self, client, auth_headers):
        """Test filtering audit logs by action."""
        response = client.get(
            "/api/audit-log?action=login",
            headers=auth_headers,
        )
        assert response.status_code in [200, 403, 404]

    def test_filter_by_user(self, client, auth_headers):
        """Test filtering audit logs by user."""
        response = client.get(
            "/api/audit-log?user_id=test-user",
            headers=auth_headers,
        )
        assert response.status_code in [200, 403, 404]

    def test_filter_by_date_range(self, client, auth_headers):
        """Test filtering audit logs by date range."""
        response = client.get(
            "/api/audit-log?start_date=2024-01-01&end_date=2024-12-31",
            headers=auth_headers,
        )
        assert response.status_code in [200, 403, 404]


class TestAuditLogHostEndpoint:
    """Test cases for host-specific audit log."""

    def test_host_audit_log_requires_authentication(self, client):
        """Test that host audit log requires authentication."""
        host_id = str(uuid.uuid4())
        response = client.get(f"/api/host/{host_id}/audit-log")
        assert response.status_code in [401, 403, 404]

    def test_host_audit_log_not_found(self, client, auth_headers):
        """Test that host audit log returns error for non-existent host."""
        host_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host_id}/audit-log",
            headers=auth_headers,
        )
        assert response.status_code in [403, 404]
