"""
Comprehensive tests for backend/utils/password_policy.py module.
Tests password validation, requirements text generation, and policy enforcement.
"""

from unittest.mock import patch

import pytest

from backend.utils.password_policy import PasswordPolicy, password_policy


class TestPasswordPolicy:
    """Test PasswordPolicy class initialization and configuration."""

    @patch("backend.utils.password_policy.config")
    def test_init_with_default_config(self, mock_config):
        """Test initialization with default configuration."""
        mock_config.get_config.return_value = {}
        policy = PasswordPolicy()

        assert policy.config == {}
        assert policy.policy == {}
        mock_config.get_config.assert_called_once()

    @patch("backend.utils.password_policy.config")
    def test_init_with_custom_config(self, mock_config):
        """Test initialization with custom password policy configuration."""
        test_config = {
            "security": {
                "password_policy": {
                    "min_length": 12,
                    "require_uppercase": True,
                    "require_numbers": True,
                }
            }
        }
        mock_config.get_config.return_value = test_config
        policy = PasswordPolicy()

        assert policy.config == test_config
        assert policy.policy == test_config["security"]["password_policy"]

    @patch("backend.utils.password_policy.config")
    def test_init_missing_security_section(self, mock_config):
        """Test initialization when security section is missing."""
        mock_config.get_config.return_value = {"other": "config"}
        policy = PasswordPolicy()

        assert policy.policy == {}


class TestGetRequirementsText:
    """Test get_requirements_text method."""

    @patch("backend.utils.password_policy.config")
    def test_minimal_requirements(self, mock_config):
        """Test requirements text with minimal policy."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 8, "max_length": None}}
        }
        policy = PasswordPolicy()

        result = policy.get_requirements_text()
        assert "At least 8 characters" in result

    @patch("backend.utils.password_policy.config")
    def test_length_range_requirements(self, mock_config):
        """Test requirements text with min and max length."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 8, "max_length": 50}}
        }
        policy = PasswordPolicy()

        result = policy.get_requirements_text()
        assert "Between 8 and 50 characters" in result

    @patch("backend.utils.password_policy.config")
    def test_high_max_length_requirements(self, mock_config):
        """Test requirements text with very high max length."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 8, "max_length": 2000}}
        }
        policy = PasswordPolicy()

        result = policy.get_requirements_text()
        assert "At least 8 characters" in result
        assert "2000" not in result

    @patch("backend.utils.password_policy.config")
    def test_all_character_requirements(self, mock_config):
        """Test requirements text with all character type requirements."""
        mock_config.get_config.return_value = {
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
        policy = PasswordPolicy()

        result = policy.get_requirements_text()
        assert "uppercase letters" in result
        assert "lowercase letters" in result
        assert "numbers" in result
        assert "special characters" in result
        assert "Must contain" in result

    @patch("backend.utils.password_policy.config")
    def test_partial_character_requirements(self, mock_config):
        """Test requirements text with minimum character types less than total."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "min_character_types": 2,
                }
            }
        }
        policy = PasswordPolicy()

        result = policy.get_requirements_text()
        assert "Must contain at least 2 of:" in result
        assert "uppercase letters" in result
        assert "lowercase letters" in result
        assert "numbers" in result

    @patch("backend.utils.password_policy.config")
    def test_username_restriction_requirements(self, mock_config):
        """Test requirements text with username restrictions."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                }
            }
        }
        policy = PasswordPolicy()

        result = policy.get_requirements_text()
        assert "Cannot contain your username or email" in result

    @patch("backend.utils.password_policy.config")
    def test_multiple_requirements_combined(self, mock_config):
        """Test requirements text with multiple requirements combined."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 10,
                    "max_length": 30,
                    "require_uppercase": True,
                    "require_numbers": True,
                    "allow_username_in_password": False,
                }
            }
        }
        policy = PasswordPolicy()

        result = policy.get_requirements_text()
        assert "Between 10 and 30 characters" in result
        assert "uppercase letters" in result
        assert "numbers" in result
        assert "Cannot contain your username" in result
        assert ";" in result  # Multiple requirements separator


class TestGetRequirementsList:
    """Test get_requirements_list method."""

    @patch("backend.utils.password_policy.config")
    def test_basic_requirements_list(self, mock_config):
        """Test requirements list with basic configuration."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 8, "max_length": None}}
        }
        policy = PasswordPolicy()

        result = policy.get_requirements_list()
        assert isinstance(result, list)
        assert len(result) >= 1
        assert "At least 8 characters long" in result

    @patch("backend.utils.password_policy.config")
    def test_length_range_requirements_list(self, mock_config):
        """Test requirements list with length range."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 8, "max_length": 25}}
        }
        policy = PasswordPolicy()

        result = policy.get_requirements_list()
        assert "Between 8-25 characters long" in result

    @patch("backend.utils.password_policy.config")
    def test_character_type_requirements_list(self, mock_config):
        """Test requirements list with all character types."""
        mock_config.get_config.return_value = {
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
        policy = PasswordPolicy()

        result = policy.get_requirements_list()

        # Check that each requirement is in the list
        uppercase_found = any("uppercase letter" in req for req in result)
        lowercase_found = any("lowercase letter" in req for req in result)
        numbers_found = any("number" in req for req in result)
        special_found = any("special character" in req for req in result)

        assert uppercase_found
        assert lowercase_found
        assert numbers_found
        assert special_found

    @patch("backend.utils.password_policy.config")
    def test_special_chars_display_truncation(self, mock_config):
        """Test that special characters display is truncated appropriately."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_special_chars": True,
                    "special_chars": "!@#$%^&*()_+-=[]{}|;':\",./<>?~`",
                }
            }
        }
        policy = PasswordPolicy()

        result = policy.get_requirements_list()
        special_req = next(req for req in result if "special character" in req)
        assert "..." in special_req  # Should be truncated

    @patch("backend.utils.password_policy.config")
    def test_username_restriction_in_list(self, mock_config):
        """Test username restriction appears in requirements list."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                }
            }
        }
        policy = PasswordPolicy()

        result = policy.get_requirements_list()
        username_req = any("Cannot contain your username" in req for req in result)
        assert username_req


class TestValidatePassword:
    """Test validate_password method."""

    @patch("backend.utils.password_policy.config")
    def test_valid_minimal_password(self, mock_config):
        """Test validation of password meeting minimal requirements."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 8, "min_character_types": 0}}
        }
        policy = PasswordPolicy()

        is_valid, errors = policy.validate_password("password123")
        assert is_valid
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config")
    def test_password_too_short(self, mock_config):
        """Test validation of password that is too short."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {"min_length": 10, "min_character_types": 0}
            }
        }
        policy = PasswordPolicy()

        is_valid, errors = policy.validate_password("short")
        assert not is_valid
        assert len(errors) == 1
        assert "at least 10 characters" in errors[0]

    @patch("backend.utils.password_policy.config")
    def test_password_too_long(self, mock_config):
        """Test validation of password that is too long."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "max_length": 15,
                    "min_character_types": 0,
                }
            }
        }
        policy = PasswordPolicy()

        long_password = "a" * 20
        is_valid, errors = policy.validate_password(long_password)
        assert not is_valid
        assert len(errors) == 1
        assert "no more than 15 characters" in errors[0]

    @patch("backend.utils.password_policy.config")
    def test_missing_uppercase_requirement(self, mock_config):
        """Test validation when uppercase letter is required but missing."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {"min_length": 8, "require_uppercase": True}
            }
        }
        policy = PasswordPolicy()

        is_valid, errors = policy.validate_password("lowercase123")
        assert not is_valid
        assert "uppercase letter" in errors[0]

    @patch("backend.utils.password_policy.config")
    def test_missing_lowercase_requirement(self, mock_config):
        """Test validation when lowercase letter is required but missing."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {"min_length": 8, "require_lowercase": True}
            }
        }
        policy = PasswordPolicy()

        is_valid, errors = policy.validate_password("UPPERCASE123")
        assert not is_valid
        assert "lowercase letter" in errors[0]

    @patch("backend.utils.password_policy.config")
    def test_missing_numbers_requirement(self, mock_config):
        """Test validation when numbers are required but missing."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 8, "require_numbers": True}}
        }
        policy = PasswordPolicy()

        is_valid, errors = policy.validate_password("PasswordOnly")
        assert not is_valid
        assert "number" in errors[0]

    @patch("backend.utils.password_policy.config")
    def test_missing_special_chars_requirement(self, mock_config):
        """Test validation when special characters are required but missing."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {"min_length": 8, "require_special_chars": True}
            }
        }
        policy = PasswordPolicy()

        is_valid, errors = policy.validate_password("Password123")
        assert not is_valid
        assert "special character" in errors[0]

    @patch("backend.utils.password_policy.config")
    def test_valid_password_all_requirements(self, mock_config):
        """Test validation of password meeting all requirements."""
        mock_config.get_config.return_value = {
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
        policy = PasswordPolicy()

        is_valid, errors = policy.validate_password("Password123!")
        assert is_valid
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config")
    def test_custom_special_chars(self, mock_config):
        """Test validation with custom special characters."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_special_chars": True,
                    "special_chars": "@#$",
                }
            }
        }
        policy = PasswordPolicy()

        # Should pass with custom special char
        is_valid, errors = policy.validate_password("Password123@")
        assert is_valid

        # Should fail with non-custom special char
        is_valid, _ = policy.validate_password("Password123!")
        assert not is_valid

    @patch("backend.utils.password_policy.config")
    def test_min_character_types_requirement(self, mock_config):
        """Test validation with minimum character types requirement."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "min_character_types": 2,
                }
            }
        }
        policy = PasswordPolicy()

        # Should pass with 2 character types (uppercase + lowercase + numbers)
        is_valid, errors = policy.validate_password("PasswordTest123")
        assert is_valid

        # Should fail with only 1 character type (only lowercase)
        is_valid, errors = policy.validate_password("passwordtest")
        assert not is_valid
        # Should have multiple errors: missing uppercase, missing numbers, and character types
        assert len(errors) >= 1
        assert any("at least 2 different character types" in error for error in errors)

    @patch("backend.utils.password_policy.config")
    def test_username_in_password_allowed(self, mock_config):
        """Test validation when username in password is allowed."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": True,
                    "min_character_types": 0,
                }
            }
        }
        policy = PasswordPolicy()

        is_valid, errors = policy.validate_password("johndoe123", "johndoe")
        assert is_valid
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config")
    def test_username_in_password_not_allowed(self, mock_config):
        """Test validation when username in password is not allowed."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                    "min_character_types": 0,
                }
            }
        }
        policy = PasswordPolicy()

        is_valid, errors = policy.validate_password("johndoe123", "johndoe")
        assert not is_valid
        assert "Password cannot contain your username or email address" in errors[0]

    @patch("backend.utils.password_policy.config")
    def test_email_in_password_not_allowed(self, mock_config):
        """Test validation when email in password is not allowed."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                    "min_character_types": 0,
                }
            }
        }
        policy = PasswordPolicy()

        is_valid, errors = policy.validate_password("johndoe123", "johndoe@example.com")
        assert not is_valid
        assert "Password cannot contain your username or email address" in errors[0]

    @patch("backend.utils.password_policy.config")
    def test_short_username_allowed_in_password(self, mock_config):
        """Test that short usernames (< 3 chars) are allowed in passwords."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                    "min_character_types": 0,
                }
            }
        }
        policy = PasswordPolicy()

        # Short username should be allowed
        is_valid, errors = policy.validate_password("jo123password", "jo")
        assert is_valid
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config")
    def test_no_username_provided(self, mock_config):
        """Test validation when no username is provided."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                    "min_character_types": 0,
                }
            }
        }
        policy = PasswordPolicy()

        is_valid, errors = policy.validate_password("password123")
        assert is_valid
        assert len(errors) == 0

    @patch("backend.utils.password_policy.config")
    def test_multiple_validation_errors(self, mock_config):
        """Test validation with multiple errors."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 10,
                    "require_uppercase": True,
                    "require_numbers": True,
                    "allow_username_in_password": False,
                }
            }
        }
        policy = PasswordPolicy()

        is_valid, errors = policy.validate_password("short", "short")
        assert not is_valid
        assert len(errors) >= 2  # Should have multiple errors

    @patch("backend.utils.password_policy.config")
    def test_case_insensitive_username_check(self, mock_config):
        """Test that username checking is case insensitive."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "allow_username_in_password": False,
                    "min_character_types": 0,
                }
            }
        }
        policy = PasswordPolicy()

        # Should fail regardless of case
        is_valid, errors = policy.validate_password("JohnDoe123", "johndoe")
        assert not is_valid
        assert "Password cannot contain your username or email address" in errors[0]


class TestGlobalPasswordPolicyInstance:
    """Test the global password_policy instance."""

    def test_global_instance_exists(self):
        """Test that global password_policy instance is available."""
        assert password_policy is not None
        assert isinstance(password_policy, PasswordPolicy)

    def test_global_instance_methods_callable(self):
        """Test that global instance methods are callable."""
        assert callable(password_policy.validate_password)
        assert callable(password_policy.get_requirements_text)
        assert callable(password_policy.get_requirements_list)


class TestPasswordPolicyEdgeCases:
    """Test edge cases and error conditions."""

    @patch("backend.utils.password_policy.config")
    def test_empty_password(self, mock_config):
        """Test validation of empty password."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 8}}
        }
        policy = PasswordPolicy()

        is_valid, errors = policy.validate_password("")
        assert not is_valid
        assert "at least 8 characters" in errors[0]

    @patch("backend.utils.password_policy.config")
    def test_none_password(self, mock_config):
        """Test validation of None password."""
        mock_config.get_config.return_value = {
            "security": {"password_policy": {"min_length": 8}}
        }
        policy = PasswordPolicy()

        # Should handle None gracefully
        with pytest.raises((TypeError, AttributeError)):
            policy.validate_password(None)

    @patch("backend.utils.password_policy.config")
    def test_no_max_length_specified(self, mock_config):
        """Test when max_length is None or not specified."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "max_length": None,
                    "min_character_types": 0,
                }
            }
        }
        policy = PasswordPolicy()

        # Very long password should be valid
        long_password = "a" * 1000
        is_valid, _ = policy.validate_password(long_password)
        assert is_valid

    @patch("backend.utils.password_policy.config")
    def test_regex_escaping_in_special_chars(self, mock_config):
        """Test that special characters are properly escaped in regex."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_special_chars": True,
                    "special_chars": "[]{}().*+?^$|",
                }
            }
        }
        policy = PasswordPolicy()

        # Should work with regex special characters
        is_valid, _ = policy.validate_password("Password123[")
        assert is_valid

    @patch("backend.utils.password_policy.config")
    def test_default_values_used(self, mock_config):
        """Test that default values are used when not specified."""
        mock_config.get_config.return_value = {"security": {"password_policy": {}}}
        policy = PasswordPolicy()

        # Should use default min_length of 8
        is_valid, errors = policy.validate_password("1234567")  # 7 chars
        assert not is_valid
        assert "at least 8 characters" in errors[0]

    @patch("backend.utils.password_policy.config")
    def test_zero_min_character_types(self, mock_config):
        """Test behavior when min_character_types is 0."""
        mock_config.get_config.return_value = {
            "security": {
                "password_policy": {
                    "min_length": 8,
                    "require_uppercase": True,
                    "min_character_types": 0,
                }
            }
        }
        policy = PasswordPolicy()

        # Should not enforce character types when min is 0
        is_valid, errors = policy.validate_password("lowercase")
        # Should still fail uppercase requirement since it's explicitly required
        assert not is_valid
