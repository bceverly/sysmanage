"""
Comprehensive tests for backend/utils/logging_formatter.py module.
Tests UTC timestamp formatting functionality for log messages.
"""

import datetime
import logging
from unittest.mock import patch

import pytest

from backend.utils.logging_formatter import UTCTimestampFormatter


class TestUTCTimestampFormatter:
    """Test UTCTimestampFormatter class."""

    def test_formatter_inheritance(self):
        """Test that UTCTimestampFormatter inherits from logging.Formatter."""
        formatter = UTCTimestampFormatter()
        assert isinstance(formatter, logging.Formatter)

    def test_formatter_initialization_no_args(self):
        """Test formatter initialization with no arguments."""
        formatter = UTCTimestampFormatter()
        assert formatter is not None

    def test_formatter_initialization_with_format(self):
        """Test formatter initialization with custom format string."""
        custom_format = "%(levelname)s: %(name)s: %(message)s"
        formatter = UTCTimestampFormatter(custom_format)
        assert formatter is not None

    def test_formatter_initialization_with_all_args(self):
        """Test formatter initialization with all possible arguments."""
        custom_format = "%(levelname)s: %(name)s: %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"
        formatter = UTCTimestampFormatter(custom_format, date_format)
        assert formatter is not None

    @patch("backend.utils.logging_formatter.datetime")
    def test_format_basic_message(self, mock_datetime):
        """Test basic message formatting with mocked datetime."""
        # Setup mock datetime
        mock_utc_now = datetime.datetime(2023, 12, 25, 15, 30, 45, 123456)
        mock_datetime.datetime.now.return_value = mock_utc_now
        mock_datetime.timezone.utc = datetime.timezone.utc

        # Create formatter and log record
        formatter = UTCTimestampFormatter("%(levelname)s: %(message)s")
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        expected = "[2023-12-25 15:30:45.123 UTC] INFO: Test message"
        assert result == expected

    @patch("backend.utils.logging_formatter.datetime")
    def test_format_with_logger_name(self, mock_datetime):
        """Test message formatting that includes logger name."""
        # Setup mock datetime
        mock_utc_now = datetime.datetime(2024, 1, 1, 12, 0, 0, 500000)
        mock_datetime.datetime.now.return_value = mock_utc_now
        mock_datetime.timezone.utc = datetime.timezone.utc

        # Create formatter and log record
        formatter = UTCTimestampFormatter("%(levelname)s: %(name)s: %(message)s")
        record = logging.LogRecord(
            name="my.module.logger",
            level=logging.WARNING,
            pathname="module.py",
            lineno=100,
            msg="Warning message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        expected = (
            "[2024-01-01 12:00:00.500 UTC] WARNING: my.module.logger: Warning message"
        )
        assert result == expected

    @patch("backend.utils.logging_formatter.datetime")
    def test_format_different_log_levels(self, mock_datetime):
        """Test formatting with different log levels."""
        # Setup mock datetime
        mock_utc_now = datetime.datetime(2024, 6, 15, 9, 45, 30, 750000)
        mock_datetime.datetime.now.return_value = mock_utc_now
        mock_datetime.timezone.utc = datetime.timezone.utc

        formatter = UTCTimestampFormatter("%(levelname)s: %(message)s")

        test_cases = [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
            (logging.CRITICAL, "CRITICAL"),
        ]

        for level_int, level_str in test_cases:
            record = logging.LogRecord(
                name="test",
                level=level_int,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=None,
            )
            result = formatter.format(record)
            expected = f"[2024-06-15 09:45:30.750 UTC] {level_str}: Test message"
            assert result == expected

    @patch("backend.utils.logging_formatter.datetime")
    def test_format_with_arguments(self, mock_datetime):
        """Test formatting messages with arguments."""
        # Setup mock datetime
        mock_utc_now = datetime.datetime(2024, 3, 10, 14, 20, 10, 250000)
        mock_datetime.datetime.now.return_value = mock_utc_now
        mock_datetime.timezone.utc = datetime.timezone.utc

        formatter = UTCTimestampFormatter("%(levelname)s: %(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=50,
            msg="User %s logged in with ID %d",
            args=("alice", 12345),
            exc_info=None,
        )

        result = formatter.format(record)
        expected = (
            "[2024-03-10 14:20:10.250 UTC] INFO: User alice logged in with ID 12345"
        )
        assert result == expected

    @patch("backend.utils.logging_formatter.datetime")
    def test_format_with_exception_info(self, mock_datetime):
        """Test formatting messages with exception information."""
        # Setup mock datetime
        mock_utc_now = datetime.datetime(2024, 8, 20, 16, 45, 55, 999000)
        mock_datetime.datetime.now.return_value = mock_utc_now
        mock_datetime.timezone.utc = datetime.timezone.utc

        formatter = UTCTimestampFormatter("%(levelname)s: %(message)s")

        # Create an exception for testing
        try:
            raise ValueError("Test exception")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=75,
            msg="An error occurred",
            args=(),
            exc_info=exc_info,
        )

        result = formatter.format(record)

        # Should contain timestamp, level, message, and traceback
        assert "[2024-08-20 16:45:55.999 UTC] ERROR: An error occurred" in result
        assert "ValueError: Test exception" in result
        assert "Traceback" in result

    @patch("backend.utils.logging_formatter.datetime")
    def test_format_preserves_original_formatter_behavior(self, mock_datetime):
        """Test that custom format strings work correctly."""
        # Setup mock datetime
        mock_utc_now = datetime.datetime(2024, 5, 5, 10, 15, 25, 123000)
        mock_datetime.datetime.now.return_value = mock_utc_now
        mock_datetime.timezone.utc = datetime.timezone.utc

        # Custom format with multiple fields
        custom_format = (
            "%(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s"
        )
        formatter = UTCTimestampFormatter(custom_format)

        record = logging.LogRecord(
            name="custom.logger",
            level=logging.DEBUG,
            pathname="/path/to/file.py",
            lineno=150,
            msg="Debug information",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        expected = "[2024-05-05 10:15:25.123 UTC] custom.logger - DEBUG - /path/to/file.py:150 - Debug information"
        assert result == expected

    @patch("backend.utils.logging_formatter.datetime")
    def test_millisecond_precision(self, mock_datetime):
        """Test that milliseconds are properly formatted (3 digits)."""
        test_cases = [
            # (microseconds, expected_milliseconds)
            (0, "000"),
            (1000, "001"),
            (123000, "123"),
            (999000, "999"),
            (500000, "500"),
            (1, "000"),  # Less than 1ms rounds to 000
            (999999, "999"),  # Maximum microseconds
        ]

        formatter = UTCTimestampFormatter("%(message)s")

        for microseconds, expected_ms in test_cases:
            mock_utc_now = datetime.datetime(2024, 1, 1, 12, 0, 0, microseconds)
            mock_datetime.datetime.now.return_value = mock_utc_now
            mock_datetime.timezone.utc = datetime.timezone.utc

            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test",
                args=(),
                exc_info=None,
            )

            result = formatter.format(record)
            expected = f"[2024-01-01 12:00:00.{expected_ms} UTC] Test"
            assert result == expected

    @patch("backend.utils.logging_formatter.datetime")
    def test_different_date_formats(self, mock_datetime):
        """Test formatting with various dates and times."""
        formatter = UTCTimestampFormatter("%(levelname)s: %(message)s")

        test_dates = [
            datetime.datetime(2024, 1, 1, 0, 0, 0, 0),  # New Year midnight
            datetime.datetime(2024, 12, 31, 23, 59, 59, 999000),  # End of year
            datetime.datetime(2024, 6, 15, 12, 30, 45, 500000),  # Mid-year
            datetime.datetime(2000, 2, 29, 6, 30, 15, 250000),  # Leap year
        ]

        expected_timestamps = [
            "2024-01-01 00:00:00.000 UTC",
            "2024-12-31 23:59:59.999 UTC",
            "2024-06-15 12:30:45.500 UTC",
            "2000-02-29 06:30:15.250 UTC",
        ]

        for test_date, expected_ts in zip(test_dates, expected_timestamps):
            mock_datetime.datetime.now.return_value = test_date
            mock_datetime.timezone.utc = datetime.timezone.utc

            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=None,
            )

            result = formatter.format(record)
            expected = f"[{expected_ts}] INFO: Test message"
            assert result == expected

    @patch("backend.utils.logging_formatter.datetime")
    def test_multiline_message_formatting(self, mock_datetime):
        """Test formatting of multiline messages."""
        # Setup mock datetime
        mock_utc_now = datetime.datetime(2024, 4, 10, 8, 20, 30, 100000)
        mock_datetime.datetime.now.return_value = mock_utc_now
        mock_datetime.timezone.utc = datetime.timezone.utc

        formatter = UTCTimestampFormatter("%(levelname)s: %(message)s")
        multiline_message = "First line\nSecond line\nThird line"

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=25,
            msg=multiline_message,
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        expected = (
            "[2024-04-10 08:20:30.100 UTC] INFO: First line\nSecond line\nThird line"
        )
        assert result == expected

    @patch("backend.utils.logging_formatter.datetime")
    def test_empty_message_formatting(self, mock_datetime):
        """Test formatting of empty messages."""
        # Setup mock datetime
        mock_utc_now = datetime.datetime(2024, 7, 25, 20, 10, 5, 800000)
        mock_datetime.datetime.now.return_value = mock_utc_now
        mock_datetime.timezone.utc = datetime.timezone.utc

        formatter = UTCTimestampFormatter("%(levelname)s: %(message)s")

        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=10,
            msg="",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        expected = "[2024-07-25 20:10:05.800 UTC] WARNING: "
        assert result == expected

    @patch("backend.utils.logging_formatter.datetime")
    def test_special_characters_in_message(self, mock_datetime):
        """Test formatting messages with special characters."""
        # Setup mock datetime
        mock_utc_now = datetime.datetime(2024, 9, 12, 13, 45, 20, 600000)
        mock_datetime.datetime.now.return_value = mock_utc_now
        mock_datetime.timezone.utc = datetime.timezone.utc

        formatter = UTCTimestampFormatter("%(levelname)s: %(message)s")
        special_message = "Message with special chars: !@#$%^&*()[]{}|;':\",./<>?"

        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=5,
            msg=special_message,
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        expected = "[2024-09-12 13:45:20.600 UTC] DEBUG: Message with special chars: !@#$%^&*()[]{}|;':\",./<>?"
        assert result == expected

    def test_real_datetime_integration(self):
        """Test formatter with real datetime (no mocking) to ensure integration works."""
        formatter = UTCTimestampFormatter("%(levelname)s: %(message)s")

        record = logging.LogRecord(
            name="integration_test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Integration test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)

        # Should have the expected format with current timestamp
        assert " UTC] INFO: Integration test message" in result
        assert result.startswith("[")
        assert "UTC]" in result

        # Check that timestamp has correct format (regex would be overkill for this test)
        timestamp_part = result.split("]")[0][1:]  # Remove [ and ]
        assert timestamp_part.endswith(" UTC")
        assert len(timestamp_part) == 27  # "YYYY-MM-DD HH:MM:SS.sss UTC" = 27 chars

    def test_formatter_with_custom_date_format_ignored(self):
        """Test that custom date format in constructor doesn't affect UTC timestamp."""
        # UTCTimestampFormatter should ignore date format since it generates its own timestamp
        custom_date_format = "%d/%m/%Y %H:%M:%S"
        formatter = UTCTimestampFormatter(
            "%(levelname)s: %(message)s", custom_date_format
        )

        with patch("backend.utils.logging_formatter.datetime") as mock_datetime:
            mock_utc_now = datetime.datetime(2024, 3, 15, 11, 25, 40, 300000)
            mock_datetime.datetime.now.return_value = mock_utc_now
            mock_datetime.timezone.utc = datetime.timezone.utc

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error message",
                args=(),
                exc_info=None,
            )

            result = formatter.format(record)
            # Should still use ISO format regardless of custom date format
            expected = "[2024-03-15 11:25:40.300 UTC] ERROR: Error message"
            assert result == expected


class TestUTCTimestampFormatterEdgeCases:
    """Test edge cases and error conditions."""

    @patch("backend.utils.logging_formatter.datetime")
    def test_strftime_format_consistency(self, mock_datetime):
        """Test that strftime format is consistent and correct."""
        # Test edge case where microseconds need padding
        mock_utc_now = datetime.datetime(2024, 1, 1, 1, 1, 1, 1)  # 1 microsecond
        mock_datetime.datetime.now.return_value = mock_utc_now
        mock_datetime.timezone.utc = datetime.timezone.utc

        formatter = UTCTimestampFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        # 1 microsecond should show as 000 milliseconds
        assert "[2024-01-01 01:01:01.000 UTC] Test" == result

    def test_none_record_handling(self):
        """Test that formatter doesn't crash with None record."""
        formatter = UTCTimestampFormatter()

        # This should raise AttributeError or similar, which is expected behavior
        with pytest.raises(AttributeError):
            formatter.format(None)

    @patch("backend.utils.logging_formatter.datetime")
    def test_timezone_independence(self, mock_datetime):
        """Test that formatter always uses UTC regardless of system timezone."""
        # Ensure we're always calling datetime.now(timezone.utc)
        mock_utc_now = datetime.datetime(2024, 6, 1, 15, 30, 45, 500000)
        mock_datetime.datetime.now.return_value = mock_utc_now
        mock_datetime.timezone.utc = datetime.timezone.utc

        formatter = UTCTimestampFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Timezone test",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)

        # Verify that datetime.now was called with timezone.utc
        mock_datetime.datetime.now.assert_called_once_with(datetime.timezone.utc)
        assert "[2024-06-01 15:30:45.500 UTC] Timezone test" == result
