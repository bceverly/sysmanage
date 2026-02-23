"""
Flexible logging utility for SysManage.

Provides granular logging control with pipe-separated level configuration.
Supports custom formats and selective level filtering.
"""

import logging
import re
from typing import Set

from backend.config.config import get_log_format, get_log_levels
from backend.utils.logging_formatter import UTCTimestampFormatter

# Matches control characters that can cause log injection (CWE-117)
_CONTROL_CHAR_RE = re.compile(r"[\r\n]")


def sanitize_log(value) -> str:
    """Sanitize a value for safe logging by removing newline characters (CWE-117)."""
    return _CONTROL_CHAR_RE.sub("", str(value))


class FlexibleLogger:
    """
    Logger that supports granular level filtering with pipe-separated configuration.

    Examples:
    - "DEBUG" - Only debug messages
    - "INFO|ERROR" - Only info and error messages
    - "WARNING|ERROR|CRITICAL" - Only warnings, errors, and critical messages
    - "INFO|WARNING|ERROR|CRITICAL" - Standard operational logging
    """

    def __init__(self, name: str):
        """Initialize flexible logger."""
        self.logger = logging.getLogger(name)
        self.name = name

        # Parse enabled levels from config
        self.enabled_levels = self._parse_enabled_levels()

        # Configure logger if not already done
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            log_format = get_log_format()
            handler.setFormatter(UTCTimestampFormatter(log_format))
            self.logger.addHandler(handler)
            self.logger.setLevel(
                logging.DEBUG
            )  # Let our filtering logic control output

    def _parse_enabled_levels(self) -> Set[int]:
        """Parse pipe-separated levels from config into a set of logging constants."""
        try:
            level_config = get_log_levels()
            enabled_levels = set()

            # Split by pipe and parse each level
            for level_name in level_config.split("|"):
                level_name = level_name.strip().upper()
                if hasattr(logging, level_name):
                    enabled_levels.add(getattr(logging, level_name))

            return enabled_levels
        except (KeyError, AttributeError, ValueError):
            # Default fallback to standard operational logging
            return {logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL}

    def _should_log(self, level: int) -> bool:
        """Check if message should be logged based on configured levels."""
        return level in self.enabled_levels

    def debug(self, msg: str, *args, **kwargs):
        """Log debug message if verbosity allows."""
        if self._should_log(logging.DEBUG):
            self.logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        """Log info message if verbosity allows."""
        if self._should_log(logging.INFO):
            self.logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """Log warning message if verbosity allows."""
        if self._should_log(logging.WARNING):
            self.logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        """Log error message if verbosity allows."""
        if self._should_log(logging.ERROR):
            self.logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        """Log critical message if verbosity allows."""
        if self._should_log(logging.CRITICAL):
            self.logger.critical(msg, *args, **kwargs)


def get_logger(name: str) -> FlexibleLogger:
    """Get a flexible logger instance with granular level control."""
    return FlexibleLogger(name)
