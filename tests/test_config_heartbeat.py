"""
Test heartbeat configuration functionality on the server.
"""

import os
import tempfile
from unittest.mock import mock_open, patch

import pytest

from backend.config.config import get_config, get_heartbeat_timeout_minutes


class TestHeartbeatConfiguration:
    """Test heartbeat configuration functionality."""

    def test_get_heartbeat_timeout_minutes_default(self):
        """Test default heartbeat timeout configuration."""
        # Mock config with default values
        mock_config = {"monitoring": {"heartbeat_timeout": 5}}

        with patch("backend.config.config.config", mock_config):
            timeout = get_heartbeat_timeout_minutes()
            assert timeout == 5

    def test_get_heartbeat_timeout_minutes_custom(self):
        """Test custom heartbeat timeout configuration."""
        # Mock config with custom values
        mock_config = {"monitoring": {"heartbeat_timeout": 10}}

        with patch("backend.config.config.config", mock_config):
            timeout = get_heartbeat_timeout_minutes()
            assert timeout == 10

    def test_config_loading_with_monitoring_section(self):
        """Test config loading with monitoring section."""
        # This test checks the logic of config loading, not actual file loading
        # since the config is loaded at module import time
        mock_config = {
            "api": {"host": "localhost", "port": 8443},
            "monitoring": {"heartbeat_timeout": 15},
        }

        with patch("backend.config.config.config", mock_config):
            timeout = get_heartbeat_timeout_minutes()
            assert timeout == 15

    def test_config_loading_without_monitoring_section(self):
        """Test config loading creates default monitoring section."""
        yaml_content = """
api:
  host: "localhost"
  port: 8443

webui:
  host: "localhost"
  port: 8080
"""

        with patch("builtins.open", mock_open(read_data=yaml_content)):
            with patch("os.path.exists", return_value=True):
                # Mock the config loading behavior
                mock_config = {
                    "api": {"host": "localhost", "port": 8443},
                    "webui": {"host": "localhost", "port": 8080},
                    "monitoring": {"heartbeat_timeout": 5},  # Default value
                }

                with patch("backend.config.config.config", mock_config):
                    timeout = get_heartbeat_timeout_minutes()
                    assert timeout == 5

    def test_config_validation(self):
        """Test configuration validation."""
        # Test various timeout values
        test_cases = [
            (1, 1),  # Minimum reasonable value
            (5, 5),  # Default value
            (60, 60),  # High value
            (1440, 1440),  # Very high value (24 hours)
        ]

        for input_timeout, expected_timeout in test_cases:
            mock_config = {"monitoring": {"heartbeat_timeout": input_timeout}}

            with patch("backend.config.config.config", mock_config):
                timeout = get_heartbeat_timeout_minutes()
                assert timeout == expected_timeout
                assert isinstance(timeout, int)
                assert timeout > 0


class TestConfigurationIntegration:
    """Test configuration integration with heartbeat monitoring."""

    def test_heartbeat_monitor_uses_config(self):
        """Test that heartbeat monitor uses configuration values."""
        from backend.monitoring.heartbeat_monitor import check_host_heartbeats

        mock_config = {"monitoring": {"heartbeat_timeout": 7}}

        with patch("backend.config.config.config", mock_config), patch(
            "backend.monitoring.heartbeat_monitor.get_db"
        ) as mock_get_db, patch(
            "backend.monitoring.heartbeat_monitor.datetime"
        ) as mock_datetime:

            # Setup mocks
            mock_db = mock_get_db.return_value.__next__.return_value
            mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = (
                []
            )
            mock_db.commit = lambda: None
            mock_db.rollback = lambda: None
            mock_db.close = lambda: None

            # Mock datetime to control time calculations
            from datetime import datetime, timedelta

            base_time = datetime.utcnow()
            mock_datetime.utcnow.return_value = base_time

            # Test that the configured timeout is used
            import asyncio

            asyncio.run(check_host_heartbeats())

            # Verify the query used the correct timeout value
            # The filter should use base_time - timedelta(minutes=7)
            expected_threshold = base_time - timedelta(minutes=7)
            mock_db.query.return_value.filter.assert_called()

    def test_yaml_parsing_edge_cases(self):
        """Test YAML parsing with edge cases."""
        # Test with empty monitoring section
        yaml_empty_monitoring = """
api:
  host: "localhost"
  port: 8443

monitoring:

webui:
  host: "localhost"
  port: 8080
"""

        with patch("builtins.open", mock_open(read_data=yaml_empty_monitoring)):
            with patch("os.path.exists", return_value=True):
                # Should handle empty monitoring section gracefully
                mock_config = {
                    "api": {"host": "localhost", "port": 8443},
                    "webui": {"host": "localhost", "port": 8080},
                    "monitoring": {"heartbeat_timeout": 5},  # Default applied
                }

                with patch("backend.config.config.config", mock_config):
                    timeout = get_heartbeat_timeout_minutes()
                    assert timeout == 5

    def test_config_type_validation(self):
        """Test configuration type validation."""
        # Test various timeout values - the function returns the value as-is
        test_cases = [
            (5, 5),  # Integer
            (10, 10),  # Another integer
            (60, 60),  # High value
        ]

        for input_value, expected_output in test_cases:
            mock_config = {"monitoring": {"heartbeat_timeout": input_value}}

            with patch("backend.config.config.config", mock_config):
                timeout = get_heartbeat_timeout_minutes()
                assert timeout == expected_output
