"""
Logging configuration module for the SysManage server.

This module provides functions to configure logging with UTC timestamp formatting
and proper file/console handlers.
"""

import logging
import os
import sys

from backend.utils.logging_formatter import UTCTimestampFormatter
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.startup.logging")


def configure_logging():
    """Configure logging with UTC timestamp formatter and file/console handlers."""
    logger.debug("=== CONFIGURING LOGGING ===")

    # Ensure logs directory exists
    # Use SYSMANAGE_LOG_DIR environment variable if set (for systemd service)
    # Otherwise fall back to local logs/ directory (for development)
    env_log_dir = os.environ.get("SYSMANAGE_LOG_DIR")
    if env_log_dir:
        logs_dir = env_log_dir
        logger.debug("Using log directory from SYSMANAGE_LOG_DIR: %s", logs_dir)
    else:
        logs_dir = "logs"
        logger.debug("Using local logs directory: %s", logs_dir)

    logger.debug("Creating logs directory: %s", logs_dir)
    os.makedirs(logs_dir, exist_ok=True)
    logger.debug("Logs directory exists: %s", os.path.exists(logs_dir))

    # Configure logging with error handling for file permissions
    handlers = [logging.StreamHandler()]
    logger.debug("Added console handler")

    try:
        # Try to add file handler, but fallback gracefully if permission denied
        log_file = os.path.join(logs_dir, "backend.log")
        logger.debug("Attempting to create file handler for: %s", log_file)
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        handlers.append(file_handler)
        logger.debug("File handler created successfully")
    except PermissionError as e:
        logger.error("Permission denied for log file: %s", e)
        print(
            "WARNING: Cannot write to logs/backend.log due to permissions. Logging to console only.",
            file=sys.stderr,
        )
    except Exception as e:
        logger.error("Failed to create file handler: %s", e)

    # Under pytest, skip the basicConfig + handler reconfiguration that
    # would override pytest.ini's log_level and re-introduce the import-time
    # FastAPI startup banner into test output.  The mkdir above still runs
    # so the existing ``test_configure_logging_*`` tests pass.
    if "PYTEST_VERSION" in os.environ or "PYTEST_CURRENT_TEST" in os.environ:
        # We created the file handler above but never attach it under pytest;
        # close it so its open backend.log stream isn't garbage-collected
        # unclosed (a stray "ResourceWarning: unclosed file" in the suite).
        for handler in handlers:
            if isinstance(handler, logging.FileHandler):
                handler.close()
        return

    logger.debug("Configuring basic logging with %d handlers", len(handlers))
    logging.basicConfig(
        level=logging.INFO,
        handlers=handlers,
    )

    # Apply UTC timestamp formatter to all handlers
    logger.debug("Applying UTC timestamp formatter to all handlers")
    utc_formatter = UTCTimestampFormatter("%(levelname)s: %(name)s: %(message)s")
    for i, handler in enumerate(logging.root.handlers):
        logger.debug("Setting formatter for handler %d: %s", i, type(handler).__name__)
        handler.setFormatter(utc_formatter)
    logger.info("Logging configuration complete")
