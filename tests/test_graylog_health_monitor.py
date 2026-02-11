"""
Tests for backend/monitoring/graylog_health_monitor.py module.
Tests Graylog health monitoring and port detection functionality.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestCheckGraylogHealth:
    """Tests for check_graylog_health function."""

    @patch("backend.monitoring.graylog_health_monitor.get_db")
    @pytest.mark.asyncio
    async def test_check_graylog_health_db_error(self, mock_get_db):
        """Test when database connection fails."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_get_db.side_effect = Exception("DB connection failed")

        # Should not raise, just log error
        await check_graylog_health()

    @patch("backend.monitoring.graylog_health_monitor.get_db")
    @pytest.mark.asyncio
    async def test_check_graylog_health_no_settings(self, mock_get_db):
        """Test when no Graylog settings exist."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_db = MagicMock()
        mock_db.query.return_value.first.return_value = None
        mock_get_db.return_value = iter([mock_db])

        await check_graylog_health()
        # Should return early, no error

    @patch("backend.monitoring.graylog_health_monitor.get_db")
    @pytest.mark.asyncio
    async def test_check_graylog_health_disabled(self, mock_get_db):
        """Test when Graylog integration is disabled."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = False

        mock_db = MagicMock()
        mock_db.query.return_value.first.return_value = mock_settings
        mock_get_db.return_value = iter([mock_db])

        await check_graylog_health()
        # Should return early

    @patch("backend.monitoring.graylog_health_monitor.get_db")
    @pytest.mark.asyncio
    async def test_check_graylog_health_no_url(self, mock_get_db):
        """Test when Graylog URL is not configured."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = None

        mock_db = MagicMock()
        mock_db.query.return_value.first.return_value = mock_settings
        mock_get_db.return_value = iter([mock_db])

        await check_graylog_health()
        # Should log warning and return

    @patch("backend.monitoring.graylog_health_monitor.socket")
    @patch("backend.monitoring.graylog_health_monitor.get_db")
    @pytest.mark.asyncio
    async def test_check_graylog_health_with_open_ports(
        self, mock_get_db, mock_socket_module
    ):
        """Test successful port detection."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog.example.com:9000"

        mock_db = MagicMock()
        mock_db.query.return_value.first.return_value = mock_settings
        mock_get_db.return_value = iter([mock_db])

        # Mock socket to simulate open ports
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0  # Port is open
        mock_socket_module.socket.return_value = mock_sock
        mock_socket_module.AF_INET = 2
        mock_socket_module.SOCK_STREAM = 1
        mock_socket_module.SOCK_DGRAM = 2

        await check_graylog_health()

        # Verify settings were updated
        assert mock_settings.has_gelf_tcp is True
        assert mock_settings.gelf_tcp_port == 12201
        mock_db.commit.assert_called_once()

    @patch("backend.monitoring.graylog_health_monitor.socket")
    @patch("backend.monitoring.graylog_health_monitor.get_db")
    @pytest.mark.asyncio
    async def test_check_graylog_health_ports_closed(
        self, mock_get_db, mock_socket_module
    ):
        """Test when all ports are closed."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog.example.com:9000"

        mock_db = MagicMock()
        mock_db.query.return_value.first.return_value = mock_settings
        mock_get_db.return_value = iter([mock_db])

        # Mock socket to simulate closed ports
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 111  # Connection refused
        mock_socket_module.socket.return_value = mock_sock
        mock_socket_module.AF_INET = 2
        mock_socket_module.SOCK_STREAM = 1
        mock_socket_module.SOCK_DGRAM = 2

        await check_graylog_health()

        # Verify settings show no open ports
        assert mock_settings.has_gelf_tcp is False
        assert mock_settings.gelf_tcp_port is None
        assert mock_settings.has_syslog_tcp is False
        assert mock_settings.has_syslog_udp is False
        assert mock_settings.has_windows_sidecar is False

    @patch("backend.monitoring.graylog_health_monitor.socket")
    @patch("backend.monitoring.graylog_health_monitor.get_db")
    @pytest.mark.asyncio
    async def test_check_graylog_health_socket_exception(
        self, mock_get_db, mock_socket_module
    ):
        """Test handling of socket exceptions."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog.example.com:9000"

        mock_db = MagicMock()
        mock_db.query.return_value.first.return_value = mock_settings
        mock_get_db.return_value = iter([mock_db])

        # Mock socket to raise exception
        mock_socket_module.socket.side_effect = Exception("Socket error")
        mock_socket_module.AF_INET = 2
        mock_socket_module.SOCK_STREAM = 1

        await check_graylog_health()

        # Should handle exception gracefully
        mock_db.commit.assert_called_once()

    @patch("backend.monitoring.graylog_health_monitor.get_db")
    @pytest.mark.asyncio
    async def test_check_graylog_health_url_parsing(self, mock_get_db):
        """Test URL parsing for hostname extraction."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "https://graylog.internal.company.com:9000/api"

        mock_db = MagicMock()
        mock_db.query.return_value.first.return_value = mock_settings
        mock_get_db.return_value = iter([mock_db])

        with patch("backend.monitoring.graylog_health_monitor.socket") as mock_socket:
            mock_sock = MagicMock()
            mock_sock.connect_ex.return_value = 111
            mock_socket.socket.return_value = mock_sock
            mock_socket.AF_INET = 2
            mock_socket.SOCK_STREAM = 1
            mock_socket.SOCK_DGRAM = 2

            await check_graylog_health()

    @patch("backend.monitoring.graylog_health_monitor.get_db")
    @pytest.mark.asyncio
    async def test_check_graylog_health_commit_error(self, mock_get_db):
        """Test handling of database commit error."""
        from backend.monitoring.graylog_health_monitor import check_graylog_health

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.graylog_url = "http://graylog:9000"

        mock_db = MagicMock()
        mock_db.query.return_value.first.return_value = mock_settings
        mock_db.commit.side_effect = Exception("Commit failed")
        mock_get_db.return_value = iter([mock_db])

        with patch("backend.monitoring.graylog_health_monitor.socket") as mock_socket:
            mock_sock = MagicMock()
            mock_sock.connect_ex.return_value = 111
            mock_socket.socket.return_value = mock_sock
            mock_socket.AF_INET = 2
            mock_socket.SOCK_STREAM = 1
            mock_socket.SOCK_DGRAM = 2

            # Should handle exception and rollback
            await check_graylog_health()
            mock_db.rollback.assert_called_once()


class TestGraylogHealthMonitorService:
    """Tests for graylog_health_monitor_service function."""

    @patch("backend.monitoring.graylog_health_monitor.check_graylog_health")
    @patch("backend.monitoring.graylog_health_monitor.asyncio.sleep")
    @pytest.mark.asyncio
    async def test_graylog_health_monitor_service_runs(self, mock_sleep, mock_check):
        """Test that the service runs and calls check_graylog_health."""
        from backend.monitoring.graylog_health_monitor import (
            graylog_health_monitor_service,
        )

        # Make sleep raise to break the loop after first iteration
        call_count = 0

        async def side_effect(_):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise asyncio.CancelledError()

        mock_sleep.side_effect = side_effect

        with pytest.raises(asyncio.CancelledError):
            await graylog_health_monitor_service()

        mock_check.assert_called_once()

    @patch("backend.monitoring.graylog_health_monitor.check_graylog_health")
    @patch("backend.monitoring.graylog_health_monitor.asyncio.sleep")
    @pytest.mark.asyncio
    async def test_graylog_health_monitor_service_handles_error(
        self, mock_sleep, mock_check
    ):
        """Test that the service handles errors and continues."""
        from backend.monitoring.graylog_health_monitor import (
            graylog_health_monitor_service,
        )

        # First call raises exception, then cancel
        call_count = 0

        async def check_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Check failed")
            raise asyncio.CancelledError()

        mock_check.side_effect = check_side_effect

        sleep_count = 0

        async def sleep_side_effect(_):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError()

        mock_sleep.side_effect = sleep_side_effect

        with pytest.raises(asyncio.CancelledError):
            await graylog_health_monitor_service()
