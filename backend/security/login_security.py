"""
Login security validation and enhancement for SysManage.
Implements security measures for authentication including rate limiting,
password policies, and security auditing.
"""

import hashlib
import hmac
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from backend.config.config import (
    get_account_lockout_duration,
    get_config,
    get_max_failed_logins,
)
from backend.persistence.models import User

logger = logging.getLogger(__name__)


class LoginSecurityValidator:
    """Validates and enforces security policies for login processes."""

    def __init__(self):
        self.config = get_config()
        # In-memory rate limiting store (in production, use Redis)
        self.failed_attempts: Dict[str, list] = defaultdict(list)
        self.successful_logins: Dict[str, list] = defaultdict(list)
        self.blocked_ips: Dict[str, datetime] = {}

    def validate_login_attempt(self, username: str, client_ip: str) -> Tuple[bool, str]:
        """
        Validate if a login attempt should be allowed.

        Returns:
            Tuple of (is_allowed, reason)
        """
        # Check if IP is temporarily blocked
        if self.is_ip_blocked(client_ip):
            logger.warning("Login attempt from blocked IP: %s", client_ip)
            return False, "IP temporarily blocked due to too many failed attempts"

        # Check rate limiting for this IP
        if self.is_rate_limited(client_ip):
            logger.warning("Rate limited login attempt from IP: %s", client_ip)
            return False, "Too many login attempts, please try again later"

        # Check user-specific rate limiting
        if self.is_user_rate_limited(username):
            logger.warning("Rate limited login attempt for user: %s", username)
            return False, "Too many failed attempts for this user"

        return True, "Login attempt allowed"

    def record_failed_login(
        self, username: str, client_ip: str, user_agent: str = ""
    ) -> None:
        """Record a failed login attempt for security monitoring."""
        current_time = datetime.now(timezone.utc)

        # Record failed attempt by IP
        self.failed_attempts[client_ip].append(current_time)

        # Clean old attempts (keep last hour only)
        self._clean_old_attempts(client_ip)

        # Check if IP should be blocked
        if len(self.failed_attempts[client_ip]) >= 10:  # 10 failures in an hour
            self.blocked_ips[client_ip] = current_time + timedelta(hours=1)
            logger.critical(
                "IP %s blocked for 1 hour due to repeated failures", client_ip
            )

        # Log security event
        logger.warning(
            "Failed login attempt - User: %s, IP: %s, User-Agent: %s, Time: %s",
            username,
            client_ip,
            user_agent,
            current_time.isoformat(),
        )

    def record_successful_login(
        self, username: str, client_ip: str, user_agent: str = ""
    ) -> None:
        """Record a successful login for security monitoring."""
        current_time = datetime.now(timezone.utc)

        # Clear failed attempts for this IP on successful login
        if client_ip in self.failed_attempts:
            del self.failed_attempts[client_ip]

        # Record successful login
        self.successful_logins[client_ip].append(current_time)

        logger.info(
            "Successful login - User: %s, IP: %s, User-Agent: %s, Time: %s",
            username,
            client_ip,
            user_agent,
            current_time.isoformat(),
        )

    def is_ip_blocked(self, client_ip: str) -> bool:
        """Check if an IP address is currently blocked."""
        if client_ip not in self.blocked_ips:
            return False

        # Check if block has expired
        if datetime.now(timezone.utc) > self.blocked_ips[client_ip]:
            del self.blocked_ips[client_ip]
            return False

        return True

    def is_rate_limited(
        self, client_ip: str, window_minutes: int = 5, max_attempts: int = 5
    ) -> bool:
        """Check if IP is rate limited (5 attempts per 5 minutes)."""
        if client_ip not in self.failed_attempts:
            return False

        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        recent_attempts = [
            attempt
            for attempt in self.failed_attempts[client_ip]
            if attempt > cutoff_time
        ]

        return len(recent_attempts) >= max_attempts

    def is_user_rate_limited(
        self, username: str, window_minutes: int = 15, max_attempts: int = 3
    ) -> bool:
        """Check if user is rate limited (3 attempts per 15 minutes)."""
        # This would typically query a database for user-specific failed attempts
        # For now, implementing basic in-memory tracking
        user_key = f"user:{username}"
        if user_key not in self.failed_attempts:
            return False

        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        recent_attempts = [
            attempt
            for attempt in self.failed_attempts[user_key]
            if attempt > cutoff_time
        ]

        return len(recent_attempts) >= max_attempts

    def _clean_old_attempts(self, key: str, hours_to_keep: int = 1) -> None:
        """Clean old failed attempts to prevent memory bloat."""
        if key not in self.failed_attempts:
            return

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_to_keep)
        self.failed_attempts[key] = [
            attempt for attempt in self.failed_attempts[key] if attempt > cutoff_time
        ]

        # Remove empty lists
        if not self.failed_attempts[key]:
            del self.failed_attempts[key]

    def is_user_account_locked(self, user: User) -> bool:
        """Check if user account is currently locked."""
        if not user.is_locked:
            return False

        # Check if lockout has expired
        if user.locked_at:
            lockout_duration = get_account_lockout_duration()
            unlock_time = user.locked_at + timedelta(minutes=lockout_duration)
            if datetime.now(timezone.utc) >= unlock_time:
                return False

        return True

    def record_failed_login_for_user(self, user: User, db_session) -> bool:
        """
        Record failed login attempt for user and lock account if needed.
        Returns True if account was locked.
        """
        max_attempts = get_max_failed_logins()
        user.failed_login_attempts += 1

        if user.failed_login_attempts >= max_attempts and not user.is_locked:
            user.is_locked = True
            user.locked_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db_session.commit()
            logger.warning(
                "User account '%s' locked after %s failed attempts",
                user.userid,
                user.failed_login_attempts,
            )
            return True

        db_session.commit()
        return False

    def reset_failed_login_attempts(self, user: User, db_session) -> None:
        """Reset failed login attempts on successful login."""
        was_locked = user.is_locked
        if user.failed_login_attempts > 0 or user.is_locked:
            user.failed_login_attempts = 0
            user.is_locked = False
            user.locked_at = None
            db_session.commit()
            if was_locked:
                logger.info(
                    "User account '%s' unlocked after successful login", user.userid
                )

    def unlock_user_account(self, user: User, db_session) -> None:
        """Manually unlock a user account."""
        if user.is_locked:
            user.is_locked = False
            user.failed_login_attempts = 0
            user.locked_at = None
            db_session.commit()
            logger.info("User account '%s' manually unlocked", user.userid)

    def lock_user_account(self, user: User, db_session) -> None:
        """Manually lock a user account."""
        if not user.is_locked:
            user.is_locked = True
            user.failed_login_attempts = 0
            user.locked_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db_session.commit()
            logger.info("User account '%s' manually locked", user.userid)


class PasswordSecurityValidator:
    """Validates password security policies."""

    @staticmethod
    # pylint: disable-next=too-many-return-statements
    def validate_password_strength(password: str) -> Tuple[bool, str]:
        """
        Validate password meets security requirements.

        Returns:
            Tuple of (is_valid, message)
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"

        if len(password) > 128:
            return False, "Password must be less than 128 characters"

        # Check for character diversity
        has_lower = any(c.islower() for c in password)
        has_upper = any(c.isupper() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)

        if not has_lower:
            return False, "Password must contain at least one lowercase letter"

        if not has_upper:
            return False, "Password must contain at least one uppercase letter"

        if not has_digit:
            return False, "Password must contain at least one number"

        if not has_special:
            return False, "Password must contain at least one special character"

        # Check for common patterns
        if password.lower() in ["password", "123456", "admin", "user"]:
            return False, "Password is too common"

        # Check for repeated characters
        if len(set(password)) < 4:
            return False, "Password must contain more diverse characters"

        return True, "Password meets security requirements"

    @staticmethod
    def is_password_compromised(password: str) -> bool:
        """
        Check if password appears in common breach databases.
        This is a simplified version - in production, integrate with HaveIBeenPwned API.
        """
        # Common compromised passwords (simplified list)
        common_passwords = {
            "password",
            "123456",
            "password123",
            "admin",
            "qwerty",
            "letmein",
            "welcome",
            "monkey",
            "1234567890",
            "abc123",
        }

        return password.lower() in common_passwords


class SessionSecurityManager:
    """Manages session security for authenticated users."""

    def __init__(self):
        self.config = get_config()

    def create_secure_session_token(self, user_id: str, client_ip: str) -> str:
        """Create a secure session token."""
        timestamp = str(int(time.time()))
        secret_key = self.config.get("security", {}).get(
            "jwt_secret", "fallback_secret"
        )

        # Create token payload
        payload = f"{user_id}:{client_ip}:{timestamp}"

        # Generate HMAC signature
        signature = hmac.new(
            secret_key.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

        return f"{payload}:{signature}"

    def validate_session_token(
        self, token: str, client_ip: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate session token and extract user ID.

        Returns:
            Tuple of (is_valid, user_id)
        """
        try:
            parts = token.split(":")
            if len(parts) != 4:
                return False, None

            user_id, token_ip, timestamp, signature = parts

            # Check IP consistency (optional - can be disabled for mobile users)
            if token_ip != client_ip:
                logger.warning(
                    "Session IP mismatch detected",
                    extra={"token_ip": token_ip, "client_ip": client_ip},
                )
                # Don't fail here - just log for monitoring

            # Check token age (12 hours max)
            token_age = int(time.time()) - int(timestamp)
            if token_age > 43200:  # 12 hours
                logger.info(
                    "Expired session token detected", extra={"token_age": token_age}
                )
                return False, None

            # Validate signature
            secret_key = self.config.get("security", {}).get(
                "jwt_secret", "fallback_secret"
            )
            payload = f"{user_id}:{token_ip}:{timestamp}"
            expected_signature = hmac.new(
                secret_key.encode(), payload.encode(), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("Invalid session signature for user: %s", user_id)
                return False, None

            return True, user_id

        except (ValueError, IndexError):
            logger.warning("Malformed session token")
            return False, None


# Global instances
login_security = LoginSecurityValidator()
password_security = PasswordSecurityValidator()
session_security = SessionSecurityManager()
