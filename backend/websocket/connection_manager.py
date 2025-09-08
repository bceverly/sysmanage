"""
WebSocket connection manager for handling real-time bidirectional communication
with SysManage agents across the fleet.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import WebSocket
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class AgentConnection:
    """Represents a single agent WebSocket connection."""

    def __init__(self, websocket: WebSocket, agent_id: str = None):
        self.websocket = websocket
        self.agent_id = agent_id or str(uuid.uuid4())
        self.hostname = None
        self.ipv4 = None
        self.ipv6 = None
        self.platform = None
        self.connected_at = datetime.now(timezone.utc)
        self.last_seen = datetime.now(timezone.utc)
        self.pending_commands = []

    async def send_message(self, message: dict):
        """Send a message to this agent."""
        try:
            await self.websocket.send_text(json.dumps(message))
            return True
        except ConnectionClosed as e:
            # WebSocket connection closed - this is a communication error that warrants disconnection
            logger.error(
                "WEBSOCKET_COMMUNICATION_ERROR: Connection closed during send to agent %s: %s",
                getattr(self, "hostname", "unknown"),
                e,
            )
            return False
        except (OSError, RuntimeError) as e:
            # Network/system level communication errors - warrants disconnection
            logger.error(
                "WEBSOCKET_COMMUNICATION_ERROR: Network/system error sending to agent %s: %s",
                getattr(self, "hostname", "unknown"),
                e,
            )
            return False
        except (TypeError, ValueError) as e:
            # Protocol/data errors - message format issues, don't disconnect
            logger.warning(
                "WEBSOCKET_PROTOCOL_ERROR: Invalid message format to agent %s (connection stays active): %s",
                getattr(self, "hostname", "unknown"),
                e,
            )
            return True  # Return True to avoid triggering disconnection
        except Exception as e:
            # Generic connection errors should trigger disconnection
            error_msg = str(e)
            if (
                "connection" in error_msg.lower()
                or "network" in error_msg.lower()
                or "timeout" in error_msg.lower()
            ):
                # Network/connection related errors - warrants disconnection
                logger.error(
                    "WEBSOCKET_COMMUNICATION_ERROR: Connection error sending to agent %s: %s",
                    getattr(self, "hostname", "unknown"),
                    e,
                )
                return False

            # Other unknown errors - log as protocol error and don't disconnect to be safe
            logger.warning(
                "WEBSOCKET_PROTOCOL_ERROR: Unknown error sending to agent %s (connection stays active): %s",
                getattr(self, "hostname", "unknown"),
                e,
            )
            return True  # Return True to avoid triggering disconnection

    def update_info(
        self,
        hostname: str = None,
        ipv4: str = None,
        ipv6: str = None,
        platform: str = None,
    ):
        """Update agent information."""
        if hostname:
            self.hostname = hostname
        if ipv4:
            self.ipv4 = ipv4
        if ipv6:
            self.ipv6 = ipv6
        if platform:
            self.platform = platform
        self.last_seen = datetime.now(timezone.utc)


class ConnectionManager:
    """Manages all active WebSocket connections to agents."""

    def __init__(self):
        # Map of agent_id -> AgentConnection
        self.active_connections: Dict[str, AgentConnection] = {}
        # Map of hostname -> agent_id for quick lookup
        self.hostname_to_agent: Dict[str, str] = {}
        self._command_queue = asyncio.Queue()

    async def connect(
        self, websocket: WebSocket, agent_id: str = None
    ) -> AgentConnection:
        """Accept a new agent connection."""
        await websocket.accept()
        connection = AgentConnection(websocket, agent_id)
        self.active_connections[connection.agent_id] = connection
        # Agent connected
        return connection

    def disconnect(self, agent_id: str):
        """Remove an agent connection."""
        if agent_id in self.active_connections:
            connection = self.active_connections[agent_id]
            if connection.hostname and connection.hostname in self.hostname_to_agent:
                del self.hostname_to_agent[connection.hostname]
            del self.active_connections[agent_id]
            # Agent disconnected

    def register_agent(
        self,
        agent_id: str,
        hostname: str,
        ipv4: str = None,
        ipv6: str = None,
        platform: str = None,
    ):
        """Register agent details for lookup."""
        if agent_id in self.active_connections:
            connection = self.active_connections[agent_id]
            connection.update_info(hostname, ipv4, ipv6, platform)
            if hostname:
                self.hostname_to_agent[hostname] = agent_id
            return connection
        return None

    async def send_to_agent(self, agent_id: str, message: dict) -> bool:
        """Send a message to a specific agent."""
        if agent_id in self.active_connections:
            connection = self.active_connections[agent_id]
            return await connection.send_message(message)
        return False

    async def send_to_hostname(self, hostname: str, message: dict) -> bool:
        """Send a message to an agent by hostname (case-insensitive)."""
        logger.info("send_to_hostname called for hostname: %s", hostname)
        logger.info("Available hostnames: %s", list(self.hostname_to_agent.keys()))

        # Try exact match first
        if hostname in self.hostname_to_agent:
            agent_id = self.hostname_to_agent[hostname]
            logger.info(
                "Found agent_id %s for hostname %s (exact match)", agent_id, hostname
            )
            return await self.send_to_agent(agent_id, message)

        # Try case-insensitive match
        hostname_lower = hostname.lower()
        for registered_hostname, agent_id in self.hostname_to_agent.items():
            if registered_hostname.lower() == hostname_lower:
                logger.info(
                    "Found agent_id %s for hostname %s (case-insensitive match with %s)",
                    agent_id,
                    hostname,
                    registered_hostname,
                )
                return await self.send_to_agent(agent_id, message)

        logger.warning("Hostname %s not found in hostname_to_agent mapping", hostname)
        return False

    async def send_to_host(self, host_id: int, message: dict) -> bool:
        """Send a message to an agent by database host ID."""
        # Import here to avoid circular imports
        from backend.persistence.db import get_engine
        from backend.persistence.models import Host
        from sqlalchemy.orm import sessionmaker

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=get_engine()
        )

        with session_local() as session:
            host = session.query(Host).filter(Host.id == host_id).first()
            if host and host.fqdn:
                return await self.send_to_hostname(host.fqdn, message)
        return False

    async def broadcast_to_all(self, message: dict) -> int:
        """Broadcast a message to all connected agents."""
        successful_sends = 0
        failed_agents = []

        for agent_id, connection in self.active_connections.items():
            if await connection.send_message(message):
                successful_sends += 1
            else:
                failed_agents.append(agent_id)

        # Clean up failed connections
        for agent_id in failed_agents:
            self.disconnect(agent_id)

        return successful_sends

    async def broadcast_to_platform(self, platform: str, message: dict) -> int:
        """Broadcast a message to all agents of a specific platform."""
        successful_sends = 0
        failed_agents = []

        for agent_id, connection in self.active_connections.items():
            if connection.platform == platform:
                if await connection.send_message(message):
                    successful_sends += 1
                else:
                    failed_agents.append(agent_id)

        # Clean up failed connections
        for agent_id in failed_agents:
            self.disconnect(agent_id)

        return successful_sends

    def get_active_agents(self) -> List[dict]:
        """Get list of all active agents with their details."""
        return [
            {
                "agent_id": agent_id,
                "hostname": conn.hostname,
                "ipv4": conn.ipv4,
                "ipv6": conn.ipv6,
                "platform": conn.platform,
                "connected_at": conn.connected_at.isoformat(),
                "last_seen": conn.last_seen.isoformat(),
            }
            for agent_id, conn in self.active_connections.items()
        ]

    def get_agent_by_hostname(self, hostname: str) -> Optional[dict]:
        """Get agent details by hostname."""
        if hostname in self.hostname_to_agent:
            agent_id = self.hostname_to_agent[hostname]
            if agent_id in self.active_connections:
                conn = self.active_connections[agent_id]
                return {
                    "agent_id": agent_id,
                    "hostname": conn.hostname,
                    "ipv4": conn.ipv4,
                    "ipv6": conn.ipv6,
                    "platform": conn.platform,
                    "connected_at": conn.connected_at.isoformat(),
                    "last_seen": conn.last_seen.isoformat(),
                }
        return None


# Global connection manager instance
connection_manager = ConnectionManager()
