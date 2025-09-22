"""
Comprehensive tests for Pydantic validators in backend/api/scripts.py module.
Tests script creation and update model validation.
"""

import pytest
from pydantic import ValidationError

from backend.api.scripts import (
    SavedScriptCreate,
    SavedScriptUpdate,
    ScriptExecutionRequest,
)


class TestSavedScriptCreate:
    """Test SavedScriptCreate model validation."""

    def test_valid_script_minimal(self):
        """Test creating script with minimal valid data."""
        data = {
            "name": "test_script",
            "content": "echo 'Hello World'",
            "shell_type": "bash",
        }
        script = SavedScriptCreate(**data)

        assert script.name == "test_script"
        assert script.content == "echo 'Hello World'"
        assert script.shell_type == "bash"
        assert script.description is None
        assert script.platform is None
        assert script.run_as_user is None

    def test_valid_script_complete(self):
        """Test creating script with all fields."""
        data = {
            "name": "deployment_script",
            "description": "Deploy application to production",
            "content": "#!/bin/bash\necho 'Deploying...'",
            "shell_type": "bash",
            "platform": "linux",
            "run_as_user": "deploy",
        }
        script = SavedScriptCreate(**data)

        assert script.name == "deployment_script"
        assert script.description == "Deploy application to production"
        assert script.content == "#!/bin/bash\necho 'Deploying...'"
        assert script.shell_type == "bash"
        assert script.platform == "linux"
        assert script.run_as_user == "deploy"

    def test_name_validation_empty_string(self):
        """Test name validation with empty string."""
        data = {"name": "", "content": "echo 'test'", "shell_type": "bash"}
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(**data)

        assert "Script name cannot be empty" in str(exc_info.value)

    def test_name_validation_whitespace_only(self):
        """Test name validation with whitespace-only string."""
        data = {"name": "   ", "content": "echo 'test'", "shell_type": "bash"}
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(**data)

        assert "Script name cannot be empty" in str(exc_info.value)

    def test_name_validation_too_long(self):
        """Test name validation with too long string."""
        long_name = "a" * 256  # Exceeds 255 character limit
        data = {"name": long_name, "content": "echo 'test'", "shell_type": "bash"}
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(**data)

        assert "Script name cannot exceed 255 characters" in str(exc_info.value)

    def test_name_validation_strips_whitespace(self):
        """Test that name validation strips whitespace."""
        data = {
            "name": "  test_script  ",
            "content": "echo 'test'",
            "shell_type": "bash",
        }
        script = SavedScriptCreate(**data)

        assert script.name == "test_script"

    def test_name_validation_max_length_boundary(self):
        """Test name validation at exactly 255 characters."""
        exact_length_name = "a" * 255
        data = {
            "name": exact_length_name,
            "content": "echo 'test'",
            "shell_type": "bash",
        }
        script = SavedScriptCreate(**data)

        assert script.name == exact_length_name
        assert len(script.name) == 255

    def test_shell_type_validation_valid_shells(self):
        """Test shell type validation with all valid shells."""
        valid_shells = ["bash", "sh", "zsh", "powershell", "cmd", "ksh"]

        for shell in valid_shells:
            data = {
                "name": f"test_{shell}",
                "content": "echo 'test'",
                "shell_type": shell,
            }
            script = SavedScriptCreate(**data)
            assert script.shell_type == shell

    def test_shell_type_validation_invalid_shell(self):
        """Test shell type validation with invalid shell."""
        data = {
            "name": "test_script",
            "content": "echo 'test'",
            "shell_type": "invalid_shell",
        }
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(**data)

        assert "Unsupported shell type: invalid_shell" in str(exc_info.value)

    def test_shell_type_validation_case_sensitive(self):
        """Test that shell type validation is case sensitive."""
        data = {
            "name": "test_script",
            "content": "echo 'test'",
            "shell_type": "BASH",  # Should be lowercase
        }
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(**data)

        assert "Unsupported shell type: BASH" in str(exc_info.value)

    def test_content_validation_empty_string(self):
        """Test content validation with empty string."""
        data = {"name": "test_script", "content": "", "shell_type": "bash"}
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(**data)

        assert "Script content cannot be empty" in str(exc_info.value)

    def test_content_validation_whitespace_only(self):
        """Test content validation with whitespace-only string."""
        data = {"name": "test_script", "content": "   \n\t  ", "shell_type": "bash"}
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(**data)

        assert "Script content cannot be empty" in str(exc_info.value)

    def test_content_validation_valid_content(self):
        """Test content validation with valid content."""
        data = {
            "name": "test_script",
            "content": "#!/bin/bash\necho 'Hello'\n# Comment\nls -la",
            "shell_type": "bash",
        }
        script = SavedScriptCreate(**data)

        assert script.content == "#!/bin/bash\necho 'Hello'\n# Comment\nls -la"

    def test_missing_required_fields(self):
        """Test validation with missing required fields."""
        # Missing name
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(content="echo 'test'", shell_type="bash")
        assert "name" in str(exc_info.value)

        # Missing content
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(name="test", shell_type="bash")
        assert "content" in str(exc_info.value)

        # Missing shell_type
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(name="test", content="echo 'test'")
        assert "shell_type" in str(exc_info.value)

    def test_optional_fields_default_none(self):
        """Test that optional fields default to None."""
        data = {"name": "test_script", "content": "echo 'test'", "shell_type": "bash"}
        script = SavedScriptCreate(**data)

        assert script.description is None
        assert script.platform is None
        assert script.run_as_user is None

    def test_special_characters_in_fields(self):
        """Test validation with special characters in various fields."""
        data = {
            "name": "test_script-2024_v1.0",
            "description": "Script with special chars: !@#$%^&*()",
            "content": "echo 'Test with special chars: !@#$%^&*()'",
            "shell_type": "bash",
            "platform": "linux-x86_64",
            "run_as_user": "service-account",
        }
        script = SavedScriptCreate(**data)

        assert script.name == "test_script-2024_v1.0"
        assert script.description == "Script with special chars: !@#$%^&*()"
        assert "special chars: !@#$%^&*()" in script.content
        assert script.platform == "linux-x86_64"
        assert script.run_as_user == "service-account"


class TestSavedScriptUpdate:
    """Test SavedScriptUpdate model validation."""

    def test_all_fields_none(self):
        """Test creating update model with all fields None."""
        script_update = SavedScriptUpdate()

        assert script_update.name is None
        assert script_update.description is None
        assert script_update.content is None
        assert script_update.shell_type is None
        assert script_update.platform is None
        assert script_update.run_as_user is None
        assert script_update.is_active is None

    def test_partial_update_name_only(self):
        """Test updating only the name field."""
        data = {"name": "updated_script_name"}
        script_update = SavedScriptUpdate(**data)

        assert script_update.name == "updated_script_name"
        assert script_update.content is None
        assert script_update.shell_type is None

    def test_partial_update_multiple_fields(self):
        """Test updating multiple fields."""
        data = {"name": "updated_script", "shell_type": "zsh", "is_active": False}
        script_update = SavedScriptUpdate(**data)

        assert script_update.name == "updated_script"
        assert script_update.shell_type == "zsh"
        assert script_update.is_active is False
        assert script_update.content is None

    def test_name_validation_none_allowed(self):
        """Test that None is allowed for name in update model."""
        data = {"name": None, "shell_type": "bash"}
        script_update = SavedScriptUpdate(**data)

        assert script_update.name is None
        assert script_update.shell_type == "bash"

    def test_name_validation_empty_string_rejected(self):
        """Test that empty string is rejected for name in update model."""
        data = {"name": ""}
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptUpdate(**data)

        assert "Script name cannot be empty" in str(exc_info.value)

    def test_name_validation_whitespace_only_rejected(self):
        """Test that whitespace-only string is rejected for name."""
        data = {"name": "   "}
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptUpdate(**data)

        assert "Script name cannot be empty" in str(exc_info.value)

    def test_name_validation_too_long_rejected(self):
        """Test that too long name is rejected in update model."""
        long_name = "a" * 256
        data = {"name": long_name}
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptUpdate(**data)

        assert "Script name cannot exceed 255 characters" in str(exc_info.value)

    def test_name_validation_strips_whitespace(self):
        """Test that name validation strips whitespace in update model."""
        data = {"name": "  updated_name  "}
        script_update = SavedScriptUpdate(**data)

        assert script_update.name == "updated_name"

    def test_name_validation_pre_true_behavior(self):
        """Test that pre=True works correctly for name validation."""
        # Test with various whitespace scenarios
        test_cases = [
            ("  valid_name  ", "valid_name"),
            ("\tname_with_tabs\t", "name_with_tabs"),
            ("\nname_with_newlines\n", "name_with_newlines"),
        ]

        for input_name, expected_name in test_cases:
            data = {"name": input_name}
            script_update = SavedScriptUpdate(**data)
            assert script_update.name == expected_name

    def test_shell_type_validation_none_allowed(self):
        """Test that None is allowed for shell_type in update model."""
        data = {"shell_type": None}
        script_update = SavedScriptUpdate(**data)

        assert script_update.shell_type is None

    def test_shell_type_validation_valid_shells(self):
        """Test shell type validation with valid shells in update model."""
        valid_shells = ["bash", "sh", "zsh", "powershell", "cmd", "ksh"]

        for shell in valid_shells:
            data = {"shell_type": shell}
            script_update = SavedScriptUpdate(**data)
            assert script_update.shell_type == shell

    def test_shell_type_validation_invalid_shell_rejected(self):
        """Test that invalid shell type is rejected in update model."""
        data = {"shell_type": "fish"}  # Not in allowed list
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptUpdate(**data)

        assert "Unsupported shell type: fish" in str(exc_info.value)

    def test_content_validation_none_allowed(self):
        """Test that None is allowed for content in update model."""
        data = {"content": None}
        script_update = SavedScriptUpdate(**data)

        assert script_update.content is None

    def test_content_validation_empty_string_rejected(self):
        """Test that empty string is rejected for content in update model."""
        data = {"content": ""}
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptUpdate(**data)

        assert "Script content cannot be empty" in str(exc_info.value)

    def test_content_validation_whitespace_only_rejected(self):
        """Test that whitespace-only content is rejected in update model."""
        data = {"content": "   \n\t  "}
        with pytest.raises(ValidationError) as exc_info:
            SavedScriptUpdate(**data)

        assert "Script content cannot be empty" in str(exc_info.value)

    def test_content_validation_valid_content(self):
        """Test that valid content is accepted in update model."""
        data = {"content": "echo 'Updated script content'"}
        script_update = SavedScriptUpdate(**data)

        assert script_update.content == "echo 'Updated script content'"

    def test_content_validation_pre_true_behavior(self):
        """Test that pre=True works correctly for content validation."""
        # Should validate before any automatic processing
        data = {"content": "#!/bin/bash\necho 'test'"}
        script_update = SavedScriptUpdate(**data)

        assert script_update.content == "#!/bin/bash\necho 'test'"

    def test_is_active_boolean_validation(self):
        """Test is_active field with boolean values."""
        # Test True
        data = {"is_active": True}
        script_update = SavedScriptUpdate(**data)
        assert script_update.is_active is True

        # Test False
        data = {"is_active": False}
        script_update = SavedScriptUpdate(**data)
        assert script_update.is_active is False

        # Test None
        data = {"is_active": None}
        script_update = SavedScriptUpdate(**data)
        assert script_update.is_active is None

    def test_complex_update_scenario(self):
        """Test a complex update scenario with multiple field changes."""
        data = {
            "name": "  updated_complex_script  ",
            "description": "Updated description with special chars: éñ中文",
            "content": "#!/bin/zsh\necho 'Updated content'\ndate",
            "shell_type": "zsh",
            "platform": "macos",
            "run_as_user": "admin",
            "is_active": True,
        }
        script_update = SavedScriptUpdate(**data)

        assert script_update.name == "updated_complex_script"  # Stripped
        assert (
            script_update.description
            == "Updated description with special chars: éñ中文"
        )
        assert script_update.content == "#!/bin/zsh\necho 'Updated content'\ndate"
        assert script_update.shell_type == "zsh"
        assert script_update.platform == "macos"
        assert script_update.run_as_user == "admin"
        assert script_update.is_active is True


class TestScriptExecutionRequest:
    """Test ScriptExecutionRequest model validation."""

    def test_valid_execution_request(self):
        """Test creating valid script execution request."""
        data = {"host_id": 1}
        request = ScriptExecutionRequest(**data)

        assert request.host_id == "1"

    def test_host_id_positive_integer(self):
        """Test host_id with positive integer values."""
        test_values = [1, 100, 999999]

        for host_id in test_values:
            data = {"host_id": host_id}
            request = ScriptExecutionRequest(**data)
            assert request.host_id == str(host_id)

    def test_host_id_zero(self):
        """Test host_id with zero value."""
        data = {"host_id": 0}
        request = ScriptExecutionRequest(**data)

        assert request.host_id == "0"

    def test_host_id_negative_integer(self):
        """Test host_id with negative integer."""
        data = {"host_id": -1}
        request = ScriptExecutionRequest(**data)

        assert request.host_id == "-1"

    def test_missing_host_id(self):
        """Test validation when host_id is missing."""
        with pytest.raises(ValidationError) as exc_info:
            ScriptExecutionRequest()

        assert "host_id" in str(exc_info.value)

    def test_host_id_string_number_conversion(self):
        """Test that string numbers are accepted as strings."""
        data = {"host_id": "123"}
        request = ScriptExecutionRequest(**data)

        assert request.host_id == "123"
        assert isinstance(request.host_id, str)

    def test_host_id_invalid_string(self):
        """Test that any string is accepted as host_id (for UUID compatibility)."""
        data = {"host_id": "not_a_number"}
        request = ScriptExecutionRequest(**data)

        # Any string should be valid for host_id to support UUIDs
        assert request.host_id == "not_a_number"
        assert isinstance(request.host_id, str)

    def test_host_id_string_conversion(self):
        """Test that host_id accepts string values (UUID format)."""
        data = {"host_id": "550e8400-e29b-41d4-a716-446655440000"}
        request = ScriptExecutionRequest(**data)

        assert request.host_id == "550e8400-e29b-41d4-a716-446655440000"
        assert isinstance(request.host_id, str)

    def test_host_id_float_with_decimal(self):
        """Test that float with decimal part raises validation error."""
        data = {"host_id": 123.45}
        with pytest.raises(ValidationError) as exc_info:
            ScriptExecutionRequest(**data)

        # Pydantic should reject non-integer floats for int fields
        assert (
            "int" in str(exc_info.value).lower()
            or "type" in str(exc_info.value).lower()
        )


class TestPydanticValidatorsIntegration:
    """Integration tests for Pydantic validators."""

    def test_create_to_update_field_consistency(self):
        """Test that create and update models handle fields consistently."""
        # Create a script first
        create_data = {
            "name": "integration_test",
            "content": "echo 'test'",
            "shell_type": "bash",
            "description": "Test description",
        }
        created_script = SavedScriptCreate(**create_data)

        # Now test updating each field
        update_data = {
            "name": "updated_integration_test",
            "content": "echo 'updated'",
            "shell_type": "zsh",
            "description": "Updated description",
        }
        updated_script = SavedScriptUpdate(**update_data)

        # Fields should be processable the same way
        assert created_script.name == "integration_test"
        assert updated_script.name == "updated_integration_test"
        assert created_script.shell_type == "bash"
        assert updated_script.shell_type == "zsh"

    def test_error_message_consistency(self):
        """Test that error messages are consistent across models."""
        # Test same validation errors in both models
        create_error_cases = [
            (
                {"name": "", "content": "test", "shell_type": "bash"},
                "Script name cannot be empty",
            ),
            (
                {"name": "test", "content": "", "shell_type": "bash"},
                "Script content cannot be empty",
            ),
            (
                {"name": "test", "content": "test", "shell_type": "invalid"},
                "Unsupported shell type",
            ),
        ]

        update_error_cases = [
            ({"name": ""}, "Script name cannot be empty"),
            ({"content": ""}, "Script content cannot be empty"),
            ({"shell_type": "invalid"}, "Unsupported shell type"),
        ]

        for create_data, expected_error in create_error_cases:
            with pytest.raises(ValidationError) as exc_info:
                SavedScriptCreate(**create_data)
            assert expected_error in str(exc_info.value)

        for update_data, expected_error in update_error_cases:
            with pytest.raises(ValidationError) as exc_info:
                SavedScriptUpdate(**update_data)
            assert expected_error in str(exc_info.value)

    def test_unicode_and_special_character_handling(self):
        """Test that models handle Unicode and special characters properly."""
        unicode_data = {
            "name": "script_测试_🚀",
            "description": "Description with éñ中文 and emojis 🎉🔧",
            "content": "echo '测试 content with special chars: éñ中文 🚀'",
            "shell_type": "bash",
            "platform": "linux-测试",
            "run_as_user": "user_éñ",
        }

        # Should work in create model
        created_script = SavedScriptCreate(**unicode_data)
        assert "测试" in created_script.name
        assert "🚀" in created_script.content

        # Should work in update model
        updated_script = SavedScriptUpdate(name="updated_测试_🎯")
        assert "测试" in updated_script.name

    def test_boundary_value_testing(self):
        """Test boundary values for length validations."""
        # Test exactly at the boundary
        boundary_name = "a" * 255

        # Should work for create
        create_data = {
            "name": boundary_name,
            "content": "echo 'test'",
            "shell_type": "bash",
        }
        created_script = SavedScriptCreate(**create_data)
        assert len(created_script.name) == 255

        # Should work for update
        update_data = {"name": boundary_name}
        updated_script = SavedScriptUpdate(**update_data)
        assert len(updated_script.name) == 255

        # Should fail at boundary + 1
        too_long_name = "a" * 256

        with pytest.raises(ValidationError):
            SavedScriptCreate(name=too_long_name, content="test", shell_type="bash")

        with pytest.raises(ValidationError):
            SavedScriptUpdate(name=too_long_name)

    def test_validator_execution_order(self):
        """Test that validators execute in the expected order."""
        # Test that pre=True validators run before others
        # This is more of a behavioral test to ensure pre-processing works

        data = {"name": "  test_name  "}  # Should be stripped by pre=True validator
        updated_script = SavedScriptUpdate(**data)

        # If pre=True works correctly, whitespace should be stripped
        assert updated_script.name == "test_name"
        assert updated_script.name != "  test_name  "

    def test_cross_field_validation_scenarios(self):
        """Test scenarios that might involve multiple field validations."""
        # Test that you can have valid combinations
        valid_combinations = [
            {"shell_type": "bash", "platform": "linux"},
            {"shell_type": "powershell", "platform": "windows"},
            {"shell_type": "zsh", "platform": "macos"},
        ]

        for combo in valid_combinations:
            create_data = {
                "name": f"test_{combo['shell_type']}",
                "content": "echo 'test'",
                **combo,
            }
            script = SavedScriptCreate(**create_data)
            assert script.shell_type == combo["shell_type"]
            assert script.platform == combo["platform"]
