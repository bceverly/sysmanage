"""
Password policy validation utility for SysManage.
Validates passwords against configurable complexity rules.
"""

import re
from typing import List, Tuple

from backend.config import config


class PasswordPolicy:
    """Password policy validation based on configuration settings."""

    def __init__(self):
        """Initialize password policy with current configuration."""
        self.config = config.get_config()
        self.policy = self.config.get("security", {}).get("password_policy", {})

    def get_requirements_text(self) -> str:
        """Get human-readable password requirements text."""
        requirements = []

        # Length requirements
        min_length = self.policy.get("min_length", 8)
        max_length = self.policy.get("max_length", 128)

        if max_length and max_length < 1000:
            requirements.append(f"Between {min_length} and {max_length} characters")
        else:
            requirements.append(f"At least {min_length} characters")

        # Character type requirements
        char_reqs = []
        if self.policy.get("require_uppercase", False):
            char_reqs.append("uppercase letters")
        if self.policy.get("require_lowercase", False):
            char_reqs.append("lowercase letters")
        if self.policy.get("require_numbers", False):
            char_reqs.append("numbers")
        if self.policy.get("require_special_chars", False):
            char_reqs.append("special characters")

        if char_reqs:
            min_types = self.policy.get("min_character_types", len(char_reqs))
            if min_types >= len(char_reqs):
                requirements.append(f"Must contain {', '.join(char_reqs)}")
            else:
                requirements.append(
                    f"Must contain at least {min_types} of: {', '.join(char_reqs)}"
                )

        # Additional requirements
        if not self.policy.get("allow_username_in_password", True):
            requirements.append("Cannot contain your username or email")

        return "; ".join(requirements)

    def get_requirements_list(self) -> List[str]:
        """Get list of password requirements for detailed display."""
        requirements = []

        # Length requirements
        min_length = self.policy.get("min_length", 8)
        max_length = self.policy.get("max_length", 128)

        if max_length and max_length < 1000:
            requirements.append(f"Between {min_length}-{max_length} characters long")
        else:
            requirements.append(f"At least {min_length} characters long")

        # Individual character requirements
        if self.policy.get("require_uppercase", False):
            requirements.append("At least one uppercase letter (A-Z)")
        if self.policy.get("require_lowercase", False):
            requirements.append("At least one lowercase letter (a-z)")
        if self.policy.get("require_numbers", False):
            requirements.append("At least one number (0-9)")
        if self.policy.get("require_special_chars", False):
            special_chars = self.policy.get(
                "special_chars", "!@#$%^&*()_+-=[]{}|;':\",./<>?"
            )
            requirements.append(
                f"At least one special character ({special_chars[:20]}...)"
            )

        # Username restriction
        if not self.policy.get("allow_username_in_password", True):
            requirements.append("Cannot contain your username or email address")

        return requirements

    def validate_password(
        self, password: str, username: str = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate a password against the policy.

        Args:
            password: The password to validate
            username: The user's username/email (optional)

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Length validation
        min_length = self.policy.get("min_length", 8)
        max_length = self.policy.get("max_length", 128)

        if len(password) < min_length:
            errors.append(f"Password must be at least {min_length} characters long")

        if max_length and len(password) > max_length:
            errors.append(f"Password must be no more than {max_length} characters long")

        # Character type validation
        char_types_found = 0

        if self.policy.get("require_uppercase", False):
            if not re.search(r"[A-Z]", password):
                errors.append("Password must contain at least one uppercase letter")
            else:
                char_types_found += 1

        if self.policy.get("require_lowercase", False):
            if not re.search(r"[a-z]", password):
                errors.append("Password must contain at least one lowercase letter")
            else:
                char_types_found += 1

        if self.policy.get("require_numbers", False):
            if not re.search(r"[0-9]", password):
                errors.append("Password must contain at least one number")
            else:
                char_types_found += 1

        if self.policy.get("require_special_chars", False):
            special_chars = self.policy.get(
                "special_chars", "!@#$%^&*()_+-=[]{}|;':\",./<>?"
            )
            special_pattern = f"[{re.escape(special_chars)}]"
            if not re.search(special_pattern, password):
                errors.append("Password must contain at least one special character")
            else:
                char_types_found += 1

        # Minimum character types validation
        min_types = self.policy.get("min_character_types", 1)
        if char_types_found < min_types:
            errors.append(
                f"Password must contain at least {min_types} different character types"
            )

        # Username validation
        if username and not self.policy.get("allow_username_in_password", True):
            username_parts = [username.lower()]
            if "@" in username:
                username_parts.append(username.split("@")[0].lower())

            password_lower = password.lower()
            for part in username_parts:
                if len(part) >= 3 and part in password_lower:
                    errors.append(
                        "Password cannot contain your username or email address"
                    )
                    break

        return len(errors) == 0, errors


# Global instance
password_policy = PasswordPolicy()
