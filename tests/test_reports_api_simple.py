"""
Unit tests for backend.api.reports module - focused on core functionality.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from backend.api.reports import generate_hosts_html, generate_users_html


class TestHostsHTMLGeneration:
    """Test cases for generate_hosts_html function."""

    def test_generate_hosts_html_basic(self):
        """Test basic HTML generation for hosts."""
        # Mock host data with correct field names
        hosts = [
            Mock(
                fqdn="host1.example.com",
                ipv4="192.168.1.1",
                ipv6="2001:db8::1",
                platform="Linux",
                platform_release="Ubuntu 22.04",
                os_details=None,
                last_access=datetime(2024, 1, 2, tzinfo=timezone.utc),
                status="up",
                tags=[],
            )
        ]

        html = generate_hosts_html(hosts, "hosts", "Test Report")

        assert "<!DOCTYPE html>" in html
        assert "Test Report" in html
        # Use HTML-safe assertion to prevent injection
        import html as html_module

        assert html_module.escape("host1.example.com") in html
        assert "192.168.1.1" in html
        assert "Ubuntu 22.04" in html

    def test_generate_hosts_html_empty_list(self):
        """Test HTML generation with empty hosts list."""
        html = generate_hosts_html([], "hosts", "Empty Report")

        assert "<!DOCTYPE html>" in html
        assert "Empty Report" in html
        # Should handle empty list gracefully


class TestUsersHTMLGeneration:
    """Test cases for generate_users_html function."""

    def test_generate_users_html_basic(self):
        """Test basic HTML generation for users."""
        users = [
            Mock(
                userid="user1@example.com",
                first_name="John",
                last_name="Doe",
                created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                last_access=datetime(2024, 1, 2, tzinfo=timezone.utc),
                failed_login_attempts=0,
                is_locked=False,
                active=True,
            )
        ]

        html = generate_users_html(users, "Users Report")

        assert "<!DOCTYPE html>" in html
        assert "Users Report" in html
        assert "user1@example.com" in html
        assert "John" in html
        assert "Doe" in html

    def test_generate_users_html_empty_list(self):
        """Test HTML generation with empty users list."""
        html = generate_users_html([], "Empty Users Report")

        assert "<!DOCTYPE html>" in html
        assert "Empty Users Report" in html
        # Should handle empty list gracefully


class TestReportsInternationalization:
    """Test cases for Reports i18n functionality."""

    @patch("backend.api.reports._")
    def test_html_generation_uses_i18n(self, mock_gettext):
        """Test that HTML generation uses internationalization."""
        mock_gettext.side_effect = lambda x: f"TRANSLATED_{x}"

        hosts = [
            Mock(
                fqdn="test.example.com",
                ipv4="192.168.1.1",
                ipv6=None,
                platform="Linux",
                platform_release="Ubuntu 22.04",
                os_details=None,
                last_access=datetime(2024, 1, 2, tzinfo=timezone.utc),
                status="up",
                tags=[],
            )
        ]

        html = generate_hosts_html(hosts, "hosts", "Test Report")

        # Verify that translation function was called
        mock_gettext.assert_called()

        # Check that translated strings appear in HTML
        assert "TRANSLATED_" in html


class TestReportsAPIEndpointsSimple:
    """Simple test cases for Reports API endpoints."""

    def test_view_hosts_report_success(self, authenticated_client, session):
        """Test viewing hosts report with authentication."""
        # Create a real host object in the database
        from backend.persistence.models import Host

        host = Host(
            id=1,
            fqdn="test.example.com",
            ipv4="192.168.1.1",
            platform="Linux",
            active=True,
            host_token="test-token",
        )
        session.add(host)
        session.commit()

        response = authenticated_client.get("/api/reports/view/registered-hosts")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        # Use HTML-safe assertion to prevent injection
        import html as html_module

        assert html_module.escape("test.example.com") in response.text

    def test_view_users_report_success(self, authenticated_client, session):
        """Test viewing users report with authentication."""
        # Create a real user object in the database
        from backend.persistence.models import User

        user = User(
            id=1,
            userid="test@example.com",
            first_name="Test",
            last_name="User",
            hashed_password="test-hash",
            active=True,
            is_locked=False,
            failed_login_attempts=0,
        )
        session.add(user)
        session.commit()

        response = authenticated_client.get("/api/reports/view/users-list")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        # Use HTML-safe assertion to prevent injection
        import html as html_module

        assert html_module.escape("test@example.com") in response.text

    def test_view_invalid_report_type(self, authenticated_client):
        """Test viewing report with invalid report type."""
        response = authenticated_client.get("/api/reports/view/invalid_type")

        assert response.status_code == 400
        assert "Invalid report type" in response.json()["detail"]

    def test_screenshots_endpoint(self, authenticated_client):
        """Test screenshots endpoint returns placeholder."""
        response = authenticated_client.get("/api/reports/screenshots/test_report")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/svg+xml"

    def test_unauthenticated_access(self):
        """Test that unauthenticated requests are rejected."""
        # Create an unauthenticated client without the auth fixture
        from fastapi.testclient import TestClient
        from backend.main import app
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_lifespan(app):
            yield

        original_lifespan = app.router.lifespan_context
        app.router.lifespan_context = mock_lifespan

        try:
            with TestClient(app) as unauthenticated_client:
                response = unauthenticated_client.get(
                    "/api/reports/view/registered-hosts"
                )
                assert response.status_code == 403

                response = unauthenticated_client.get("/api/reports/generate/hosts")
                assert response.status_code == 403

                # Screenshots endpoint is public for UI cards
                response = unauthenticated_client.get("/api/reports/screenshots/test")
                assert response.status_code == 200
        finally:
            app.router.lifespan_context = original_lifespan

    @patch("backend.api.reports.REPORTLAB_AVAILABLE", False)
    def test_generate_pdf_without_reportlab(self, authenticated_client):
        """Test PDF generation when ReportLab is not available."""
        response = authenticated_client.get("/api/reports/generate/hosts")

        assert response.status_code == 500
        assert "PDF generation is not available" in response.json()["detail"]

    def test_generate_pdf_invalid_report_type(self, authenticated_client):
        """Test PDF generation with invalid report type."""
        response = authenticated_client.get("/api/reports/generate/invalid_type")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestReportsErrorHandling:
    """Test cases for Reports error handling."""

    @patch("backend.api.reports.REPORTLAB_AVAILABLE", True)
    def test_database_error_handling(self, authenticated_client, session):
        """Test handling of database errors."""
        # Mock the session to raise an exception
        with patch.object(session, "query", side_effect=Exception("Database error")):
            response = authenticated_client.get("/api/reports/view/registered-hosts")

            assert response.status_code == 500
            assert "Internal server error" in response.json()["detail"]
