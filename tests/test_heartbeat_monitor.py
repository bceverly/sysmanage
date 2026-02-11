"""
Tests for backend/monitoring/heartbeat_monitor.py module.
Tests heartbeat monitoring service for tracking host status.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCheckHostHeartbeats:
    """Tests for check_host_heartbeats function."""

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_check_heartbeats_no_stale_hosts(self, mock_timeout, mock_get_db):
        """Test check when no hosts are stale."""
        from backend.monitoring.heartbeat_monitor import check_host_heartbeats

        mock_timeout.return_value = 5
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )
        mock_get_db.return_value = iter([mock_db])

        await check_host_heartbeats()

        mock_db.commit.assert_not_called()
        mock_db.close.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_check_heartbeats_with_stale_hosts(self, mock_timeout, mock_get_db):
        """Test check marks stale hosts as down."""
        from backend.monitoring.heartbeat_monitor import check_host_heartbeats

        mock_timeout.return_value = 5

        mock_host1 = MagicMock()
        mock_host1.fqdn = "host1.example.com"
        mock_host1.status = "up"
        mock_host1.active = True

        mock_host2 = MagicMock()
        mock_host2.fqdn = "host2.example.com"
        mock_host2.status = "up"
        mock_host2.active = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = [
            mock_host1,
            mock_host2,
        ]
        mock_get_db.return_value = iter([mock_db])

        await check_host_heartbeats()

        assert mock_host1.status == "down"
        assert mock_host1.active is False
        assert mock_host2.status == "down"
        assert mock_host2.active is False
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @pytest.mark.asyncio
    async def test_check_heartbeats_db_connection_error(self, mock_get_db):
        """Test handles database connection error gracefully."""
        from backend.monitoring.heartbeat_monitor import check_host_heartbeats

        mock_get_db.side_effect = Exception("Connection failed")

        # Should not raise
        await check_host_heartbeats()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_check_heartbeats_query_error(self, mock_timeout, mock_get_db):
        """Test handles query error gracefully."""
        from backend.monitoring.heartbeat_monitor import check_host_heartbeats

        mock_timeout.return_value = 5
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Query failed")
        mock_get_db.return_value = iter([mock_db])

        # Should not raise
        await check_host_heartbeats()

        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()


class TestHeartbeatMonitorService:
    """Tests for heartbeat_monitor_service function."""

    @patch("backend.monitoring.heartbeat_monitor.check_host_heartbeats")
    @patch("backend.monitoring.heartbeat_monitor.asyncio.sleep")
    @pytest.mark.asyncio
    async def test_service_runs_checks(self, mock_sleep, mock_check):
        """Test service runs heartbeat checks."""
        from backend.monitoring.heartbeat_monitor import heartbeat_monitor_service

        call_count = 0

        async def mock_check_coro():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError()

        mock_check.side_effect = mock_check_coro
        mock_sleep.return_value = None

        with pytest.raises(asyncio.CancelledError):
            await heartbeat_monitor_service()

        assert call_count >= 2

    @patch("backend.monitoring.heartbeat_monitor.check_host_heartbeats")
    @patch("backend.monitoring.heartbeat_monitor.asyncio.sleep")
    @pytest.mark.asyncio
    async def test_service_handles_errors(self, mock_sleep, mock_check):
        """Test service handles errors and continues."""
        from backend.monitoring.heartbeat_monitor import heartbeat_monitor_service

        call_count = 0

        async def mock_check_coro():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Check failed")
            elif call_count >= 2:
                raise asyncio.CancelledError()

        mock_check.side_effect = mock_check_coro
        mock_sleep.return_value = None

        with pytest.raises(asyncio.CancelledError):
            await heartbeat_monitor_service()

        # Should have tried at least twice despite first error
        assert call_count >= 2
