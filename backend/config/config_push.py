"""
Configuration push functionality for SysManage server.
Allows server to push configuration updates to agents via the durable
DB-backed outbound queue.

Architectural invariant (server-wide):
  Every server -> agent message MUST be persisted to the
  ``message_queue`` table via ``QueueOperations.enqueue_message``.
  The outbound websocket processor is the only sanctioned consumer
  of that table.  Direct ``connection_manager.send_*`` calls bypass
  the queue, lose messages on transient disconnects, and never reach
  offline agents.

Earlier versions of this module called ``connection_manager.send_to_hostname``
and ``connection_manager.broadcast_to_platform`` inline; both are
removed and replaced with per-host queue enqueue.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.security.communication_security import message_encryption
from backend.websocket.messages import Message, MessageType
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)

_queue_ops = QueueOperations()


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

    def _build_config_envelope(
        self, label: str, config_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build the encrypted envelope for a single target.

        ``label`` is only used for version bookkeeping / pending-state
        tracking (it can be a hostname for per-host pushes or a
        platform tag for fan-out pushes).  Returns the message dict
        ready to enqueue, or ``None`` if envelope construction fails.
        """
        try:
            agent_config = self.create_agent_config(label, config_data)
            encrypted_config = message_encryption.encrypt_sensitive_data(agent_config)
            message = Message(
                message_type=MessageType.CONFIG_UPDATE.value,
                data={
                    "encrypted_config": encrypted_config,
                    "version": agent_config["version"],
                    "requires_restart": config_data.get("requires_restart", False),
                },
            )
            self.pending_configs[label] = agent_config
            return message.to_dict()
        except (ValueError, KeyError, OSError) as e:
            logger.error(
                "Error building config envelope for %s: %s", sanitize_log(label), e
            )
            return None

    def _enqueue_for_host(
        self,
        db: Session,
        host_id: str,
        envelope: Dict[str, Any],
    ) -> bool:
        """Persist one OUTBOUND queue row of ``envelope`` for ``host_id``.

        Returns True on success, False if the enqueue raised.  Caller
        is responsible for ``db.commit()`` once the batch is built —
        ``QueueOperations.enqueue_message`` only flushes when given a
        session.
        """
        try:
            _queue_ops.enqueue_message(
                message_type=MessageType.CONFIG_UPDATE.value,
                message_data=envelope,
                direction=QueueDirection.OUTBOUND,
                host_id=host_id,
                db=db,
            )
            return True
        except Exception as enqueue_error:  # pylint: disable=broad-exception-caught
            logger.error(
                "Failed to enqueue config push for host %s: %s",
                host_id,
                enqueue_error,
            )
            return False

    def push_config_to_agent(
        self, db: Session, hostname: str, config_data: Dict[str, Any]
    ) -> bool:
        """Enqueue a configuration push for a specific agent.

        Resolves ``hostname`` to a Host row by ``fqdn`` (only active
        hosts are matched), builds the encrypted envelope, and writes
        one OUTBOUND row to ``message_queue``.  The outbound websocket
        processor picks it up and delivers when the agent is
        connectable — offline agents receive it on reconnect.
        """
        host = (
            db.query(models.Host)
            .filter(models.Host.fqdn == hostname, models.Host.active.is_(True))
            .first()
        )
        if host is None:
            logger.warning(
                "Cannot push config — no active host with fqdn=%s",
                sanitize_log(hostname),
            )
            return False

        envelope = self._build_config_envelope(hostname, config_data)
        if envelope is None:
            return False

        if not self._enqueue_for_host(db, str(host.id), envelope):
            return False

        db.commit()
        logger.info(
            "Configuration enqueued for agent %s, version %s",
            sanitize_log(hostname),
            self.pending_configs[hostname]["version"],
        )
        return True

    def push_config_to_all_agents(
        self, db: Session, config_data: Dict[str, Any]
    ) -> Dict[str, bool]:
        """Enqueue a configuration push for every active host.

        Unlike the legacy implementation which only addressed currently-
        connected agents, this queries ``Host.active=True`` directly so
        offline hosts also receive the update on reconnect.
        """
        hosts = (
            db.query(models.Host.id, models.Host.fqdn)
            .filter(models.Host.active.is_(True))
            .all()
        )
        if not hosts:
            return {}

        results: Dict[str, bool] = {}
        enqueued = 0
        for host_id, fqdn in hosts:
            envelope = self._build_config_envelope(fqdn, config_data)
            if envelope is None:
                results[fqdn] = False
                continue
            ok = self._enqueue_for_host(db, str(host_id), envelope)
            results[fqdn] = ok
            if ok:
                enqueued += 1

        if enqueued:
            db.commit()
        logger.info("Configuration enqueued for %s agent(s)", enqueued)
        return results

    def push_config_by_platform(
        self, db: Session, platform: str, config_data: Dict[str, Any]
    ) -> int:
        """Enqueue a configuration push for every active host on a platform.

        Same fan-out pattern as ``push_config_to_all_agents`` but
        filtered by ``Host.platform``.  Returns the number of rows
        successfully enqueued.
        """
        hosts = (
            db.query(models.Host.id, models.Host.fqdn)
            .filter(
                models.Host.active.is_(True),
                models.Host.platform == platform,
            )
            .all()
        )
        if not hosts:
            return 0

        # One envelope per host (each carries its own encrypted+versioned
        # config); the platform label is folded into the per-host
        # ``create_agent_config`` call so version bookkeeping stays
        # per-host as before.
        enqueued = 0
        for host_id, fqdn in hosts:
            envelope = self._build_config_envelope(fqdn, config_data)
            if envelope is None:
                continue
            if self._enqueue_for_host(db, str(host_id), envelope):
                enqueued += 1

        if enqueued:
            db.commit()
        logger.info(
            "Configuration enqueued for %s agent(s) on platform %s",
            enqueued,
            sanitize_log(platform),
        )
        return enqueued

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
                        sanitize_log(version),
                        sanitize_log(hostname),
                    )
                    # Remove from pending
                    del self.pending_configs[hostname]
                else:
                    logger.error(
                        "Configuration v%s failed on %s: %s",
                        sanitize_log(version),
                        sanitize_log(hostname),
                        sanitize_log(error),
                    )
                    # Keep in pending for potential retry
            else:
                logger.warning(
                    "Version mismatch in ack from %s: expected %s, got %s",
                    sanitize_log(hostname),
                    config["version"],
                    sanitize_log(version),
                )
        else:
            logger.warning(
                "Received ack for unknown config from %s", sanitize_log(hostname)
            )

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
