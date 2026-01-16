"""
Tests for the core message handlers module.

This module tests the core message handler functions for authentication,
system info, and heartbeat messages from agents.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from backend.api.message_handlers_core import (
    validate_host_authentication,
    handle_system_info,
    handle_heartbeat,
)


class TestValidateHostAuthentication:
    """Test cases for validate_host_authentication function."""

    @pytest.mark.asyncio
    async def test_returns_true_when_no_auth_provided(self, session, mock_connection):
        """Test that validation passes when no auth is provided."""
        message_data = {}

        is_valid, host = await validate_host_authentication(
            session, mock_connection, message_data
        )

        assert is_valid is True
        assert host is None

    @pytest.mark.asyncio
    async def test_validates_host_token_successfully(self, session, mock_connection):
        """Test that valid host token passes validation."""
        from backend.persistence.models import Host

        # Create a host with a token
        host = Host(
            fqdn="test.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            host_token="valid-token-12345",
            active=True,
            approval_status="approved",
        )
        session.add(host)
        session.commit()

        message_data = {"host_token": "valid-token-12345"}

        is_valid, found_host = await validate_host_authentication(
            session, mock_connection, message_data
        )

        assert is_valid is True
        assert found_host is not None
        assert found_host.fqdn == "test.example.com"

    @pytest.mark.asyncio
    async def test_rejects_invalid_host_token(self, session, mock_connection):
        """Test that invalid host token fails validation."""
        mock_connection.send_message = AsyncMock()

        message_data = {"host_token": "invalid-token"}

        is_valid, host = await validate_host_authentication(
            session, mock_connection, message_data
        )

        assert is_valid is False
        assert host is None
        mock_connection.send_message.assert_called_once()
        call_args = mock_connection.send_message.call_args[0][0]
        assert call_args["message_type"] == "error"
        assert call_args["error_type"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_validates_host_id_successfully(self, session, mock_connection):
        """Test that valid host ID passes validation (legacy)."""
        from backend.persistence.models import Host

        host = Host(
            fqdn="test.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
            approval_status="approved",
        )
        session.add(host)
        session.commit()

        message_data = {"host_id": str(host.id)}

        is_valid, found_host = await validate_host_authentication(
            session, mock_connection, message_data
        )

        assert is_valid is True
        assert found_host is not None
        assert found_host.id == host.id

    @pytest.mark.asyncio
    async def test_rejects_invalid_host_id(self, session, mock_connection):
        """Test that invalid host ID fails validation."""
        mock_connection.send_message = AsyncMock()

        message_data = {"host_id": str(uuid.uuid4())}

        is_valid, host = await validate_host_authentication(
            session, mock_connection, message_data
        )

        assert is_valid is False
        assert host is None
        mock_connection.send_message.assert_called_once()


class TestHandleSystemInfo:
    """Test cases for handle_system_info function."""

    @pytest.mark.asyncio
    async def test_returns_none_without_hostname(self, session, mock_connection):
        """Test that missing hostname returns None."""
        message_data = {
            "ipv4": "192.168.1.100",
            "ipv6": "::1",
        }

        with patch(
            "backend.utils.host_validation.validate_host_id",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await handle_system_info(session, mock_connection, message_data)

            assert result is None

    @pytest.mark.asyncio
    async def test_registers_new_host(self, session, mock_connection):
        """Test that new host is registered from system info."""
        mock_connection.agent_id = "agent-123"
        mock_connection.hostname = None

        message_data = {
            "hostname": "newhost.example.com",
            "ipv4": "192.168.1.100",
            "ipv6": "::1",
            "platform": "Linux",
        }

        with patch(
            "backend.api.host_utils.update_or_create_host",
            new_callable=AsyncMock,
        ) as mock_update:
            mock_host = MagicMock()
            mock_host.id = uuid.uuid4()
            mock_host.fqdn = "newhost.example.com"
            mock_host.approval_status = "pending"
            mock_host.host_token = "token-123"
            mock_update.return_value = mock_host

            with patch(
                "backend.websocket.connection_manager.connection_manager"
            ) as mock_conn_mgr:
                with patch(
                    "backend.utils.host_validation.validate_host_id",
                    new_callable=AsyncMock,
                    return_value=True,
                ):
                    result = await handle_system_info(
                        session, mock_connection, message_data
                    )

                    assert result["message_type"] == "registration_pending"
                    assert result["approved"] is False
                    mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_success_for_approved_host(self, session, mock_connection):
        """Test that approved host gets success response."""
        mock_connection.agent_id = "agent-123"
        mock_connection.hostname = None

        message_data = {
            "hostname": "approved.example.com",
            "ipv4": "192.168.1.100",
            "ipv6": "::1",
            "platform": "Linux",
        }

        with patch(
            "backend.api.host_utils.update_or_create_host",
            new_callable=AsyncMock,
        ) as mock_update:
            mock_host = MagicMock()
            mock_host.id = uuid.uuid4()
            mock_host.fqdn = "approved.example.com"
            mock_host.approval_status = "approved"
            mock_host.host_token = "token-123"
            mock_update.return_value = mock_host

            with patch(
                "backend.websocket.connection_manager.connection_manager"
            ) as mock_conn_mgr:
                with patch(
                    "backend.utils.host_validation.validate_host_id",
                    new_callable=AsyncMock,
                    return_value=True,
                ):
                    result = await handle_system_info(
                        session, mock_connection, message_data
                    )

                    assert result["message_type"] == "registration_success"
                    assert result["approved"] is True
                    assert result["hostname"] == "approved.example.com"
                    assert "host_token" in result


class TestHandleHeartbeat:
    """Test cases for handle_heartbeat function."""

    @pytest.mark.asyncio
    async def test_updates_existing_host(self, session, mock_connection):
        """Test that heartbeat updates existing host."""
        from backend.persistence.models import Host

        # Create a host
        host = Host(
            fqdn="heartbeat.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
            status="down",
            approval_status="approved",
        )
        session.add(host)
        session.commit()

        mock_connection.host_id = host.id
        mock_connection.hostname = "heartbeat.example.com"
        mock_connection.send_message = AsyncMock()

        message_data = {"message_id": "msg-123"}

        with patch(
            "backend.utils.host_validation.validate_host_id",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await handle_heartbeat(session, mock_connection, message_data)

            assert result["message_type"] == "heartbeat_ack"
            mock_connection.send_message.assert_called_once()

            # Verify host was updated
            updated_host = session.query(Host).filter_by(id=host.id).first()
            assert updated_host.status == "up"
            assert updated_host.active is True

    @pytest.mark.asyncio
    async def test_returns_error_without_host_id(self, session, mock_connection):
        """Test that heartbeat without host_id returns error."""
        mock_connection.host_id = None
        mock_connection.hostname = None

        message_data = {"message_id": "msg-123"}

        with patch(
            "backend.utils.host_validation.validate_host_id",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await handle_heartbeat(session, mock_connection, message_data)

            assert result["message_type"] == "error"
            assert result["error_type"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_updates_privileged_status(self, session, mock_connection):
        """Test that heartbeat updates privileged status."""
        from backend.persistence.models import Host

        host = Host(
            fqdn="privileged.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
            status="up",
            approval_status="approved",
            is_agent_privileged=False,
        )
        session.add(host)
        session.commit()

        mock_connection.host_id = host.id
        mock_connection.hostname = "privileged.example.com"
        mock_connection.send_message = AsyncMock()

        message_data = {"message_id": "msg-123", "is_privileged": True}

        with patch(
            "backend.utils.host_validation.validate_host_id",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await handle_heartbeat(session, mock_connection, message_data)

            updated_host = session.query(Host).filter_by(id=host.id).first()
            assert updated_host.is_agent_privileged is True

    @pytest.mark.asyncio
    async def test_updates_enabled_shells(self, session, mock_connection):
        """Test that heartbeat updates enabled shells."""
        from backend.persistence.models import Host

        host = Host(
            fqdn="shells.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
            status="up",
            approval_status="approved",
        )
        session.add(host)
        session.commit()

        mock_connection.host_id = host.id
        mock_connection.hostname = "shells.example.com"
        mock_connection.send_message = AsyncMock()

        message_data = {
            "message_id": "msg-123",
            "enabled_shells": ["/bin/bash", "/bin/zsh"],
        }

        with patch(
            "backend.utils.host_validation.validate_host_id",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await handle_heartbeat(session, mock_connection, message_data)

            import json

            updated_host = session.query(Host).filter_by(id=host.id).first()
            shells = json.loads(updated_host.enabled_shells)
            assert "/bin/bash" in shells
            assert "/bin/zsh" in shells

    @pytest.mark.asyncio
    async def test_handles_mock_connection(self, session, mock_connection):
        """Test that mock connections are handled correctly."""
        mock_connection.host_id = "<Mock id='123'>"
        mock_connection.hostname = None
        mock_connection.send_message = AsyncMock()

        message_data = {"message_id": "msg-123"}

        with patch(
            "backend.utils.host_validation.validate_host_id",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await handle_heartbeat(session, mock_connection, message_data)

            # Mock connection should get acknowledgment
            mock_connection.send_message.assert_called_once()
            assert result["message_type"] == "success"
