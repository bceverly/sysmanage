"""
Tests for backend/startup/logging_config.py module.
Tests logging configuration functionality.
"""

import os
from unittest.mock import patch

import pytest


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_module_has_configure_logging_function(self):
        """Test module exports configure_logging function."""
        from backend.startup import logging_config

        assert hasattr(logging_config, "configure_logging")
        assert callable(logging_config.configure_logging)

    def test_module_has_logger(self):
        """Test module has a logger instance."""
        from backend.startup import logging_config

        assert hasattr(logging_config, "logger")

    def test_configure_logging_with_env_var(self, tmp_path):
        """Test configure_logging respects SYSMANAGE_LOG_DIR environment variable."""
        from backend.startup.logging_config import configure_logging

        log_dir = str(tmp_path / "logs")

        with patch.dict(os.environ, {"SYSMANAGE_LOG_DIR": log_dir}):
            configure_logging()

        # Verify directory was created
        assert os.path.exists(log_dir)

    def test_configure_logging_creates_local_logs_dir(self, tmp_path, monkeypatch):
        """Test configure_logging creates local logs directory when env not set."""
        from backend.startup import logging_config

        # Change to tmp directory for this test
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SYSMANAGE_LOG_DIR", raising=False)

        logging_config.configure_logging()

        # Should create logs directory in current working directory
        assert os.path.exists(os.path.join(tmp_path, "logs"))


class TestLoggingConfigImports:
    """Tests for module imports."""

    def test_imports_utc_timestamp_formatter(self):
        """Test UTCTimestampFormatter is imported from correct location."""
        from backend.startup.logging_config import UTCTimestampFormatter

        assert UTCTimestampFormatter is not None

    def test_imports_get_logger(self):
        """Test get_logger is imported from correct location."""
        from backend.startup.logging_config import get_logger

        assert get_logger is not None
        assert callable(get_logger)
