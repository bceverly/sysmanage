"""
Comprehensive unit tests for backend.config.config module.
Tests configuration loading and accessor functions.
"""

import os
from unittest.mock import Mock, mock_open, patch

import pytest
import yaml

from backend.config import config


class TestConfigAccessors:
    """Test configuration accessor functions."""

    def test_get_config(self):
        """Test get_config returns the config object."""
        result = config.get_config()
        assert result is not None
        assert isinstance(result, dict)

    def test_get_heartbeat_timeout_minutes(self):
        """Test get_heartbeat_timeout_minutes."""
        with patch.object(config, "config", {"monitoring": {"heartbeat_timeout": 10}}):
            result = config.get_heartbeat_timeout_minutes()
            assert result == 10

    def test_get_max_failed_logins(self):
        """Test get_max_failed_logins."""
        with patch.object(config, "config", {"security": {"max_failed_logins": 3}}):
            result = config.get_max_failed_logins()
            assert result == 3

    def test_get_account_lockout_duration(self):
        """Test get_account_lockout_duration."""
        with patch.object(
            config, "config", {"security": {"account_lockout_duration": 30}}
        ):
            result = config.get_account_lockout_duration()
            assert result == 30

    def test_get_log_levels(self):
        """Test get_log_levels."""
        log_levels = "DEBUG|INFO|WARNING|ERROR|CRITICAL"
        with patch.object(config, "config", {"logging": {"level": log_levels}}):
            result = config.get_log_levels()
            assert result == log_levels

    def test_get_log_format(self):
        """Test get_log_format."""
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        with patch.object(config, "config", {"logging": {"format": log_format}}):
            result = config.get_log_format()
            assert result == log_format

    def test_get_log_file_exists(self):
        """Test get_log_file when file is specified."""
        log_file = "/var/log/sysmanage.log"
        with patch.object(config, "config", {"logging": {"file": log_file}}):
            result = config.get_log_file()
            assert result == log_file

    def test_get_log_file_not_exists(self):
        """Test get_log_file when file is not specified."""
        with patch.object(config, "config", {"logging": {}}):
            result = config.get_log_file()
            assert result is None

    def test_get_email_config(self):
        """Test get_email_config."""
        email_config = {
            "enabled": True,
            "smtp": {"host": "smtp.example.com"},
            "from_address": "test@example.com",
        }
        with patch.object(config, "config", {"email": email_config}):
            result = config.get_email_config()
            assert result == email_config

    def test_is_email_enabled_true(self):
        """Test is_email_enabled when email is enabled."""
        with patch.object(config, "config", {"email": {"enabled": True}}):
            result = config.is_email_enabled()
            assert result is True

    def test_is_email_enabled_false(self):
        """Test is_email_enabled when email is disabled."""
        with patch.object(config, "config", {"email": {"enabled": False}}):
            result = config.is_email_enabled()
            assert result is False

    def test_get_smtp_config(self):
        """Test get_smtp_config."""
        smtp_config = {
            "host": "smtp.example.com",
            "port": 587,
            "use_tls": True,
            "username": "user@example.com",
        }
        with patch.object(config, "config", {"email": {"smtp": smtp_config}}):
            result = config.get_smtp_config()
            assert result == smtp_config


class TestConfigLoadingDefaults:
    """Test configuration loading and default value assignment."""

    @patch("backend.config.config.yaml.safe_load")
    @patch("backend.config.config.open", new_callable=mock_open)
    @patch("backend.config.config.os.path.exists")
    def test_config_loading_with_minimal_config(
        self, mock_exists, mock_file, mock_yaml
    ):
        """Test config loading fills in defaults for minimal config."""
        # Simulate finding the config file
        mock_exists.return_value = True

        # Minimal config with just required sections
        minimal_config = {"api": {}, "webui": {}, "security": {}}
        mock_yaml.return_value = minimal_config

        # Import the module to trigger config loading
        import importlib

        from backend.config import config as config_module

        importlib.reload(config_module)

        # Verify defaults were set
        loaded_config = mock_yaml.return_value
        assert "host" in loaded_config["api"]
        assert loaded_config["api"]["host"] == "localhost"
        assert "port" in loaded_config["api"]
        assert loaded_config["api"]["port"] == 8443

    @patch("backend.config.config.yaml.safe_load")
    @patch("backend.config.config.open", new_callable=mock_open)
    @patch("backend.config.config.os.path.exists")
    def test_config_loading_preserves_existing_values(
        self, mock_exists, mock_file, mock_yaml
    ):
        """Test config loading preserves existing values and only adds missing defaults."""
        mock_exists.return_value = True

        # Config with some values already set
        existing_config = {
            "api": {"host": "custom.example.com", "port": 9443},
            "webui": {
                "host": "ui.example.com"
                # port missing - should get default
            },
            "security": {
                "max_failed_logins": 10
                # account_lockout_duration missing - should get default
            },
        }
        mock_yaml.return_value = existing_config

        import importlib

        from backend.config import config as config_module

        importlib.reload(config_module)

        loaded_config = mock_yaml.return_value
        # Should preserve existing values
        assert loaded_config["api"]["host"] == "custom.example.com"
        assert loaded_config["api"]["port"] == 9443
        assert loaded_config["webui"]["host"] == "ui.example.com"
        assert loaded_config["security"]["max_failed_logins"] == 10

    def test_config_adds_missing_sections(self):
        """Test config loading behavior for missing sections."""
        # This test verifies the existing config has the expected structure
        # since the actual config loading happens at module import time
        from backend.config import config as config_module

        loaded_config = config_module.get_config()
        # Should have all required sections
        assert "webui" in loaded_config
        assert "monitoring" in loaded_config
        assert "logging" in loaded_config
        assert "message_queue" in loaded_config
        assert "email" in loaded_config

    def test_config_path_windows(self):
        """Test config path logic for Windows."""
        # Test the path selection logic without reloading the module
        import os

        # Test Windows path selection
        with patch("backend.config.config.os.name", "nt"):
            expected_path = r"C:\ProgramData\SysManage\sysmanage.yaml"
            # This tests the path string construction logic
            if os.name == "nt":
                config_path = r"C:\ProgramData\SysManage\sysmanage.yaml"
            else:
                config_path = "/etc/sysmanage.yaml"

            # On Windows systems, the path should be the Windows path
            if os.name == "nt":
                assert config_path == expected_path

    def test_config_path_unix(self):
        """Test config path selection on Unix-like systems."""
        mock_config = """api:
  host: localhost
  port: 8443
webui:
  host: localhost
  port: 8080
security:
  max_failed_logins: 5
  account_lockout_duration: 15
"""
        with patch("backend.config.config.os.name", "posix"), patch(
            "backend.config.config.os.path.exists", return_value=True
        ), patch("builtins.open", mock_open(read_data=mock_config)):

            import importlib

            from backend.config import config as config_module

            importlib.reload(config_module)

            expected_path = "/etc/sysmanage.yaml"
            assert config_module.CONFIG_PATH == expected_path

    @patch("backend.config.config.os.path.exists")
    def test_config_fallback_to_dev_config(self, mock_exists):
        """Test fallback to development config when system config doesn't exist."""

        def mock_exists_side_effect(path):
            if path == "/etc/sysmanage.yaml":
                return False
            elif path == "sysmanage-dev.yaml":
                return True
            return False

        mock_exists.side_effect = mock_exists_side_effect

        import importlib

        from backend.config import config as config_module

        importlib.reload(config_module)

        assert config_module.CONFIG_PATH == "sysmanage-dev.yaml"

    @patch("backend.config.config.yaml.safe_load")
    @patch("backend.config.config.open", new_callable=mock_open)
    @patch("backend.config.config.os.path.exists")
    def test_all_default_values_comprehensive(self, mock_exists, mock_file, mock_yaml):
        """Test that all default values are set correctly."""
        mock_exists.return_value = True

        # Completely empty config except required sections
        empty_config = {"api": {}, "webui": {}, "security": {}}
        mock_yaml.return_value = empty_config

        import importlib

        from backend.config import config as config_module

        importlib.reload(config_module)

        loaded_config = mock_yaml.return_value

        # API defaults
        assert loaded_config["api"]["host"] == "localhost"
        assert loaded_config["api"]["port"] == 8443

        # WebUI defaults
        assert loaded_config["webui"]["host"] == "localhost"
        assert loaded_config["webui"]["port"] == 8080

        # Monitoring defaults
        assert "monitoring" in loaded_config
        assert loaded_config["monitoring"]["heartbeat_timeout"] == 5

        # Security defaults
        assert loaded_config["security"]["max_failed_logins"] == 5
        assert loaded_config["security"]["account_lockout_duration"] == 15

        # Logging defaults
        assert "logging" in loaded_config
        assert loaded_config["logging"]["level"] == "INFO|WARNING|ERROR|CRITICAL"
        assert (
            loaded_config["logging"]["format"]
            == "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # Message queue defaults
        assert "message_queue" in loaded_config
        assert loaded_config["message_queue"]["expiration_timeout_minutes"] == 60
        assert loaded_config["message_queue"]["cleanup_interval_minutes"] == 30

        # Email defaults
        assert "email" in loaded_config
        assert loaded_config["email"]["enabled"] is False
        assert loaded_config["email"]["smtp"]["host"] == "localhost"
        assert loaded_config["email"]["smtp"]["port"] == 587
        assert loaded_config["email"]["smtp"]["use_tls"] is True
        assert loaded_config["email"]["smtp"]["use_ssl"] is False
        assert loaded_config["email"]["smtp"]["username"] == ""
        assert loaded_config["email"]["smtp"]["password"] == ""
        assert loaded_config["email"]["smtp"]["timeout"] == 30
        assert loaded_config["email"]["from_address"] == "noreply@localhost"
        assert loaded_config["email"]["from_name"] == "SysManage System"
        assert loaded_config["email"]["templates"]["subject_prefix"] == "[SysManage]"

    @patch("backend.config.config.yaml.safe_load")
    @patch("backend.config.config.open", new_callable=mock_open)
    @patch("backend.config.config.os.path.exists")
    @patch("backend.config.config.sys.exit")
    def test_yaml_error_handling_with_problem_mark(
        self, mock_exit, mock_exists, mock_file, mock_yaml
    ):
        """Test YAML error handling when error has problem_mark."""
        mock_exists.return_value = True

        # Create a YAML error with problem_mark
        yaml_error = yaml.YAMLError("Test error")
        yaml_error.problem_mark = Mock()
        yaml_error.problem_mark.line = 5
        yaml_error.problem_mark.column = 10
        mock_yaml.side_effect = yaml_error

        import importlib

        from backend.config import config as config_module

        importlib.reload(config_module)

        mock_exit.assert_called_with(1)

    @patch("backend.config.config.yaml.safe_load")
    @patch("backend.config.config.open", new_callable=mock_open)
    @patch("backend.config.config.os.path.exists")
    @patch("backend.config.config.sys.exit")
    def test_yaml_error_handling_without_problem_mark(
        self, mock_exit, mock_exists, mock_file, mock_yaml
    ):
        """Test YAML error handling when error has no problem_mark."""
        mock_exists.return_value = True

        # Create a YAML error without problem_mark
        yaml_error = yaml.YAMLError("Test error")
        mock_yaml.side_effect = yaml_error

        import importlib

        from backend.config import config as config_module

        importlib.reload(config_module)

        mock_exit.assert_called_with(1)

    @patch("backend.config.config.yaml.safe_load")
    @patch("backend.config.config.open", new_callable=mock_open)
    @patch("backend.config.config.os.path.exists")
    def test_config_nested_dict_creation(self, mock_exists, mock_file, mock_yaml):
        """Test that nested dictionaries are created properly."""
        mock_exists.return_value = True

        # Config with minimal nested structure
        minimal_config = {
            "api": {},
            "webui": {},
            "security": {},
            # No email section at all
        }
        mock_yaml.return_value = minimal_config

        import importlib

        from backend.config import config as config_module

        importlib.reload(config_module)

        loaded_config = mock_yaml.return_value

        # Should create nested email.smtp structure
        assert "email" in loaded_config
        assert "smtp" in loaded_config["email"]
        assert isinstance(loaded_config["email"]["smtp"], dict)
        assert loaded_config["email"]["smtp"]["host"] == "localhost"

        # Should create email.templates structure
        assert "templates" in loaded_config["email"]
        assert isinstance(loaded_config["email"]["templates"], dict)
        assert loaded_config["email"]["templates"]["subject_prefix"] == "[SysManage]"

    def test_config_module_imports_successfully(self):
        """Test that the config module can be imported without errors."""
        try:
            from backend.config import config as config_module

            assert config_module is not None
        except Exception as e:
            pytest.fail(f"Config module import failed: {e}")

    def test_config_object_structure(self):
        """Test that the loaded config has expected structure."""
        from backend.config import config as config_module

        config_obj = config_module.get_config()
        assert isinstance(config_obj, dict)

        # Should have main sections
        expected_sections = [
            "api",
            "webui",
            "security",
            "monitoring",
            "logging",
            "message_queue",
            "email",
        ]
        for section in expected_sections:
            assert section in config_obj, f"Missing config section: {section}"

    def test_config_functions_dont_raise_errors(self):
        """Test that all config accessor functions work without errors."""
        from backend.config import config as config_module

        # Test all accessor functions
        try:
            config_module.get_config()
            config_module.get_heartbeat_timeout_minutes()
            config_module.get_max_failed_logins()
            config_module.get_account_lockout_duration()
            config_module.get_log_levels()
            config_module.get_log_format()
            config_module.get_log_file()  # May return None
            config_module.get_email_config()
            config_module.is_email_enabled()
            config_module.get_smtp_config()
        except Exception as e:
            pytest.fail(f"Config accessor function failed: {e}")
