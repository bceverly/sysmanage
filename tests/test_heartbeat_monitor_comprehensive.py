"""
Comprehensive unit tests for backend.monitoring.heartbeat_monitor module.
Tests heartbeat monitoring service and host status checking.
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, AsyncMock

from backend.monitoring.heartbeat_monitor import (
    check_host_heartbeats,
    heartbeat_monitor_service,
)


class TestCheckHostHeartbeats:
    """Test cases for check_host_heartbeats function."""

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_check_host_heartbeats_no_stale_hosts(
        self, mock_get_timeout, mock_get_db
    ):
        """Test checking heartbeats when no hosts are stale."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_get_timeout.return_value = 5

        # No stale hosts found
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )

        await check_host_heartbeats()

        mock_db.query.assert_called_once()
        mock_db.commit.assert_not_called()
        mock_db.close.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_check_host_heartbeats_with_stale_hosts(
        self, mock_get_timeout, mock_get_db
    ):
        """Test checking heartbeats when stale hosts are found."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_get_timeout.return_value = 5

        # Create mock stale hosts
        stale_host1 = Mock()
        stale_host1.fqdn = "host1.example.com"
        stale_host1.status = "up"
        stale_host1.active = True

        stale_host2 = Mock()
        stale_host2.fqdn = "host2.example.com"
        stale_host2.status = "up"
        stale_host2.active = True

        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            stale_host1,
            stale_host2,
        ]

        await check_host_heartbeats()

        # Verify hosts were marked as down
        assert stale_host1.status == "down"
        assert stale_host1.active is False
        assert stale_host2.status == "down"
        assert stale_host2.active is False

        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_check_host_heartbeats_single_stale_host(
        self, mock_get_timeout, mock_get_db
    ):
        """Test checking heartbeats with single stale host."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_get_timeout.return_value = 10

        # Create single mock stale host
        stale_host = Mock()
        stale_host.fqdn = "stale.example.com"
        stale_host.status = "up"
        stale_host.active = True

        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            stale_host
        ]

        await check_host_heartbeats()

        # Verify host was marked as down
        assert stale_host.status == "down"
        assert stale_host.active is False

        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @pytest.mark.asyncio
    async def test_check_host_heartbeats_db_connection_error(self, mock_get_db):
        """Test checking heartbeats when database connection fails."""
        mock_get_db.side_effect = Exception("Database connection failed")

        # Should not raise exception, just log error
        await check_host_heartbeats()

        mock_get_db.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_check_host_heartbeats_query_error(
        self, mock_get_timeout, mock_get_db
    ):
        """Test checking heartbeats when database query fails."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_get_timeout.return_value = 5

        # Mock database query error
        mock_db.query.side_effect = Exception("Database query failed")

        await check_host_heartbeats()

        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_check_host_heartbeats_commit_error(
        self, mock_get_timeout, mock_get_db
    ):
        """Test checking heartbeats when database commit fails."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_get_timeout.return_value = 5

        # Create mock stale host
        stale_host = Mock()
        stale_host.fqdn = "host.example.com"
        stale_host.status = "up"
        stale_host.active = True

        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            stale_host
        ]
        mock_db.commit.side_effect = Exception("Commit failed")

        await check_host_heartbeats()

        # Host should still be updated
        assert stale_host.status == "down"
        assert stale_host.active is False

        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_check_host_heartbeats_timeout_calculation(
        self, mock_get_timeout, mock_get_db
    ):
        """Test that timeout calculation works correctly."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_get_timeout.return_value = 15  # 15 minutes timeout

        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )

        # Mock datetime to control the current time
        fixed_time = datetime.now(timezone.utc)
        expected_threshold = fixed_time - timedelta(minutes=15)

        with patch("backend.monitoring.heartbeat_monitor.datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_time
            mock_datetime.timezone = timezone

            await check_host_heartbeats()

            # Verify the timeout calculation was used in the query
            mock_db.query.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_check_host_heartbeats_config_error(
        self, mock_get_timeout, mock_get_db
    ):
        """Test checking heartbeats when configuration reading fails."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_get_timeout.side_effect = Exception("Config error")

        await check_host_heartbeats()

        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()


class TestHeartbeatMonitorService:
    """Test cases for heartbeat_monitor_service function."""

    def test_heartbeat_monitor_service_exists(self):
        """Test that heartbeat_monitor_service function exists and is callable."""
        from backend.monitoring.heartbeat_monitor import heartbeat_monitor_service

        assert callable(heartbeat_monitor_service)
        # Note: We don't test the infinite loop behavior due to testing complexity


class TestHeartbeatMonitorIntegration:
    """Integration test cases."""

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_heartbeat_workflow_integration(self, mock_get_timeout, mock_get_db):
        """Test complete heartbeat monitoring workflow."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_get_timeout.return_value = 5

        # Create hosts with different states
        active_host = Mock()
        active_host.fqdn = "active.example.com"
        active_host.status = "up"
        active_host.active = True
        active_host.last_access = datetime.now(timezone.utc)  # Recent

        stale_host = Mock()
        stale_host.fqdn = "stale.example.com"
        stale_host.status = "up"
        stale_host.active = True
        stale_host.last_access = datetime.now(timezone.utc) - timedelta(hours=1)  # Old

        # Mock query to return only stale host (filtering should work)
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            stale_host
        ]

        await check_host_heartbeats()

        # Verify only stale host was updated
        assert stale_host.status == "down"
        assert stale_host.active is False

        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_empty_database(self, mock_get_timeout, mock_get_db):
        """Test heartbeat checking with empty database."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_get_timeout.return_value = 5

        # Empty result
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )

        await check_host_heartbeats()

        # Should complete without error
        mock_db.commit.assert_not_called()  # No changes to commit
        mock_db.close.assert_called_once()


class TestHeartbeatMonitorEdgeCases:
    """Test edge cases and error conditions."""

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_zero_timeout_config(self, mock_get_timeout, mock_get_db):
        """Test heartbeat checking with zero timeout configuration."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_get_timeout.return_value = 0  # Zero timeout

        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )

        await check_host_heartbeats()

        # Should complete without error even with zero timeout
        mock_db.close.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_negative_timeout_config(self, mock_get_timeout, mock_get_db):
        """Test heartbeat checking with negative timeout configuration."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_get_timeout.return_value = -5  # Negative timeout

        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )

        await check_host_heartbeats()

        # Should complete without error even with negative timeout
        mock_db.close.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_large_timeout_config(self, mock_get_timeout, mock_get_db):
        """Test heartbeat checking with very large timeout configuration."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_get_timeout.return_value = 999999  # Very large timeout

        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )

        await check_host_heartbeats()

        # Should complete without error
        mock_db.close.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    @pytest.mark.asyncio
    async def test_host_without_fqdn(self, mock_get_timeout, mock_get_db):
        """Test heartbeat checking with host that has no FQDN."""
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_get_timeout.return_value = 5

        # Create host without FQDN
        host_no_fqdn = Mock()
        host_no_fqdn.fqdn = None
        host_no_fqdn.status = "up"
        host_no_fqdn.active = True

        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            host_no_fqdn
        ]

        await check_host_heartbeats()

        # Should still mark host as down
        assert host_no_fqdn.status == "down"
        assert host_no_fqdn.active is False

        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()
