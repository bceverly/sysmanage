"""
Tests for backend/api/reports/endpoints.py module.
Tests report generation API endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestReportType:
    """Tests for ReportType enum."""

    def test_registered_hosts_value(self):
        """Test REGISTERED_HOSTS has correct value."""
        from backend.api.reports.endpoints import ReportType

        assert ReportType.REGISTERED_HOSTS.value == "registered-hosts"

    def test_hosts_with_tags_value(self):
        """Test HOSTS_WITH_TAGS has correct value."""
        from backend.api.reports.endpoints import ReportType

        assert ReportType.HOSTS_WITH_TAGS.value == "hosts-with-tags"

    def test_users_list_value(self):
        """Test USERS_LIST has correct value."""
        from backend.api.reports.endpoints import ReportType

        assert ReportType.USERS_LIST.value == "users-list"

    def test_firewall_status_value(self):
        """Test FIREWALL_STATUS has correct value."""
        from backend.api.reports.endpoints import ReportType

        assert ReportType.FIREWALL_STATUS.value == "firewall-status"

    def test_antivirus_opensource_value(self):
        """Test ANTIVIRUS_OPENSOURCE has correct value."""
        from backend.api.reports.endpoints import ReportType

        assert ReportType.ANTIVIRUS_OPENSOURCE.value == "antivirus-opensource"

    def test_antivirus_commercial_value(self):
        """Test ANTIVIRUS_COMMERCIAL has correct value."""
        from backend.api.reports.endpoints import ReportType

        assert ReportType.ANTIVIRUS_COMMERCIAL.value == "antivirus-commercial"

    def test_user_rbac_value(self):
        """Test USER_RBAC has correct value."""
        from backend.api.reports.endpoints import ReportType

        assert ReportType.USER_RBAC.value == "user-rbac"

    def test_audit_log_value(self):
        """Test AUDIT_LOG has correct value."""
        from backend.api.reports.endpoints import ReportType

        assert ReportType.AUDIT_LOG.value == "audit-log"


class TestViewReportHtml:
    """Tests for view_report_html endpoint."""

    @patch("backend.api.reports.endpoints.generate_hosts_html")
    @patch("backend.api.reports.endpoints.sessionmaker")
    def test_view_registered_hosts_success(self, mock_sessionmaker, mock_generate_html):
        """Test successful HTML report generation for registered hosts."""
        from backend.api.reports.endpoints import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        # Mock user with VIEW_REPORT role
        mock_user = MagicMock()
        mock_user.userid = "admin@example.com"
        mock_user._role_cache = ["VIEW_REPORT"]
        mock_user.has_role.return_value = True

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        mock_generate_html.return_value = "<html><body>Test Report</body></html>"

        mock_db = MagicMock()
        mock_db.query.return_value.order_by.return_value.all.return_value = []
        mock_db.get_bind.return_value = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: "admin@example.com"
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.get("/api/reports/view/registered-hosts")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @patch("backend.api.reports.endpoints.sessionmaker")
    def test_view_report_user_not_found(self, mock_sessionmaker):
        """Test report viewing when user not found."""
        from backend.api.reports.endpoints import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        mock_db = MagicMock()
        mock_db.get_bind.return_value = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: "unknown@example.com"
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.get("/api/reports/view/registered-hosts")

        assert response.status_code == 401

    @patch("backend.api.reports.endpoints.sessionmaker")
    def test_view_report_permission_denied(self, mock_sessionmaker):
        """Test report viewing when user lacks permission."""
        from backend.api.reports.endpoints import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        mock_user = MagicMock()
        mock_user.userid = "user@example.com"
        mock_user._role_cache = []
        mock_user.has_role.return_value = False

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        mock_db = MagicMock()
        mock_db.get_bind.return_value = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: "user@example.com"
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.get("/api/reports/view/registered-hosts")

        assert response.status_code == 403

    def test_view_report_invalid_type(self):
        """Test report viewing with invalid report type."""
        from backend.api.reports.endpoints import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        mock_db = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: "admin@example.com"
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.get("/api/reports/view/invalid-report-type")

        assert response.status_code == 422


class TestGenerateReport:
    """Tests for generate_report endpoint."""

    @patch("backend.api.reports.endpoints.REPORTLAB_AVAILABLE", False)
    @patch("backend.api.reports.endpoints.sessionmaker")
    def test_generate_pdf_reportlab_not_available(self, mock_sessionmaker):
        """Test PDF generation when reportlab not available."""
        from backend.api.reports.endpoints import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        mock_user = MagicMock()
        mock_user.userid = "admin@example.com"
        mock_user._role_cache = ["GENERATE_PDF_REPORT"]
        mock_user.has_role.return_value = True

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        mock_db = MagicMock()
        mock_db.get_bind.return_value = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: "admin@example.com"
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.get("/api/reports/generate/registered-hosts")

        assert response.status_code == 500
        assert "reportlab" in response.json()["detail"].lower()

    @patch("backend.api.reports.endpoints.sessionmaker")
    def test_generate_pdf_user_not_found(self, mock_sessionmaker):
        """Test PDF generation when user not found."""
        from backend.api.reports.endpoints import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        mock_db = MagicMock()
        mock_db.get_bind.return_value = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: "unknown@example.com"
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.get("/api/reports/generate/registered-hosts")

        assert response.status_code == 401

    @patch("backend.api.reports.endpoints.sessionmaker")
    def test_generate_pdf_permission_denied(self, mock_sessionmaker):
        """Test PDF generation when user lacks permission."""
        from backend.api.reports.endpoints import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        mock_user = MagicMock()
        mock_user.userid = "user@example.com"
        mock_user._role_cache = []
        mock_user.has_role.return_value = False

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        mock_db = MagicMock()
        mock_db.get_bind.return_value = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: "user@example.com"
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        response = client.get("/api/reports/generate/registered-hosts")

        assert response.status_code == 403


class TestGetReportScreenshot:
    """Tests for get_report_screenshot endpoint."""

    def test_get_screenshot_success(self):
        """Test successful screenshot retrieval."""
        from backend.api.reports.endpoints import router

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/api/reports/screenshots/registered-hosts")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/svg+xml"
        assert "<svg" in response.text

    def test_get_screenshot_head_request(self):
        """Test HEAD request for screenshot."""
        from backend.api.reports.endpoints import router

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.head("/api/reports/screenshots/users-list")

        assert response.status_code == 200

    def test_get_screenshot_options_request(self):
        """Test OPTIONS request for screenshot."""
        from backend.api.reports.endpoints import router

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.options("/api/reports/screenshots/firewall-status")

        assert response.status_code == 200

    def test_get_screenshot_content_format(self):
        """Test that screenshot returns valid SVG content."""
        from backend.api.reports.endpoints import router

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/api/reports/screenshots/some-report")

        assert response.status_code == 200
        assert "<svg" in response.text
        assert "viewBox" in response.text
        # Check that the report name is in the SVG
        assert "Some Report" in response.text

    def test_get_screenshot_cache_headers(self):
        """Test that screenshot has cache headers."""
        from backend.api.reports.endpoints import router

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/api/reports/screenshots/audit-log")

        assert response.status_code == 200
        assert "Cache-Control" in response.headers
        assert "max-age=3600" in response.headers["Cache-Control"]


class TestRouterConfiguration:
    """Tests for router configuration."""

    def test_router_prefix(self):
        """Test router has correct prefix."""
        from backend.api.reports.endpoints import router

        assert router.prefix == "/api/reports"

    def test_router_tags(self):
        """Test router has correct tags."""
        from backend.api.reports.endpoints import router

        assert "reports" in router.tags
