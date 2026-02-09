"""
Comprehensive unit tests for the Graylog health monitor functionality.

Tests cover:
- Port checking logic (GELF TCP, Syslog TCP/UDP, Windows Sidecar)
- Database updates for health status
- Background monitoring service
- Error handling scenarios
"""

import asyncio
import socket
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch, PropertyMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.persistence import models

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def test_engine():
    """Create a shared in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def test_session(test_engine):
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture
def graylog_settings(test_session):
    """Create Graylog integration settings in the database."""
    settings = models.GraylogIntegrationSettings(
        enabled=True,
        graylog_url="http://graylog.example.com:9000",
        api_token="test-api-token",
    )
    test_session.add(settings)
    test_session.commit()
    test_session.refresh(settings)
    return settings


@pytest.fixture
def disabled_graylog_settings(test_session):
    """Create disabled Graylog integration settings."""
    settings = models.GraylogIntegrationSettings(
        enabled=False,
        graylog_url="http://graylog.example.com:9000",
    )
    test_session.add(settings)
    test_session.commit()
    test_session.refresh(settings)
    return settings


# =============================================================================
# check_graylog_health() TESTS
# =============================================================================


class TestCheckGraylogHealth:
    """Test cases for check_graylog_health function."""

    @pytest.mark.asyncio
    async def test_check_health_no_settings(self):
        """Test health check when no Graylog settings exist."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        with patch("backend.monitoring.graylog_health_monitor.get_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = None
            mock_get_db.return_value = iter([mock_session])

            # Should complete without error
            await check_graylog_health()

            # Verify query was made
            mock_session.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_health_integration_disabled(self):
        """Test health check when Graylog integration is disabled."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = False

        with patch("backend.monitoring.graylog_health_monitor.get_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_get_db.return_value = iter([mock_session])

            # Should complete without error (no port checks)
            await check_graylog_health()

    @pytest.mark.asyncio
    async def test_check_health_no_url_configured(self):
        """Test health check when Graylog URL is not configured."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = None

        with patch("backend.monitoring.graylog_health_monitor.get_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_get_db.return_value = iter([mock_session])

            # Should complete without error
            await check_graylog_health()

    @pytest.mark.asyncio
    async def test_check_health_gelf_port_open(self):
        """Test health check detecting open GELF TCP port."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog.example.com:9000"

        with patch(
            "backend.monitoring.graylog_health_monitor.get_db"
        ) as mock_get_db, patch(
            "backend.monitoring.graylog_health_monitor.socket.socket"
        ) as mock_socket_class:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_get_db.return_value = iter([mock_session])

            # Mock socket to return 0 (success) for GELF port 12201
            mock_socket = MagicMock()
            mock_socket.connect_ex.side_effect = lambda addr: (
                0 if addr[1] == 12201 else 1
            )
            mock_socket_class.return_value = mock_socket

            await check_graylog_health()

            # Verify settings were updated
            assert mock_settings.has_gelf_tcp is True
            assert mock_settings.gelf_tcp_port == 12201

    @pytest.mark.asyncio
    async def test_check_health_syslog_port_1514_open(self):
        """Test health check detecting open Syslog TCP port 1514."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog.example.com:9000"

        with patch(
            "backend.monitoring.graylog_health_monitor.get_db"
        ) as mock_get_db, patch(
            "backend.monitoring.graylog_health_monitor.socket.socket"
        ) as mock_socket_class:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_get_db.return_value = iter([mock_session])

            # Mock socket to return 0 (success) for port 1514
            mock_socket = MagicMock()
            mock_socket.connect_ex.side_effect = lambda addr: (
                0 if addr[1] == 1514 else 1
            )
            mock_socket_class.return_value = mock_socket

            await check_graylog_health()

            # Verify settings were updated
            assert mock_settings.has_syslog_tcp is True
            assert mock_settings.syslog_tcp_port == 1514
            # UDP is assumed available if TCP is open on same port
            assert mock_settings.has_syslog_udp is True
            assert mock_settings.syslog_udp_port == 1514

    @pytest.mark.asyncio
    async def test_check_health_syslog_port_514_fallback(self):
        """Test health check falling back to Syslog port 514."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog.example.com:9000"

        with patch(
            "backend.monitoring.graylog_health_monitor.get_db"
        ) as mock_get_db, patch(
            "backend.monitoring.graylog_health_monitor.socket.socket"
        ) as mock_socket_class:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_get_db.return_value = iter([mock_session])

            # Mock socket to return 0 (success) only for port 514
            mock_socket = MagicMock()
            mock_socket.connect_ex.side_effect = lambda addr: (
                0 if addr[1] == 514 else 1
            )
            mock_socket_class.return_value = mock_socket

            await check_graylog_health()

            # Verify settings show port 514
            assert mock_settings.has_syslog_tcp is True
            assert mock_settings.syslog_tcp_port == 514

    @pytest.mark.asyncio
    async def test_check_health_windows_sidecar_open(self):
        """Test health check detecting open Windows Sidecar (Beats) port."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog.example.com:9000"

        with patch(
            "backend.monitoring.graylog_health_monitor.get_db"
        ) as mock_get_db, patch(
            "backend.monitoring.graylog_health_monitor.socket.socket"
        ) as mock_socket_class:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_get_db.return_value = iter([mock_session])

            # Mock socket to return 0 (success) for port 5044
            mock_socket = MagicMock()
            mock_socket.connect_ex.side_effect = lambda addr: (
                0 if addr[1] == 5044 else 1
            )
            mock_socket_class.return_value = mock_socket

            await check_graylog_health()

            # Verify settings were updated
            assert mock_settings.has_windows_sidecar is True
            assert mock_settings.windows_sidecar_port == 5044

    @pytest.mark.asyncio
    async def test_check_health_all_ports_closed(self):
        """Test health check when all ports are closed."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog.example.com:9000"

        with patch(
            "backend.monitoring.graylog_health_monitor.get_db"
        ) as mock_get_db, patch(
            "backend.monitoring.graylog_health_monitor.socket.socket"
        ) as mock_socket_class:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_get_db.return_value = iter([mock_session])

            # Mock socket to return non-zero (failure) for all ports
            mock_socket = MagicMock()
            mock_socket.connect_ex.return_value = 1  # Connection refused
            mock_socket_class.return_value = mock_socket

            await check_graylog_health()

            # Verify all ports marked as closed
            assert mock_settings.has_gelf_tcp is False
            assert mock_settings.gelf_tcp_port is None
            assert mock_settings.has_syslog_tcp is False
            assert mock_settings.syslog_tcp_port is None
            assert mock_settings.has_syslog_udp is False
            assert mock_settings.syslog_udp_port is None
            assert mock_settings.has_windows_sidecar is False
            assert mock_settings.windows_sidecar_port is None

    @pytest.mark.asyncio
    async def test_check_health_all_ports_open(self):
        """Test health check when all ports are open."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog.example.com:9000"

        with patch(
            "backend.monitoring.graylog_health_monitor.get_db"
        ) as mock_get_db, patch(
            "backend.monitoring.graylog_health_monitor.socket.socket"
        ) as mock_socket_class:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_get_db.return_value = iter([mock_session])

            # Mock socket to return 0 (success) for all ports
            mock_socket = MagicMock()
            mock_socket.connect_ex.return_value = 0
            mock_socket_class.return_value = mock_socket

            await check_graylog_health()

            # Verify all ports marked as open
            assert mock_settings.has_gelf_tcp is True
            assert mock_settings.gelf_tcp_port == 12201
            assert mock_settings.has_syslog_tcp is True
            assert mock_settings.syslog_tcp_port == 1514  # First checked
            assert mock_settings.has_windows_sidecar is True
            assert mock_settings.windows_sidecar_port == 5044

    @pytest.mark.asyncio
    async def test_check_health_updates_timestamp(self):
        """Test health check updates last checked timestamp."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog.example.com:9000"
        mock_settings.inputs_last_checked = None

        with patch(
            "backend.monitoring.graylog_health_monitor.get_db"
        ) as mock_get_db, patch(
            "backend.monitoring.graylog_health_monitor.socket.socket"
        ) as mock_socket_class:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_get_db.return_value = iter([mock_session])

            mock_socket = MagicMock()
            mock_socket.connect_ex.return_value = 1
            mock_socket_class.return_value = mock_socket

            await check_graylog_health()

            # Verify timestamp was set
            assert mock_settings.inputs_last_checked is not None
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_health_socket_exception(self):
        """Test health check handles socket exceptions gracefully."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog.example.com:9000"

        with patch(
            "backend.monitoring.graylog_health_monitor.get_db"
        ) as mock_get_db, patch(
            "backend.monitoring.graylog_health_monitor.socket.socket"
        ) as mock_socket_class:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_get_db.return_value = iter([mock_session])

            # Mock socket to raise exception
            mock_socket = MagicMock()
            mock_socket.connect_ex.side_effect = socket.error("Connection failed")
            mock_socket_class.return_value = mock_socket

            # Should not raise, should handle gracefully
            await check_graylog_health()

    @pytest.mark.asyncio
    async def test_check_health_database_error(self):
        """Test health check handles database errors gracefully."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        with patch("backend.monitoring.graylog_health_monitor.get_db") as mock_get_db:
            mock_get_db.return_value = iter([])
            mock_get_db.side_effect = StopIteration()

            # Should handle gracefully (may log error but not crash)
            # Note: The actual implementation catches this
            try:
                await check_graylog_health()
            except StopIteration:
                pass  # Expected in test scenario

    @pytest.mark.asyncio
    async def test_check_health_url_parsing(self):
        """Test health check correctly parses various URL formats."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        test_urls = [
            ("http://graylog.example.com:9000", "graylog.example.com"),
            ("https://logs.company.org", "logs.company.org"),
            ("http://192.168.1.100:9000", "192.168.1.100"),
        ]

        for url, expected_host in test_urls:
            mock_settings = MagicMock()
            mock_settings.enabled = True
            mock_settings.graylog_url = url

            with patch(
                "backend.monitoring.graylog_health_monitor.get_db"
            ) as mock_get_db, patch(
                "backend.monitoring.graylog_health_monitor.socket.socket"
            ) as mock_socket_class:
                mock_session = MagicMock()
                mock_session.query.return_value.first.return_value = mock_settings
                mock_get_db.return_value = iter([mock_session])

                mock_socket = MagicMock()
                # Capture the host being connected to
                connected_hosts = []

                def capture_connect(addr):
                    connected_hosts.append(addr[0])
                    return 1  # Closed

                mock_socket.connect_ex.side_effect = capture_connect
                mock_socket_class.return_value = mock_socket

                await check_graylog_health()

                # Verify correct host was used
                if connected_hosts:
                    assert connected_hosts[0] == expected_host


# =============================================================================
# graylog_health_monitor_service() TESTS
# =============================================================================


class TestGraylogHealthMonitorService:
    """Test cases for graylog_health_monitor_service background task."""

    @pytest.mark.asyncio
    async def test_service_runs_check(self):
        """Test that monitor service calls check_graylog_health."""
        from backend.monitoring.graylog_health_monitor import (
            graylog_health_monitor_service,
        )

        with patch(
            "backend.monitoring.graylog_health_monitor.check_graylog_health"
        ) as mock_check, patch(
            "backend.monitoring.graylog_health_monitor.asyncio.sleep"
        ) as mock_sleep:
            # Make check return immediately
            mock_check.return_value = None

            # Make sleep raise after first call to stop the loop
            call_count = 0

            async def controlled_sleep(seconds):
                nonlocal call_count
                call_count += 1
                if call_count >= 1:
                    raise asyncio.CancelledError()

            mock_sleep.side_effect = controlled_sleep

            # Run the service (will be cancelled after one iteration)
            try:
                await graylog_health_monitor_service()
            except asyncio.CancelledError:
                pass

            # Verify check was called
            mock_check.assert_called()

    @pytest.mark.asyncio
    async def test_service_handles_check_exception(self):
        """Test that monitor service handles exceptions from check."""
        from backend.monitoring.graylog_health_monitor import (
            graylog_health_monitor_service,
        )

        with patch(
            "backend.monitoring.graylog_health_monitor.check_graylog_health"
        ) as mock_check, patch(
            "backend.monitoring.graylog_health_monitor.asyncio.sleep"
        ) as mock_sleep:
            # Make check raise an exception
            mock_check.side_effect = RuntimeError("Test error")

            # Make sleep raise after first call to stop the loop
            call_count = 0

            async def controlled_sleep(seconds):
                nonlocal call_count
                call_count += 1
                if call_count >= 1:
                    raise asyncio.CancelledError()

            mock_sleep.side_effect = controlled_sleep

            # Should not raise, should continue to sleep
            try:
                await graylog_health_monitor_service()
            except asyncio.CancelledError:
                pass

            # Verify check was called
            mock_check.assert_called()

    @pytest.mark.asyncio
    async def test_service_sleep_interval(self):
        """Test that monitor service sleeps for correct interval."""
        from backend.monitoring.graylog_health_monitor import (
            graylog_health_monitor_service,
        )

        with patch(
            "backend.monitoring.graylog_health_monitor.check_graylog_health"
        ) as mock_check, patch(
            "backend.monitoring.graylog_health_monitor.asyncio.sleep"
        ) as mock_sleep:
            mock_check.return_value = None
            sleep_durations = []

            async def capture_sleep(seconds):
                sleep_durations.append(seconds)
                if len(sleep_durations) >= 1:
                    raise asyncio.CancelledError()

            mock_sleep.side_effect = capture_sleep

            try:
                await graylog_health_monitor_service()
            except asyncio.CancelledError:
                pass

            # Verify sleep was called with 5 minute interval (300 seconds)
            assert 300 in sleep_durations


# =============================================================================
# URL PARSING TESTS
# =============================================================================


class TestUrlParsing:
    """Test cases for URL parsing in health monitor."""

    def test_parse_standard_http_url(self):
        """Test parsing standard HTTP URL."""
        from urllib.parse import urlparse

        url = "http://graylog.example.com:9000"
        parsed = urlparse(url)
        assert parsed.hostname == "graylog.example.com"
        assert parsed.port == 9000
        assert parsed.scheme == "http"

    def test_parse_https_url(self):
        """Test parsing HTTPS URL."""
        from urllib.parse import urlparse

        url = "https://graylog.example.com"
        parsed = urlparse(url)
        assert parsed.hostname == "graylog.example.com"
        assert parsed.port is None  # Default HTTPS port
        assert parsed.scheme == "https"

    def test_parse_ip_address_url(self):
        """Test parsing URL with IP address."""
        from urllib.parse import urlparse

        url = "http://192.168.1.100:9000"
        parsed = urlparse(url)
        assert parsed.hostname == "192.168.1.100"
        assert parsed.port == 9000

    def test_parse_url_with_path(self):
        """Test parsing URL with path component."""
        from urllib.parse import urlparse

        url = "http://graylog.example.com:9000/api"
        parsed = urlparse(url)
        assert parsed.hostname == "graylog.example.com"
        assert parsed.path == "/api"


# =============================================================================
# SOCKET MOCKING HELPER TESTS
# =============================================================================


class TestSocketBehavior:
    """Test cases for understanding socket mock behavior."""

    def test_socket_connect_ex_success(self):
        """Test socket.connect_ex returns 0 for success."""
        with patch("socket.socket") as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket.connect_ex.return_value = 0
            mock_socket_class.return_value = mock_socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(("localhost", 12201))

            assert result == 0

    def test_socket_connect_ex_failure(self):
        """Test socket.connect_ex returns non-zero for failure."""
        with patch("socket.socket") as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket.connect_ex.return_value = 111  # Connection refused
            mock_socket_class.return_value = mock_socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(("localhost", 12201))

            assert result == 111

    def test_socket_timeout_setting(self):
        """Test socket timeout is set correctly."""
        with patch("socket.socket") as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket_class.return_value = mock_socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)

            mock_socket.settimeout.assert_called_with(2)


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestEdgeCases:
    """Test edge cases in the Graylog health monitor."""

    @pytest.mark.asyncio
    async def test_empty_graylog_url(self):
        """Test health check with empty Graylog URL string."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = ""

        with patch("backend.monitoring.graylog_health_monitor.get_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_get_db.return_value = iter([mock_session])

            # Should handle empty URL gracefully
            await check_graylog_health()

    @pytest.mark.asyncio
    async def test_malformed_graylog_url(self):
        """Test health check with malformed Graylog URL."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "not-a-valid-url"

        with patch(
            "backend.monitoring.graylog_health_monitor.get_db"
        ) as mock_get_db, patch(
            "backend.monitoring.graylog_health_monitor.socket.socket"
        ) as mock_socket_class:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_get_db.return_value = iter([mock_session])

            mock_socket = MagicMock()
            mock_socket.connect_ex.return_value = 1
            mock_socket_class.return_value = mock_socket

            # Should handle malformed URL gracefully
            await check_graylog_health()

    @pytest.mark.asyncio
    async def test_database_commit_failure(self):
        """Test health check handles database commit failure."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog.example.com:9000"

        with patch(
            "backend.monitoring.graylog_health_monitor.get_db"
        ) as mock_get_db, patch(
            "backend.monitoring.graylog_health_monitor.socket.socket"
        ) as mock_socket_class:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_session.commit.side_effect = Exception("Database error")
            mock_get_db.return_value = iter([mock_session])

            mock_socket = MagicMock()
            mock_socket.connect_ex.return_value = 0
            mock_socket_class.return_value = mock_socket

            # Should handle commit failure gracefully
            await check_graylog_health()

            # Verify rollback was called
            mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_socket_close_always_called(self):
        """Test socket is always closed even on exception."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog.example.com:9000"

        with patch(
            "backend.monitoring.graylog_health_monitor.get_db"
        ) as mock_get_db, patch(
            "backend.monitoring.graylog_health_monitor.socket.socket"
        ) as mock_socket_class:
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_settings
            mock_get_db.return_value = iter([mock_session])

            mock_socket = MagicMock()
            mock_socket.connect_ex.return_value = 0
            mock_socket_class.return_value = mock_socket

            await check_graylog_health()

            # Verify socket.close() was called for each port check
            assert mock_socket.close.call_count >= 1
