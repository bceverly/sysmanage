"""
Comprehensive tests for backend/security/login_security.py module.
Tests security validation and enhancement for SysManage server.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from backend.security.login_security import (
    LoginSecurityValidator,
    PasswordSecurityValidator,
    SessionSecurityManager,
    login_security,
    password_security,
    session_security,
)


class MockUser:
    """Mock user object for testing."""

    def __init__(self, userid="testuser", is_locked=False, failed_attempts=0):
        self.userid = userid
        self.is_locked = is_locked
        self.failed_login_attempts = failed_attempts
        self.locked_at = None


class MockDBSession:
    """Mock database session."""

    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True


class TestLoginSecurityValidator:
    """Test LoginSecurityValidator class."""

    def test_init(self):
        """Test validator initialization."""
        validator = LoginSecurityValidator()
        assert isinstance(validator.failed_attempts, dict)
        assert isinstance(validator.successful_logins, dict)
        assert isinstance(validator.blocked_ips, dict)

    def test_validate_login_attempt_allowed(self):
        """Test login attempt that should be allowed."""
        validator = LoginSecurityValidator()
        is_allowed, reason = validator.validate_login_attempt("user", "192.168.1.1")

        assert is_allowed is True
        assert reason == "Login attempt allowed"

    def test_validate_login_attempt_blocked_ip(self):
        """Test login attempt from blocked IP."""
        validator = LoginSecurityValidator()

        # Block the IP
        validator.blocked_ips["192.168.1.100"] = datetime.now(timezone.utc) + timedelta(
            hours=1
        )

        is_allowed, reason = validator.validate_login_attempt("user", "192.168.1.100")

        assert is_allowed is False
        assert "blocked" in reason.lower()

    def test_validate_login_attempt_rate_limited(self):
        """Test rate limited login attempt."""
        validator = LoginSecurityValidator()

        # Add enough failed attempts to trigger rate limiting
        current_time = datetime.now(timezone.utc)
        for _ in range(6):  # More than the 5 attempt limit
            validator.failed_attempts["192.168.1.200"].append(current_time)

        is_allowed, reason = validator.validate_login_attempt("user", "192.168.1.200")

        assert is_allowed is False
        assert "too many" in reason.lower()

    def test_validate_login_attempt_user_rate_limited(self):
        """Test user-specific rate limiting."""
        validator = LoginSecurityValidator()

        # Add failed attempts for specific user
        current_time = datetime.now(timezone.utc)
        user_key = "user:testuser"
        for _ in range(4):  # More than the 3 attempt limit
            validator.failed_attempts[user_key].append(current_time)

        is_allowed, reason = validator.validate_login_attempt(
            "testuser", "192.168.1.50"
        )

        assert is_allowed is False
        assert "too many failed attempts" in reason.lower()

    def test_record_failed_login(self):
        """Test recording failed login attempt."""
        validator = LoginSecurityValidator()

        validator.record_failed_login("testuser", "192.168.1.10", "TestAgent")

        assert len(validator.failed_attempts["192.168.1.10"]) == 1

    def test_record_failed_login_triggers_block(self):
        """Test that too many failures trigger IP block."""
        validator = LoginSecurityValidator()

        # Record 10 failed attempts to trigger block
        for _ in range(10):
            validator.record_failed_login("testuser", "192.168.1.20", "TestAgent")

        assert "192.168.1.20" in validator.blocked_ips
        assert validator.is_ip_blocked("192.168.1.20") is True

    def test_record_successful_login(self):
        """Test recording successful login."""
        validator = LoginSecurityValidator()

        # First add some failed attempts
        validator.failed_attempts["192.168.1.30"].append(datetime.now(timezone.utc))

        # Record successful login
        validator.record_successful_login("testuser", "192.168.1.30", "TestAgent")

        # Failed attempts should be cleared
        assert "192.168.1.30" not in validator.failed_attempts
        assert len(validator.successful_logins["192.168.1.30"]) == 1

    def test_is_ip_blocked_false(self):
        """Test IP not blocked."""
        validator = LoginSecurityValidator()
        assert validator.is_ip_blocked("192.168.1.40") is False

    def test_is_ip_blocked_expired(self):
        """Test expired IP block."""
        validator = LoginSecurityValidator()

        # Set block that has already expired
        validator.blocked_ips["192.168.1.50"] = datetime.now(timezone.utc) - timedelta(
            hours=2
        )

        # Should return False and clean up the expired block
        assert validator.is_ip_blocked("192.168.1.50") is False
        assert "192.168.1.50" not in validator.blocked_ips

    def test_is_rate_limited_false(self):
        """Test IP not rate limited."""
        validator = LoginSecurityValidator()
        assert validator.is_rate_limited("192.168.1.60") is False

    def test_is_rate_limited_old_attempts(self):
        """Test rate limiting with old attempts."""
        validator = LoginSecurityValidator()

        # Add old attempts (more than 5 minutes ago)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        for _ in range(6):
            validator.failed_attempts["192.168.1.70"].append(old_time)

        # Should not be rate limited due to age
        assert validator.is_rate_limited("192.168.1.70") is False

    def test_is_user_rate_limited_false(self):
        """Test user not rate limited."""
        validator = LoginSecurityValidator()
        assert validator.is_user_rate_limited("testuser") is False

    def test_clean_old_attempts(self):
        """Test cleaning old attempts."""
        validator = LoginSecurityValidator()

        # Add old and new attempts
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        new_time = datetime.now(timezone.utc)

        key = "test-key"
        validator.failed_attempts[key] = [old_time, new_time]

        validator._clean_old_attempts(key, hours_to_keep=1)

        # Only new attempt should remain
        assert len(validator.failed_attempts[key]) == 1
        assert validator.failed_attempts[key][0] == new_time

    def test_clean_old_attempts_empty(self):
        """Test cleaning removes empty lists."""
        validator = LoginSecurityValidator()

        # Add only old attempts
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        key = "test-key-2"
        validator.failed_attempts[key] = [old_time]

        validator._clean_old_attempts(key, hours_to_keep=1)

        # Key should be removed
        assert key not in validator.failed_attempts

    def test_is_user_account_locked_false(self):
        """Test user account not locked."""
        validator = LoginSecurityValidator()
        user = MockUser(is_locked=False)

        assert validator.is_user_account_locked(user) is False

    @patch("backend.security.login_security.get_account_lockout_duration")
    def test_is_user_account_locked_expired(self, mock_get_duration):
        """Test expired user account lock."""
        mock_get_duration.return_value = 30  # 30 minutes

        validator = LoginSecurityValidator()
        user = MockUser(is_locked=True)
        user.locked_at = datetime.now(timezone.utc) - timedelta(
            hours=1
        )  # Locked 1 hour ago

        # Should not be locked anymore (lockout was 30 minutes)
        assert validator.is_user_account_locked(user) is False

    @patch("backend.security.login_security.get_account_lockout_duration")
    def test_is_user_account_locked_active(self, mock_get_duration):
        """Test active user account lock."""
        mock_get_duration.return_value = 60  # 60 minutes

        validator = LoginSecurityValidator()
        user = MockUser(is_locked=True)
        user.locked_at = datetime.now(timezone.utc) - timedelta(
            minutes=10
        )  # Locked 10 minutes ago

        # Should still be locked (lockout is 60 minutes)
        assert validator.is_user_account_locked(user) is True

    @patch("backend.security.login_security.get_max_failed_logins")
    def test_record_failed_login_for_user_lock(self, mock_max_logins):
        """Test recording failed login locks user account."""
        mock_max_logins.return_value = 3

        validator = LoginSecurityValidator()
        user = MockUser(failed_attempts=2)  # Will reach 3 after increment
        db_session = MockDBSession()

        result = validator.record_failed_login_for_user(user, db_session)

        assert result is True  # Account was locked
        assert user.is_locked is True
        assert user.failed_login_attempts == 3
        assert user.locked_at is not None
        assert db_session.committed is True

    @patch("backend.security.login_security.get_max_failed_logins")
    def test_record_failed_login_for_user_no_lock(self, mock_max_logins):
        """Test recording failed login doesn't lock account yet."""
        mock_max_logins.return_value = 5

        validator = LoginSecurityValidator()
        user = MockUser(failed_attempts=2)  # Will be 3, but limit is 5
        db_session = MockDBSession()

        result = validator.record_failed_login_for_user(user, db_session)

        assert result is False  # Account was not locked
        assert user.is_locked is False
        assert user.failed_login_attempts == 3
        assert db_session.committed is True

    def test_reset_failed_login_attempts(self):
        """Test resetting failed login attempts."""
        validator = LoginSecurityValidator()
        user = MockUser(failed_attempts=3, is_locked=True)
        user.locked_at = datetime.now(timezone.utc)
        db_session = MockDBSession()

        validator.reset_failed_login_attempts(user, db_session)

        assert user.failed_login_attempts == 0
        assert user.is_locked is False
        assert user.locked_at is None
        assert db_session.committed is True

    def test_reset_failed_login_attempts_no_change(self):
        """Test resetting when no changes needed."""
        validator = LoginSecurityValidator()
        user = MockUser(failed_attempts=0, is_locked=False)
        db_session = MockDBSession()

        validator.reset_failed_login_attempts(user, db_session)

        # Should not commit if no changes
        assert db_session.committed is False

    def test_unlock_user_account(self):
        """Test manually unlocking user account."""
        validator = LoginSecurityValidator()
        user = MockUser(failed_attempts=5, is_locked=True)
        user.locked_at = datetime.now(timezone.utc)
        db_session = MockDBSession()

        validator.unlock_user_account(user, db_session)

        assert user.is_locked is False
        assert user.failed_login_attempts == 0
        assert user.locked_at is None
        assert db_session.committed is True

    def test_unlock_user_account_not_locked(self):
        """Test unlocking already unlocked account."""
        validator = LoginSecurityValidator()
        user = MockUser(is_locked=False)
        db_session = MockDBSession()

        validator.unlock_user_account(user, db_session)

        # Should not commit if no changes
        assert db_session.committed is False


class TestPasswordSecurityValidator:
    """Test PasswordSecurityValidator class."""

    def test_validate_password_strength_valid(self):
        """Test valid password."""
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            "Test123!@#"
        )

        assert is_valid is True
        assert "meets security requirements" in message

    def test_validate_password_strength_too_short(self):
        """Test password too short."""
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            "Test1!"
        )

        assert is_valid is False
        assert "at least 8 characters" in message

    def test_validate_password_strength_too_long(self):
        """Test password too long."""
        long_password = "A" * 129  # 129 characters
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            long_password
        )

        assert is_valid is False
        assert "less than 128 characters" in message

    def test_validate_password_strength_no_lowercase(self):
        """Test password without lowercase."""
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            "TEST123!@#"
        )

        assert is_valid is False
        assert "lowercase letter" in message

    def test_validate_password_strength_no_uppercase(self):
        """Test password without uppercase."""
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            "test123!@#"
        )

        assert is_valid is False
        assert "uppercase letter" in message

    def test_validate_password_strength_no_digit(self):
        """Test password without digit."""
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            "TestABC!@#"
        )

        assert is_valid is False
        assert "number" in message

    def test_validate_password_strength_no_special(self):
        """Test password without special character."""
        is_valid, message = PasswordSecurityValidator.validate_password_strength(
            "Test123ABC"
        )

        assert is_valid is False
        assert "special character" in message

    def test_is_password_compromised_true(self):
        """Test compromised password detection."""
        assert PasswordSecurityValidator.is_password_compromised("password") is True
        assert PasswordSecurityValidator.is_password_compromised("123456") is True
        assert (
            PasswordSecurityValidator.is_password_compromised("PASSWORD") is True
        )  # Case insensitive

    def test_is_password_compromised_false(self):
        """Test secure password not compromised."""
        assert (
            PasswordSecurityValidator.is_password_compromised("SecurePass123!") is False
        )


class TestSessionSecurityManager:
    """Test SessionSecurityManager class."""

    @patch("backend.security.login_security.get_config")
    def test_init(self, mock_config):
        """Test session manager initialization."""
        mock_config.return_value = {
            "security": {"jwt_secret": "test_jwt_secret_key_for_login_testing_32bytes"}
        }

        manager = SessionSecurityManager()
        assert manager.config is not None

    @patch("backend.security.login_security.get_config")
    @patch("time.time")
    def test_create_secure_session_token(self, mock_time, mock_config):
        """Test creating secure session token."""
        mock_time.return_value = 1234567890
        mock_config.return_value = {
            "security": {"jwt_secret": "test_jwt_secret_key_for_login_testing_32bytes"}
        }

        manager = SessionSecurityManager()
        token = manager.create_secure_session_token("user123", "192.168.1.1")

        assert isinstance(token, str)
        assert ":" in token
        parts = token.split(":")
        assert len(parts) == 4
        assert parts[0] == "user123"
        assert parts[1] == "192.168.1.1"
        assert parts[2] == "1234567890"

    @patch("backend.security.login_security.get_config")
    @patch("time.time")
    def test_validate_session_token_valid(self, mock_time, mock_config):
        """Test validating valid session token."""
        mock_time.return_value = 1234567890
        mock_config.return_value = {
            "security": {"jwt_secret": "test_jwt_secret_key_for_login_testing_32bytes"}
        }

        manager = SessionSecurityManager()

        # Create token
        token = manager.create_secure_session_token("user123", "192.168.1.1")

        # Validate token (slightly in future to test age check)
        mock_time.return_value = 1234567890 + 3600  # 1 hour later
        is_valid, user_id = manager.validate_session_token(token, "192.168.1.1")

        assert is_valid is True
        assert user_id == "user123"

    @patch("backend.security.login_security.get_config")
    def test_validate_session_token_malformed(self, mock_config):
        """Test validating malformed token."""
        mock_config.return_value = {
            "security": {"jwt_secret": "test_jwt_secret_key_for_login_testing_32bytes"}
        }

        manager = SessionSecurityManager()
        is_valid, user_id = manager.validate_session_token(
            "invalid:token", "192.168.1.1"
        )

        assert is_valid is False
        assert user_id is None

    @patch("backend.security.login_security.get_config")
    @patch("time.time")
    def test_validate_session_token_expired(self, mock_time, mock_config):
        """Test validating expired token."""
        mock_time.return_value = 1234567890
        mock_config.return_value = {
            "security": {"jwt_secret": "test_jwt_secret_key_for_login_testing_32bytes"}
        }

        manager = SessionSecurityManager()
        token = manager.create_secure_session_token("user123", "192.168.1.1")

        # Token expired (more than 12 hours old)
        mock_time.return_value = 1234567890 + 50000  # ~14 hours later
        is_valid, user_id = manager.validate_session_token(token, "192.168.1.1")

        assert is_valid is False
        assert user_id is None

    @patch("backend.security.login_security.get_config")
    @patch("time.time")
    def test_validate_session_token_ip_mismatch(self, mock_time, mock_config):
        """Test validating token with IP mismatch."""
        mock_time.return_value = 1234567890
        mock_config.return_value = {
            "security": {"jwt_secret": "test_jwt_secret_key_for_login_testing_32bytes"}
        }

        manager = SessionSecurityManager()
        token = manager.create_secure_session_token("user123", "192.168.1.1")

        # Different IP but should still work (just logged)
        mock_time.return_value = 1234567890 + 3600
        is_valid, user_id = manager.validate_session_token(token, "192.168.1.2")

        assert is_valid is True  # Should still work
        assert user_id == "user123"

    @patch("backend.security.login_security.get_config")
    @patch("time.time")
    def test_validate_session_token_invalid_signature(self, mock_time, mock_config):
        """Test validating token with invalid signature."""
        mock_time.return_value = 1234567890
        mock_config.return_value = {
            "security": {"jwt_secret": "test_jwt_secret_key_for_login_testing_32bytes"}
        }

        manager = SessionSecurityManager()

        # Create token with one secret
        token = manager.create_secure_session_token("user123", "192.168.1.1")

        # Try to validate with different secret
        mock_config.return_value = {
            "security": {"jwt_secret": "different_jwt_secret_key_for_testing_32bytes"}
        }
        manager.config = mock_config.return_value

        mock_time.return_value = 1234567890 + 3600
        is_valid, user_id = manager.validate_session_token(token, "192.168.1.1")

        assert is_valid is False
        assert user_id is None


class TestGlobalInstances:
    """Test global instances are created correctly."""

    def test_global_instances_exist(self):
        """Test that global instances are available."""
        assert login_security is not None
        assert isinstance(login_security, LoginSecurityValidator)

        assert password_security is not None
        assert isinstance(password_security, PasswordSecurityValidator)

        assert session_security is not None
        assert isinstance(session_security, SessionSecurityManager)


class TestLoginSecurityIntegration:
    """Integration tests for login security."""

    def test_full_login_flow_success(self):
        """Test complete successful login flow."""
        validator = LoginSecurityValidator()

        # Validate login attempt
        is_allowed, _ = validator.validate_login_attempt("testuser", "192.168.1.100")
        assert is_allowed is True

        # Record successful login
        validator.record_successful_login("testuser", "192.168.1.100", "TestAgent")

        # Verify no failed attempts recorded
        assert "192.168.1.100" not in validator.failed_attempts

    def test_full_login_flow_with_failures(self):
        """Test login flow with failures leading to block."""
        validator = LoginSecurityValidator()
        ip = "192.168.1.200"

        # Record multiple failures
        for i in range(10):
            validator.record_failed_login(f"user{i}", ip, "TestAgent")

        # IP should now be blocked
        is_allowed, reason = validator.validate_login_attempt("testuser", ip)
        assert is_allowed is False
        assert "blocked" in reason.lower()

    @patch("backend.security.login_security.get_max_failed_logins")
    def test_user_account_lockout_flow(self, mock_max_logins):
        """Test user account lockout flow."""
        mock_max_logins.return_value = 3

        validator = LoginSecurityValidator()
        user = MockUser(failed_attempts=0)
        db_session = MockDBSession()

        # Record failures until lockout
        for _ in range(3):
            locked = validator.record_failed_login_for_user(user, db_session)

        # Last attempt should trigger lock
        assert locked is True
        assert user.is_locked is True

        # Reset on successful login
        validator.reset_failed_login_attempts(user, db_session)
        assert user.is_locked is False

    def test_password_validation_edge_cases(self):
        """Test password validation edge cases."""
        test_cases = [
            ("", False),  # Empty
            ("a", False),  # Too short
            ("Test123!", True),  # Valid
            ("test123!", False),  # No uppercase
            ("TEST123!", False),  # No lowercase
            ("TestABC!", False),  # No number
            ("Test123", False),  # No special
            ("password", False),  # Common
            ("aaaa1!", False),  # Not diverse
        ]

        for password, expected_valid in test_cases:
            is_valid, _ = PasswordSecurityValidator.validate_password_strength(password)
            assert (
                is_valid == expected_valid
            ), f"Password '{password}' should be {expected_valid}"

    @patch("backend.security.login_security.get_config")
    @patch("time.time")
    def test_session_token_lifecycle(self, mock_time, mock_config):
        """Test complete session token lifecycle."""
        mock_time.return_value = 1234567890
        mock_config.return_value = {
            "security": {"jwt_secret": "test_jwt_secret_key_for_login_testing_32bytes"}
        }

        manager = SessionSecurityManager()

        # Create token
        token = manager.create_secure_session_token("user123", "192.168.1.1")
        assert isinstance(token, str)

        # Validate immediately
        mock_time.return_value = 1234567890 + 60  # 1 minute later
        is_valid, user_id = manager.validate_session_token(token, "192.168.1.1")
        assert is_valid is True
        assert user_id == "user123"

        # Validate near expiry
        mock_time.return_value = 1234567890 + 43100  # Just under 12 hours
        is_valid, user_id = manager.validate_session_token(token, "192.168.1.1")
        assert is_valid is True

        # Validate after expiry
        mock_time.return_value = 1234567890 + 43300  # Over 12 hours
        is_valid, user_id = manager.validate_session_token(token, "192.168.1.1")
        assert is_valid is False


class TestLoginSecurityMissingCoverage:
    """Test missing coverage paths in login security."""

    def test_validate_session_token_malformed_token_logs_warning(self):
        """Test that malformed session token logs warning."""
        with patch("backend.security.login_security.get_config") as mock_config:
            mock_config.return_value = {"security": {"session_secret": "secret"}}
            manager = SessionSecurityManager()

            with patch("backend.security.login_security.logger") as mock_logger:
                # Test malformed tokens that trigger ValueError/IndexError (lines 366-368)

                # Test token with insufficient parts (IndexError on line 333)
                is_valid, user_id = manager.validate_session_token(
                    "only:two:parts", "192.168.1.1"
                )
                assert is_valid is False
                assert user_id is None

                # Reset the mock for next test
                mock_logger.reset_mock()

                # Test with invalid timestamp that causes ValueError when converting to int
                with patch("time.time", return_value=1234567890):
                    # Create a token with non-numeric timestamp
                    malformed_token = "user123:192.168.1.1:invalid_timestamp:signature"
                    is_valid, user_id = manager.validate_session_token(
                        malformed_token, "192.168.1.1"
                    )
                    assert is_valid is False
                    assert user_id is None

                # Should have logged warning about malformed token
                mock_logger.warning.assert_called_with("Malformed session token")
