"""
Test heartbeat monitoring functionality on the server.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.orm import Session

from backend.config.config import get_heartbeat_timeout_minutes
from backend.monitoring.heartbeat_monitor import check_host_heartbeats
from backend.persistence.models import Host


class TestHeartbeatMonitor:
    """Test heartbeat monitoring functionality."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = Mock(spec=Session)
        session.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )
        session.commit = Mock()
        session.rollback = Mock()
        session.close = Mock()
        return session

    @pytest.fixture
    def mock_host_up(self):
        """Create a mock host that is up."""
        host = Mock(spec=Host)
        host.id = 1
        host.fqdn = "test-host-up.example.com"
        host.status = "up"
        host.active = True
        host.last_access = datetime.utcnow() - timedelta(minutes=2)
        return host

    @pytest.fixture
    def mock_host_down(self):
        """Create a mock host that should be marked down."""
        host = Mock(spec=Host)
        host.id = 2
        host.fqdn = "test-host-down.example.com"
        host.status = "up"
        host.active = True
        host.last_access = datetime.utcnow() - timedelta(
            minutes=10
        )  # Older than timeout
        return host

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    def test_check_host_heartbeats_no_stale_hosts(
        self, mock_timeout, mock_get_db, mock_db_session
    ):
        """Test heartbeat check when no hosts are stale."""
        # Setup
        mock_timeout.return_value = 5
        mock_get_db.return_value = iter([mock_db_session])
        mock_db_session.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )

        # Execute
        asyncio.run(check_host_heartbeats())

        # Verify
        mock_db_session.query.assert_called_once()
        mock_db_session.commit.assert_not_called()
        mock_db_session.close.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    def test_check_host_heartbeats_with_stale_hosts(
        self, mock_timeout, mock_get_db, mock_db_session, mock_host_down
    ):
        """Test heartbeat check when hosts need to be marked down."""
        # Setup
        mock_timeout.return_value = 5
        mock_get_db.return_value = iter([mock_db_session])
        mock_db_session.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            mock_host_down
        ]

        # Execute
        asyncio.run(check_host_heartbeats())

        # Verify
        assert mock_host_down.status == "down"
        assert mock_host_down.active is False
        mock_db_session.commit.assert_called_once()
        mock_db_session.close.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    def test_check_host_heartbeats_multiple_stale_hosts(
        self, mock_timeout, mock_get_db, mock_db_session
    ):
        """Test heartbeat check with multiple stale hosts."""
        # Setup
        mock_timeout.return_value = 5
        mock_get_db.return_value = iter([mock_db_session])

        # Create multiple stale hosts
        host1 = Mock(spec=Host)
        host1.fqdn = "host1.example.com"
        host1.status = "up"
        host1.active = True

        host2 = Mock(spec=Host)
        host2.fqdn = "host2.example.com"
        host2.status = "up"
        host2.active = True

        stale_hosts = [host1, host2]
        mock_db_session.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            stale_hosts
        )

        # Execute
        asyncio.run(check_host_heartbeats())

        # Verify
        for host in stale_hosts:
            assert host.status == "down"
            assert host.active is False
        mock_db_session.commit.assert_called_once()

    @patch("backend.monitoring.heartbeat_monitor.get_db")
    @patch("backend.monitoring.heartbeat_monitor.get_heartbeat_timeout_minutes")
    def test_check_host_heartbeats_database_error(
        self, mock_timeout, mock_get_db, mock_db_session
    ):
        """Test heartbeat check handles database errors gracefully."""
        # Setup
        mock_timeout.return_value = 5
        mock_get_db.return_value = iter([mock_db_session])
        mock_db_session.query.side_effect = Exception("Database error")

        # Execute - should not raise exception
        asyncio.run(check_host_heartbeats())

        # Verify rollback was called
        mock_db_session.rollback.assert_called_once()
        mock_db_session.close.assert_called_once()

    def test_heartbeat_timeout_configuration(self):
        """Test heartbeat timeout configuration."""
        timeout = get_heartbeat_timeout_minutes()
        assert isinstance(timeout, int)
        assert timeout > 0


class TestHeartbeatHandling:
    """Test WebSocket heartbeat message handling."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock WebSocket connection."""
        connection = Mock()
        connection.hostname = "test-host.example.com"
        connection.last_seen = datetime.utcnow()
        connection.send_message = AsyncMock()
        return connection

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = Mock(spec=Session)
        session.commit = Mock()
        return session

    @pytest.fixture
    def mock_host(self):
        """Create a mock host."""
        host = Mock(spec=Host)
        host.fqdn = "test-host.example.com"
        host.last_access = datetime.utcnow() - timedelta(minutes=1)
        host.status = "down"
        host.active = False
        return host

    @pytest.mark.asyncio
    async def test_handle_heartbeat_updates_host_status(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test that heartbeat handling updates host status in database."""
        from backend.api.agent import handle_heartbeat

        # Setup
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        message_data = {"message_id": "test-123"}

        # Execute
        await handle_heartbeat(mock_db_session, mock_connection, message_data)

        # Verify host status was updated
        assert mock_host.status == "up"
        assert mock_host.active is True
        mock_db_session.commit.assert_called_once()

        # Verify acknowledgment was sent
        mock_connection.send_message.assert_called_once()
        ack_message = mock_connection.send_message.call_args[0][0]
        assert ack_message["message_type"] == "ack"
        assert ack_message["data"]["status"] == "received"

    @pytest.mark.asyncio
    async def test_handle_heartbeat_no_hostname(self, mock_db_session, mock_connection):
        """Test heartbeat handling when connection has no hostname."""
        from backend.api.agent import handle_heartbeat

        # Setup
        mock_connection.hostname = None
        message_data = {"message_id": "test-123"}

        # Execute
        await handle_heartbeat(mock_db_session, mock_connection, message_data)

        # Verify database was not queried
        mock_db_session.query.assert_not_called()

        # Verify acknowledgment was still sent
        mock_connection.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_heartbeat_host_not_found(
        self, mock_db_session, mock_connection
    ):
        """Test heartbeat handling when host is not found in database."""
        from backend.api.agent import handle_heartbeat

        # Setup - need to mock connection properties for host creation
        mock_connection.ipv4 = "192.168.1.100"
        mock_connection.ipv6 = "2001:db8::1"
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        mock_db_session.add = Mock()
        mock_db_session.refresh = Mock()
        message_data = {"message_id": "test-123"}

        # Execute
        await handle_heartbeat(mock_db_session, mock_connection, message_data)

        # Verify host was created and committed
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

        # Verify acknowledgment was still sent
        mock_connection.send_message.assert_called_once()
