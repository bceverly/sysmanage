"""
Unit tests for server-side discovery beacon service.
"""

import json
import socket
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from backend.discovery.discovery_service import (
    DiscoveryBeaconService,
    DiscoveryProtocol,
    NetworkScanner,
)


class TestDiscoveryBeaconService:
    """Test cases for DiscoveryBeaconService."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch("backend.discovery.discovery_service.get_config") as mock_config:
            mock_config.return_value = {
                "api": {"host": "localhost", "port": 8000, "certFile": "/path/to/cert"},
                "webui": {"port": 8080},
            }
            self.service = DiscoveryBeaconService(discovery_port=31337)

    @pytest.mark.asyncio
    async def test_start_beacon_service(self):
        """Test starting the beacon service."""
        mock_loop = AsyncMock()
        mock_transport = Mock()
        mock_protocol = Mock()

        mock_loop.create_datagram_endpoint.return_value = (
            mock_transport,
            mock_protocol,
        )

        with patch("asyncio.get_running_loop", return_value=mock_loop):
            await self.service.start_beacon_service()

            assert self.service.running is True
            assert self.service.transport == mock_transport
            assert self.service.protocol == mock_protocol

            mock_loop.create_datagram_endpoint.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_beacon_service_failure(self):
        """Test beacon service startup failure."""
        mock_loop = AsyncMock()
        mock_loop.create_datagram_endpoint.side_effect = Exception(
            "Port already in use"
        )

        with patch("asyncio.get_running_loop", return_value=mock_loop):
            with pytest.raises(Exception, match="Port already in use"):
                await self.service.start_beacon_service()

    @pytest.mark.asyncio
    async def test_stop_beacon_service(self):
        """Test stopping the beacon service."""
        mock_transport = Mock()
        self.service.transport = mock_transport
        self.service.running = True

        await self.service.stop_beacon_service()

        mock_transport.close.assert_called_once()
        assert self.service.running is False

    def test_create_discovery_response_basic(self):
        """Test creating basic discovery response."""
        request_data = {
            "service": "sysmanage-agent",
            "hostname": "test-agent",
            "platform": "Linux",
        }

        response = self.service.create_discovery_response(request_data)

        assert response["service"] == "sysmanage-server"
        assert response["version"] == "1.0.0"
        assert "timestamp" in response
        assert "server_info" in response

        server_info = response["server_info"]
        assert server_info["hostname"] == "localhost"
        assert server_info["api_port"] == 8000
        assert server_info["use_ssl"] is True
        assert server_info["websocket_endpoint"] == "/api/agent/connect"

    def test_create_discovery_response_with_config_request(self):
        """Test creating discovery response with configuration."""
        request_data = {
            "service": "sysmanage-agent",
            "hostname": "test-agent",
            "request_config": True,
        }

        response = self.service.create_discovery_response(request_data)

        assert "default_config" in response
        config = response["default_config"]
        assert config["server"]["hostname"] == "localhost"
        assert config["server"]["port"] == 8000
        assert config["logging"]["file"] == "/var/log/sysmanage-agent-test-agent.log"

    def test_create_default_agent_config(self):
        """Test creating default agent configuration."""
        hostname = "test-agent-01"
        config = self.service.create_default_agent_config(hostname)

        assert config["server"]["hostname"] == "localhost"
        assert config["server"]["port"] == 8000
        assert config["server"]["use_https"] is True
        assert config["client"]["registration_retry_interval"] == 30
        assert config["logging"]["file"] == f"/var/log/sysmanage-agent-{hostname}.log"
        assert config["websocket"]["auto_reconnect"] is True
        assert config["i18n"]["language"] == "en"


class TestDiscoveryProtocol:
    """Test cases for DiscoveryProtocol."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_beacon = Mock()
        self.protocol = DiscoveryProtocol(self.mock_beacon)
        self.protocol.transport = Mock()

    def test_connection_made(self):
        """Test protocol connection establishment."""
        mock_transport = Mock()
        self.protocol.connection_made(mock_transport)
        assert self.protocol.transport == mock_transport

    def test_datagram_received_valid_request(self):
        """Test handling valid discovery request."""
        request = {
            "service": "sysmanage-agent",
            "hostname": "test-agent",
            "platform": "Linux",
        }

        response = {
            "service": "sysmanage-server",
            "server_info": {"hostname": "localhost"},
        }

        self.mock_beacon.create_discovery_response.return_value = response

        with patch.object(
            self.protocol, "validate_discovery_request", return_value=True
        ):
            self.protocol.datagram_received(
                json.dumps(request).encode("utf-8"), ("192.168.1.100", 12345)
            )

            self.mock_beacon.create_discovery_response.assert_called_once_with(request)
            self.protocol.transport.sendto.assert_called_once()

    def test_datagram_received_invalid_request(self):
        """Test handling invalid discovery request."""
        request = {"service": "wrong-service"}

        with patch.object(
            self.protocol, "validate_discovery_request", return_value=False
        ):
            self.protocol.datagram_received(
                json.dumps(request).encode("utf-8"), ("192.168.1.100", 12345)
            )

            self.mock_beacon.create_discovery_response.assert_not_called()
            self.protocol.transport.sendto.assert_not_called()

    def test_datagram_received_invalid_json(self):
        """Test handling invalid JSON in request."""
        invalid_json = b"not valid json"

        self.protocol.datagram_received(invalid_json, ("192.168.1.100", 12345))

        # Should not crash, just log warning
        self.mock_beacon.create_discovery_response.assert_not_called()

    def test_validate_discovery_request_valid(self):
        """Test validation of valid discovery request."""
        request = {
            "service": "sysmanage-agent",
            "hostname": "test-agent",
            "platform": "Linux",
        }

        is_valid = self.protocol.validate_discovery_request(
            request, ("192.168.1.100", 12345)
        )
        assert is_valid is True

    def test_validate_discovery_request_missing_service(self):
        """Test validation of request missing service field."""
        request = {"hostname": "test-agent"}

        is_valid = self.protocol.validate_discovery_request(
            request, ("192.168.1.100", 12345)
        )
        assert is_valid is False

    def test_validate_discovery_request_wrong_service(self):
        """Test validation of request with wrong service."""
        request = {"service": "wrong-service", "hostname": "test-agent"}

        is_valid = self.protocol.validate_discovery_request(
            request, ("192.168.1.100", 12345)
        )
        assert is_valid is False

    def test_validate_discovery_request_missing_hostname(self):
        """Test validation of request missing hostname."""
        request = {"service": "sysmanage-agent"}

        is_valid = self.protocol.validate_discovery_request(
            request, ("192.168.1.100", 12345)
        )
        assert is_valid is False

    def test_validate_discovery_request_invalid_hostname(self):
        """Test validation of request with invalid hostname."""
        request = {"service": "sysmanage-agent", "hostname": ""}  # Empty hostname

        is_valid = self.protocol.validate_discovery_request(
            request, ("192.168.1.100", 12345)
        )
        assert is_valid is False

    def test_error_received(self):
        """Test protocol error handling."""
        exc = Exception("Test error")

        # Should not raise exception, just log
        self.protocol.error_received(exc)


class TestNetworkScanner:
    """Test cases for NetworkScanner."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch("backend.discovery.discovery_service.get_config") as mock_config:
            mock_config.return_value = {"api": {"host": "localhost", "port": 8000}}
            self.scanner = NetworkScanner()

    @pytest.mark.asyncio
    @patch("socket.socket")
    async def test_broadcast_server_announcement(self, mock_socket_class):
        """Test broadcasting server announcement."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket

        await self.scanner.broadcast_server_announcement("192.168.1.255", 31338)

        mock_socket_class.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
        mock_socket.setsockopt.assert_called_once()
        mock_socket.sendto.assert_called_once()
        mock_socket.close.assert_called_once()

        # Check announcement structure
        call_args = mock_socket.sendto.call_args[0]
        announcement_data = json.loads(call_args[0].decode("utf-8"))

        assert announcement_data["service"] == "sysmanage-server"
        assert announcement_data["announcement_type"] == "server_broadcast"
        assert "server_info" in announcement_data

    @pytest.mark.asyncio
    @patch("socket.socket")
    async def test_broadcast_server_announcement_failure(self, mock_socket_class):
        """Test broadcast failure handling."""
        mock_socket = Mock()
        # Make sendto fail before socket operations
        mock_socket.sendto.side_effect = Exception("Network error")
        mock_socket_class.return_value = mock_socket

        # Should not raise exception, but should still try to close socket
        await self.scanner.broadcast_server_announcement("192.168.1.255", 31338)

    @patch("builtins.__import__")
    def test_get_local_subnets_with_netifaces(self, mock_import):
        """Test getting local subnets with netifaces available."""
        # Mock netifaces and ipaddress modules
        mock_netifaces = Mock()
        mock_netifaces.interfaces.return_value = ["eth0"]
        mock_netifaces.ifaddresses.return_value = {
            2: [{"addr": "192.168.1.10", "netmask": "255.255.255.0"}]  # AF_INET = 2
        }
        mock_netifaces.AF_INET = 2

        mock_ipaddress = Mock()
        mock_network = Mock()
        mock_network.broadcast_address = "192.168.1.255"
        mock_ipaddress.IPv4Network.return_value = mock_network

        def import_side_effect(name, *args, **kwargs):
            if name == "netifaces":
                return mock_netifaces
            elif name == "ipaddress":
                return mock_ipaddress
            return __import__(name, *args, **kwargs)

        mock_import.side_effect = import_side_effect

        addresses = self.scanner.get_local_subnets()

        assert "192.168.1.255" in addresses

    @patch("builtins.__import__")
    def test_get_local_subnets_without_netifaces(self, mock_import):
        """Test getting local subnets when netifaces is not available."""

        def import_side_effect(name, *args, **kwargs):
            if name == "netifaces":
                raise ImportError("No module named 'netifaces'")
            return __import__(name, *args, **kwargs)

        mock_import.side_effect = import_side_effect

        addresses = self.scanner.get_local_subnets()

        # Should return default addresses
        expected_defaults = [
            "192.168.1.255",
            "192.168.0.255",
            "10.0.0.255",
            "172.16.255.255",
        ]
        for addr in expected_defaults:
            assert addr in addresses

    @patch("builtins.__import__")
    def test_get_local_subnets_with_exception(self, mock_import):
        """Test subnet detection with exception handling."""
        mock_netifaces = Mock()
        mock_netifaces.interfaces.side_effect = Exception("Network error")

        def import_side_effect(name, *args, **kwargs):
            if name == "netifaces":
                return mock_netifaces
            return __import__(name, *args, **kwargs)

        mock_import.side_effect = import_side_effect

        addresses = self.scanner.get_local_subnets()

        # Should return default addresses on error
        expected_defaults = [
            "192.168.1.255",
            "192.168.0.255",
            "10.0.0.255",
            "172.16.255.255",
        ]
        assert len(addresses) == len(expected_defaults)
        for addr in expected_defaults:
            assert addr in addresses
