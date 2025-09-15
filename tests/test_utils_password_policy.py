"""
Unit tests for backend.utils.password_policy module.
Tests password policy validation and requirements generation.
"""

from unittest.mock import Mock, patch

import pytest

from backend.utils.password_policy import PasswordPolicy


class TestPasswordPolicy:
    """Test cases for PasswordPolicy class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.default_policy = {
            "min_length": 8,
            "max_length": 128,
            "require_uppercase": True,
            "require_lowercase": True,
            "require_numbers": True,
            "require_special_chars": True,
            "special_chars": "!@#$%^&*()_+-=[]{}|;:,.<>?",
            "allow_username_in_password": True,
            "min_character_types": 1,
        }

    @patch("backend.utils.password_policy.config")
    def test_init_with_default_config(self, mock_config):
        """Test PasswordPolicy initialization with default config."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": self.default_policy}
        }

        policy = PasswordPolicy()

        assert policy.config is not None
        assert policy.policy == self.default_policy

    @patch("backend.utils.password_policy.config")
    def test_init_with_empty_config(self, mock_config):
        """Test PasswordPolicy initialization with empty config."""
        mock_config.get_config.return_value = {}

        policy = PasswordPolicy()

        assert policy.policy == {}

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_text_full_policy(self, mock_config):
        """Test requirements text generation with full policy."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": self.default_policy}
        }

        policy = PasswordPolicy()
        requirements = policy.get_requirements_text()

        assert "Between 8 and 128 characters" in requirements
        assert "uppercase letters" in requirements
        assert "lowercase letters" in requirements
        assert "numbers" in requirements
        assert "special characters" in requirements

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_text_min_only(self, mock_config):
        """Test requirements text with only minimum length."""
        policy_config = {
            "min_length": 10,
            "max_length": 9999,
        }  # High max_length triggers "At least"
        mock_config.get_config.return_value = {
            "security": {"password_policy": policy_config}
        }

        policy = PasswordPolicy()
        requirements = policy.get_requirements_text()

        assert "At least 10 characters" in requirements

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_text_no_max_length(self, mock_config):
        """Test requirements text with no max length limit."""
        policy_config = {"min_length": 8, "max_length": None}
        mock_config.get_config.return_value = {
            "security": {"password_policy": policy_config}
        }

        policy = PasswordPolicy()
        requirements = policy.get_requirements_text()

        assert "At least 8 characters" in requirements
        assert "and" not in requirements.split("characters")[0]

    @patch("backend.utils.password_policy.config")
    def test_validate_password_success(self, mock_config):
        """Test successful password validation."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": self.default_policy}
        }

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("StrongP@ssw0rd!")

        assert is_valid is True
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config")
    def test_validate_password_too_short(self, mock_config):
        """Test password validation with too short password."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": self.default_policy}
        }

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("Sh0rt!")

        assert is_valid is False
        assert any("at least 8 characters" in error for error in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_too_long(self, mock_config):
        """Test password validation with too long password."""
        policy_config = self.default_policy.copy()
        policy_config["max_length"] = 20
        mock_config.get_config.return_value = {
            "security": {"password_policy": policy_config}
        }

        policy = PasswordPolicy()
        long_password = "A" * 25 + "1!b"
        is_valid, errors = policy.validate_password(long_password)

        assert is_valid is False
        assert any("no more than 20 characters" in error for error in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_missing_uppercase(self, mock_config):
        """Test password validation missing uppercase letters."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": self.default_policy}
        }

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("weakpassw0rd!")

        assert is_valid is False
        assert any("uppercase letter" in error for error in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_missing_lowercase(self, mock_config):
        """Test password validation missing lowercase letters."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": self.default_policy}
        }

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("WEAKPASSW0RD!")

        assert is_valid is False
        assert any("lowercase letter" in error for error in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_missing_numbers(self, mock_config):
        """Test password validation missing numbers."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": self.default_policy}
        }

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("WeakPassword!")

        assert is_valid is False
        assert any("number" in error for error in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_missing_special(self, mock_config):
        """Test password validation missing special characters."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": self.default_policy}
        }

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("WeakPassw0rd")

        assert is_valid is False
        assert any("special character" in error for error in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_with_username_restriction(self, mock_config):
        """Test password validation with username restriction."""
        policy_config = self.default_policy.copy()
        policy_config["allow_username_in_password"] = False
        mock_config.get_config.return_value = {
            "security": {"password_policy": policy_config}
        }

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password(
            "StrongPass123!", username="strongpass"
        )

        assert is_valid is False
        assert any("username" in error for error in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_no_policy(self, mock_config):
        """Test password validation with no policy configured."""
        mock_config.get_config.return_value = {}

        policy = PasswordPolicy()
        # With no policy, but still has default min_character_types validation
        # This should fail due to character type requirements
        is_valid, errors = policy.validate_password("password")

        assert is_valid is False
        assert len(errors) > 0

    @patch("backend.utils.password_policy.config")
    def test_validate_password_partial_policy(self, mock_config):
        """Test password validation with partial policy."""
        partial_policy = {"min_length": 6, "require_numbers": True}
        mock_config.get_config.return_value = {
            "security": {"password_policy": partial_policy}
        }

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("simple1")

        assert is_valid is True
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config")
    def test_validate_password_custom_special_chars(self, mock_config):
        """Test password validation with custom special characters."""
        custom_policy = self.default_policy.copy()
        custom_policy["special_chars"] = "!@#"
        mock_config.get_config.return_value = {
            "security": {"password_policy": custom_policy}
        }

        policy = PasswordPolicy()

        # Valid with allowed special char
        is_valid, errors = policy.validate_password("StrongP@ssw0rd")
        assert is_valid is True

        # Invalid with disallowed special char
        is_valid, errors = policy.validate_password("StrongP%ssw0rd")
        assert is_valid is False
        assert any("special character" in error for error in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_empty_string(self, mock_config):
        """Test password validation with empty string."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": self.default_policy}
        }

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("")

        assert is_valid is False
        assert len(errors) > 0

    @patch("backend.utils.password_policy.config")
    def test_validate_password_none(self, mock_config):
        """Test password validation with None."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": self.default_policy}
        }

        policy = PasswordPolicy()

        # The function expects a string, so None should raise an error
        with pytest.raises(TypeError):
            policy.validate_password(None)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_multiple_errors(self, mock_config):
        """Test password validation with multiple validation errors."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": self.default_policy}
        }

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("bad")

        assert is_valid is False
        assert len(errors) > 1  # Should have multiple errors

    @patch("backend.utils.password_policy.config")
    def test_validate_password_edge_case_lengths(self, mock_config):
        """Test password validation with edge case lengths."""
        policy_config = {"min_length": 5, "max_length": 10, "min_character_types": 0}
        mock_config.get_config.return_value = {
            "security": {"password_policy": policy_config}
        }

        policy = PasswordPolicy()

        # Exactly min length (5 chars)
        is_valid, errors = policy.validate_password("12345")
        assert is_valid is True
        assert len(errors) == 0

        # Exactly max length (10 chars)
        is_valid, errors = policy.validate_password("1234567890")
        assert is_valid is True
        assert len(errors) == 0

        # One under min (4 chars)
        is_valid, errors = policy.validate_password("1234")
        assert is_valid is False

        # One over max (11 chars)
        is_valid, errors = policy.validate_password("12345678901")
        assert is_valid is False

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_text_no_char_requirements(self, mock_config):
        """Test requirements text with no character type requirements."""
        policy_config = {"min_length": 8}
        mock_config.get_config.return_value = {
            "security": {"password_policy": policy_config}
        }

        policy = PasswordPolicy()
        requirements = policy.get_requirements_text()

        assert "uppercase" not in requirements
        assert "lowercase" not in requirements
        assert "numbers" not in requirements
        assert "special" not in requirements

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_list_method(self, mock_config):
        """Test get_requirements_list method."""
        policy_config = {
            "min_length": 8,
            "require_uppercase": True,
            "require_numbers": True,
        }
        mock_config.get_config.return_value = {
            "security": {"password_policy": policy_config}
        }

        policy = PasswordPolicy()
        requirements_list = policy.get_requirements_list()

        assert isinstance(requirements_list, list)
        assert len(requirements_list) >= 2  # At least length and one char requirement
        assert any("8 characters" in req for req in requirements_list)
        assert any("uppercase" in req for req in requirements_list)
