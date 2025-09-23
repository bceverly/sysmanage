"""
Test server-side data separation functionality.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.api.host import HostRegistration, HostRegistrationLegacy
from backend.persistence import models
from backend.websocket.messages import (
    MessageType,
    OSVersionUpdateMessage,
    create_message,
)


class TestServerDataSeparation:
    """Test server-side handling of separated data flow."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        return Mock()

    @pytest.fixture
    def mock_host(self):
        """Create a mock host for testing."""
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

    def test_host_registration_model_minimal_fields(self):
        """Test that HostRegistration only accepts minimal fields."""
        minimal_data = {
            "active": True,
            "fqdn": "minimal-host.example.com",
            "hostname": "minimal-host",
            "ipv4": "10.0.0.1",
            "ipv6": "2001:db8::1",
        }

        reg = HostRegistration(**minimal_data)

        assert reg.active is True
        assert reg.fqdn == "minimal-host.example.com"
        assert reg.hostname == "minimal-host"
        assert reg.ipv4 == "10.0.0.1"
        assert reg.ipv6 == "2001:db8::1"

    def test_host_registration_model_rejects_os_fields(self):
        """Test that HostRegistration rejects OS version fields."""
        os_data = {
            "active": True,
            "fqdn": "test-host.example.com",
            "hostname": "test-host",
            "platform": "Linux",  # This should be rejected
            "machine_architecture": "x86_64",  # This should be rejected
        }

        with pytest.raises(
            Exception
        ):  # Pydantic raises ValidationError for extra fields
            # pydantic should reject unknown fields
            HostRegistration(**os_data)

    def test_legacy_registration_model_accepts_all_fields(self):
        """Test that HostRegistrationLegacy accepts all fields for backward compatibility."""
        comprehensive_data = {
            "active": True,
            "fqdn": "legacy-host.example.com",
            "hostname": "legacy-host",
            "ipv4": "172.16.0.1",
            "ipv6": None,
            "platform": "Windows",
            "platform_release": "10",
            "platform_version": "10.0.19045",
            "architecture": "64bit",
            "processor": "Intel Core i7",
            "machine_architecture": "AMD64",
            "python_version": "3.11.5",
            "os_info": {"windows_version": "10", "windows_service_pack": "10.0.19045"},
        }

        reg = HostRegistrationLegacy(**comprehensive_data)

        # Should accept all fields
        assert reg.platform == "Windows"
        assert reg.machine_architecture == "AMD64"
        assert reg.os_info["windows_version"] == "10"

    def test_os_version_update_message_creation(self):
        """Test creation of OS version update message."""
        os_data = {
            "platform": "Darwin",
            "platform_release": "23.1.0",
            "platform_version": "Darwin Kernel Version 23.1.0",
            "architecture": "64bit",
            "processor": "arm",
            "machine_architecture": "arm64",
            "python_version": "3.11.5",
            "os_info": {"mac_version": "14.1.1"},
        }

        message = OSVersionUpdateMessage(**os_data)

        assert message.message_type == MessageType.OS_VERSION_UPDATE
        assert message.data["platform"] == "Darwin"
        assert message.data["machine_architecture"] == "arm64"
        assert message.data["os_info"]["mac_version"] == "14.1.1"

    def test_create_message_factory_os_version(self):
        """Test message factory creates OS version update message correctly."""
        raw_message = {
            "message_type": "os_version_update",
            "message_id": "msg-456",
            "timestamp": "2023-12-01T10:30:00Z",
            "data": {
                "platform": "Linux",
                "platform_release": "6.1.0-16-amd64",
                "machine_architecture": "x86_64",
                "processor": "AMD Ryzen 7",
                "os_info": {"distribution": "Debian", "distribution_version": "12"},
            },
        }

        message = create_message(raw_message)

        assert isinstance(message, OSVersionUpdateMessage)
        assert message.message_type == MessageType.OS_VERSION_UPDATE
        assert message.data["platform"] == "Linux"
        assert message.data["machine_architecture"] == "x86_64"

    @pytest.mark.asyncio
    async def test_handle_os_version_update_database_update(
        self, mock_db_session, mock_host
    ):
        """Test that OS version update handler correctly updates database."""
        # Mock connection
        mock_connection = Mock()
        mock_connection.hostname = "test-host.example.com"
        mock_connection.send_message = AsyncMock()

        # Mock database query
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        # OS version data from agent
        message_data = {
            "message_id": "msg-789",
            "platform": "FreeBSD",
            "platform_release": "14.0-RELEASE",
            "platform_version": "FreeBSD 14.0-RELEASE",
            "machine_architecture": "amd64",
            "processor": "Intel Xeon",
            "python_version": "3.11.6",
            "os_info": {"version": "14.0-RELEASE-p2"},
        }

        from backend.api.agent import handle_os_version_update

        await handle_os_version_update(mock_db_session, mock_connection, message_data)

        # Verify all OS version fields were updated
        assert mock_host.platform == "FreeBSD"
        assert mock_host.platform_release == "14.0-RELEASE"
        assert mock_host.platform_version == "FreeBSD 14.0-RELEASE"
        assert mock_host.machine_architecture == "amd64"
        assert mock_host.processor == "Intel Xeon"

        # Verify JSON os_details field
        expected_os_details = json.dumps({"version": "14.0-RELEASE-p2"})
        assert mock_host.os_details == expected_os_details

        # Verify timestamp was set
        assert mock_host.os_version_updated_at is not None
        assert isinstance(mock_host.os_version_updated_at, datetime)

        # Verify database operations
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(mock_host)

    @pytest.mark.asyncio
    async def test_handle_os_version_update_acknowledgment(
        self, mock_db_session, mock_host
    ):
        """Test that OS version update handler sends acknowledgment."""
        mock_connection = Mock()
        mock_connection.hostname = "ack-test-host.example.com"
        mock_connection.send_message = AsyncMock()

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        message_data = {
            "message_id": "ack-test-123",
            "platform": "OpenBSD",
            "machine_architecture": "amd64",
        }

        from backend.api.agent import handle_os_version_update

        await handle_os_version_update(mock_db_session, mock_connection, message_data)

        # Verify acknowledgment was sent
        mock_connection.send_message.assert_called_once()
        ack_call = mock_connection.send_message.call_args[0][0]

        assert ack_call["message_type"] == "ack"
        assert ack_call["message_id"] == "ack-test-123"
        assert ack_call["data"]["status"] == "os_version_updated"

    @pytest.mark.asyncio
    async def test_connection_manager_send_to_host(self):
        """Test that connection manager can send to host by ID."""
        from backend.websocket.connection_manager import ConnectionManager

        # Mock database components
        mock_host = Mock()
        mock_host.fqdn = "target-host.example.com"

        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker, patch(
            "backend.persistence.db.get_engine"
        ):

            mock_sessionmaker.return_value.return_value.__enter__.return_value = (
                mock_session
            )

            # Create connection manager and mock hostname sending
            conn_mgr = ConnectionManager()
            conn_mgr.send_to_hostname = AsyncMock(return_value=True)

            test_message = {"command": "test"}
            result = await conn_mgr.send_to_host(42, test_message)

            assert result is True
            conn_mgr.send_to_hostname.assert_called_once_with(
                "target-host.example.com", test_message
            )

    def test_data_separation_message_types(self):
        """Test that message types support data separation."""
        # Test basic system info (minimal registration data)
        system_info_raw = {
            "message_type": "system_info",
            "data": {
                "hostname": "sys-info-host",
                "ipv4": "192.168.1.200",
                "ipv6": "2001:db8::200",
            },
        }

        system_msg = create_message(system_info_raw)
        assert system_msg.message_type == MessageType.SYSTEM_INFO
        assert system_msg.data["hostname"] == "sys-info-host"

        # Test OS version update (comprehensive OS data)
        os_update_raw = {
            "message_type": "os_version_update",
            "data": {
                "platform": "NetBSD",
                "machine_architecture": "amd64",
                "os_info": {"version": "9.3"},
            },
        }

        os_msg = create_message(os_update_raw)
        assert os_msg.message_type == MessageType.OS_VERSION_UPDATE
        assert os_msg.data["platform"] == "NetBSD"

    def test_architecture_coverage_in_os_messages(self):
        """Test that OS version messages support various architectures."""
        architectures = [
            ("x86_64", "Intel/AMD 64-bit"),
            ("aarch64", "ARM 64-bit"),
            ("arm64", "ARM 64-bit Apple"),
            ("riscv64", "RISC-V 64-bit"),
            ("ppc64le", "PowerPC 64-bit LE"),
            ("s390x", "IBM System Z"),
            ("sparc64", "SPARC 64-bit"),
        ]

        for arch, description in architectures:
            os_data = {
                "platform": "Linux",
                "machine_architecture": arch,
                "processor": description,
                "os_info": {"arch_notes": f"Testing {arch}"},
            }

            message = OSVersionUpdateMessage(**os_data)
            assert message.data["machine_architecture"] == arch
            assert message.data["processor"] == description
