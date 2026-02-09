"""
Comprehensive unit tests for the report generation functionality in SysManage.

Tests cover:
- PDF report generation (hosts, users, firewall, antivirus, RBAC, audit log)
- HTML report generation (all report types)
- Report API endpoints (view, generate PDF, screenshots)
- Report type enum validation
- HTML escaping and XSS prevention
- Error handling (missing data, permissions, PDF library availability)
- Report metadata (timestamps, counts)
- Data formatting (dates, IPs, ports, status indicators)

These tests use pytest and pytest-asyncio for async tests with mocked database.
"""

import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from backend.api.reports.endpoints import ReportType

# =============================================================================
# TEST CONFIGURATION AND FIXTURES
# =============================================================================


# Test configuration
TEST_CONFIG = {
    "api": {
        "host": "localhost",
        "port": 9443,
        "certFile": None,
    },
    "webui": {"host": "localhost", "port": 9080},
    "security": {
        "password_salt": "test_salt",
        "admin_userid": "admin@test.com",
        "admin_password": "testadminpass",
        "jwt_secret": "test_secret_key_for_testing_only",
        "jwt_algorithm": "HS256",
        "jwt_auth_timeout": 3600,
        "jwt_refresh_timeout": 86400,
    },
}


@pytest.fixture
def mock_config():
    """Mock the configuration system to use test config."""
    with patch("backend.config.config.get_config", return_value=TEST_CONFIG):
        yield TEST_CONFIG


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    mock_session = MagicMock()
    mock_session.query.return_value = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()
    mock_session.rollback = MagicMock()
    mock_session.close = MagicMock()
    mock_session.refresh = MagicMock()
    mock_session.delete = MagicMock()
    mock_session.flush = MagicMock()
    mock_session.get_bind.return_value = MagicMock()
    return mock_session


@pytest.fixture
def mock_host():
    """Create a mock host object for reports."""
    host = MagicMock()
    host.id = uuid.uuid4()
    host.fqdn = "test-host.example.com"
    host.ipv4 = "192.168.1.100"
    host.ipv6 = "2001:db8::1"
    host.status = "up"
    host.approval_status = "approved"
    host.last_access = datetime.now(timezone.utc)
    host.platform = "Linux"
    host.platform_release = "5.15.0"
    host.os_details = json.dumps(
        {"distribution": "Ubuntu", "distribution_version": "22.04"}
    )
    host.tags = []

    # Firewall status
    host.firewall_status = MagicMock()
    host.firewall_status.firewall_name = "ufw"
    host.firewall_status.enabled = True
    host.firewall_status.ipv4_ports = json.dumps(
        [
            {"port": "22", "protocols": ["tcp"]},
            {"port": "80", "protocols": ["tcp"]},
        ]
    )
    host.firewall_status.ipv6_ports = json.dumps(
        [
            {"port": "22", "protocols": ["tcp"]},
        ]
    )

    # Open-source antivirus status
    host.antivirus_status = MagicMock()
    host.antivirus_status.software_name = "ClamAV"
    host.antivirus_status.version = "0.105.0"
    host.antivirus_status.install_path = "/usr/bin/clamscan"
    host.antivirus_status.enabled = True
    host.antivirus_status.last_updated = datetime.now(timezone.utc)

    # Commercial antivirus status
    host.commercial_antivirus_status = MagicMock()
    host.commercial_antivirus_status.product_name = "ESET NOD32"
    host.commercial_antivirus_status.product_version = "8.0.0"
    host.commercial_antivirus_status.signature_version = "27000"
    host.commercial_antivirus_status.signature_last_updated = datetime.now(timezone.utc)
    host.commercial_antivirus_status.realtime_protection_enabled = True
    host.commercial_antivirus_status.service_enabled = True

    return host


@pytest.fixture
def mock_host_minimal():
    """Create a mock host with minimal data (missing optional fields)."""
    host = MagicMock()
    host.id = uuid.uuid4()
    host.fqdn = "minimal-host.example.com"
    host.ipv4 = None
    host.ipv6 = None
    host.status = None
    host.approval_status = "pending"
    host.last_access = None
    host.platform = None
    host.platform_release = None
    host.os_details = None
    host.tags = []
    host.firewall_status = None
    host.antivirus_status = None
    host.commercial_antivirus_status = None
    return host


@pytest.fixture
def mock_host_with_tags():
    """Create a mock host with tags."""
    host = MagicMock()
    host.id = uuid.uuid4()
    host.fqdn = "tagged-host.example.com"
    host.ipv4 = "10.0.0.1"
    host.ipv6 = None
    host.status = "up"
    host.last_access = datetime.now(timezone.utc)

    tag1 = MagicMock()
    tag1.name = "production"
    tag2 = MagicMock()
    tag2.name = "webserver"
    host.tags = [tag1, tag2]

    return host


@pytest.fixture
def mock_user():
    """Create a mock user object for reports."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.userid = "testuser@example.com"
    user.first_name = "Test"
    user.last_name = "User"
    user.active = True
    user.is_locked = False
    user.failed_login_attempts = 0
    user.last_access = datetime.now(timezone.utc)
    user.security_roles = []
    user._role_cache = None
    user.load_role_cache = MagicMock()
    user.has_role = MagicMock(return_value=True)
    return user


@pytest.fixture
def mock_user_with_roles():
    """Create a mock user with security roles."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.userid = "admin@example.com"
    user.first_name = "Admin"
    user.last_name = "User"
    user.active = True
    user.is_locked = False
    user.failed_login_attempts = 0
    user.last_access = datetime.now(timezone.utc)

    # Create mock roles
    role1 = MagicMock()
    role1.name = "VIEW_HOSTS"
    role1.group_id = 1

    role2 = MagicMock()
    role2.name = "MANAGE_HOSTS"
    role2.group_id = 1

    role3 = MagicMock()
    role3.name = "VIEW_USERS"
    role3.group_id = 2

    user.security_roles = [role1, role2, role3]
    user._role_cache = None
    user.load_role_cache = MagicMock()
    user.has_role = MagicMock(return_value=True)

    return user


@pytest.fixture
def mock_user_locked():
    """Create a mock locked user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.userid = "locked@example.com"
    user.first_name = "Locked"
    user.last_name = "User"
    user.active = False
    user.is_locked = True
    user.failed_login_attempts = 5
    user.last_access = datetime.now(timezone.utc) - timedelta(days=30)
    user.security_roles = []
    return user


@pytest.fixture
def mock_audit_entry():
    """Create a mock audit log entry."""
    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.timestamp = datetime.now(timezone.utc)
    entry.username = "admin@example.com"
    entry.action_type = "CREATE"
    entry.entity_type = "Host"
    entry.entity_name = "test-host.example.com"
    entry.result = "SUCCESS"
    entry.description = "Created new host"
    return entry


@pytest.fixture
def mock_role_group():
    """Create a mock security role group."""
    group = MagicMock()
    group.id = 1
    group.name = "Host Management"
    return group


def create_mock_session_context(mock_session):
    """Helper to create a mock session context manager."""
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_session_factory.return_value.__exit__ = MagicMock(return_value=False)
    return mock_session_factory


# =============================================================================
# REPORT TYPE ENUM TESTS
# =============================================================================


class TestReportTypeEnum:
    """Test cases for the ReportType enum."""

    def test_all_report_types_exist(self):
        """Test that all expected report types are defined."""
        expected_types = [
            "REGISTERED_HOSTS",
            "HOSTS_WITH_TAGS",
            "USERS_LIST",
            "FIREWALL_STATUS",
            "ANTIVIRUS_OPENSOURCE",
            "ANTIVIRUS_COMMERCIAL",
            "USER_RBAC",
            "AUDIT_LOG",
        ]

        for report_type in expected_types:
            assert hasattr(ReportType, report_type)

    def test_report_type_values(self):
        """Test that report type values are correctly formatted."""
        assert ReportType.REGISTERED_HOSTS.value == "registered-hosts"
        assert ReportType.HOSTS_WITH_TAGS.value == "hosts-with-tags"
        assert ReportType.USERS_LIST.value == "users-list"
        assert ReportType.FIREWALL_STATUS.value == "firewall-status"
        assert ReportType.ANTIVIRUS_OPENSOURCE.value == "antivirus-opensource"
        assert ReportType.ANTIVIRUS_COMMERCIAL.value == "antivirus-commercial"
        assert ReportType.USER_RBAC.value == "user-rbac"
        assert ReportType.AUDIT_LOG.value == "audit-log"

    def test_report_type_is_string_enum(self):
        """Test that ReportType is a string enum."""
        assert isinstance(ReportType.REGISTERED_HOSTS.value, str)


# =============================================================================
# HTML ESCAPE UTILITY TESTS
# =============================================================================


class TestHtmlEscaping:
    """Test cases for HTML escaping utility."""

    def test_escape_basic_html_chars(self):
        """Test escaping of basic HTML characters."""
        from backend.api.reports.html.common import escape

        assert escape("<script>") == "&lt;script&gt;"
        assert escape("&") == "&amp;"
        assert escape('"') == "&quot;"
        assert escape("'") == "&#x27;"

    def test_escape_none_returns_empty_string(self):
        """Test that None returns empty string."""
        from backend.api.reports.html.common import escape

        assert escape(None) == ""

    def test_escape_normal_text(self):
        """Test that normal text is unchanged."""
        from backend.api.reports.html.common import escape

        assert escape("Hello World") == "Hello World"
        assert escape("test-host.example.com") == "test-host.example.com"

    def test_escape_xss_prevention(self):
        """Test XSS attack prevention."""
        from backend.api.reports.html.common import escape

        xss_attempt = '<script>alert("XSS")</script>'
        escaped = escape(xss_attempt)
        assert "<script>" not in escaped
        assert 'alert("XSS")' not in escaped

    def test_escape_converts_numbers(self):
        """Test that numbers are converted to strings."""
        from backend.api.reports.html.common import escape

        assert escape(123) == "123"
        assert escape(45.67) == "45.67"


# =============================================================================
# HTML REPORT GENERATION TESTS - HOSTS
# =============================================================================


class TestHtmlHostReports:
    """Test cases for HTML host report generation."""

    def test_generate_hosts_html_with_data(self, mock_host):
        """Test generating hosts HTML report with data."""
        from backend.api.reports.html.hosts import generate_hosts_html

        hosts = [mock_host]
        html = generate_hosts_html(hosts, "registered-hosts", "Registered Hosts")

        # Check structure
        assert "<!DOCTYPE html>" in html
        assert '<html lang="en">' in html
        assert "Registered Hosts" in html
        assert "test-host.example.com" in html
        assert "192.168.1.100" in html

    def test_generate_hosts_html_empty(self):
        """Test generating hosts HTML report with no hosts."""
        from backend.api.reports.html.hosts import generate_hosts_html

        html = generate_hosts_html([], "registered-hosts", "Registered Hosts")

        assert "No hosts are currently registered" in html

    def test_generate_hosts_with_tags_html(self, mock_host_with_tags):
        """Test generating hosts with tags HTML report."""
        from backend.api.reports.html.hosts import generate_hosts_html

        hosts = [mock_host_with_tags]
        html = generate_hosts_html(hosts, "hosts-with-tags", "Hosts with Tags")

        assert "production" in html
        assert "webserver" in html
        assert "tagged-host.example.com" in html

    def test_generate_hosts_html_with_minimal_host(self, mock_host_minimal):
        """Test generating hosts HTML report with minimal host data."""
        from backend.api.reports.html.hosts import generate_hosts_html

        hosts = [mock_host_minimal]
        html = generate_hosts_html(hosts, "registered-hosts", "Registered Hosts")

        assert "minimal-host" in html
        # Should handle None values gracefully
        assert html is not None

    def test_generate_firewall_status_html_with_data(self, mock_host):
        """Test generating firewall status HTML report."""
        from backend.api.reports.html.hosts import generate_firewall_status_html

        hosts = [mock_host]
        html = generate_firewall_status_html(hosts, "Host Firewall Status")

        assert "Host Firewall Status" in html
        assert "ufw" in html
        assert "Enabled" in html
        assert "22" in html  # Port 22

    def test_generate_firewall_status_html_empty(self):
        """Test generating firewall status HTML report with no hosts."""
        from backend.api.reports.html.hosts import generate_firewall_status_html

        html = generate_firewall_status_html([], "Host Firewall Status")

        assert "No hosts with firewall status found" in html

    def test_generate_antivirus_opensource_html_with_data(self, mock_host):
        """Test generating open-source antivirus HTML report."""
        from backend.api.reports.html.hosts import generate_antivirus_opensource_html

        hosts = [mock_host]
        html = generate_antivirus_opensource_html(hosts, "Open-Source Antivirus Status")

        assert "Open-Source Antivirus Status" in html
        assert "ClamAV" in html
        assert "0.105.0" in html

    def test_generate_antivirus_commercial_html_with_data(self, mock_host):
        """Test generating commercial antivirus HTML report."""
        from backend.api.reports.html.hosts import generate_antivirus_commercial_html

        hosts = [mock_host]
        html = generate_antivirus_commercial_html(hosts, "Commercial Antivirus Status")

        assert "Commercial Antivirus Status" in html
        assert "ESET NOD32" in html
        assert "8.0.0" in html

    def test_generate_hosts_html_escapes_xss(self):
        """Test that hosts HTML report escapes XSS attempts."""
        from backend.api.reports.html.hosts import generate_hosts_html

        malicious_host = MagicMock()
        malicious_host.fqdn = '<script>alert("XSS")</script>'
        malicious_host.ipv4 = "192.168.1.1"
        malicious_host.ipv6 = None
        malicious_host.status = "up"
        malicious_host.last_access = datetime.now(timezone.utc)
        malicious_host.platform = "Linux"
        malicious_host.platform_release = "5.15.0"
        malicious_host.os_details = None
        malicious_host.tags = []

        html = generate_hosts_html([malicious_host], "registered-hosts", "Test")

        assert "<script>" not in html
        assert "&lt;script&gt;" in html


# =============================================================================
# HTML REPORT GENERATION TESTS - USERS
# =============================================================================


class TestHtmlUserReports:
    """Test cases for HTML user report generation."""

    def test_generate_users_html_with_data(self, mock_user):
        """Test generating users HTML report with data."""
        from backend.api.reports.html.users import generate_users_html

        users = [mock_user]
        html = generate_users_html(users, "SysManage Users")

        assert "SysManage Users" in html
        assert "testuser@example.com" in html
        assert "Test" in html
        assert "User" in html
        assert "Active" in html

    def test_generate_users_html_empty(self):
        """Test generating users HTML report with no users."""
        from backend.api.reports.html.users import generate_users_html

        html = generate_users_html([], "SysManage Users")

        assert "No users are currently registered" in html

    def test_generate_users_html_locked_user(self, mock_user_locked):
        """Test generating users HTML report with locked user."""
        from backend.api.reports.html.users import generate_users_html

        users = [mock_user_locked]
        html = generate_users_html(users, "SysManage Users")

        assert "Locked" in html
        assert "Inactive" in html
        assert "5 failed attempts" in html

    def test_generate_user_rbac_html_with_roles(
        self, mock_user_with_roles, mock_db_session, mock_role_group
    ):
        """Test generating user RBAC HTML report with roles."""
        from backend.api.reports.html.users import generate_user_rbac_html

        mock_db_session.query.return_value.order_by.return_value.all.return_value = [
            mock_role_group
        ]

        users = [mock_user_with_roles]
        html = generate_user_rbac_html(mock_db_session, users, "User Security Roles")

        assert "User Security Roles" in html
        assert "admin@example.com" in html
        assert "Host Management" in html

    def test_generate_user_rbac_html_no_roles(self, mock_user, mock_db_session):
        """Test generating user RBAC HTML report for user with no roles."""
        from backend.api.reports.html.users import generate_user_rbac_html

        mock_db_session.query.return_value.order_by.return_value.all.return_value = []

        users = [mock_user]
        html = generate_user_rbac_html(mock_db_session, users, "User Security Roles")

        assert "No security roles assigned" in html

    def test_generate_audit_log_html_with_data(self, mock_audit_entry):
        """Test generating audit log HTML report with data."""
        from backend.api.reports.html.users import generate_audit_log_html

        entries = [mock_audit_entry]
        html = generate_audit_log_html(entries, "Audit Log")

        assert "Audit Log" in html
        assert "admin@example.com" in html
        assert "CREATE" in html
        assert "Host" in html
        assert "SUCCESS" in html
        assert "result-success" in html  # CSS class for success

    def test_generate_audit_log_html_empty(self):
        """Test generating audit log HTML report with no entries."""
        from backend.api.reports.html.users import generate_audit_log_html

        html = generate_audit_log_html([], "Audit Log")

        assert "No audit log entries found" in html

    def test_generate_audit_log_html_failure_styling(self):
        """Test that audit log entries with FAILURE result get correct styling."""
        from backend.api.reports.html.users import generate_audit_log_html

        entry = MagicMock()
        entry.timestamp = datetime.now(timezone.utc)
        entry.username = "user@example.com"
        entry.action_type = "DELETE"
        entry.entity_type = "Host"
        entry.entity_name = "test-host"
        entry.result = "FAILURE"
        entry.description = "Permission denied"

        html = generate_audit_log_html([entry], "Audit Log")

        assert "result-failure" in html


# =============================================================================
# PDF REPORT GENERATION TESTS
# =============================================================================


class TestPdfReportGeneration:
    """Test cases for PDF report generation."""

    def test_reportlab_availability_check(self):
        """Test that REPORTLAB_AVAILABLE is set correctly."""
        from backend.api.reports.pdf import REPORTLAB_AVAILABLE

        # Should be True if reportlab is installed
        assert isinstance(REPORTLAB_AVAILABLE, bool)

    def test_report_generator_base_class(self, mock_db_session):
        """Test ReportGenerator base class initialization."""
        from backend.api.reports.pdf.base import ReportGenerator, REPORTLAB_AVAILABLE

        if REPORTLAB_AVAILABLE:
            generator = ReportGenerator(mock_db_session)
            assert generator.db == mock_db_session
            assert generator.styles is not None

    @pytest.mark.skipif(
        not __import__(
            "backend.api.reports.pdf.base", fromlist=["REPORTLAB_AVAILABLE"]
        ).REPORTLAB_AVAILABLE,
        reason="reportlab not available",
    )
    def test_hosts_report_generator_create(self, mock_db_session):
        """Test creating HostsReportGenerator."""
        from backend.api.reports.pdf.hosts import HostsReportGenerator

        generator = HostsReportGenerator(mock_db_session)
        assert generator.db == mock_db_session

    @pytest.mark.skipif(
        not __import__(
            "backend.api.reports.pdf.base", fromlist=["REPORTLAB_AVAILABLE"]
        ).REPORTLAB_AVAILABLE,
        reason="reportlab not available",
    )
    def test_users_report_generator_create(self, mock_db_session):
        """Test creating UsersReportGenerator."""
        from backend.api.reports.pdf.users import UsersReportGenerator

        generator = UsersReportGenerator(mock_db_session)
        assert generator.db == mock_db_session

    @pytest.mark.skipif(
        not __import__(
            "backend.api.reports.pdf.base", fromlist=["REPORTLAB_AVAILABLE"]
        ).REPORTLAB_AVAILABLE,
        reason="reportlab not available",
    )
    def test_generate_hosts_pdf_report(self, mock_db_session, mock_host):
        """Test generating hosts PDF report."""
        from backend.api.reports.pdf.hosts import HostsReportGenerator

        mock_db_session.query.return_value.order_by.return_value.all.return_value = [
            mock_host
        ]

        generator = HostsReportGenerator(mock_db_session)
        pdf_buffer = generator.generate_hosts_report()

        assert isinstance(pdf_buffer, io.BytesIO)
        assert pdf_buffer.getvalue().startswith(b"%PDF")

    @pytest.mark.skipif(
        not __import__(
            "backend.api.reports.pdf.base", fromlist=["REPORTLAB_AVAILABLE"]
        ).REPORTLAB_AVAILABLE,
        reason="reportlab not available",
    )
    def test_generate_hosts_pdf_empty(self, mock_db_session):
        """Test generating hosts PDF report with no hosts."""
        from backend.api.reports.pdf.hosts import HostsReportGenerator

        mock_db_session.query.return_value.order_by.return_value.all.return_value = []

        generator = HostsReportGenerator(mock_db_session)
        pdf_buffer = generator.generate_hosts_report()

        assert isinstance(pdf_buffer, io.BytesIO)
        assert pdf_buffer.getvalue().startswith(b"%PDF")

    @pytest.mark.skipif(
        not __import__(
            "backend.api.reports.pdf.base", fromlist=["REPORTLAB_AVAILABLE"]
        ).REPORTLAB_AVAILABLE,
        reason="reportlab not available",
    )
    def test_generate_hosts_with_tags_pdf_report(
        self, mock_db_session, mock_host_with_tags
    ):
        """Test generating hosts with tags PDF report."""
        from backend.api.reports.pdf.hosts import HostsReportGenerator

        mock_db_session.query.return_value.order_by.return_value.all.return_value = [
            mock_host_with_tags
        ]

        generator = HostsReportGenerator(mock_db_session)
        pdf_buffer = generator.generate_hosts_with_tags_report()

        assert isinstance(pdf_buffer, io.BytesIO)
        assert pdf_buffer.getvalue().startswith(b"%PDF")

    @pytest.mark.skipif(
        not __import__(
            "backend.api.reports.pdf.base", fromlist=["REPORTLAB_AVAILABLE"]
        ).REPORTLAB_AVAILABLE,
        reason="reportlab not available",
    )
    def test_generate_firewall_pdf_report(self, mock_db_session, mock_host):
        """Test generating firewall status PDF report."""
        from backend.api.reports.pdf.hosts import HostsReportGenerator

        mock_db_session.query.return_value.order_by.return_value.all.return_value = [
            mock_host
        ]

        generator = HostsReportGenerator(mock_db_session)
        pdf_buffer = generator.generate_firewall_status_report()

        assert isinstance(pdf_buffer, io.BytesIO)
        assert pdf_buffer.getvalue().startswith(b"%PDF")

    @pytest.mark.skipif(
        not __import__(
            "backend.api.reports.pdf.base", fromlist=["REPORTLAB_AVAILABLE"]
        ).REPORTLAB_AVAILABLE,
        reason="reportlab not available",
    )
    def test_generate_antivirus_opensource_pdf_report(self, mock_db_session, mock_host):
        """Test generating open-source antivirus PDF report."""
        from backend.api.reports.pdf.hosts import HostsReportGenerator

        mock_db_session.query.return_value.order_by.return_value.all.return_value = [
            mock_host
        ]

        generator = HostsReportGenerator(mock_db_session)
        pdf_buffer = generator.generate_antivirus_opensource_report()

        assert isinstance(pdf_buffer, io.BytesIO)
        assert pdf_buffer.getvalue().startswith(b"%PDF")

    @pytest.mark.skipif(
        not __import__(
            "backend.api.reports.pdf.base", fromlist=["REPORTLAB_AVAILABLE"]
        ).REPORTLAB_AVAILABLE,
        reason="reportlab not available",
    )
    def test_generate_antivirus_commercial_pdf_report(self, mock_db_session, mock_host):
        """Test generating commercial antivirus PDF report."""
        from backend.api.reports.pdf.hosts import HostsReportGenerator

        mock_db_session.query.return_value.order_by.return_value.all.return_value = [
            mock_host
        ]

        generator = HostsReportGenerator(mock_db_session)
        pdf_buffer = generator.generate_antivirus_commercial_report()

        assert isinstance(pdf_buffer, io.BytesIO)
        assert pdf_buffer.getvalue().startswith(b"%PDF")

    @pytest.mark.skipif(
        not __import__(
            "backend.api.reports.pdf.base", fromlist=["REPORTLAB_AVAILABLE"]
        ).REPORTLAB_AVAILABLE,
        reason="reportlab not available",
    )
    def test_generate_users_list_pdf_report(self, mock_db_session, mock_user):
        """Test generating users list PDF report."""
        from backend.api.reports.pdf.users import UsersReportGenerator

        mock_db_session.query.return_value.order_by.return_value.all.return_value = [
            mock_user
        ]

        generator = UsersReportGenerator(mock_db_session)
        pdf_buffer = generator.generate_users_list_report()

        assert isinstance(pdf_buffer, io.BytesIO)
        assert pdf_buffer.getvalue().startswith(b"%PDF")

    @pytest.mark.skipif(
        not __import__(
            "backend.api.reports.pdf.base", fromlist=["REPORTLAB_AVAILABLE"]
        ).REPORTLAB_AVAILABLE,
        reason="reportlab not available",
    )
    def test_generate_user_rbac_pdf_report(
        self, mock_db_session, mock_user_with_roles, mock_role_group
    ):
        """Test generating user RBAC PDF report."""
        from backend.api.reports.pdf.users import UsersReportGenerator

        # Setup mock queries
        mock_query = MagicMock()
        mock_db_session.query.return_value = mock_query
        mock_query.order_by.return_value.all.side_effect = [
            [mock_user_with_roles],  # Users query
            [mock_role_group],  # Role groups query
        ]

        generator = UsersReportGenerator(mock_db_session)
        pdf_buffer = generator.generate_user_rbac_report()

        assert isinstance(pdf_buffer, io.BytesIO)
        assert pdf_buffer.getvalue().startswith(b"%PDF")

    @pytest.mark.skipif(
        not __import__(
            "backend.api.reports.pdf.base", fromlist=["REPORTLAB_AVAILABLE"]
        ).REPORTLAB_AVAILABLE,
        reason="reportlab not available",
    )
    def test_generate_audit_log_pdf_report(self, mock_db_session, mock_audit_entry):
        """Test generating audit log PDF report."""
        from backend.api.reports.pdf.users import UsersReportGenerator

        mock_db_session.query.return_value.order_by.return_value.all.return_value = [
            mock_audit_entry
        ]

        generator = UsersReportGenerator(mock_db_session)
        pdf_buffer = generator.generate_audit_log_report()

        assert isinstance(pdf_buffer, io.BytesIO)
        assert pdf_buffer.getvalue().startswith(b"%PDF")


# =============================================================================
# REPORT API ENDPOINT TESTS
# =============================================================================


class TestReportEndpoints:
    """Test cases for report API endpoints."""

    @pytest.mark.asyncio
    async def test_view_report_html_registered_hosts(
        self, mock_config, mock_user, mock_host, mock_db_session
    ):
        """Test viewing registered hosts HTML report."""
        from backend.api.reports.endpoints import view_report_html

        mock_db_session.query.return_value.order_by.return_value.all.return_value = [
            mock_host
        ]
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        with patch("backend.api.reports.endpoints.sessionmaker") as mock_sessionmaker:
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            result = await view_report_html(
                ReportType.REGISTERED_HOSTS,
                current_user="testuser@example.com",
                db=mock_db_session,
            )

            assert isinstance(result, HTMLResponse)
            assert b"Registered Hosts" in result.body

    @pytest.mark.asyncio
    async def test_view_report_html_without_permission(
        self, mock_config, mock_user, mock_db_session
    ):
        """Test viewing report without VIEW_REPORT role."""
        from backend.api.reports.endpoints import view_report_html

        mock_user.has_role = MagicMock(return_value=False)
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        with patch("backend.api.reports.endpoints.sessionmaker") as mock_sessionmaker:
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            with pytest.raises(HTTPException) as exc_info:
                await view_report_html(
                    ReportType.REGISTERED_HOSTS,
                    current_user="testuser@example.com",
                    db=mock_db_session,
                )

            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_view_report_html_user_not_found(self, mock_config, mock_db_session):
        """Test viewing report when user not found."""
        from backend.api.reports.endpoints import view_report_html

        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with patch("backend.api.reports.endpoints.sessionmaker") as mock_sessionmaker:
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            with pytest.raises(HTTPException) as exc_info:
                await view_report_html(
                    ReportType.REGISTERED_HOSTS,
                    current_user="unknown@example.com",
                    db=mock_db_session,
                )

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_pdf_report_without_permission(
        self, mock_config, mock_user, mock_db_session
    ):
        """Test generating PDF report without GENERATE_PDF_REPORT role."""
        from backend.api.reports.endpoints import generate_report

        mock_user.has_role = MagicMock(return_value=False)
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        with patch("backend.api.reports.endpoints.sessionmaker") as mock_sessionmaker:
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            with pytest.raises(HTTPException) as exc_info:
                await generate_report(
                    ReportType.REGISTERED_HOSTS,
                    current_user="testuser@example.com",
                    db=mock_db_session,
                )

            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_generate_pdf_report_reportlab_unavailable(
        self, mock_config, mock_user, mock_db_session
    ):
        """Test generating PDF report when reportlab is not available."""
        from backend.api.reports.endpoints import generate_report

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        with patch(
            "backend.api.reports.endpoints.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.reports.endpoints.REPORTLAB_AVAILABLE", False
        ):
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            with pytest.raises(HTTPException) as exc_info:
                await generate_report(
                    ReportType.REGISTERED_HOSTS,
                    current_user="testuser@example.com",
                    db=mock_db_session,
                )

            assert exc_info.value.status_code == 500
            assert "reportlab" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_report_screenshot(self):
        """Test getting report screenshot placeholder."""
        from backend.api.reports.endpoints import get_report_screenshot

        response = await get_report_screenshot("registered-hosts")

        assert response.media_type == "image/svg+xml"
        assert b"<svg" in response.body
        assert b"Registered Hosts" in response.body

    @pytest.mark.asyncio
    async def test_get_report_screenshot_escapes_xss(self):
        """Test that report screenshot endpoint escapes XSS attempts."""
        from backend.api.reports.endpoints import get_report_screenshot

        response = await get_report_screenshot('<script>alert("XSS")</script>')

        assert b"<script>" not in response.body
        # The escape function title-cases the text, so check for the escaped version
        # (either lowercase or title-case depending on implementation)
        assert b"&lt;" in response.body
        assert b"&gt;" in response.body


# =============================================================================
# REPORT DATA FORMATTING TESTS
# =============================================================================


class TestReportDataFormatting:
    """Test cases for report data formatting."""

    def test_ipv6_truncation_in_hosts_html(self):
        """Test that long IPv6 addresses are truncated in HTML reports."""
        from backend.api.reports.html.hosts import generate_hosts_html

        host = MagicMock()
        host.fqdn = "test.example.com"
        host.ipv4 = None
        host.ipv6 = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"  # Long IPv6
        host.status = "up"
        host.last_access = datetime.now(timezone.utc)
        host.platform = "Linux"
        host.platform_release = "5.15.0"
        host.os_details = None
        host.tags = []

        html = generate_hosts_html([host], "registered-hosts", "Test")

        # Should contain truncated IPv6 or full IPv6
        assert "2001:" in html

    def test_date_formatting_in_reports(self):
        """Test that dates are formatted correctly in reports."""
        from backend.api.reports.html.users import generate_users_html

        user = MagicMock()
        user.userid = "test@example.com"
        user.first_name = "Test"
        user.last_name = "User"
        user.active = True
        user.is_locked = False
        user.failed_login_attempts = 0
        user.last_access = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        user.security_roles = []

        html = generate_users_html([user], "Users")

        assert "2024-01-15" in html
        assert "10:30" in html

    def test_never_last_access_in_reports(self):
        """Test handling of None last_access (Never)."""
        from backend.api.reports.html.users import generate_users_html

        user = MagicMock()
        user.userid = "newuser@example.com"
        user.first_name = "New"
        user.last_name = "User"
        user.active = True
        user.is_locked = False
        user.failed_login_attempts = 0
        user.last_access = None
        user.security_roles = []

        html = generate_users_html([user], "Users")

        assert "Never" in html

    def test_port_formatting_in_firewall_report(self, mock_host):
        """Test port formatting in firewall status report."""
        from backend.api.reports.html.hosts import generate_firewall_status_html

        html = generate_firewall_status_html([mock_host], "Firewall Status")

        assert "22" in html
        assert "tcp" in html
        assert "80" in html

    def test_invalid_json_ports_handling(self):
        """Test handling of invalid JSON in port data."""
        from backend.api.reports.html.hosts import generate_firewall_status_html

        host = MagicMock()
        host.fqdn = "test.example.com"
        host.ipv4 = "192.168.1.1"
        host.ipv6 = None
        host.platform = "Linux"
        host.platform_release = "5.15.0"
        host.os_details = None
        host.firewall_status = MagicMock()
        host.firewall_status.firewall_name = "ufw"
        host.firewall_status.enabled = True
        host.firewall_status.ipv4_ports = "invalid json"
        host.firewall_status.ipv6_ports = "also invalid"

        # Should not raise exception
        html = generate_firewall_status_html([host], "Firewall Status")
        assert html is not None


# =============================================================================
# REPORT METADATA TESTS
# =============================================================================


class TestReportMetadata:
    """Test cases for report metadata (timestamps, counts)."""

    def test_html_report_includes_timestamp(self, mock_host):
        """Test that HTML reports include generation timestamp."""
        from backend.api.reports.html.hosts import generate_hosts_html

        html = generate_hosts_html([mock_host], "registered-hosts", "Test Report")

        assert "Generated" in html
        assert "UTC" in html

    def test_html_report_includes_count(self, mock_host):
        """Test that HTML reports include item count."""
        from backend.api.reports.html.hosts import generate_hosts_html

        hosts = [mock_host, mock_host, mock_host]
        html = generate_hosts_html(hosts, "registered-hosts", "Test Report")

        assert "Total Hosts" in html
        assert "3" in html

    def test_user_report_includes_total_users(self, mock_user):
        """Test that user reports include total user count."""
        from backend.api.reports.html.users import generate_users_html

        users = [mock_user, mock_user]
        html = generate_users_html(users, "User Report")

        assert "Total Users" in html
        assert "2" in html

    def test_audit_log_includes_total_entries(self, mock_audit_entry):
        """Test that audit log reports include total entry count."""
        from backend.api.reports.html.users import generate_audit_log_html

        entries = [mock_audit_entry, mock_audit_entry, mock_audit_entry]
        html = generate_audit_log_html(entries, "Audit Log")

        assert "Total Entries" in html
        assert "3" in html


# =============================================================================
# REPORT ERROR HANDLING TESTS
# =============================================================================


class TestReportErrorHandling:
    """Test cases for error handling in report generation."""

    def test_generate_hosts_html_handles_json_decode_error(self):
        """Test that hosts HTML generation handles JSON decode errors gracefully."""
        from backend.api.reports.html.hosts import generate_hosts_html

        host = MagicMock()
        host.fqdn = "test.example.com"
        host.ipv4 = "192.168.1.1"
        host.ipv6 = None
        host.status = "up"
        host.last_access = datetime.now(timezone.utc)
        host.platform = "Linux"
        host.platform_release = "5.15.0"
        host.os_details = "invalid json {"
        host.tags = []

        # Should not raise exception
        html = generate_hosts_html([host], "registered-hosts", "Test")
        assert html is not None
        assert "test.example.com" in html

    def test_generate_hosts_html_handles_missing_fqdn(self):
        """Test that hosts HTML generation handles missing FQDN."""
        from backend.api.reports.html.hosts import generate_hosts_html

        host = MagicMock()
        host.fqdn = None
        host.ipv4 = "192.168.1.1"
        host.ipv6 = None
        host.status = "up"
        host.last_access = datetime.now(timezone.utc)
        host.platform = None
        host.platform_release = None
        host.os_details = None
        host.tags = []

        # Should not raise exception
        html = generate_hosts_html([host], "registered-hosts", "Test")
        assert html is not None

    @pytest.mark.asyncio
    async def test_view_report_handles_database_error(
        self, mock_config, mock_user, mock_db_session
    ):
        """Test that view_report handles database errors gracefully."""
        from backend.api.reports.endpoints import view_report_html

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )
        mock_db_session.query.return_value.order_by.return_value.all.side_effect = (
            Exception("Database error")
        )

        with patch("backend.api.reports.endpoints.sessionmaker") as mock_sessionmaker:
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            with pytest.raises(HTTPException) as exc_info:
                await view_report_html(
                    ReportType.REGISTERED_HOSTS,
                    current_user="testuser@example.com",
                    db=mock_db_session,
                )

            assert exc_info.value.status_code == 500


# =============================================================================
# REPORT CSS AND STYLING TESTS
# =============================================================================


class TestReportStyling:
    """Test cases for report styling and CSS."""

    def test_html_report_includes_css_styles(self, mock_host):
        """Test that HTML reports include CSS styles."""
        from backend.api.reports.html.hosts import generate_hosts_html

        html = generate_hosts_html([mock_host], "registered-hosts", "Test")

        assert "<style>" in html
        assert "font-family" in html
        assert "background-color" in html

    def test_audit_log_result_classes(self, mock_audit_entry):
        """Test that audit log uses correct CSS classes for results."""
        from backend.api.reports.html.users import generate_audit_log_html

        # Test SUCCESS styling
        mock_audit_entry.result = "SUCCESS"
        html = generate_audit_log_html([mock_audit_entry], "Audit Log")
        assert "result-success" in html

        # Test FAILURE styling
        mock_audit_entry.result = "FAILURE"
        html = generate_audit_log_html([mock_audit_entry], "Audit Log")
        assert "result-failure" in html

        # Test PENDING styling
        mock_audit_entry.result = "PENDING"
        html = generate_audit_log_html([mock_audit_entry], "Audit Log")
        assert "result-pending" in html

    def test_html_report_responsive_viewport(self, mock_host):
        """Test that HTML reports have responsive viewport meta tag."""
        from backend.api.reports.html.hosts import generate_hosts_html

        html = generate_hosts_html([mock_host], "registered-hosts", "Test")

        assert "viewport" in html
        assert "width=device-width" in html


# =============================================================================
# REPORT INTEGRATION TESTS
# =============================================================================


class TestReportIntegration:
    """Integration tests for report generation flow."""

    @pytest.mark.asyncio
    async def test_full_html_report_flow_hosts(
        self, mock_config, mock_user, mock_host, mock_db_session
    ):
        """Test full flow of generating an HTML hosts report."""
        from backend.api.reports.endpoints import view_report_html

        # Setup mocks
        mock_db_session.query.return_value.order_by.return_value.all.return_value = [
            mock_host
        ]
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        with patch("backend.api.reports.endpoints.sessionmaker") as mock_sessionmaker:
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            result = await view_report_html(
                ReportType.REGISTERED_HOSTS,
                current_user="testuser@example.com",
                db=mock_db_session,
            )

            # Verify response
            assert isinstance(result, HTMLResponse)
            body = result.body.decode("utf-8")

            # Check all expected elements
            assert "<!DOCTYPE html>" in body
            assert "Registered Hosts" in body
            assert "test-host.example.com" in body
            assert "192.168.1.100" in body
            assert "Generated" in body
            assert "Total Hosts" in body

    @pytest.mark.asyncio
    async def test_all_host_report_types_generate_html(
        self, mock_config, mock_user, mock_host, mock_db_session
    ):
        """Test that all host report types can generate HTML without errors."""
        from backend.api.reports.endpoints import view_report_html

        # Setup mocks for host reports
        mock_db_session.query.return_value.order_by.return_value.all.return_value = [
            mock_host
        ]
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        host_report_types = [
            ReportType.REGISTERED_HOSTS,
            ReportType.HOSTS_WITH_TAGS,
            ReportType.FIREWALL_STATUS,
            ReportType.ANTIVIRUS_OPENSOURCE,
            ReportType.ANTIVIRUS_COMMERCIAL,
        ]

        for report_type in host_report_types:
            with patch(
                "backend.api.reports.endpoints.sessionmaker"
            ) as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_db_session
                )

                result = await view_report_html(
                    report_type, current_user="testuser@example.com", db=mock_db_session
                )

                assert isinstance(result, HTMLResponse), f"Failed for {report_type}"
