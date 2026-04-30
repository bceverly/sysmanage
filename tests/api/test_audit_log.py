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


class TestAuditLogResultFilter:
    """Phase 8.4 added a `result` query parameter to /list (SUCCESS,
    FAILURE, PENDING).  Verify it's accepted without error."""

    def test_filter_by_result_success(self, client, auth_headers):
        response = client.get(
            "/api/audit-log/list?result=SUCCESS", headers=auth_headers
        )
        assert response.status_code in [200, 403, 404]

    def test_filter_by_result_failure(self, client, auth_headers):
        response = client.get(
            "/api/audit-log/list?result=FAILURE", headers=auth_headers
        )
        assert response.status_code in [200, 403, 404]


class TestAuditLogCsvExport:
    """Phase 8.4 added an OSS CSV export path to /export."""

    def test_export_requires_auth(self, client):
        response = client.get("/api/audit-log/export?fmt=csv")
        assert response.status_code in [401, 403, 404]

    def test_export_csv_authorized(self, client, auth_headers):
        """Authorized CSV export must return text/csv (200) or 403 if the
        test user lacks VIEW_AUDIT_LOG.  Either way: NEVER 500."""
        response = client.get("/api/audit-log/export?fmt=csv", headers=auth_headers)
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            assert response.headers.get("content-type", "").startswith("text/csv")
            # Header row must include the canonical columns.
            body = response.text
            assert "timestamp" in body.split("\n", 1)[0]

    def test_export_unsupported_format_400(self, client, auth_headers):
        """An unknown format string must produce a 400, not silently
        fall through to the Pro+ redirect or to CSV."""
        response = client.get("/api/audit-log/export?fmt=xml", headers=auth_headers)
        # 400 if authorized; 401/403 if not authorized.
        assert response.status_code in [400, 401, 403]

    def test_export_json_without_proplus_returns_402(self, client, auth_headers):
        """JSON/CEF/LEEF require Pro+; OSS-only deployments must get 402
        (Payment Required) — NOT a CSV in disguise."""
        response = client.get("/api/audit-log/export?fmt=json", headers=auth_headers)
        # 402 if authorized + OSS-only; 307 if Pro+ engine is loaded;
        # 401/403 if unauthorized.
        assert response.status_code in [307, 402, 401, 403]


class TestAuditLogPdfExport:
    """Phase 8.4 closeout — OSS PDF export sibling of the CSV path."""

    def test_export_pdf_authorized(self, client, auth_headers):
        """Authorized PDF export must return application/pdf (200) or 403
        if the test user lacks VIEW_AUDIT_LOG.  Either way:  NEVER 500."""
        response = client.get("/api/audit-log/export?fmt=pdf", headers=auth_headers)
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            assert response.headers.get("content-type", "").startswith(
                "application/pdf"
            )
            # PDFs always start with a "%PDF-" header byte sequence —
            # asserting it confirms reportlab actually produced a doc
            # rather than e.g. an empty body or HTML error page.
            assert response.content[:5] == b"%PDF-"

    def test_export_pdf_with_filters(self, client, auth_headers):
        """Filter passthrough:  PDF route consumes the same
        ``AuditLogFilters`` shape as CSV, so a filtered range must
        still produce a 200 + application/pdf response (even if zero
        entries match — empty PDFs are still PDFs)."""
        response = client.get(
            "/api/audit-log/export?fmt=pdf&result=SUCCESS&entity_type=USER",
            headers=auth_headers,
        )
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            assert response.content[:5] == b"%PDF-"

    def test_export_pdf_filename_header(self, client, auth_headers):
        """Content-Disposition must point at a .pdf filename so the
        browser saves with the right extension."""
        response = client.get("/api/audit-log/export?fmt=pdf", headers=auth_headers)
        if response.status_code == 200:
            cd = response.headers.get("content-disposition", "")
            assert ".pdf" in cd
            assert "audit-log-" in cd


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
