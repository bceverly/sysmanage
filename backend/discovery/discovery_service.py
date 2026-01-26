"""
Network discovery service for SysManage server.
Provides UDP beacon service for agent auto-discovery and configuration distribution.
"""

import asyncio
import ipaddress
import json
import logging
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

try:
    import netifaces
except ImportError:
    netifaces = None

from backend.config.config import get_config

logger = logging.getLogger(__name__)


class DiscoveryBeaconService:
    """
    UDP beacon service that responds to agent discovery requests.
    Runs on port 31337 (UDP) to provide server discovery and basic configuration.
    """

    def __init__(
        self, discovery_port_param: int = 31337, bind_address_param: str = "127.0.0.1"
    ):
        self.discovery_port = discovery_port_param
        # Security: Default to localhost only. Set to "0.0.0.0" in config only if needed
        # for multi-host discovery
        self.bind_address = bind_address_param
        self.config = get_config()
        self.running = False
        self.transport = None
        self.protocol = None

    async def start_beacon_service(self):
        """Start the UDP discovery beacon service."""
        loop = asyncio.get_running_loop()

        try:
            # Create UDP server - bind to specific address for security
            self.transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: DiscoveryProtocol(self),
                local_addr=(self.bind_address, self.discovery_port),
            )

            self.running = True
            logger.info(
                "Discovery beacon service started on %s:%s",
                self.bind_address,
                self.discovery_port,
            )

        except Exception as e:
            logger.error("Failed to start discovery beacon service: %s", e)
            raise

    async def stop_beacon_service(
        self,
    ):  # NOSONAR: async method required for interface consistency
        """Stop the UDP discovery beacon service."""
        if self.transport:
            self.transport.close()
            self.running = False
            logger.info("Discovery beacon service stopped")

    def create_discovery_response(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a discovery response with server information and basic configuration.

        Args:
            request_data: The discovery request from an agent

        Returns:
            Discovery response dictionary
        """
        server_config = self.config.get("api", {})
        webui_config = self.config.get("webui", {})

        # Basic server information
        response = {
            "service": "sysmanage-server",
            "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "server_info": {
                "hostname": server_config.get("host", "localhost"),
                "api_port": server_config.get("port", 8000),
                "webui_port": webui_config.get("port", 8080),
                "use_ssl": bool(server_config.get("certFile")),
                "websocket_endpoint": "/api/agent/connect",
                "registration_endpoint": "/api/host/register",
            },
        }

        # Add default configuration for new agents
        agent_hostname = request_data.get("hostname", "unknown")
        if request_data.get("request_config", False):
            response["default_config"] = self.create_default_agent_config(
                agent_hostname
            )

        # Add network information
        response["network_info"] = {
            "discovery_port": self.discovery_port,
            "supported_protocols": ["websocket", "https", "http"],
        }

        return response

    def create_default_agent_config(self, hostname: str) -> Dict[str, Any]:
        """
        Create default configuration for a new agent.

        Args:
            hostname: The agent's hostname

        Returns:
            Default agent configuration
        """
        server_config = self.config.get("api", {})

        return {
            "server": {
                "hostname": server_config.get("host", "localhost"),
                "port": server_config.get("port", 8000),
                "use_https": bool(server_config.get("certFile")),
                "api_path": "/api",
            },
            "client": {
                "hostname_override": None,
                "registration_retry_interval": 30,
                "max_registration_retries": 10,
            },
            "logging": {
                "level": "INFO",
                "file": f"/var/log/sysmanage-agent-{hostname}.log",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
            "websocket": {
                "auto_reconnect": True,
                "reconnect_interval": 5,
                "ping_interval": 30,
            },
            "i18n": {"language": "en"},
        }


class DiscoveryProtocol(asyncio.DatagramProtocol):
    """UDP protocol handler for discovery requests."""

    def __init__(self, beacon_service: DiscoveryBeaconService):
        self.beacon_service = beacon_service
        self.transport = None

    def connection_made(self, transport):
        """Called when the UDP socket is ready."""
        self.transport = transport
        logger.debug("Discovery protocol connection established")

    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        """Handle incoming discovery requests."""
        try:
            # Parse the discovery request
            request_data = json.loads(data.decode("utf-8"))

            # Validate this is a legitimate discovery request
            if not self.validate_discovery_request(request_data, addr):
                logger.warning("Invalid discovery request from %s", addr[0])
                return

            # Create response
            response = self.beacon_service.create_discovery_response(request_data)

            # Send response
            response_data = json.dumps(response).encode("utf-8")
            self.transport.sendto(response_data, addr)

            logger.info(
                "Discovery response sent to %s for agent '%s'",
                addr[0],
                request_data.get("hostname", "unknown"),
            )

        except json.JSONDecodeError:
            logger.warning("Invalid JSON in discovery request from %s", addr[0])
        except Exception as e:
            logger.error("Error handling discovery request from %s: %s", addr[0], e)

    def validate_discovery_request(
        self, request_data: Dict[str, Any], _addr: Tuple[str, int]
    ) -> bool:
        """
        Validate a discovery request.

        Args:
            request_data: The request data
            addr: Source address tuple (ip, port)

        Returns:
            True if request is valid
        """
        # Check required fields
        required_fields = ["service", "hostname"]
        for field in required_fields:
            if field not in request_data:
                return False

        # Validate service type
        if request_data.get("service") != "sysmanage-agent":
            return False

        # Basic hostname validation
        hostname = request_data.get("hostname", "")
        if not hostname or len(hostname) < 1 or len(hostname) > 255:
            return False

        # Rate limiting - simple IP-based check
        # In production, implement proper rate limiting

        return True

    def error_received(self, exc):
        """Handle protocol errors."""
        logger.error("Discovery protocol error: %s", exc)


class NetworkScanner:
    """
    Network scanning utilities for discovery service.
    Provides methods to scan for agents and broadcast discovery information.
    """

    def __init__(self):
        self.config = get_config()

    async def broadcast_server_announcement(  # NOSONAR: async method for future async I/O operations
        self, subnet: str = "192.168.1.255", port: int = 31338
    ):
        """
        Broadcast server announcement to help agents discover the server.

        Args:
            subnet: Broadcast address for the subnet
            port: Port to broadcast to (different from discovery port)
        """
        try:
            # Create broadcast socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            # Create announcement
            announcement = {
                "service": "sysmanage-server",
                "announcement_type": "server_broadcast",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "server_info": {
                    "hostname": self.config.get("api", {}).get("host", "localhost"),
                    "api_port": self.config.get("api", {}).get("port", 8000),
                    "discovery_port": 31337,
                    "websocket_endpoint": "/api/agent/connect",
                },
            }

            # Send broadcast
            data = json.dumps(announcement).encode("utf-8")
            sock.sendto(data, (subnet, port))
            sock.close()

            logger.info("Server announcement broadcast to %s:%s", subnet, port)

        except Exception as e:
            logger.error("Failed to broadcast server announcement: %s", e)

    def get_local_subnets(
        self,
    ) -> (
        list
    ):  # NOSONAR: cognitive complexity is justified for network interface enumeration
        """
        Get list of local subnet broadcast addresses.

        Returns:
            List of broadcast addresses to use for announcements
        """
        broadcast_addresses = []

        if netifaces:
            try:
                # Get all network interfaces
                interfaces = netifaces.interfaces()

                for interface in interfaces:
                    addrs = netifaces.ifaddresses(interface)

                    # Check IPv4 addresses
                    if netifaces.AF_INET not in addrs:
                        continue

                    for addr_info in addrs[netifaces.AF_INET]:
                        addr_ip = addr_info.get("addr")
                        netmask = addr_info.get("netmask")

                        if not (addr_ip and netmask and not addr_ip.startswith("127.")):
                            continue

                        try:
                            network = ipaddress.IPv4Network(
                                f"{addr_ip}/{netmask}", strict=False
                            )
                            broadcast_addresses.append(str(network.broadcast_address))
                        except ValueError:
                            continue

            except Exception as e:
                logger.error("Error determining subnet broadcast addresses: %s", e)
        else:
            logger.warning(
                "netifaces module not available, using default broadcast addresses"
            )

        # Fallback to common broadcast addresses if none found
        if not broadcast_addresses:
            broadcast_addresses = [
                "192.168.1.255",
                "192.168.0.255",
                "10.0.0.255",
                "172.16.255.255",
            ]

        return broadcast_addresses


# Global instances
config = get_config()
discovery_config = config.get("discovery", {})
bind_address = discovery_config.get(
    "bind_address", "127.0.0.1"
)  # Secure default: localhost only
discovery_port = discovery_config.get("port", 31337)

discovery_beacon = DiscoveryBeaconService(
    discovery_port_param=discovery_port, bind_address_param=bind_address
)
network_scanner = NetworkScanner()
