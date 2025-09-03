"""
Configuration push functionality for SysManage server.
Allows server to push configuration updates to connected agents.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import Message
from backend.security.communication_security import message_encryption

logger = logging.getLogger(__name__)


class ConfigPushManager:
    """Manages configuration push operations to agents."""

    def __init__(self):
        self.pending_configs: Dict[str, Dict[str, Any]] = {}
        self.config_versions: Dict[str, int] = {}

    def create_agent_config(
        self, hostname: str, config_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a configuration for a specific agent.

        Args:
            hostname: Target agent hostname
            config_data: Configuration data to push

        Returns:
            Configuration with metadata
        """
        # Generate version number
        current_version = self.config_versions.get(hostname, 0) + 1
        self.config_versions[hostname] = current_version

        # Create config with metadata
        agent_config = {
            "version": current_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "target_hostname": hostname,
            "config": config_data,
            "checksum": self._calculate_checksum(config_data),
        }

        return agent_config

    async def push_config_to_agent(
        self, hostname: str, config_data: Dict[str, Any]
    ) -> bool:
        """
        Push configuration to a specific agent.

        Args:
            hostname: Target agent hostname
            config_data: Configuration data to push

        Returns:
            True if config was sent successfully
        """
        try:
            # Create agent config
            agent_config = self.create_agent_config(hostname, config_data)

            # Encrypt sensitive configuration data
            encrypted_config = message_encryption.encrypt_sensitive_data(agent_config)

            # Create config push message
            message = Message(
                message_type="config_update",
                data={
                    "encrypted_config": encrypted_config,
                    "version": agent_config["version"],
                    "requires_restart": config_data.get("requires_restart", False),
                },
            )

            # Send to specific agent
            success = await connection_manager.send_to_hostname(
                hostname, message.to_dict()
            )

            if success:
                # Store as pending config
                self.pending_configs[hostname] = agent_config
                logger.info(
                    "Configuration pushed to agent %s, version %s",
                    hostname,
                    agent_config["version"],
                )
            else:
                logger.warning("Failed to send configuration to agent %s", hostname)

            return success

        except (ValueError, KeyError, OSError) as e:
            logger.error("Error pushing config to agent %s: %s", hostname, e)
            return False

    async def push_config_to_all_agents(
        self, config_data: Dict[str, Any]
    ) -> Dict[str, bool]:
        """
        Push configuration to all connected agents.

        Args:
            config_data: Configuration data to push

        Returns:
            Dictionary mapping hostname to success status
        """
        results = {}

        # Get all active agents
        active_agents = connection_manager.get_active_agents()

        for agent_info in active_agents:
            hostname = agent_info.get("hostname")
            if hostname:
                success = await self.push_config_to_agent(hostname, config_data)
                results[hostname] = success

        logger.info("Configuration pushed to %s agents", len(results))
        return results

    async def push_config_by_platform(
        self, platform: str, config_data: Dict[str, Any]
    ) -> int:
        """
        Push configuration to all agents of a specific platform.

        Args:
            platform: Target platform (e.g., "Linux", "Windows")
            config_data: Configuration data to push

        Returns:
            Number of agents that received the configuration
        """
        # Create encrypted config message
        agent_config = self.create_agent_config(f"platform-{platform}", config_data)
        encrypted_config = message_encryption.encrypt_sensitive_data(agent_config)

        message = Message(
            message_type="config_update",
            data={
                "encrypted_config": encrypted_config,
                "version": agent_config["version"],
                "requires_restart": config_data.get("requires_restart", False),
            },
        )

        # Broadcast to platform
        successful_sends = await connection_manager.broadcast_to_platform(
            platform, message.to_dict()
        )

        logger.info("Configuration pushed to %s %s agents", successful_sends, platform)
        return successful_sends

    def handle_config_acknowledgment(
        self, hostname: str, version: int, success: bool, error: str = None
    ) -> None:
        """
        Handle configuration acknowledgment from agent.

        Args:
            hostname: Agent hostname
            version: Configuration version
            success: Whether config was applied successfully
            error: Error message if failed
        """
        if hostname in self.pending_configs:
            config = self.pending_configs[hostname]

            if config["version"] == version:
                if success:
                    logger.info(
                        "Configuration v%s successfully applied on %s",
                        version,
                        hostname,
                    )
                    # Remove from pending
                    del self.pending_configs[hostname]
                else:
                    logger.error(
                        "Configuration v%s failed on %s: %s", version, hostname, error
                    )
                    # Keep in pending for potential retry
            else:
                logger.warning(
                    "Version mismatch in ack from %s: expected %s, got %s",
                    hostname,
                    config["version"],
                    version,
                )
        else:
            logger.warning("Received ack for unknown config from %s", hostname)

    def get_pending_configs(self) -> Dict[str, Dict[str, Any]]:
        """Get all pending configuration pushes."""
        return self.pending_configs.copy()

    def create_logging_config(
        self, log_level: str = "INFO", log_file: str = None
    ) -> Dict[str, Any]:
        """
        Create a logging configuration update.

        Args:
            log_level: New log level
            log_file: New log file path

        Returns:
            Logging configuration
        """
        config = {
            "logging": {
                "level": log_level,
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
            "requires_restart": False,
        }

        if log_file:
            config["logging"]["file"] = log_file

        return config

    def create_websocket_config(
        self, ping_interval: int = 30, reconnect_interval: int = 5
    ) -> Dict[str, Any]:
        """
        Create a WebSocket configuration update.

        Args:
            ping_interval: Heartbeat interval in seconds
            reconnect_interval: Reconnection interval in seconds

        Returns:
            WebSocket configuration
        """
        return {
            "websocket": {
                "ping_interval": ping_interval,
                "reconnect_interval": reconnect_interval,
                "auto_reconnect": True,
            },
            "requires_restart": False,
        }

    def create_server_config(
        self, hostname: str, port: int = 8000, use_https: bool = False
    ) -> Dict[str, Any]:
        """
        Create a server configuration update.

        Args:
            hostname: Server hostname
            port: Server port
            use_https: Whether to use HTTPS

        Returns:
            Server configuration
        """
        return {
            "server": {
                "hostname": hostname,
                "port": port,
                "use_https": use_https,
                "api_path": "/api",
            },
            "requires_restart": True,
        }

    def _calculate_checksum(self, config_data: Dict[str, Any]) -> str:
        """Calculate checksum for configuration data."""
        config_json = json.dumps(config_data, sort_keys=True)
        return hashlib.sha256(config_json.encode()).hexdigest()[:16]


# Global instance
config_push_manager = ConfigPushManager()
