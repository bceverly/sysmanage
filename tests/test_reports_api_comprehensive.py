"""
Comprehensive unit tests for backend.api.reports module.
Tests HTML generation, PDF generation, and API endpoint logic.
"""

import io
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException

from backend.api.reports import generate_hosts_html, generate_users_html


class TestHostsHTMLGeneration:
    """Test cases for generate_hosts_html function."""

    def test_generate_hosts_html_basic(self):
        """Test basic HTML generation for hosts."""
        # Mock host data
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

    def test_generate_hosts_html_with_tags(self):
        """Test HTML generation for hosts with tags."""
        # Mock tag
        mock_tag = Mock()
        mock_tag.name = "production"

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
                tags=[mock_tag],
            )
        ]

        html = generate_hosts_html(hosts, "hosts_with_tags", "Hosts with Tags Report")

        assert "production" in html
        assert "Tags" in html  # Column header

    def test_generate_hosts_html_empty_list(self):
        """Test HTML generation with empty hosts list."""
        html = generate_hosts_html([], "hosts", "Empty Report")

        assert "<!DOCTYPE html>" in html
        assert "Empty Report" in html
        assert "No hosts are currently registered" in html

    def test_generate_hosts_html_missing_fields(self):
        """Test HTML generation with hosts having missing optional fields."""
        hosts = [
            Mock(
                fqdn="host1.example.com",
                ipv4="192.168.1.1",
                ipv6=None,  # Missing IPv6
                platform="Linux",
                platform_release=None,  # Missing version
                os_details=None,
                last_access=None,  # Missing last access
                status="up",
                tags=[],
            )
        ]

        html = generate_hosts_html(hosts, "hosts", "Test Report")

        # Use HTML-safe assertion to prevent injection
        import html as html_module

        assert html_module.escape("host1.example.com") in html
        assert "N/A" in html  # Should show N/A for missing fields


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

    def test_generate_users_html_with_locked_account(self):
        """Test HTML generation for users with locked accounts."""
        users = [
            Mock(
                userid="locked@example.com",
                first_name="Locked",
                last_name="User",
                created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                last_access=None,
                failed_login_attempts=5,
                is_locked=True,
                active=False,
            )
        ]

        html = generate_users_html(users, "Users Report")

        assert "locked@example.com" in html
        assert "Locked" in html  # Account locked status

    def test_generate_users_html_empty_list(self):
        """Test HTML generation with empty users list."""
        html = generate_users_html([], "Empty Users Report")

        assert "<!DOCTYPE html>" in html
        assert "Empty Users Report" in html
        assert "No users are currently registered" in html


class TestReportsAPIEndpoints:
    """Test cases for Reports API endpoints."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_db = Mock()
        self.mock_current_user = "test_user"

    @patch("backend.api.reports.REPORTLAB_AVAILABLE", True)
    def test_view_hosts_report_success(self, authenticated_client, session):
        """Test viewing hosts report with authentication."""
        # Create a real host object in the database
        from backend.persistence.models import Host

        host = Host(
            id=1,
            fqdn="test.example.com",
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

    @patch("backend.api.reports.REPORTLAB_AVAILABLE", True)
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

    @patch("backend.api.reports.REPORTLAB_AVAILABLE", False)
    def test_generate_pdf_without_reportlab(self, authenticated_client):
        """Test PDF generation when ReportLab is not available."""
        response = authenticated_client.get("/api/reports/generate/registered-hosts")

        assert response.status_code == 500
        assert "PDF generation is not available" in response.json()["detail"]

    @patch("backend.api.reports.REPORTLAB_AVAILABLE", True)
    def test_generate_pdf_hosts_success(self, authenticated_client, session):
        """Test successful PDF generation for hosts."""
        from backend.api.reports import HostsReportGenerator
        import io

        # Create real host data in database
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

        # Mock the PDF generation method to return fake PDF content
        with patch.object(HostsReportGenerator, "generate_hosts_report") as mock_gen:
            # Create a fake PDF buffer
            fake_pdf = io.BytesIO(b"%PDF-1.4 fake pdf content")
            mock_gen.return_value = fake_pdf

            response = authenticated_client.get(
                "/api/reports/generate/registered-hosts"
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/pdf"
            assert "attachment; filename=" in response.headers["content-disposition"]
            mock_gen.assert_called_once()

    def test_generate_pdf_invalid_report_type(self, authenticated_client):
        """Test PDF generation with invalid report type."""
        response = authenticated_client.get("/api/reports/generate/invalid_type")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_screenshots_endpoint(self, authenticated_client):
        """Test screenshots endpoint returns placeholder."""
        response = authenticated_client.get("/api/reports/screenshots/test_report")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/svg+xml"

    def test_unauthenticated_access(self, client):
        """Test that unauthenticated requests are rejected."""
        response = client.get("/api/reports/view/registered-hosts")
        assert response.status_code == 403

        response = client.get("/api/reports/generate/hosts")
        assert response.status_code == 403

        # Screenshots endpoint is public for UI cards
        response = client.get("/api/reports/screenshots/test")
        assert response.status_code == 200


class TestReportsPDFGeneration:
    """Test cases for PDF generation functionality."""

    @patch("backend.api.reports.REPORTLAB_AVAILABLE", True)
    @patch("backend.api.reports.getSampleStyleSheet")
    def test_hosts_report_generator_creation(self, mock_styles, session):
        """Test creation of HostsReportGenerator."""
        from backend.api.reports import HostsReportGenerator

        mock_styles.return_value = {
            "Title": Mock(),
            "Heading1": Mock(),
            "Normal": Mock(),
        }

        generator = HostsReportGenerator(session)

        assert generator.db == session
        assert generator.styles is not None

    @patch("backend.api.reports.REPORTLAB_AVAILABLE", True)
    @patch("backend.api.reports.getSampleStyleSheet")
    def test_users_report_generator_creation(self, mock_styles, session):
        """Test creation of UsersReportGenerator."""
        from backend.api.reports import UsersReportGenerator

        mock_styles.return_value = {
            "Title": Mock(),
            "Heading1": Mock(),
            "Normal": Mock(),
        }

        generator = UsersReportGenerator(session)

        assert generator.db == session
        assert generator.styles is not None


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

    @patch("backend.api.reports._")
    def test_users_html_uses_i18n(self, mock_gettext):
        """Test that users HTML generation uses internationalization."""
        mock_gettext.side_effect = lambda x: f"TRANSLATED_{x}"

        users = [
            Mock(
                userid="test@example.com",
                first_name="Test",
                last_name="User",
                created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                last_access=None,
                failed_login_attempts=0,
                is_locked=False,
                active=True,
            )
        ]

        html = generate_users_html(users, "Test Report")

        # Verify that translation function was called
        mock_gettext.assert_called()

        # Check that translated strings appear in HTML
        assert "TRANSLATED_" in html


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

    @patch("backend.api.reports.REPORTLAB_AVAILABLE", True)
    @patch("backend.api.reports.SimpleDocTemplate")
    def test_pdf_generation_error_handling(
        self, mock_doc, authenticated_client, session
    ):
        """Test handling of PDF generation errors."""
        # Mock PDF generation to raise an exception
        mock_doc.side_effect = Exception("PDF generation error")

        # Create real host data in database
        from backend.persistence.models import Host

        host = Host(
            id=1,
            fqdn="test.example.com",
            active=True,
            host_token="test-token",
        )
        session.add(host)
        session.commit()

        response = authenticated_client.get("/api/reports/generate/registered-hosts")

        assert response.status_code == 500
        assert "Error generating PDF report" in response.json()["detail"]

    def test_hosts_with_tags_query_error(self, authenticated_client, session):
        """Test error handling for hosts-with-tags query."""
        # Mock the session to raise an exception for queries
        with patch.object(session, "query", side_effect=Exception("Join error")):
            response = authenticated_client.get("/api/reports/view/hosts-with-tags")

            assert response.status_code == 500
            assert "Internal server error" in response.json()["detail"]
