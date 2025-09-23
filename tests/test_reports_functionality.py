"""
Basic functionality tests for the Reports feature.
Tests the core functionality without complex mocking.
"""

from unittest.mock import patch

import pytest


class TestReportsBasicFunctionality:
    """Basic tests to ensure Reports functionality works."""

    def test_reports_module_imports(self):
        """Test that the reports module can be imported."""
        from backend.api import reports

        assert reports is not None

    def test_reports_router_configuration(self):
        """Test that the router is properly configured."""
        from backend.api.reports import router

        assert router.prefix == "/api/reports"
        assert "reports" in router.tags

    def test_html_generation_functions_exist(self):
        """Test that HTML generation functions exist."""
        from backend.api.reports import generate_hosts_html, generate_users_html

        assert callable(generate_hosts_html)
        assert callable(generate_users_html)

    @patch("backend.api.reports._")
    def test_basic_html_generation(self, mock_gettext):
        """Test basic HTML generation with minimal mocking."""
        from backend.api.reports import generate_hosts_html, generate_users_html

        # Mock the translation function to return input
        mock_gettext.side_effect = lambda x: x

        # Test with empty lists
        hosts_html = generate_hosts_html([], "hosts", "Test Report")
        users_html = generate_users_html([], "Test Report")

        # Basic assertions
        assert "<!DOCTYPE html>" in hosts_html
        assert "<!DOCTYPE html>" in users_html
        assert "Test Report" in hosts_html
        assert "Test Report" in users_html

    def test_authentication_required(self):
        """Test that endpoints require authentication."""
        # Create an unauthenticated client without the auth fixture
        from contextlib import asynccontextmanager

        from fastapi.testclient import TestClient

        from backend.main import app

        @asynccontextmanager
        async def mock_lifespan(app):
            yield

        original_lifespan = app.router.lifespan_context
        app.router.lifespan_context = mock_lifespan

        try:
            with TestClient(app) as unauthenticated_client:
                # Test that protected endpoints return 403 without auth
                protected_endpoints = [
                    "/api/reports/view/registered-hosts",
                    "/api/reports/view/users-list",
                    "/api/reports/generate/hosts",
                    "/api/reports/generate/users",
                ]

                for endpoint in protected_endpoints:
                    response = unauthenticated_client.get(endpoint)
                    assert response.status_code == 403

                # Screenshots endpoint is public for UI cards
                response = unauthenticated_client.get("/api/reports/screenshots/test")
                assert response.status_code == 200
        finally:
            app.router.lifespan_context = original_lifespan

    def test_invalid_report_types(self, authenticated_client):
        """Test handling of invalid report types."""
        # View endpoints return 400 for invalid report types
        response = authenticated_client.get("/api/reports/view/invalid")
        assert response.status_code == 400

        # Generate endpoints return 404 for invalid report types
        response = authenticated_client.get("/api/reports/generate/invalid")
        assert response.status_code == 404

    @patch("backend.api.reports.REPORTLAB_AVAILABLE", False)
    def test_pdf_without_reportlab(self, authenticated_client):
        """Test PDF generation without ReportLab."""
        response = authenticated_client.get("/api/reports/generate/hosts")
        assert response.status_code == 500
        assert "PDF generation is not available" in response.json()["detail"]


class TestReportsWithRealData:
    """Test reports with actual database data."""

    def test_hosts_report_with_data(self, authenticated_client, session):
        """Test hosts report with real data."""
        from datetime import datetime, timezone

        from backend.persistence.models import Host

        # Create a test host
        host = Host(
            fqdn="test.example.com",
            ipv4="192.168.1.1",
            platform="Linux",
            active=True,
            host_token="test-token-123",
        )
        session.add(host)
        session.commit()

        response = authenticated_client.get("/api/reports/view/registered-hosts")
        assert response.status_code == 200
        # Use HTML-safe assertion to prevent injection
        import html as html_module

        assert html_module.escape("test.example.com") in response.text

    def test_users_report_with_data(self, authenticated_client, session):
        """Test users report with real data."""
        from datetime import datetime, timezone

        from backend.persistence.models import User

        # Create a test user
        now = datetime.now(timezone.utc)
        user = User(
            userid="test@example.com",
            first_name="Test",
            last_name="User",
            hashed_password="test-hash",
            active=True,
            is_locked=False,
            failed_login_attempts=0,
            last_access=now,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.commit()

        response = authenticated_client.get("/api/reports/view/users-list")
        assert response.status_code == 200
        # Use HTML-safe assertion to prevent injection
        import html as html_module

        assert html_module.escape("test@example.com") in response.text

    def test_screenshots_endpoint(self, authenticated_client):
        """Test the screenshots endpoint."""
        response = authenticated_client.get("/api/reports/screenshots/test")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/svg+xml"


class TestReportsErrorHandling:
    """Test error handling in reports."""

    def test_database_connection_error(self, authenticated_client, session):
        """Test graceful handling of database errors."""
        # This test would require more complex mocking to simulate DB failures
        # For now, just ensure the endpoint exists and responds
        response = authenticated_client.get("/api/reports/view/registered-hosts")
        # Should return 200 (success) or 500 (internal error), not 404
        assert response.status_code in [200, 500]

    def test_large_dataset_handling(self, authenticated_client, session):
        """Test that reports can handle reasonable datasets."""
        from datetime import datetime, timezone

        from backend.persistence.models import Host

        # Create multiple hosts
        hosts = []
        for i in range(5):  # Small number for test speed
            host = Host(
                fqdn=f"host{i}.example.com",
                ipv4=f"192.168.1.{i+10}",
                platform="Linux",
                active=True,
                host_token=f"token-{i}",
            )
            hosts.append(host)
            session.add(host)

        session.commit()

        response = authenticated_client.get("/api/reports/view/registered-hosts")
        assert response.status_code == 200

        # Verify all hosts appear in the report
        import html as html_module

        for i in range(5):
            # Use HTML-safe assertion to prevent injection
            assert html_module.escape(f"host{i}.example.com") in response.text
