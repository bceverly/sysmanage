# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Comprehensive tests for backend/config/config_push.py module.
Tests configuration push functionality for SysManage server.
"""

import json
from datetime import datetime
from unittest.mock import Mock, patch

from backend.config.config_push import ConfigPushManager, config_push_manager


class TestConfigPushManager:
    """Test ConfigPushManager class functionality."""

    def test_init(self):
        """Test ConfigPushManager initialization."""
        manager = ConfigPushManager()
        assert isinstance(manager.pending_configs, dict)
        assert isinstance(manager.config_versions, dict)
        assert len(manager.pending_configs) == 0
        assert len(manager.config_versions) == 0

    def test_create_agent_config_basic(self):
        """Test basic agent configuration creation."""
        manager = ConfigPushManager()
        hostname = "test-host"
        config_data = {"test": "value", "number": 42}

        result = manager.create_agent_config(hostname, config_data)

        assert isinstance(result, dict)
        assert result["version"] == 1
        assert result["target_hostname"] == hostname
        assert result["config"] == config_data
        assert "created_at" in result
        assert "checksum" in result
        assert len(result["checksum"]) == 16

    def test_create_agent_config_version_increment(self):
        """Test that version numbers increment correctly."""
        manager = ConfigPushManager()
        hostname = "test-host"
        config_data = {"test": "value"}

        # First config
        config1 = manager.create_agent_config(hostname, config_data)
        assert config1["version"] == 1

        # Second config for same hostname
        config2 = manager.create_agent_config(hostname, config_data)
        assert config2["version"] == 2

        # Different hostname starts at 1
        config3 = manager.create_agent_config("different-host", config_data)
        assert config3["version"] == 1

    def test_create_agent_config_different_hostnames(self):
        """Test config creation for different hostnames."""
        manager = ConfigPushManager()
        config_data = {"test": "value"}

        config1 = manager.create_agent_config("host1", config_data)
        config2 = manager.create_agent_config("host2", config_data)

        assert config1["version"] == 1
        assert config2["version"] == 1
        assert config1["target_hostname"] == "host1"
        assert config2["target_hostname"] == "host2"

    def test_create_agent_config_timestamp_format(self):
        """Test that created_at timestamp is ISO format."""
        manager = ConfigPushManager()
        config = manager.create_agent_config("test-host", {"test": "value"})

        # Should be valid ISO timestamp
        timestamp = datetime.fromisoformat(config["created_at"].replace("Z", "+00:00"))
        assert timestamp.tzinfo is not None

    def test_calculate_checksum_consistency(self):
        """Test that checksum calculation is consistent."""
        manager = ConfigPushManager()
        config_data = {"key": "value", "num": 123}

        manager.create_agent_config("host", config_data)
        manager.create_agent_config("host", config_data)

        # Same data should produce same checksum
        checksum1 = manager._calculate_checksum(config_data)
        checksum2 = manager._calculate_checksum(config_data)
        assert checksum1 == checksum2

        # Different data should produce different checksums
        different_data = {"key": "different", "num": 456}
        checksum3 = manager._calculate_checksum(different_data)
        assert checksum1 != checksum3

    def test_calculate_checksum_order_independence(self):
        """Test that checksum is independent of key order."""
        manager = ConfigPushManager()
        config1 = {"a": 1, "b": 2, "c": 3}
        config2 = {"c": 3, "a": 1, "b": 2}

        checksum1 = manager._calculate_checksum(config1)
        checksum2 = manager._calculate_checksum(config2)
        assert checksum1 == checksum2

    # ------------------------------------------------------------------
    # Helpers for the queue-based push tests below.
    #
    # The push methods now resolve target hosts via a SQLAlchemy session
    # passed in by the caller, and enqueue OUTBOUND rows via
    # ``_queue_ops.enqueue_message`` instead of calling
    # ``connection_manager`` directly.  Tests mock the session and the
    # queue-ops singleton; assertions exercise the enqueue contract,
    # not any websocket-side behavior.
    # ------------------------------------------------------------------

    @staticmethod
    def _mock_session_for_single_host(host_id: str, fqdn: str):
        """Return a mock session whose ``.query(...).filter(...).first()``
        chain yields a Host-like object with the given id/fqdn."""
        session = Mock()
        host = Mock()
        host.id = host_id
        host.fqdn = fqdn
        session.query.return_value.filter.return_value.first.return_value = host
        return session

    @staticmethod
    def _mock_session_with_no_host():
        """Return a mock session whose host lookup yields ``None``."""
        session = Mock()
        session.query.return_value.filter.return_value.first.return_value = None
        return session

    @staticmethod
    def _mock_session_for_host_list(rows):
        """Return a mock session whose ``.query(...).filter(...).all()``
        chain yields the given ``[(host_id, fqdn), ...]`` rows."""
        session = Mock()
        session.query.return_value.filter.return_value.all.return_value = rows
        return session

    def test_push_config_to_agent_success(self):
        """Successful push enqueues one OUTBOUND row and commits."""
        manager = ConfigPushManager()
        hostname = "test-host"
        config_data = {"test": "value"}
        session = self._mock_session_for_single_host("host-uuid-1", hostname)

        with patch("backend.config.config_push._queue_ops") as mock_queue_ops:
            result = manager.push_config_to_agent(session, hostname, config_data)

        assert result is True
        assert hostname in manager.pending_configs
        assert manager.pending_configs[hostname]["version"] == 1
        mock_queue_ops.enqueue_message.assert_called_once()
        # Verify the enqueue carried the right host_id and an OUTBOUND
        # direction; the inner envelope is built by ``_build_config_envelope``
        # and exercised by the envelope-shape test below.
        kwargs = mock_queue_ops.enqueue_message.call_args.kwargs
        assert kwargs["host_id"] == "host-uuid-1"
        assert kwargs["message_type"] == "config_update"
        assert kwargs["db"] is session
        session.commit.assert_called_once()

    def test_push_config_to_agent_host_not_found(self):
        """When the hostname has no active Host row, push returns False
        without enqueuing or committing."""
        manager = ConfigPushManager()
        session = self._mock_session_with_no_host()

        with patch("backend.config.config_push._queue_ops") as mock_queue_ops:
            result = manager.push_config_to_agent(session, "ghost-host", {"k": "v"})

        assert result is False
        assert "ghost-host" not in manager.pending_configs
        mock_queue_ops.enqueue_message.assert_not_called()
        session.commit.assert_not_called()

    def test_push_config_to_agent_envelope_build_failure(self):
        """If envelope construction raises (e.g. encryption error), push
        returns False and the host's pending-config slot stays empty."""
        manager = ConfigPushManager()
        hostname = "test-host"
        session = self._mock_session_for_single_host("host-uuid-1", hostname)

        with patch(
            "backend.config.config_push.message_encryption"
        ) as mock_encryption, patch(
            "backend.config.config_push._queue_ops"
        ) as mock_queue_ops:
            mock_encryption.encrypt_sensitive_data.side_effect = ValueError(
                "Encryption error"
            )
            result = manager.push_config_to_agent(session, hostname, {"k": "v"})

        assert result is False
        assert hostname not in manager.pending_configs
        mock_queue_ops.enqueue_message.assert_not_called()

    def test_push_config_to_all_agents(self):
        """Fan-out push enqueues one row per active host and commits once."""
        manager = ConfigPushManager()
        config_data = {"test": "value"}
        session = self._mock_session_for_host_list(
            [
                ("host-uuid-1", "host1.example"),
                ("host-uuid-2", "host2.example"),
            ]
        )

        with patch("backend.config.config_push._queue_ops") as mock_queue_ops:
            results = manager.push_config_to_all_agents(session, config_data)

        assert results == {"host1.example": True, "host2.example": True}
        assert mock_queue_ops.enqueue_message.call_count == 2
        # Both hosts received an enqueue with the right host_id
        host_ids_enqueued = {
            call.kwargs["host_id"]
            for call in mock_queue_ops.enqueue_message.call_args_list
        }
        assert host_ids_enqueued == {"host-uuid-1", "host-uuid-2"}
        session.commit.assert_called_once()

    def test_push_config_to_all_agents_empty(self):
        """No active hosts → empty result dict, no commit."""
        manager = ConfigPushManager()
        session = self._mock_session_for_host_list([])

        with patch("backend.config.config_push._queue_ops") as mock_queue_ops:
            results = manager.push_config_to_all_agents(session, {"k": "v"})

        assert results == {}
        mock_queue_ops.enqueue_message.assert_not_called()
        session.commit.assert_not_called()

    def test_push_config_by_platform(self):
        """Platform fan-out enqueues one row per matching host and
        returns the count of successful enqueues."""
        manager = ConfigPushManager()
        session = self._mock_session_for_host_list(
            [
                ("host-uuid-a", "linux-a.example"),
                ("host-uuid-b", "linux-b.example"),
                ("host-uuid-c", "linux-c.example"),
            ]
        )

        with patch("backend.config.config_push._queue_ops") as mock_queue_ops:
            count = manager.push_config_by_platform(session, "Linux", {"k": "v"})

        assert count == 3
        assert mock_queue_ops.enqueue_message.call_count == 3
        session.commit.assert_called_once()

    def test_push_config_by_platform_no_matches(self):
        """No hosts on the named platform → returns 0, no commit."""
        manager = ConfigPushManager()
        session = self._mock_session_for_host_list([])

        with patch("backend.config.config_push._queue_ops") as mock_queue_ops:
            count = manager.push_config_by_platform(session, "OpenBSD", {"k": "v"})

        assert count == 0
        mock_queue_ops.enqueue_message.assert_not_called()
        session.commit.assert_not_called()

    def test_handle_config_acknowledgment_success(self):
        """Test handling successful configuration acknowledgment."""
        manager = ConfigPushManager()
        hostname = "test-host"

        # Set up pending config
        manager.pending_configs[hostname] = {"version": 1, "config": {"test": "value"}}

        manager.handle_config_acknowledgment(hostname, 1, True)

        # Should remove from pending configs
        assert hostname not in manager.pending_configs

    def test_handle_config_acknowledgment_failure(self):
        """Test handling failed configuration acknowledgment."""
        manager = ConfigPushManager()
        hostname = "test-host"

        # Set up pending config
        manager.pending_configs[hostname] = {"version": 1, "config": {"test": "value"}}

        manager.handle_config_acknowledgment(hostname, 1, False, "Test error")

        # Should keep in pending configs for retry
        assert hostname in manager.pending_configs

    def test_handle_config_acknowledgment_version_mismatch(self):
        """Test handling acknowledgment with version mismatch."""
        manager = ConfigPushManager()
        hostname = "test-host"

        # Set up pending config
        manager.pending_configs[hostname] = {"version": 2, "config": {"test": "value"}}

        manager.handle_config_acknowledgment(hostname, 1, True)

        # Should keep in pending configs due to version mismatch
        assert hostname in manager.pending_configs

    def test_handle_config_acknowledgment_unknown_host(self):
        """Test handling acknowledgment for unknown host."""
        manager = ConfigPushManager()

        # No pending configs
        manager.handle_config_acknowledgment("unknown-host", 1, True)

        # Should not raise exception, just log warning
        assert len(manager.pending_configs) == 0

    def test_get_pending_configs(self):
        """Test getting pending configurations."""
        manager = ConfigPushManager()

        # Add some pending configs
        manager.pending_configs["host1"] = {"version": 1}
        manager.pending_configs["host2"] = {"version": 2}

        result = manager.get_pending_configs()

        assert len(result) == 2
        assert result["host1"]["version"] == 1
        assert result["host2"]["version"] == 2

        # Should be a copy, not the original
        assert result is not manager.pending_configs

    def test_create_logging_config_basic(self):
        """Test creating basic logging configuration."""
        manager = ConfigPushManager()

        config = manager.create_logging_config()

        assert "logging" in config
        assert config["logging"]["level"] == "INFO"
        assert "format" in config["logging"]
        assert config["requires_restart"] is False
        assert "file" not in config["logging"]

    def test_create_logging_config_with_file(self):
        """Test creating logging configuration with file."""
        manager = ConfigPushManager()
        log_file = "/var/log/sysmanage.log"

        config = manager.create_logging_config("DEBUG", log_file)

        assert config["logging"]["level"] == "DEBUG"
        assert config["logging"]["file"] == log_file
        assert config["requires_restart"] is False

    def test_create_websocket_config_default(self):
        """Test creating default WebSocket configuration."""
        manager = ConfigPushManager()

        config = manager.create_websocket_config()

        assert "websocket" in config
        assert config["websocket"]["ping_interval"] == 30
        assert config["websocket"]["reconnect_interval"] == 5
        assert config["websocket"]["auto_reconnect"] is True
        assert config["requires_restart"] is False

    def test_create_websocket_config_custom(self):
        """Test creating custom WebSocket configuration."""
        manager = ConfigPushManager()

        config = manager.create_websocket_config(60, 10)

        assert config["websocket"]["ping_interval"] == 60
        assert config["websocket"]["reconnect_interval"] == 10
        assert config["websocket"]["auto_reconnect"] is True

    def test_create_server_config_basic(self):
        """Test creating basic server configuration."""
        manager = ConfigPushManager()
        hostname = "server.example.com"

        config = manager.create_server_config(hostname)

        assert "server" in config
        assert config["server"]["hostname"] == hostname
        assert config["server"]["port"] == 8000
        assert config["server"]["use_https"] is False
        assert config["server"]["api_path"] == "/api"
        assert config["requires_restart"] is True

    def test_create_server_config_custom(self):
        """Test creating custom server configuration."""
        manager = ConfigPushManager()
        hostname = "secure.example.com"

        config = manager.create_server_config(hostname, 443, True)

        assert config["server"]["hostname"] == hostname
        assert config["server"]["port"] == 443
        assert config["server"]["use_https"] is True
        assert config["requires_restart"] is True


class TestGlobalInstance:
    """Test the global config_push_manager instance."""

    def test_global_instance_exists(self):
        """Test that global instance is available."""
        assert config_push_manager is not None
        assert isinstance(config_push_manager, ConfigPushManager)

    def test_global_instance_initialized(self):
        """Test that global instance is properly initialized."""
        assert isinstance(config_push_manager.pending_configs, dict)
        assert isinstance(config_push_manager.config_versions, dict)


class TestConfigPushIntegration:
    """Integration tests for configuration push functionality."""

    def test_full_config_creation_flow(self):
        """Test complete configuration creation and management flow."""
        manager = ConfigPushManager()

        # Create multiple configs for same host
        hostname = "integration-test"
        config1 = {"setting1": "value1"}
        config2 = {"setting2": "value2"}

        # Create configs
        result1 = manager.create_agent_config(hostname, config1)
        result2 = manager.create_agent_config(hostname, config2)

        # Verify version increment
        assert result1["version"] == 1
        assert result2["version"] == 2

        # Verify checksums are different
        assert result1["checksum"] != result2["checksum"]

        # Verify proper structure
        for result in [result1, result2]:
            assert "version" in result
            assert "created_at" in result
            assert "target_hostname" in result
            assert "config" in result
            assert "checksum" in result

    def test_logging_config_structure(self):
        """Test logging configuration structure is valid."""
        manager = ConfigPushManager()

        config = manager.create_logging_config("WARNING", "/tmp/test.log")

        # Should be valid JSON serializable
        json_str = json.dumps(config)
        parsed = json.loads(json_str)

        assert parsed == config
        assert parsed["logging"]["level"] == "WARNING"
        assert parsed["logging"]["file"] == "/tmp/test.log"

    def test_websocket_config_structure(self):
        """Test WebSocket configuration structure is valid."""
        manager = ConfigPushManager()

        config = manager.create_websocket_config(45, 15)

        # Should be valid JSON serializable
        json_str = json.dumps(config)
        parsed = json.loads(json_str)

        assert parsed == config
        assert parsed["websocket"]["ping_interval"] == 45
        assert parsed["websocket"]["reconnect_interval"] == 15

    def test_server_config_structure(self):
        """Test server configuration structure is valid."""
        manager = ConfigPushManager()

        config = manager.create_server_config("test.local", 9000, True)

        # Should be valid JSON serializable
        json_str = json.dumps(config)
        parsed = json.loads(json_str)

        assert parsed == config
        assert parsed["server"]["hostname"] == "test.local"
        assert parsed["server"]["port"] == 9000
        assert parsed["server"]["use_https"] is True
