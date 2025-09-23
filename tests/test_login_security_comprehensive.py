"""
Comprehensive tests for backend/security/login_security.py

Tests the LoginSecurityValidator class methods including rate limiting,
IP blocking, user validation, and security monitoring.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from backend.security.login_security import LoginSecurityValidator


class TestLoginSecurityValidator:
    """Test cases for LoginSecurityValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a fresh LoginSecurityValidator instance for each test."""
        with patch("backend.security.login_security.get_config") as mock_config:
            mock_config.return_value = {"security": {"test": "config"}}
            return LoginSecurityValidator()

    def test_init(self, validator):
        """Test validator initialization."""
        assert validator.config is not None
        assert isinstance(validator.failed_attempts, dict)
        assert isinstance(validator.successful_logins, dict)
        assert isinstance(validator.blocked_ips, dict)
        assert len(validator.failed_attempts) == 0
        assert len(validator.successful_logins) == 0
        assert len(validator.blocked_ips) == 0

    def test_validate_login_attempt_allowed(self, validator):
        """Test validate_login_attempt when attempt should be allowed."""
        result = validator.validate_login_attempt("testuser", "192.168.1.1")

        assert result[0] is True
        assert result[1] == "Login attempt allowed"

    def test_validate_login_attempt_blocked_ip(self, validator):
        """Test validate_login_attempt with blocked IP."""
        # Block the IP
        validator.blocked_ips["192.168.1.100"] = datetime.now(timezone.utc) + timedelta(
            hours=1
        )

        with patch("backend.security.login_security.logger") as mock_logger:
            result = validator.validate_login_attempt("testuser", "192.168.1.100")

            assert result[0] is False
            assert "IP temporarily blocked" in result[1]
            mock_logger.warning.assert_called_once()

    @patch("backend.security.login_security.datetime")
    def test_validate_login_attempt_rate_limited_ip(self, mock_datetime, validator):
        """Test validate_login_attempt with rate limited IP."""
        # Mock current time
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        # Add 5 failed attempts within the window
        for i in range(5):
            attempt_time = current_time - timedelta(minutes=i)
            validator.failed_attempts["192.168.1.200"].append(attempt_time)

        with patch("backend.security.login_security.logger") as mock_logger:
            result = validator.validate_login_attempt("testuser", "192.168.1.200")

            assert result[0] is False
            assert "Too many login attempts" in result[1]
            mock_logger.warning.assert_called_once()

    @patch("backend.security.login_security.datetime")
    def test_validate_login_attempt_user_rate_limited(self, mock_datetime, validator):
        """Test validate_login_attempt with user rate limited."""
        # Mock current time
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        # Add 3 failed attempts for user within the window
        user_key = "user:testuser"
        for i in range(3):
            attempt_time = current_time - timedelta(minutes=i)
            validator.failed_attempts[user_key].append(attempt_time)

        with patch("backend.security.login_security.logger") as mock_logger:
            result = validator.validate_login_attempt("testuser", "192.168.1.1")

            assert result[0] is False
            assert "Too many failed attempts for this user" in result[1]
            mock_logger.warning.assert_called_once()

    @patch("backend.security.login_security.datetime")
    def test_record_failed_login(self, mock_datetime, validator):
        """Test record_failed_login functionality."""
        # Mock current time
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        with patch("backend.security.login_security.logger") as mock_logger:
            validator.record_failed_login("testuser", "192.168.1.1", "Mozilla/5.0")

            # Check that failed attempt was recorded
            assert "192.168.1.1" in validator.failed_attempts
            assert len(validator.failed_attempts["192.168.1.1"]) == 1
            assert validator.failed_attempts["192.168.1.1"][0] == current_time

            # Check logging
            mock_logger.warning.assert_called_once()
            log_args = mock_logger.warning.call_args[0]
            assert "Failed login attempt" in log_args[0]
            assert "testuser" in log_args[1]  # First substitution argument

    @patch("backend.security.login_security.datetime")
    def test_record_failed_login_triggers_ip_block(self, mock_datetime, validator):
        """Test record_failed_login triggers IP block after 10 failures."""
        # Mock current time
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        # Pre-populate with 9 failed attempts
        for i in range(9):
            validator.failed_attempts["192.168.1.100"].append(
                current_time - timedelta(minutes=i)
            )

        with patch("backend.security.login_security.logger") as mock_logger:
            # The 10th attempt should trigger a block
            validator.record_failed_login("testuser", "192.168.1.100", "Mozilla/5.0")

            # Check IP is now blocked
            assert "192.168.1.100" in validator.blocked_ips
            expected_unblock_time = current_time + timedelta(hours=1)
            assert validator.blocked_ips["192.168.1.100"] == expected_unblock_time

            # Check critical log was called
            mock_logger.critical.assert_called_once()
            critical_args = mock_logger.critical.call_args[0]
            assert "IP %s blocked" in critical_args[0]
            assert "192.168.1.100" in critical_args[1]  # First substitution argument

    @patch("backend.security.login_security.datetime")
    def test_record_successful_login(self, mock_datetime, validator):
        """Test record_successful_login functionality."""
        # Mock current time
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        # Pre-populate some failed attempts for the IP
        validator.failed_attempts["192.168.1.1"] = [current_time - timedelta(minutes=5)]

        with patch("backend.security.login_security.logger") as mock_logger:
            validator.record_successful_login("testuser", "192.168.1.1", "Mozilla/5.0")

            # Check that failed attempts were cleared
            assert "192.168.1.1" not in validator.failed_attempts

            # Check that successful login was recorded
            assert "192.168.1.1" in validator.successful_logins
            assert len(validator.successful_logins["192.168.1.1"]) == 1
            assert validator.successful_logins["192.168.1.1"][0] == current_time

            # Check logging
            mock_logger.info.assert_called_once()
            log_args = mock_logger.info.call_args[0]
            assert "Successful login" in log_args[0]
            assert "testuser" in log_args[1]  # First substitution argument

    def test_is_ip_blocked_not_blocked(self, validator):
        """Test is_ip_blocked with non-blocked IP."""
        result = validator.is_ip_blocked("192.168.1.1")
        assert result is False

    @patch("backend.security.login_security.datetime")
    def test_is_ip_blocked_currently_blocked(self, mock_datetime, validator):
        """Test is_ip_blocked with currently blocked IP."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        # Block IP for 1 hour from now
        validator.blocked_ips["192.168.1.100"] = current_time + timedelta(hours=1)

        result = validator.is_ip_blocked("192.168.1.100")
        assert result is True

    @patch("backend.security.login_security.datetime")
    def test_is_ip_blocked_expired_block(self, mock_datetime, validator):
        """Test is_ip_blocked with expired block."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        # Block IP for 1 hour ago (expired)
        validator.blocked_ips["192.168.1.100"] = current_time - timedelta(hours=1)

        result = validator.is_ip_blocked("192.168.1.100")
        assert result is False
        # Check that expired block was cleaned up
        assert "192.168.1.100" not in validator.blocked_ips

    @patch("backend.security.login_security.datetime")
    def test_is_rate_limited_no_attempts(self, mock_datetime, validator):
        """Test is_rate_limited with no failed attempts."""
        result = validator.is_rate_limited("192.168.1.1")
        assert result is False

    @patch("backend.security.login_security.datetime")
    def test_is_rate_limited_under_threshold(self, mock_datetime, validator):
        """Test is_rate_limited with attempts under threshold."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        # Add 4 attempts within window (under threshold of 5)
        for i in range(4):
            validator.failed_attempts["192.168.1.1"].append(
                current_time - timedelta(minutes=i)
            )

        result = validator.is_rate_limited("192.168.1.1")
        assert result is False

    @patch("backend.security.login_security.datetime")
    def test_is_rate_limited_over_threshold(self, mock_datetime, validator):
        """Test is_rate_limited with attempts over threshold."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        # Add 5 attempts within window (meets threshold)
        for i in range(5):
            validator.failed_attempts["192.168.1.1"].append(
                current_time - timedelta(minutes=i)
            )

        result = validator.is_rate_limited("192.168.1.1")
        assert result is True

    @patch("backend.security.login_security.datetime")
    def test_is_rate_limited_old_attempts_ignored(self, mock_datetime, validator):
        """Test is_rate_limited ignores old attempts outside window."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        # Add 3 recent attempts and 3 old attempts
        for i in range(3):
            validator.failed_attempts["192.168.1.1"].append(
                current_time - timedelta(minutes=i)
            )
        for i in range(3):
            validator.failed_attempts["192.168.1.1"].append(
                current_time - timedelta(minutes=10 + i)
            )

        result = validator.is_rate_limited("192.168.1.1")
        assert result is False  # Only 3 recent attempts, under threshold of 5

    @patch("backend.security.login_security.datetime")
    def test_is_rate_limited_custom_parameters(self, mock_datetime, validator):
        """Test is_rate_limited with custom window and max attempts."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        # Add 2 attempts within custom window
        for i in range(2):
            validator.failed_attempts["192.168.1.1"].append(
                current_time - timedelta(minutes=i)
            )

        # With default params (5 attempts, 5 min window) - should be False
        result = validator.is_rate_limited("192.168.1.1")
        assert result is False

        # With custom params (2 attempts, 10 min window) - should be True
        result = validator.is_rate_limited(
            "192.168.1.1", window_minutes=10, max_attempts=2
        )
        assert result is True

    @patch("backend.security.login_security.datetime")
    def test_is_user_rate_limited_no_attempts(self, mock_datetime, validator):
        """Test is_user_rate_limited with no failed attempts."""
        result = validator.is_user_rate_limited("testuser")
        assert result is False

    @patch("backend.security.login_security.datetime")
    def test_is_user_rate_limited_under_threshold(self, mock_datetime, validator):
        """Test is_user_rate_limited with attempts under threshold."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        user_key = "user:testuser"
        # Add 2 attempts within window (under threshold of 3)
        for i in range(2):
            validator.failed_attempts[user_key].append(
                current_time - timedelta(minutes=i)
            )

        result = validator.is_user_rate_limited("testuser")
        assert result is False

    @patch("backend.security.login_security.datetime")
    def test_is_user_rate_limited_over_threshold(self, mock_datetime, validator):
        """Test is_user_rate_limited with attempts over threshold."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        user_key = "user:testuser"
        # Add 3 attempts within window (meets threshold)
        for i in range(3):
            validator.failed_attempts[user_key].append(
                current_time - timedelta(minutes=i)
            )

        result = validator.is_user_rate_limited("testuser")
        assert result is True

    @patch("backend.security.login_security.datetime")
    def test_is_user_rate_limited_custom_parameters(self, mock_datetime, validator):
        """Test is_user_rate_limited with custom window and max attempts."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        user_key = "user:testuser"
        # Add 1 attempt within custom window
        validator.failed_attempts[user_key].append(current_time)

        # With default params (3 attempts, 15 min window) - should be False
        result = validator.is_user_rate_limited("testuser")
        assert result is False

        # With custom params (1 attempt, 5 min window) - should be True
        result = validator.is_user_rate_limited(
            "testuser", window_minutes=5, max_attempts=1
        )
        assert result is True

    @patch("backend.security.login_security.datetime")
    def test_clean_old_attempts_no_key(self, mock_datetime, validator):
        """Test _clean_old_attempts with non-existent key."""
        # Should not raise exception
        validator._clean_old_attempts("nonexistent")
        assert "nonexistent" not in validator.failed_attempts

    @patch("backend.security.login_security.datetime")
    def test_clean_old_attempts_removes_old(self, mock_datetime, validator):
        """Test _clean_old_attempts removes old attempts."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        # Add recent and old attempts
        validator.failed_attempts["192.168.1.1"] = [
            current_time - timedelta(minutes=30),  # Recent
            current_time - timedelta(hours=2),  # Old
            current_time - timedelta(minutes=10),  # Recent
            current_time - timedelta(hours=3),  # Old
        ]

        validator._clean_old_attempts("192.168.1.1")

        # Should only have 2 recent attempts
        assert len(validator.failed_attempts["192.168.1.1"]) == 2
        # All remaining should be within 1 hour
        for attempt in validator.failed_attempts["192.168.1.1"]:
            assert attempt > current_time - timedelta(hours=1)

    @patch("backend.security.login_security.datetime")
    def test_clean_old_attempts_custom_hours(self, mock_datetime, validator):
        """Test _clean_old_attempts with custom hours_to_keep."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        # Add attempts at different times
        validator.failed_attempts["192.168.1.1"] = [
            current_time - timedelta(minutes=30),  # Within 2 hours
            current_time - timedelta(hours=1.5),  # Within 2 hours
            current_time - timedelta(hours=3),  # Outside 2 hours
        ]

        validator._clean_old_attempts("192.168.1.1", hours_to_keep=2)

        # Should only have 2 attempts within 2 hours
        assert len(validator.failed_attempts["192.168.1.1"]) == 2
        # All remaining should be within 2 hours
        for attempt in validator.failed_attempts["192.168.1.1"]:
            assert attempt > current_time - timedelta(hours=2)


class TestLoginSecurityIntegration:
    """Integration tests for LoginSecurityValidator workflow."""

    @pytest.fixture
    def validator(self):
        """Create a fresh LoginSecurityValidator instance for integration tests."""
        with patch("backend.security.login_security.get_config") as mock_config:
            mock_config.return_value = {"security": {"test": "config"}}
            return LoginSecurityValidator()

    @patch("backend.security.login_security.datetime")
    def test_full_workflow_normal_login(self, mock_datetime, validator):
        """Test complete workflow for normal login."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        username = "testuser"
        client_ip = "192.168.1.1"

        # 1. Validate login attempt - should be allowed
        result = validator.validate_login_attempt(username, client_ip)
        assert result[0] is True

        # 2. Record successful login
        with patch("backend.security.login_security.logger"):
            validator.record_successful_login(username, client_ip, "Mozilla/5.0")

        # 3. Verify successful login was recorded
        assert client_ip in validator.successful_logins
        assert len(validator.successful_logins[client_ip]) == 1

    @patch("backend.security.login_security.datetime")
    def test_full_workflow_rate_limiting_scenario(self, mock_datetime, validator):
        """Test complete workflow for rate limiting scenario."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        username = "testuser"
        client_ip = "192.168.1.100"

        # Record 5 failed attempts within the 5-minute rate limiting window
        with patch("backend.security.login_security.logger"):
            for i in range(5):
                # Keep all attempts within the 5-minute window
                mock_datetime.now.return_value = current_time + timedelta(
                    seconds=i * 30
                )  # 30 seconds apart

                # Record failed login
                validator.record_failed_login(username, client_ip, "Mozilla/5.0")

        # Next attempt should be rate limited (rate limit check happens BEFORE recording)
        mock_datetime.now.return_value = current_time + timedelta(minutes=2, seconds=30)
        result = validator.validate_login_attempt(username, client_ip)
        assert result[0] is False
        assert "Too many login attempts" in result[1]

    @patch("backend.security.login_security.datetime")
    def test_full_workflow_ip_blocking_scenario(self, mock_datetime, validator):
        """Test complete workflow for IP blocking scenario."""
        current_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = current_time

        username = "testuser"
        client_ip = "192.168.1.200"

        # Record 10 failed attempts to trigger IP block
        with patch("backend.security.login_security.logger"):
            for i in range(10):
                # Skip rate limiting check for this test
                validator.record_failed_login(username, client_ip, "Mozilla/5.0")

        # Next attempt should be blocked due to IP block
        result = validator.validate_login_attempt(username, client_ip)
        assert result[0] is False
        assert "IP temporarily blocked" in result[1]

        # Verify IP is in blocked list
        assert client_ip in validator.blocked_ips
