"""
Unit tests for login security functionality including user account locking.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from backend.security.login_security import LoginSecurityValidator
from backend.persistence.models import User


class TestLoginSecurityValidator:
    """Test cases for LoginSecurityValidator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = LoginSecurityValidator()

    def test_validate_login_attempt_allowed(self):
        """Test that valid login attempts are allowed."""
        is_allowed, reason = self.validator.validate_login_attempt(
            "test@example.com", "192.168.1.1"
        )
        assert is_allowed is True
        assert reason == "Login attempt allowed"

    def test_ip_blocking_after_multiple_failures(self):
        """Test that IPs are blocked after multiple failed attempts."""
        client_ip = "192.168.1.100"

        # Record 10 failed attempts (should trigger IP block)
        for _ in range(10):
            self.validator.record_failed_login("user@example.com", client_ip)

        # Next attempt should be blocked
        is_allowed, reason = self.validator.validate_login_attempt(
            "user@example.com", client_ip
        )
        assert is_allowed is False
        assert "IP temporarily blocked" in reason

    def test_rate_limiting_for_ip(self):
        """Test rate limiting based on IP address."""
        client_ip = "192.168.1.101"

        # Record 5 failed attempts within 5 minutes (should trigger rate limiting)
        for _ in range(5):
            self.validator.record_failed_login("user@example.com", client_ip)

        # Check rate limiting
        assert self.validator.is_rate_limited(client_ip) is True

    def test_successful_login_clears_ip_failures(self):
        """Test that successful login clears failed attempts for IP."""
        client_ip = "192.168.1.102"

        # Record some failed attempts
        for _ in range(3):
            self.validator.record_failed_login("user@example.com", client_ip)

        # Record successful login
        self.validator.record_successful_login("user@example.com", client_ip)

        # Failed attempts should be cleared
        assert client_ip not in self.validator.failed_attempts

    def test_user_account_not_locked_initially(self):
        """Test that new user accounts are not locked."""
        user = User(userid="test@example.com", is_locked=False, failed_login_attempts=0)
        assert self.validator.is_user_account_locked(user) is False

    def test_user_account_locked_status(self):
        """Test checking locked user account status."""
        # Create locked user
        user = User(
            userid="test@example.com",
            is_locked=True,
            failed_login_attempts=5,
            locked_at=datetime.now(timezone.utc),
        )
        assert self.validator.is_user_account_locked(user) is True

    @patch("backend.security.login_security.get_account_lockout_duration")
    def test_user_account_lock_expires(self, mock_lockout_duration):
        """Test that user account locks expire after configured duration."""
        mock_lockout_duration.return_value = 15  # 15 minutes

        # Create user locked 20 minutes ago (should be expired)
        past_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        user = User(
            userid="test@example.com",
            is_locked=True,
            failed_login_attempts=5,
            locked_at=past_time,
        )

        assert self.validator.is_user_account_locked(user) is False

    @patch("backend.security.login_security.get_max_failed_logins")
    def test_record_failed_login_for_user_locks_account(self, mock_max_failed):
        """Test that recording failed logins locks user account after max attempts."""
        mock_max_failed.return_value = 3

        user = User(userid="test@example.com", is_locked=False, failed_login_attempts=2)
        mock_session = Mock()

        # This should lock the account (3rd attempt)
        account_locked = self.validator.record_failed_login_for_user(user, mock_session)

        assert account_locked is True
        assert user.is_locked is True
        assert user.failed_login_attempts == 3
        assert user.locked_at is not None
        mock_session.commit.assert_called()

    @patch("backend.security.login_security.get_max_failed_logins")
    def test_record_failed_login_for_user_no_lock(self, mock_max_failed):
        """Test that failed login doesn't lock account before max attempts."""
        mock_max_failed.return_value = 5

        user = User(userid="test@example.com", is_locked=False, failed_login_attempts=2)
        mock_session = Mock()

        # This should not lock the account (3rd of 5 attempts)
        account_locked = self.validator.record_failed_login_for_user(user, mock_session)

        assert account_locked is False
        assert user.is_locked is False
        assert user.failed_login_attempts == 3
        mock_session.commit.assert_called()

    def test_record_successful_login_for_user_resets_failures(self):
        """Test that successful login resets failed login attempts."""
        user = User(
            userid="test@example.com",
            is_locked=True,
            failed_login_attempts=5,
            locked_at=datetime.now(timezone.utc),
        )
        mock_session = Mock()

        self.validator.reset_failed_login_attempts(user, mock_session)

        assert user.failed_login_attempts == 0
        assert user.is_locked is False
        assert user.locked_at is None
        mock_session.commit.assert_called()

    def test_unlock_user_account_manually(self):
        """Test manual user account unlocking."""
        user = User(
            userid="test@example.com",
            is_locked=True,
            failed_login_attempts=5,
            locked_at=datetime.now(timezone.utc),
        )
        mock_session = Mock()

        self.validator.unlock_user_account(user, mock_session)

        assert user.is_locked is False
        assert user.failed_login_attempts == 0
        assert user.locked_at is None
        mock_session.commit.assert_called()

    def test_unlock_user_account_already_unlocked(self):
        """Test unlocking an already unlocked user account."""
        user = User(userid="test@example.com", is_locked=False, failed_login_attempts=0)
        mock_session = Mock()

        self.validator.unlock_user_account(user, mock_session)

        # Should not call commit if user was already unlocked
        mock_session.commit.assert_not_called()

    def test_clean_old_attempts(self):
        """Test cleaning of old failed attempts."""
        client_ip = "192.168.1.103"

        # Add old attempts (2 hours ago)
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        self.validator.failed_attempts[client_ip] = [old_time]

        # Clean old attempts (keep last hour only)
        self.validator._clean_old_attempts(client_ip, hours_to_keep=1)

        # Old attempts should be removed
        assert client_ip not in self.validator.failed_attempts

    def test_user_rate_limiting(self):
        """Test user-specific rate limiting."""
        username = "test@example.com"
        user_key = f"user:{username}"

        # Record multiple failed attempts for user
        current_time = datetime.now(timezone.utc)
        self.validator.failed_attempts[user_key] = [
            current_time - timedelta(minutes=1),
            current_time - timedelta(minutes=2),
            current_time - timedelta(minutes=3),
        ]

        # Should be rate limited
        assert self.validator.is_user_rate_limited(username) is True

    def test_user_not_rate_limited_old_attempts(self):
        """Test that old user attempts don't trigger rate limiting."""
        username = "test@example.com"
        user_key = f"user:{username}"

        # Record old failed attempts (20 minutes ago)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        self.validator.failed_attempts[user_key] = [old_time, old_time, old_time]

        # Should not be rate limited
        assert self.validator.is_user_rate_limited(username) is False
