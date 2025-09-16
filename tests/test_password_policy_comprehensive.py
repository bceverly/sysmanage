"""
Comprehensive unit tests for backend.utils.password_policy module.
Tests password policy validation and requirements text generation.
"""

import pytest
from unittest.mock import Mock, patch

from backend.utils.password_policy import PasswordPolicy, password_policy


class TestPasswordPolicyInitialization:
    """Test cases for PasswordPolicy initialization."""

    @patch("backend.utils.password_policy.config.get_config")
    def test_password_policy_initialization(self, mock_get_config):
        """Test PasswordPolicy initialization with config."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 12,
                    "max_length": 64,
                    "require_uppercase": True,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()

        assert policy.config == mock_config
        assert policy.policy == mock_config["security"]["password_policy"]

    @patch("backend.utils.password_policy.config.get_config")
    def test_password_policy_initialization_no_security_config(self, mock_get_config):
        """Test PasswordPolicy initialization without security config."""
        mock_config = {"other_section": {}}
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()

        assert policy.config == mock_config
        assert policy.policy == {}

    @patch("backend.utils.password_policy.config.get_config")
    def test_password_policy_initialization_no_password_policy(self, mock_get_config):
        """Test PasswordPolicy initialization without password_policy config."""
        mock_config = {"security": {"other_setting": "value"}}
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()

        assert policy.config == mock_config
        assert policy.policy == {}


class TestGetRequirementsText:
    """Test cases for get_requirements_text method."""

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_text_basic(self, mock_get_config):
        """Test basic requirements text generation."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "max_length": 128,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_text()

        assert "Between 8 and 128 characters" in requirements

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_text_no_max_length(self, mock_get_config):
        """Test requirements text with no max length."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 10,
                    "max_length": None,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_text()

        assert "At least 10 characters" in requirements

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_text_high_max_length(self, mock_get_config):
        """Test requirements text with very high max length."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "max_length": 2000,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_text()

        assert "At least 8 characters" in requirements

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_text_all_char_types(self, mock_get_config):
        """Test requirements text with all character types required."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "require_special_chars": True,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_text()

        assert "uppercase letters" in requirements
        assert "lowercase letters" in requirements
        assert "numbers" in requirements
        assert "special characters" in requirements

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_text_min_char_types(self, mock_get_config):
        """Test requirements text with minimum character types."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "require_special_chars": True,
                    "min_character_types": 3,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_text()

        assert "Must contain at least 3 of:" in requirements

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_text_all_char_types_required(self, mock_get_config):
        """Test requirements text when all character types are required."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "require_special_chars": True,
                    "min_character_types": 4,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_text()

        assert (
            "Must contain uppercase letters, lowercase letters, numbers, special characters"
            in requirements
        )

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_text_username_restriction(self, mock_get_config):
        """Test requirements text with username restriction."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_text()

        assert "Cannot contain your username or email" in requirements

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_text_username_allowed(self, mock_get_config):
        """Test requirements text when username is allowed."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": True,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_text()

        assert "Cannot contain your username or email" not in requirements


class TestGetRequirementsList:
    """Test cases for get_requirements_list method."""

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_list_basic(self, mock_get_config):
        """Test basic requirements list generation."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "max_length": 64,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_list()

        assert "Between 8-64 characters long" in requirements

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_list_no_max_length(self, mock_get_config):
        """Test requirements list with no max length."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 12,
                    "max_length": None,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_list()

        assert "At least 12 characters long" in requirements

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_list_high_max_length(self, mock_get_config):
        """Test requirements list with very high max length."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "max_length": 5000,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_list()

        assert "At least 8 characters long" in requirements

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_list_character_types(self, mock_get_config):
        """Test requirements list with character type requirements."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "require_special_chars": True,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_list()

        assert any("uppercase letter" in req for req in requirements)
        assert any("lowercase letter" in req for req in requirements)
        assert any("number" in req for req in requirements)
        assert any("special character" in req for req in requirements)

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_list_custom_special_chars(self, mock_get_config):
        """Test requirements list with custom special characters."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_special_chars": True,
                    "special_chars": "!@#$%^&*",
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_list()

        special_req = next(
            (req for req in requirements if "special character" in req), None
        )
        assert special_req is not None
        assert "!@#$%^&*" in special_req

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_list_long_special_chars(self, mock_get_config):
        """Test requirements list with long special characters string."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_special_chars": True,
                    "special_chars": "!@#$%^&*()_+-=[]{}|;':\",./<>?abcdefghijklmnopqrstuvwxyz",
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_list()

        special_req = next(
            (req for req in requirements if "special character" in req), None
        )
        assert special_req is not None
        assert "..." in special_req

    @patch("backend.utils.password_policy.config.get_config")
    def test_get_requirements_list_username_restriction(self, mock_get_config):
        """Test requirements list with username restriction."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_list()

        assert any("Cannot contain your username" in req for req in requirements)


class TestValidatePassword:
    """Test cases for validate_password method."""

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_success(self, mock_get_config):
        """Test successful password validation."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "max_length": 128,
                    "min_character_types": 0,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("ValidPassword123")

        assert is_valid is True
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_too_short(self, mock_get_config):
        """Test password too short validation."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 10,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("short")

        assert is_valid is False
        assert "must be at least 10 characters long" in errors[0]

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_too_long(self, mock_get_config):
        """Test password too long validation."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "max_length": 16,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("ThisPasswordIsTooLongForThePolicy")

        assert is_valid is False
        assert "must be no more than 16 characters long" in errors[0]

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_no_max_length(self, mock_get_config):
        """Test password validation with no max length restriction."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "max_length": None,
                    "min_character_types": 0,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password(
            "VeryLongPasswordThatShouldBeAcceptedBecauseThereIsNoMaximumLengthSet"
        )

        assert is_valid is True
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_missing_uppercase(self, mock_get_config):
        """Test password validation missing uppercase."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_uppercase": True,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("nouppercase123")

        assert is_valid is False
        assert "must contain at least one uppercase letter" in errors[0]

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_missing_lowercase(self, mock_get_config):
        """Test password validation missing lowercase."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_lowercase": True,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("NOLOWERCASE123")

        assert is_valid is False
        assert "must contain at least one lowercase letter" in errors[0]

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_missing_numbers(self, mock_get_config):
        """Test password validation missing numbers."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_numbers": True,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("NoNumbers")

        assert is_valid is False
        assert "must contain at least one number" in errors[0]

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_missing_special_chars(self, mock_get_config):
        """Test password validation missing special characters."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_special_chars": True,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("NoSpecialChars123")

        assert is_valid is False
        assert "must contain at least one special character" in errors[0]

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_custom_special_chars(self, mock_get_config):
        """Test password validation with custom special characters."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_special_chars": True,
                    "special_chars": "!@#",
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()

        # Test with valid special char
        is_valid, errors = policy.validate_password("Password123!")
        assert is_valid is True
        assert len(errors) == 0

        # Test with invalid special char
        is_valid, errors = policy.validate_password("Password123$")
        assert is_valid is False
        assert "must contain at least one special character" in errors[0]

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_min_character_types(self, mock_get_config):
        """Test password validation with minimum character types."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "require_special_chars": True,
                    "min_character_types": 3,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()

        # Test with only 2 character types (should fail)
        is_valid, errors = policy.validate_password("Password")
        assert is_valid is False
        # Should have multiple errors: missing numbers, special chars, and min character types
        error_messages = " ".join(errors)
        assert "must contain at least one number" in error_messages
        assert "must contain at least one special character" in error_messages
        assert "must contain at least 3 different character types" in error_messages

        # Test with 3 character types (should pass min types requirement)
        is_valid, errors = policy.validate_password("Password123")
        # This should still fail because we're missing special chars requirement
        assert is_valid is False
        assert "must contain at least one special character" in errors[0]

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_username_restriction(self, mock_get_config):
        """Test password validation with username restriction."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                    "min_character_types": 0,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()

        # Test with username in password
        is_valid, errors = policy.validate_password("myusername123", "myusername")
        assert is_valid is False
        assert "Password cannot contain your username or email address" in errors[0]

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_email_restriction(self, mock_get_config):
        """Test password validation with email restriction."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                    "min_character_types": 0,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()

        # Test with email local part in password
        is_valid, errors = policy.validate_password("myuser123", "myuser@example.com")
        assert is_valid is False
        assert "Password cannot contain your username or email address" in errors[0]

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_short_username_allowed(self, mock_get_config):
        """Test password validation allows short usernames in password."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                    "min_character_types": 0,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()

        # Test with short username (less than 3 chars) in password - should be allowed
        is_valid, errors = policy.validate_password("MyABPassword", "ab")
        assert is_valid is True
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config.get_config")
    def test_validate_password_username_allowed(self, mock_get_config):
        """Test password validation when username is allowed in password."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": True,
                    "min_character_types": 0,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()

        # Test with username in password - should be allowed
        is_valid, errors = policy.validate_password("myusername123", "myusername")
        assert is_valid is True
        assert len(errors) == 0


class TestPasswordPolicyDefaults:
    """Test cases for password policy default values."""

    @patch("backend.utils.password_policy.config.get_config")
    def test_default_min_length(self, mock_get_config):
        """Test default minimum length is 8."""
        mock_config = {"security": {"password_policy": {}}}
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("1234567")  # 7 chars

        assert is_valid is False
        assert "must be at least 8 characters long" in errors[0]

    @patch("backend.utils.password_policy.config.get_config")
    def test_default_max_length(self, mock_get_config):
        """Test default maximum length is 128."""
        mock_config = {"security": {"password_policy": {}}}
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_text()

        assert "Between 8 and 128 characters" in requirements

    @patch("backend.utils.password_policy.config.get_config")
    def test_default_character_requirements_disabled(self, mock_get_config):
        """Test default character requirements are disabled."""
        mock_config = {"security": {"password_policy": {"min_character_types": 0}}}
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("simplepass")

        assert is_valid is True
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config.get_config")
    def test_default_username_allowed(self, mock_get_config):
        """Test default allows username in password."""
        mock_config = {"security": {"password_policy": {"min_character_types": 0}}}
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("myusername123", "myusername")

        assert is_valid is True
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config.get_config")
    def test_default_special_chars(self, mock_get_config):
        """Test default special characters string."""
        mock_config = {
            "security": {
                "password_policy": {
                    "require_special_chars": True,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        requirements = policy.get_requirements_list()

        special_req = next(
            (req for req in requirements if "special character" in req), None
        )
        assert special_req is not None
        assert "!@#$%^&*()_+-=[]{}|" in special_req


class TestGlobalPasswordPolicyInstance:
    """Test cases for the global password_policy instance."""

    def test_global_instance_exists(self):
        """Test that global password_policy instance exists."""
        assert password_policy is not None
        assert isinstance(password_policy, PasswordPolicy)

    def test_global_instance_callable(self):
        """Test that global password_policy instance methods are callable."""
        assert callable(password_policy.get_requirements_text)
        assert callable(password_policy.get_requirements_list)
        assert callable(password_policy.validate_password)


class TestPasswordPolicyEdgeCases:
    """Test edge cases and error conditions."""

    @patch("backend.utils.password_policy.config.get_config")
    def test_empty_password_validation(self, mock_get_config):
        """Test validation of empty password."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("")

        assert is_valid is False
        assert "must be at least 8 characters long" in errors[0]

    @patch("backend.utils.password_policy.config.get_config")
    def test_none_username_validation(self, mock_get_config):
        """Test password validation with None username."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                    "min_character_types": 0,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("ValidPassword123", None)

        assert is_valid is True
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config.get_config")
    def test_empty_username_validation(self, mock_get_config):
        """Test password validation with empty username."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                    "min_character_types": 0,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("ValidPassword123", "")

        assert is_valid is True
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config.get_config")
    def test_zero_min_length(self, mock_get_config):
        """Test password policy with zero minimum length."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 0,
                    "min_character_types": 0,
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()
        is_valid, errors = policy.validate_password("")

        assert is_valid is True
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config.get_config")
    def test_regex_special_characters(self, mock_get_config):
        """Test password policy with regex special characters in special_chars."""
        mock_config = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_special_chars": True,
                    "special_chars": "[]{}()+*?^$|\\.",
                }
            }
        }
        mock_get_config.return_value = mock_config

        policy = PasswordPolicy()

        # Test with special char that needs escaping
        is_valid, errors = policy.validate_password("Password123[")
        assert is_valid is True
        assert len(errors) == 0
