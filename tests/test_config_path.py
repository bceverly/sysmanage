"""
Simple test for config path determination to achieve full coverage.
"""

from unittest.mock import patch, mock_open

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
        # Import the module after patching
        import importlib
        import backend.config.config

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
        # Import the module after patching
        import importlib
        import backend.config.config

        importlib.reload(backend.config.config)

        # Check that the Unix path is set
        assert backend.config.config.CONFIG_PATH == "/etc/sysmanage.yaml"
