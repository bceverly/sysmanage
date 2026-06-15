"""
Simple test for config path determination to achieve full coverage.
"""

import importlib
from unittest.mock import mock_open, patch

import pytest

import backend.config.config


@pytest.fixture(autouse=True)
def _restore_config_singleton():
    """Restore the global config singleton after each test.

    These tests ``importlib.reload(backend.config.config)`` with a mocked
    config and never reload back, polluting the singleton for later tests in
    the same pytest-xdist worker. Save/restore contains that leak.
    """
    saved = backend.config.config.config
    try:
        yield
    finally:
        backend.config.config.config = saved


# Sample config data to mock file reading
MOCK_CONFIG_DATA = """
api:
  host: localhost
  port: 8443
webui:
  host: localhost
  port: 8080
monitoring:
  heartbeat_timeout: 5
security:
  max_failed_logins: 5
  account_lockout_duration: 15
logging:
  level: INFO|WARNING|ERROR|CRITICAL
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
message_queue:
  expiration_timeout_minutes: 60
  cleanup_interval_minutes: 30
email:
  enabled: false
"""


def test_windows_config_path():
    """Test that Windows config path is used on Windows (line 15)."""
    with patch("backend.config.config.os.name", "nt"), patch(
        "backend.config.config.os.path.exists", return_value=True
    ), patch("builtins.open", mock_open(read_data=MOCK_CONFIG_DATA)):
        # Reload to re-run the module's path determination under the patches
        # (backend.config.config is already imported at module top; importlib
        # is imported once at module scope to avoid duplicate-import findings).
        importlib.reload(backend.config.config)

        # Check that the Windows path is set
        assert (
            backend.config.config.CONFIG_PATH
            == r"C:\ProgramData\SysManage\sysmanage.yaml"
        )


def test_unix_config_path():
    """Test that Unix config path is used on non-Windows systems."""
    with patch("backend.config.config.os.name", "posix"), patch(
        "backend.config.config.os.path.exists", return_value=True
    ), patch("builtins.open", mock_open(read_data=MOCK_CONFIG_DATA)):
        # Reload to re-run the module's path determination under the patches
        # (backend.config.config is already imported at module top; importlib
        # is imported once at module scope to avoid duplicate-import findings).
        importlib.reload(backend.config.config)

        # Check that the Unix path is set
        assert backend.config.config.CONFIG_PATH == "/etc/sysmanage.yaml"
