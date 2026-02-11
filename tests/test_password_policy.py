"""
Tests for backend/utils/password_policy.py module.
Tests password policy validation and requirements display.
"""

from unittest.mock import patch

import pytest


class TestPasswordPolicyValidate:
    """Tests for PasswordPolicy.validate_password method."""

    @patch("backend.utils.password_policy.config")
    def test_validate_password_min_length_pass(self, mock_config):
        """Test password meeting minimum length."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 8, "min_character_types": 0}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("password123")

        assert valid is True
        assert not errors

    @patch("backend.utils.password_policy.config")
    def test_validate_password_min_length_fail(self, mock_config):
        """Test password failing minimum length."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 12}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("short")

        assert valid is False
        assert any("at least 12 characters" in e for e in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_max_length_pass(self, mock_config):
        """Test password meeting maximum length."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {"max_length": 20, "min_character_types": 0}
            }
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("shortpassword")

        assert valid is True
        assert not errors

    @patch("backend.utils.password_policy.config")
    def test_validate_password_max_length_fail(self, mock_config):
        """Test password exceeding maximum length."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"max_length": 10}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("verylongpassword")

        assert valid is False
        assert any("no more than 10 characters" in e for e in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_require_uppercase_pass(self, mock_config):
        """Test password with required uppercase."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"require_uppercase": True}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("Password123")

        assert valid is True

    @patch("backend.utils.password_policy.config")
    def test_validate_password_require_uppercase_fail(self, mock_config):
        """Test password missing required uppercase."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"require_uppercase": True}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("password123")

        assert valid is False
        assert any("uppercase letter" in e for e in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_require_lowercase_pass(self, mock_config):
        """Test password with required lowercase."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"require_lowercase": True}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("PASSWORD123a")

        assert valid is True

    @patch("backend.utils.password_policy.config")
    def test_validate_password_require_lowercase_fail(self, mock_config):
        """Test password missing required lowercase."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"require_lowercase": True}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("PASSWORD123")

        assert valid is False
        assert any("lowercase letter" in e for e in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_require_numbers_pass(self, mock_config):
        """Test password with required numbers."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"require_numbers": True}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("password123")

        assert valid is True

    @patch("backend.utils.password_policy.config")
    def test_validate_password_require_numbers_fail(self, mock_config):
        """Test password missing required numbers."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"require_numbers": True}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("password")

        assert valid is False
        assert any("number" in e for e in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_require_special_chars_pass(self, mock_config):
        """Test password with required special characters."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"require_special_chars": True}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("password123!")

        assert valid is True

    @patch("backend.utils.password_policy.config")
    def test_validate_password_require_special_chars_fail(self, mock_config):
        """Test password missing required special characters."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"require_special_chars": True}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("password123")

        assert valid is False
        assert any("special character" in e for e in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_custom_special_chars(self, mock_config):
        """Test password with custom special character set."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "require_special_chars": True,
                    "special_chars": "@#$",
                }
            }
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("password123@")

        assert valid is True

    @patch("backend.utils.password_policy.config")
    def test_validate_password_min_character_types(self, mock_config):
        """Test minimum character types requirement."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "min_character_types": 3,
                }
            }
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("Password123")

        assert valid is True

    @patch("backend.utils.password_policy.config")
    def test_validate_password_min_character_types_fail(self, mock_config):
        """Test failing minimum character types requirement."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "min_character_types": 3,
                }
            }
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("password")

        assert valid is False
        assert any("character types" in e for e in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_username_allowed(self, mock_config):
        """Test password containing username when allowed."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "allow_username_in_password": True,
                    "min_character_types": 0,
                }
            }
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("johndoe123", username="johndoe")

        assert valid is True

    @patch("backend.utils.password_policy.config")
    def test_validate_password_username_not_allowed(self, mock_config):
        """Test password containing username when not allowed."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"allow_username_in_password": False}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password("johndoe123", username="johndoe")

        assert valid is False
        assert any("username" in e for e in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_email_prefix_not_allowed(self, mock_config):
        """Test password containing email prefix when not allowed."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"allow_username_in_password": False}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        valid, errors = policy.validate_password(
            "johndoe123", username="johndoe@example.com"
        )

        assert valid is False
        assert any("username" in e or "email" in e for e in errors)

    @patch("backend.utils.password_policy.config")
    def test_validate_password_short_username_ignored(self, mock_config):
        """Test that short usernames are not checked in password."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "allow_username_in_password": False,
                    "min_character_types": 0,
                }
            }
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        # Username "ab" is less than 3 characters so should be ignored
        valid, errors = policy.validate_password("password123", username="ab")

        assert valid is True


class TestPasswordPolicyRequirementsText:
    """Tests for PasswordPolicy.get_requirements_text method."""

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_text_min_length_only(self, mock_config):
        """Test requirements text with only min length."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 10, "max_length": 10000}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        text = policy.get_requirements_text()

        assert "At least 10 characters" in text

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_text_min_and_max_length(self, mock_config):
        """Test requirements text with min and max length."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 8, "max_length": 32}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        text = policy.get_requirements_text()

        assert "Between 8 and 32 characters" in text

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_text_char_requirements(self, mock_config):
        """Test requirements text with character requirements."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                }
            }
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        text = policy.get_requirements_text()

        assert "uppercase" in text
        assert "lowercase" in text
        assert "numbers" in text

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_text_min_char_types(self, mock_config):
        """Test requirements text with min character types."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "require_special_chars": True,
                    "min_character_types": 2,
                }
            }
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        text = policy.get_requirements_text()

        assert "at least 2 of" in text

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_text_username_restriction(self, mock_config):
        """Test requirements text with username restriction."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"allow_username_in_password": False}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        text = policy.get_requirements_text()

        assert "username" in text or "email" in text


class TestPasswordPolicyRequirementsList:
    """Tests for PasswordPolicy.get_requirements_list method."""

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_list_length_range(self, mock_config):
        """Test requirements list with length range."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 8, "max_length": 32}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        reqs = policy.get_requirements_list()

        assert any("8-32" in r for r in reqs)

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_list_length_min_only(self, mock_config):
        """Test requirements list with only min length."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 10, "max_length": 5000}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        reqs = policy.get_requirements_list()

        assert any("At least 10" in r for r in reqs)

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_list_all_char_types(self, mock_config):
        """Test requirements list with all character types."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "require_special_chars": True,
                }
            }
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        reqs = policy.get_requirements_list()

        assert any("uppercase" in r.lower() for r in reqs)
        assert any("lowercase" in r.lower() for r in reqs)
        assert any("number" in r.lower() for r in reqs)
        assert any("special" in r.lower() for r in reqs)

    @patch("backend.utils.password_policy.config")
    def test_get_requirements_list_username_restriction(self, mock_config):
        """Test requirements list with username restriction."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"allow_username_in_password": False}}
        }

        from backend.utils.password_policy import PasswordPolicy

        policy = PasswordPolicy()
        reqs = policy.get_requirements_list()

        assert any("username" in r.lower() for r in reqs)


class TestPasswordPolicyGlobalInstance:
    """Tests for global password_policy instance."""

    @patch("backend.utils.password_policy.config")
    def test_global_instance_exists(self, mock_config):
        """Test that global password_policy instance exists."""
        mock_config.get_config.return_value = {"security": {"password_policy": {}}}

        from backend.utils.password_policy import password_policy

        assert password_policy is not None

    @patch("backend.utils.password_policy.config")
    def test_global_instance_type(self, mock_config):
        """Test that global instance is PasswordPolicy type."""
        mock_config.get_config.return_value = {"security": {"password_policy": {}}}

        from backend.utils.password_policy import PasswordPolicy, password_policy

        assert isinstance(password_policy, PasswordPolicy)
