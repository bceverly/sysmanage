"""
Comprehensive tests for backend/config/config_push.py module.
Tests configuration push functionality for SysManage server.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

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

        config1 = manager.create_agent_config("host", config_data)
        config2 = manager.create_agent_config("host", config_data)

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

    @pytest.mark.asyncio
    async def test_push_config_to_agent_success(self):
        """Test successful configuration push to agent."""
        manager = ConfigPushManager()
        hostname = "test-host"
        config_data = {"test": "value"}

        with patch(
            "backend.config.config_push.message_encryption"
        ) as mock_encryption, patch(
            "backend.config.config_push.connection_manager"
        ) as mock_conn_mgr, patch(
            "backend.config.config_push.Message"
        ) as mock_message:

            mock_encryption.encrypt_sensitive_data.return_value = "encrypted_data"
            mock_conn_mgr.send_to_hostname = AsyncMock(return_value=True)
            mock_message_instance = Mock()
            mock_message_instance.to_dict.return_value = {"message": "data"}
            mock_message.return_value = mock_message_instance

            result = await manager.push_config_to_agent(hostname, config_data)

            assert result is True
            assert hostname in manager.pending_configs
            assert manager.pending_configs[hostname]["version"] == 1
            mock_encryption.encrypt_sensitive_data.assert_called_once()
            mock_conn_mgr.send_to_hostname.assert_called_once_with(
                hostname, {"message": "data"}
            )

    @pytest.mark.asyncio
    async def test_push_config_to_agent_failure(self):
        """Test configuration push failure."""
        manager = ConfigPushManager()
        hostname = "test-host"
        config_data = {"test": "value"}

        with patch(
            "backend.config.config_push.message_encryption"
        ) as mock_encryption, patch(
            "backend.config.config_push.connection_manager"
        ) as mock_conn_mgr, patch(
            "backend.config.config_push.Message"
        ) as mock_message:

            mock_encryption.encrypt_sensitive_data.return_value = "encrypted_data"
            mock_conn_mgr.send_to_hostname = AsyncMock(return_value=False)
            mock_message_instance = Mock()
            mock_message_instance.to_dict.return_value = {"message": "data"}
            mock_message.return_value = mock_message_instance

            result = await manager.push_config_to_agent(hostname, config_data)

            assert result is False
            assert hostname not in manager.pending_configs

    @pytest.mark.asyncio
    async def test_push_config_to_agent_exception(self):
        """Test configuration push with exception."""
        manager = ConfigPushManager()
        hostname = "test-host"
        config_data = {"test": "value"}

        with patch("backend.config.config_push.message_encryption") as mock_encryption:
            mock_encryption.encrypt_sensitive_data.side_effect = ValueError(
                "Encryption error"
            )

            result = await manager.push_config_to_agent(hostname, config_data)

            assert result is False
            assert hostname not in manager.pending_configs

    @pytest.mark.asyncio
    async def test_push_config_to_all_agents(self):
        """Test pushing configuration to all agents."""
        manager = ConfigPushManager()
        config_data = {"test": "value"}

        agent_list = [
            {"hostname": "host1"},
            {"hostname": "host2"},
            {"hostname": None},  # Should be skipped
        ]

        with patch("backend.config.config_push.connection_manager") as mock_conn_mgr:
            mock_conn_mgr.get_active_agents.return_value = agent_list

            # Mock push_config_to_agent method
            with patch.object(
                manager, "push_config_to_agent", new_callable=AsyncMock
            ) as mock_push:
                mock_push.side_effect = [True, False]  # host1 success, host2 fail

                results = await manager.push_config_to_all_agents(config_data)

                assert len(results) == 2
                assert results["host1"] is True
                assert results["host2"] is False
                assert mock_push.call_count == 2

    @pytest.mark.asyncio
    async def test_push_config_by_platform(self):
        """Test pushing configuration by platform."""
        manager = ConfigPushManager()
        platform = "Linux"
        config_data = {"test": "value"}

        with patch(
            "backend.config.config_push.message_encryption"
        ) as mock_encryption, patch(
            "backend.config.config_push.connection_manager"
        ) as mock_conn_mgr, patch(
            "backend.config.config_push.Message"
        ) as mock_message:

            mock_encryption.encrypt_sensitive_data.return_value = "encrypted_data"
            mock_conn_mgr.broadcast_to_platform = AsyncMock(return_value=3)
            mock_message_instance = Mock()
            mock_message_instance.to_dict.return_value = {"message": "data"}
            mock_message.return_value = mock_message_instance

            result = await manager.push_config_by_platform(platform, config_data)

            assert result == 3
            mock_conn_mgr.broadcast_to_platform.assert_called_once_with(
                platform, {"message": "data"}
            )

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
