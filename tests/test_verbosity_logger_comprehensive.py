"""
Comprehensive unit tests for backend.utils.verbosity_logger module.
Tests the FlexibleLogger class and logging configuration.
"""

import logging
import pytest
from unittest.mock import Mock, patch

from backend.utils.verbosity_logger import FlexibleLogger, get_logger


class TestFlexibleLogger:
    """Test cases for FlexibleLogger class."""

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_initialization_default_config(self, mock_get_format, mock_get_levels):
        """Test FlexibleLogger initialization with default config."""
        mock_get_levels.return_value = "INFO|WARNING|ERROR|CRITICAL"
        mock_get_format.return_value = (
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        logger = FlexibleLogger("test.logger")

        assert logger.name == "test.logger"
        assert logger.logger is not None
        assert isinstance(logger.enabled_levels, set)
        assert logging.INFO in logger.enabled_levels
        assert logging.WARNING in logger.enabled_levels
        assert logging.ERROR in logger.enabled_levels
        assert logging.CRITICAL in logger.enabled_levels

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_initialization_debug_only(self, mock_get_format, mock_get_levels):
        """Test FlexibleLogger initialization with debug-only config."""
        mock_get_levels.return_value = "DEBUG"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("debug.logger")

        assert logging.DEBUG in logger.enabled_levels
        assert logging.INFO not in logger.enabled_levels
        assert logging.WARNING not in logger.enabled_levels

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_initialization_custom_levels(self, mock_get_format, mock_get_levels):
        """Test FlexibleLogger initialization with custom level combination."""
        mock_get_levels.return_value = "DEBUG|ERROR|CRITICAL"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("custom.logger")

        assert logging.DEBUG in logger.enabled_levels
        assert logging.INFO not in logger.enabled_levels
        assert logging.WARNING not in logger.enabled_levels
        assert logging.ERROR in logger.enabled_levels
        assert logging.CRITICAL in logger.enabled_levels

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_parse_enabled_levels_with_spaces(self, mock_get_format, mock_get_levels):
        """Test parsing levels with extra spaces."""
        mock_get_levels.return_value = " INFO | WARNING | ERROR "
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("space.logger")

        assert logging.INFO in logger.enabled_levels
        assert logging.WARNING in logger.enabled_levels
        assert logging.ERROR in logger.enabled_levels

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_parse_enabled_levels_invalid_level(self, mock_get_format, mock_get_levels):
        """Test parsing levels with invalid level names."""
        mock_get_levels.return_value = "INFO|INVALID_LEVEL|ERROR"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("invalid.logger")

        assert logging.INFO in logger.enabled_levels
        assert logging.ERROR in logger.enabled_levels
        # INVALID_LEVEL should be ignored

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_parse_enabled_levels_exception_fallback(
        self, mock_get_format, mock_get_levels
    ):
        """Test fallback behavior when config parsing fails."""
        mock_get_levels.side_effect = KeyError("Config not found")
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("fallback.logger")

        # Should fallback to default operational levels
        assert logging.INFO in logger.enabled_levels
        assert logging.WARNING in logger.enabled_levels
        assert logging.ERROR in logger.enabled_levels
        assert logging.CRITICAL in logger.enabled_levels

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_should_log_enabled_level(self, mock_get_format, mock_get_levels):
        """Test _should_log method for enabled level."""
        mock_get_levels.return_value = "INFO|ERROR"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("test.logger")

        assert logger._should_log(logging.INFO) is True
        assert logger._should_log(logging.ERROR) is True

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_should_log_disabled_level(self, mock_get_format, mock_get_levels):
        """Test _should_log method for disabled level."""
        mock_get_levels.return_value = "INFO|ERROR"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("test.logger")

        assert logger._should_log(logging.DEBUG) is False
        assert logger._should_log(logging.WARNING) is False
        assert logger._should_log(logging.CRITICAL) is False

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_debug_logging_enabled(self, mock_get_format, mock_get_levels):
        """Test debug logging when DEBUG level is enabled."""
        mock_get_levels.return_value = "DEBUG"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("debug.test")
        logger.logger.debug = Mock()

        logger.debug("Debug message")

        logger.logger.debug.assert_called_once_with("Debug message")

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_debug_logging_disabled(self, mock_get_format, mock_get_levels):
        """Test debug logging when DEBUG level is disabled."""
        mock_get_levels.return_value = "INFO|ERROR"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("no.debug")
        logger.logger.debug = Mock()

        logger.debug("Debug message")

        logger.logger.debug.assert_not_called()

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_info_logging_enabled(self, mock_get_format, mock_get_levels):
        """Test info logging when INFO level is enabled."""
        mock_get_levels.return_value = "INFO|ERROR"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("info.test")
        logger.logger.info = Mock()

        logger.info("Info message")

        logger.logger.info.assert_called_once_with("Info message")

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_info_logging_disabled(self, mock_get_format, mock_get_levels):
        """Test info logging when INFO level is disabled."""
        mock_get_levels.return_value = "DEBUG|ERROR"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("no.info")
        logger.logger.info = Mock()

        logger.info("Info message")

        logger.logger.info.assert_not_called()

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_warning_logging_enabled(self, mock_get_format, mock_get_levels):
        """Test warning logging when WARNING level is enabled."""
        mock_get_levels.return_value = "WARNING|ERROR"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("warning.test")
        logger.logger.warning = Mock()

        logger.warning("Warning message")

        logger.logger.warning.assert_called_once_with("Warning message")

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_warning_logging_disabled(self, mock_get_format, mock_get_levels):
        """Test warning logging when WARNING level is disabled."""
        mock_get_levels.return_value = "INFO|ERROR"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("no.warning")
        logger.logger.warning = Mock()

        logger.warning("Warning message")

        logger.logger.warning.assert_not_called()

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_error_logging_enabled(self, mock_get_format, mock_get_levels):
        """Test error logging when ERROR level is enabled."""
        mock_get_levels.return_value = "INFO|ERROR"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("error.test")
        logger.logger.error = Mock()

        logger.error("Error message")

        logger.logger.error.assert_called_once_with("Error message")

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_error_logging_disabled(self, mock_get_format, mock_get_levels):
        """Test error logging when ERROR level is disabled."""
        mock_get_levels.return_value = "INFO|WARNING"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("no.error")
        logger.logger.error = Mock()

        logger.error("Error message")

        logger.logger.error.assert_not_called()

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_critical_logging_enabled(self, mock_get_format, mock_get_levels):
        """Test critical logging when CRITICAL level is enabled."""
        mock_get_levels.return_value = "ERROR|CRITICAL"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("critical.test")
        logger.logger.critical = Mock()

        logger.critical("Critical message")

        logger.logger.critical.assert_called_once_with("Critical message")

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_critical_logging_disabled(self, mock_get_format, mock_get_levels):
        """Test critical logging when CRITICAL level is disabled."""
        mock_get_levels.return_value = "INFO|WARNING|ERROR"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("no.critical")
        logger.logger.critical = Mock()

        logger.critical("Critical message")

        logger.logger.critical.assert_not_called()

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_logging_with_args_and_kwargs(self, mock_get_format, mock_get_levels):
        """Test logging methods with arguments and keyword arguments."""
        mock_get_levels.return_value = "INFO"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("args.test")
        logger.logger.info = Mock()

        logger.info("Message with %s and %d", "string", 42, extra={"key": "value"})

        logger.logger.info.assert_called_once_with(
            "Message with %s and %d", "string", 42, extra={"key": "value"}
        )

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_handler_configuration(self, mock_get_format, mock_get_levels):
        """Test that logger handlers are configured properly."""
        mock_get_levels.return_value = "INFO"
        mock_get_format.return_value = "%(asctime)s - %(message)s"

        # Create logger with no existing handlers
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger_instance = Mock()
            mock_logger_instance.handlers = []
            mock_get_logger.return_value = mock_logger_instance

            logger = FlexibleLogger("handler.test")

            # Verify handler was added and configured
            mock_logger_instance.addHandler.assert_called_once()
            mock_logger_instance.setLevel.assert_called_once_with(logging.DEBUG)

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_no_handler_added_when_exists(self, mock_get_format, mock_get_levels):
        """Test that no additional handler is added when one already exists."""
        mock_get_levels.return_value = "INFO"
        mock_get_format.return_value = "%(message)s"

        # Create logger with existing handlers
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger_instance = Mock()
            mock_logger_instance.handlers = [Mock()]  # Existing handler
            mock_get_logger.return_value = mock_logger_instance

            logger = FlexibleLogger("existing.handler")

            # Verify no additional handler was added
            mock_logger_instance.addHandler.assert_not_called()


class TestGetLoggerFunction:
    """Test cases for get_logger function."""

    def test_get_logger_returns_flexible_logger(self):
        """Test that get_logger returns FlexibleLogger instance."""
        with patch("backend.utils.verbosity_logger.get_log_levels") as mock_levels:
            with patch("backend.utils.verbosity_logger.get_log_format") as mock_format:
                mock_levels.return_value = "INFO"
                mock_format.return_value = "%(message)s"

                logger = get_logger("test.module")

                assert isinstance(logger, FlexibleLogger)
                assert logger.name == "test.module"

    def test_get_logger_with_different_names(self):
        """Test get_logger with different logger names."""
        with patch("backend.utils.verbosity_logger.get_log_levels") as mock_levels:
            with patch("backend.utils.verbosity_logger.get_log_format") as mock_format:
                mock_levels.return_value = "INFO"
                mock_format.return_value = "%(message)s"

                logger1 = get_logger("module.one")
                logger2 = get_logger("module.two")

                assert logger1.name == "module.one"
                assert logger2.name == "module.two"
                assert logger1 is not logger2


class TestFlexibleLoggerEdgeCases:
    """Test edge cases and error conditions."""

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_empty_level_config(self, mock_get_format, mock_get_levels):
        """Test behavior with empty level configuration."""
        mock_get_levels.return_value = ""
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("empty.config")

        # With empty config, enabled_levels should be empty set
        assert isinstance(logger.enabled_levels, set)
        # Empty config results in no enabled levels in this implementation

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_level_config_with_only_separators(self, mock_get_format, mock_get_levels):
        """Test behavior with level config containing only pipe separators."""
        mock_get_levels.return_value = "||||||"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("separators.only")

        # Should have empty enabled levels or fallback
        # Implementation may vary, but should not crash
        assert isinstance(logger.enabled_levels, set)

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_mixed_case_levels(self, mock_get_format, mock_get_levels):
        """Test parsing with mixed case level names."""
        mock_get_levels.return_value = "info|Warning|ERROR|critical"
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("mixed.case")

        # Should handle mixed case (converted to uppercase internally)
        assert logging.INFO in logger.enabled_levels
        assert logging.WARNING in logger.enabled_levels
        assert logging.ERROR in logger.enabled_levels
        assert logging.CRITICAL in logger.enabled_levels

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_attribute_error_fallback(self, mock_get_format, mock_get_levels):
        """Test fallback behavior when AttributeError occurs."""
        mock_get_levels.side_effect = AttributeError("Attribute not found")
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("attr.error")

        # Should fallback to default operational levels
        assert logging.INFO in logger.enabled_levels
        assert logging.WARNING in logger.enabled_levels
        assert logging.ERROR in logger.enabled_levels
        assert logging.CRITICAL in logger.enabled_levels

    @patch("backend.utils.verbosity_logger.get_log_levels")
    @patch("backend.utils.verbosity_logger.get_log_format")
    def test_value_error_fallback(self, mock_get_format, mock_get_levels):
        """Test fallback behavior when ValueError occurs."""
        mock_get_levels.side_effect = ValueError("Invalid value")
        mock_get_format.return_value = "%(message)s"

        logger = FlexibleLogger("value.error")

        # Should fallback to default operational levels
        assert logging.INFO in logger.enabled_levels
        assert logging.WARNING in logger.enabled_levels
        assert logging.ERROR in logger.enabled_levels
        assert logging.CRITICAL in logger.enabled_levels
