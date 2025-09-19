"""
Test OS version API functionality on the server side.
"""

import json
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.api.host import router
from backend.persistence import models


class TestOSVersionAPI:
    """Test OS version API endpoints and message handling."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        mock_session = Mock()
        mock_db_func = Mock(return_value=mock_session)
        return mock_db_func, mock_session

    @pytest.fixture
    def mock_host(self):
        """Create a mock host with OS version fields."""
        host = Mock(spec=models.Host)
        host.id = 1
        host.fqdn = "test-host.example.com"
        host.active = True
        host.ipv4 = "192.168.1.100"
        host.ipv6 = "2001:db8::1"
        host.approval_status = "approved"
        host.platform = None
        host.platform_release = None
        host.platform_version = None
        host.machine_architecture = None
        host.processor = None
        host.os_details = None
        host.os_version_updated_at = None
        return host

    def test_host_registration_minimal_fields_only(self, mock_db):
        """Test that host registration only accepts minimal fields."""
        mock_db_func, mock_session = mock_db

        # Test that minimal registration works
        minimal_data = {
            "active": True,
            "fqdn": "new-host.example.com",
            "hostname": "new-host",
            "ipv4": "192.168.1.101",
            "ipv6": "2001:db8::2",
        }

        from backend.api.host import HostRegistration

        reg_model = HostRegistration(**minimal_data)
        assert reg_model.fqdn == "new-host.example.com"
        assert reg_model.active is True

        # Test that OS version fields are rejected
        os_data = {
            **minimal_data,
            "platform": "Linux",  # This should be rejected
            "machine_architecture": "x86_64",  # This should be rejected
        }

        with pytest.raises(Exception):  # Should raise validation error
            HostRegistration(**os_data)

    @pytest.mark.asyncio
    async def test_request_os_version_update_endpoint(self, mock_db, mock_host):
        """Test the request OS version update endpoint."""
        mock_db_func, mock_session = mock_db

        # Mock the query to return our test host
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("backend.api.host.connection_manager") as mock_conn_mgr, patch(
            "backend.api.host.create_command_message"
        ) as mock_create_msg, patch(
            "sqlalchemy.orm.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.host.db.get_engine"
        ):

            mock_conn_mgr.send_to_host = AsyncMock(return_value=True)
            mock_create_msg.return_value = {"command": "update_os_version"}

            # Set up the sessionmaker mock properly for context manager
            mock_session_instance = Mock()
            mock_session_instance.__enter__ = Mock(return_value=mock_session)
            mock_session_instance.__exit__ = Mock(return_value=None)
            mock_sessionmaker.return_value = Mock(return_value=mock_session_instance)

            from backend.api.host import request_os_version_update

            result = await request_os_version_update(1)

            assert result["result"] is True
            assert "OS version update requested" in result["message"]
            mock_conn_mgr.send_to_host.assert_called_once_with(
                1, {"command": "update_os_version"}
            )

    @pytest.mark.asyncio
    async def test_request_os_version_host_not_found(self, mock_db):
        """Test request OS version update with non-existent host."""
        mock_db_func, mock_session = mock_db

        # Mock the query to return no host
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker, patch(
            "backend.api.host.db.get_engine"
        ):
            # Set up the sessionmaker mock properly for context manager
            mock_session_instance = Mock()
            mock_session_instance.__enter__ = Mock(return_value=mock_session)
            mock_session_instance.__exit__ = Mock(return_value=None)
            mock_sessionmaker.return_value = Mock(return_value=mock_session_instance)

            from backend.api.host import request_os_version_update
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await request_os_version_update(999)

            assert exc_info.value.status_code == 404
            assert "Host not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_request_os_version_host_not_approved(self, mock_db, mock_host):
        """Test request OS version update with unapproved host."""
        mock_db_func, mock_session = mock_db
        mock_host.approval_status = "pending"

        # Mock the query to return our test host
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker, patch(
            "backend.api.host.db.get_engine"
        ):
            # Set up the sessionmaker mock properly for context manager
            mock_session_instance = Mock()
            mock_session_instance.__enter__ = Mock(return_value=mock_session)
            mock_session_instance.__exit__ = Mock(return_value=None)
            mock_sessionmaker.return_value = Mock(return_value=mock_session_instance)

            from backend.api.host import request_os_version_update
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await request_os_version_update(1)

            assert exc_info.value.status_code == 400
            assert "Host is not approved" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_handle_os_version_update_message(self, mock_db, mock_host):
        """Test handling of OS version update message from agent."""
        mock_db_func, mock_session = mock_db

        # Mock connection
        mock_connection = Mock()
        mock_connection.hostname = "test-host.example.com"
        mock_connection.send_message = AsyncMock()

        # Mock the query to return our test host
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        # OS version data from agent
        message_data = {
            "message_id": "msg-123",
            "platform": "Linux",
            "platform_release": "5.15.0-88-generic",
            "platform_version": "#98-Ubuntu SMP Mon Oct 2 15:29:04 UTC 2023",
            "machine_architecture": "x86_64",
            "processor": "Intel Core i7-10700K",
            "os_info": {
                "distribution": "Ubuntu",
                "distribution_version": "22.04",
                "distribution_codename": "jammy",
            },
            "python_version": "3.11.5",
        }

        from backend.api.agent import handle_os_version_update

        await handle_os_version_update(mock_session, mock_connection, message_data)

        # Verify host was updated
        assert mock_host.platform == "Linux"
        assert mock_host.platform_release == "5.15.0-88-generic"
        assert mock_host.machine_architecture == "x86_64"
        assert mock_host.processor == "Intel Core i7-10700K"
        assert mock_host.os_details == json.dumps(message_data["os_info"])
        assert mock_host.os_version_updated_at is not None

        # Verify acknowledgment was sent
        mock_connection.send_message.assert_called_once()
        ack_message = mock_connection.send_message.call_args[0][0]
        assert ack_message["message_type"] == "ack"
        assert ack_message["data"]["status"] == "os_version_updated"

    @pytest.mark.asyncio
    async def test_handle_os_version_update_no_hostname_no_ip(self, mock_db):
        """Test handling OS version update when connection has no hostname and no IP lookup possible."""
        mock_db_func, mock_session = mock_db

        # Mock connection without hostname and without websocket.client (no IP available)
        mock_connection = Mock()
        mock_connection.hostname = None
        mock_connection.ipv4 = None
        mock_connection.websocket = Mock()
        mock_connection.websocket.client = None
        mock_connection.send_message = AsyncMock()

        message_data = {"platform": "Linux"}

        from backend.api.agent import handle_os_version_update

        # Should return early without error when no hostname and no IP available
        await handle_os_version_update(mock_session, mock_connection, message_data)

        # Should not send acknowledgment when no hostname can be determined
        mock_connection.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_os_version_update_ip_lookup_success(self, mock_db, mock_host):
        """Test handling OS version update using IP lookup when no hostname in connection."""
        mock_db_func, mock_session = mock_db

        # Mock connection without hostname but with websocket client IP
        mock_connection = Mock()
        mock_connection.hostname = None
        mock_connection.ipv4 = None
        mock_connection.websocket = Mock()
        mock_connection.websocket.client = Mock()
        mock_connection.websocket.client.host = (
            "192.168.1.100"  # IP that matches mock_host
        )
        mock_connection.send_message = AsyncMock()

        # Mock the query to return our test host
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        message_data = {
            "message_id": "msg-456",
            "platform": "Linux",
            "platform_release": "6.2.0-35-generic",
            "machine_architecture": "x86_64",
            "processor": "AMD Ryzen 7",
            "os_info": {"distribution": "Ubuntu", "distribution_version": "23.04"},
        }

        from backend.api.agent import handle_os_version_update

        await handle_os_version_update(mock_session, mock_connection, message_data)

        # Verify host was updated
        assert mock_host.platform == "Linux"
        assert mock_host.platform_release == "6.2.0-35-generic"
        assert mock_host.machine_architecture == "x86_64"
        assert mock_host.processor == "AMD Ryzen 7"

        # Verify acknowledgment was sent
        mock_connection.send_message.assert_called_once()
        ack_message = mock_connection.send_message.call_args[0][0]
        assert ack_message["message_type"] == "ack"
        assert ack_message["data"]["status"] == "os_version_updated"
