"""
Comprehensive unit tests for backend.api.scripts module.
Tests Pydantic models, validators, and API endpoint logic.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from unittest.mock import Mock, patch

from backend.api.scripts import (
    SavedScriptCreate,
    SavedScriptUpdate,
    ScriptExecutionRequest,
    SavedScriptResponse,
)


class TestSavedScriptCreateModel:
    """Test cases for SavedScriptCreate model."""

    def test_saved_script_create_valid(self):
        """Test creating a valid SavedScriptCreate model."""
        script_data = {
            "name": "Test Script",
            "description": "A test script",
            "content": "#!/bin/bash\necho 'Hello World'",
            "shell_type": "bash",
            "platform": "linux",
            "run_as_user": "root",
        }

        script = SavedScriptCreate(**script_data)

        assert script.name == "Test Script"
        assert script.description == "A test script"
        assert script.content == "#!/bin/bash\necho 'Hello World'"
        assert script.shell_type == "bash"
        assert script.platform == "linux"
        assert script.run_as_user == "root"

    def test_saved_script_create_minimal_fields(self):
        """Test creating SavedScriptCreate with minimal required fields."""
        script_data = {
            "name": "Minimal Script",
            "content": "echo 'test'",
            "shell_type": "bash",
        }

        script = SavedScriptCreate(**script_data)

        assert script.name == "Minimal Script"
        assert script.description is None
        assert script.content == "echo 'test'"
        assert script.shell_type == "bash"
        assert script.platform is None
        assert script.run_as_user is None

    def test_saved_script_create_name_validation_empty(self):
        """Test name validation fails for empty string."""
        script_data = {
            "name": "",
            "content": "echo 'test'",
            "shell_type": "bash",
        }

        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(**script_data)

        assert "Script name cannot be empty" in str(exc_info.value)

    def test_saved_script_create_name_validation_whitespace_only(self):
        """Test name validation fails for whitespace-only string."""
        script_data = {
            "name": "   ",
            "content": "echo 'test'",
            "shell_type": "bash",
        }

        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(**script_data)

        assert "Script name cannot be empty" in str(exc_info.value)

    def test_saved_script_create_name_validation_too_long(self):
        """Test name validation fails for names exceeding 255 characters."""
        script_data = {
            "name": "x" * 256,  # 256 characters
            "content": "echo 'test'",
            "shell_type": "bash",
        }

        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(**script_data)

        assert "Script name cannot exceed 255 characters" in str(exc_info.value)

    def test_saved_script_create_name_validation_trims_whitespace(self):
        """Test name validation trims whitespace."""
        script_data = {
            "name": "  Test Script  ",
            "content": "echo 'test'",
            "shell_type": "bash",
        }

        script = SavedScriptCreate(**script_data)
        assert script.name == "Test Script"

    def test_saved_script_create_shell_type_validation_valid_shells(self):
        """Test shell_type validation accepts valid shell types."""
        valid_shells = ["bash", "sh", "zsh", "powershell", "cmd", "ksh"]

        for shell in valid_shells:
            script_data = {
                "name": f"Test {shell}",
                "content": "echo 'test'",
                "shell_type": shell,
            }

            script = SavedScriptCreate(**script_data)
            assert script.shell_type == shell

    def test_saved_script_create_shell_type_validation_invalid_shell(self):
        """Test shell_type validation fails for invalid shell types."""
        script_data = {
            "name": "Test Script",
            "content": "echo 'test'",
            "shell_type": "invalid_shell",
        }

        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(**script_data)

        assert "Unsupported shell type: invalid_shell" in str(exc_info.value)

    def test_saved_script_create_content_validation_empty(self):
        """Test content validation fails for empty content."""
        script_data = {
            "name": "Test Script",
            "content": "",
            "shell_type": "bash",
        }

        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(**script_data)

        assert "Script content cannot be empty" in str(exc_info.value)

    def test_saved_script_create_content_validation_whitespace_only(self):
        """Test content validation fails for whitespace-only content."""
        script_data = {
            "name": "Test Script",
            "content": "   \n\t  ",
            "shell_type": "bash",
        }

        with pytest.raises(ValidationError) as exc_info:
            SavedScriptCreate(**script_data)

        assert "Script content cannot be empty" in str(exc_info.value)

    def test_saved_script_create_missing_required_fields(self):
        """Test validation fails when required fields are missing."""
        # Missing name
        with pytest.raises(ValidationError):
            SavedScriptCreate(content="echo 'test'", shell_type="bash")

        # Missing content
        with pytest.raises(ValidationError):
            SavedScriptCreate(name="Test", shell_type="bash")

        # Missing shell_type
        with pytest.raises(ValidationError):
            SavedScriptCreate(name="Test", content="echo 'test'")


class TestSavedScriptUpdateModel:
    """Test cases for SavedScriptUpdate model."""

    def test_saved_script_update_all_fields(self):
        """Test SavedScriptUpdate with all fields."""
        update_data = {
            "name": "Updated Script",
            "description": "Updated description",
            "content": "#!/bin/bash\necho 'Updated'",
            "shell_type": "zsh",
            "platform": "darwin",
            "run_as_user": "admin",
            "is_active": False,
        }

        update = SavedScriptUpdate(**update_data)

        assert update.name == "Updated Script"
        assert update.description == "Updated description"
        assert update.content == "#!/bin/bash\necho 'Updated'"
        assert update.shell_type == "zsh"
        assert update.platform == "darwin"
        assert update.run_as_user == "admin"
        assert update.is_active is False

    def test_saved_script_update_partial_fields(self):
        """Test SavedScriptUpdate with only some fields."""
        update_data = {
            "name": "Partially Updated Script",
            "is_active": True,
        }

        update = SavedScriptUpdate(**update_data)

        assert update.name == "Partially Updated Script"
        assert update.description is None
        assert update.content is None
        assert update.shell_type is None
        assert update.platform is None
        assert update.run_as_user is None
        assert update.is_active is True

    def test_saved_script_update_empty_object(self):
        """Test SavedScriptUpdate with no fields."""
        update = SavedScriptUpdate()

        assert update.name is None
        assert update.description is None
        assert update.content is None
        assert update.shell_type is None
        assert update.platform is None
        assert update.run_as_user is None
        assert update.is_active is None

    def test_saved_script_update_name_validation_empty(self):
        """Test name validation fails for empty string in update."""
        update_data = {"name": ""}

        with pytest.raises(ValidationError) as exc_info:
            SavedScriptUpdate(**update_data)

        assert "Script name cannot be empty" in str(exc_info.value)

    def test_saved_script_update_name_validation_whitespace_only(self):
        """Test name validation fails for whitespace-only string in update."""
        update_data = {"name": "   "}

        with pytest.raises(ValidationError) as exc_info:
            SavedScriptUpdate(**update_data)

        assert "Script name cannot be empty" in str(exc_info.value)

    def test_saved_script_update_name_validation_too_long(self):
        """Test name validation fails for names exceeding 255 characters in update."""
        update_data = {"name": "x" * 256}

        with pytest.raises(ValidationError) as exc_info:
            SavedScriptUpdate(**update_data)

        assert "Script name cannot exceed 255 characters" in str(exc_info.value)

    def test_saved_script_update_name_validation_trims_whitespace(self):
        """Test name validation trims whitespace in update."""
        update_data = {"name": "  Updated Script  "}

        update = SavedScriptUpdate(**update_data)
        assert update.name == "Updated Script"

    def test_saved_script_update_name_validation_none_allowed(self):
        """Test name validation allows None values in update."""
        update_data = {"name": None}

        update = SavedScriptUpdate(**update_data)
        assert update.name is None

    def test_saved_script_update_shell_type_validation_valid_shells(self):
        """Test shell_type validation accepts valid shell types in update."""
        valid_shells = ["bash", "sh", "zsh", "powershell", "cmd", "ksh"]

        for shell in valid_shells:
            update_data = {"shell_type": shell}
            update = SavedScriptUpdate(**update_data)
            assert update.shell_type == shell

    def test_saved_script_update_shell_type_validation_invalid_shell(self):
        """Test shell_type validation fails for invalid shell types in update."""
        update_data = {"shell_type": "invalid_shell"}

        with pytest.raises(ValidationError) as exc_info:
            SavedScriptUpdate(**update_data)

        assert "Unsupported shell type: invalid_shell" in str(exc_info.value)

    def test_saved_script_update_shell_type_validation_none_allowed(self):
        """Test shell_type validation allows None values in update."""
        update_data = {"shell_type": None}

        update = SavedScriptUpdate(**update_data)
        assert update.shell_type is None

    def test_saved_script_update_content_validation_empty(self):
        """Test content validation fails for empty content in update."""
        update_data = {"content": ""}

        with pytest.raises(ValidationError) as exc_info:
            SavedScriptUpdate(**update_data)

        assert "Script content cannot be empty" in str(exc_info.value)

    def test_saved_script_update_content_validation_whitespace_only(self):
        """Test content validation fails for whitespace-only content in update."""
        update_data = {"content": "   \n\t  "}

        with pytest.raises(ValidationError) as exc_info:
            SavedScriptUpdate(**update_data)

        assert "Script content cannot be empty" in str(exc_info.value)

    def test_saved_script_update_content_validation_none_allowed(self):
        """Test content validation allows None values in update."""
        update_data = {"content": None}

        update = SavedScriptUpdate(**update_data)
        assert update.content is None


class TestScriptExecutionRequestModel:
    """Test cases for ScriptExecutionRequest model."""

    def test_script_execution_request_with_saved_script(self):
        """Test ScriptExecutionRequest using a saved script."""
        request_data = {
            "host_id": 1,
            "saved_script_id": "550e8400-e29b-41d4-a716-446655440010",
        }

        request = ScriptExecutionRequest(**request_data)

        assert request.host_id == "1"
        assert request.saved_script_id == "550e8400-e29b-41d4-a716-446655440010"
        assert request.script_name is None
        assert request.script_content is None
        assert request.shell_type is None
        assert request.run_as_user is None

    def test_script_execution_request_with_adhoc_script(self):
        """Test ScriptExecutionRequest with ad-hoc script."""
        request_data = {
            "host_id": 1,
            "script_name": "Ad-hoc Test",
            "script_content": "echo 'Hello World'",
            "shell_type": "bash",
            "run_as_user": "testuser",
        }

        request = ScriptExecutionRequest(**request_data)

        assert request.host_id == "1"
        assert request.saved_script_id is None
        assert request.script_name == "Ad-hoc Test"
        assert request.script_content == "echo 'Hello World'"
        assert request.shell_type == "bash"
        assert request.run_as_user == "testuser"

    def test_script_execution_request_validation_missing_content_and_saved_id(self):
        """Test that ScriptExecutionRequest allows missing script_content when no saved_script_id."""
        # This should actually succeed because the validator only runs when script_content is provided
        request_data = {
            "host_id": 1,
            "script_name": "Test Script",
            "shell_type": "bash",
        }

        # This should succeed, validation happens when script_content is explicitly provided
        request = ScriptExecutionRequest(**request_data)
        assert request.script_content is None
        assert request.saved_script_id is None

    def test_script_execution_request_validation_empty_content_no_saved_id(self):
        """Test validation fails when script_content is empty and no saved_script_id."""
        request_data = {
            "host_id": 1,
            "script_name": "Test Script",
            "script_content": "",
            "shell_type": "bash",
        }

        with pytest.raises(ValidationError) as exc_info:
            ScriptExecutionRequest(**request_data)

        assert "Either saved_script_id or script_content must be provided" in str(
            exc_info.value
        )

    def test_script_execution_request_validation_whitespace_only_content_no_saved_id(
        self,
    ):
        """Test validation fails when script_content is whitespace-only and no saved_script_id."""
        request_data = {
            "host_id": 1,
            "script_name": "Test Script",
            "script_content": "   \n\t  ",
            "shell_type": "bash",
        }

        with pytest.raises(ValidationError) as exc_info:
            ScriptExecutionRequest(**request_data)

        assert "Either saved_script_id or script_content must be provided" in str(
            exc_info.value
        )

    def test_script_execution_request_validation_shell_type_required_for_adhoc(self):
        """Test shell_type validation when explicitly provided as None for ad-hoc scripts."""
        request_data = {
            "host_id": 1,
            "script_name": "Test Script",
            "script_content": "echo 'test'",
            "shell_type": None,  # Explicitly set to None to trigger validator
        }

        with pytest.raises(ValidationError) as exc_info:
            ScriptExecutionRequest(**request_data)

        assert "shell_type is required for ad-hoc scripts" in str(exc_info.value)

    def test_script_execution_request_validation_shell_type_valid_shells(self):
        """Test shell_type validation accepts valid shell types for ad-hoc scripts."""
        valid_shells = ["bash", "sh", "zsh", "powershell", "cmd", "ksh"]

        for shell in valid_shells:
            request_data = {
                "host_id": 1,
                "script_content": "echo 'test'",
                "shell_type": shell,
            }

            request = ScriptExecutionRequest(**request_data)
            assert request.shell_type == shell

    def test_script_execution_request_validation_shell_type_invalid_shell(self):
        """Test shell_type validation fails for invalid shell types."""
        request_data = {
            "host_id": 1,
            "script_content": "echo 'test'",
            "shell_type": "invalid_shell",
        }

        with pytest.raises(ValidationError) as exc_info:
            ScriptExecutionRequest(**request_data)

        assert "Unsupported shell type: invalid_shell" in str(exc_info.value)

    def test_script_execution_request_validation_saved_script_no_shell_type_required(
        self,
    ):
        """Test shell_type not required when using saved_script_id."""
        request_data = {
            "host_id": 1,
            "saved_script_id": "550e8400-e29b-41d4-a716-446655440010",
            # No shell_type provided
        }

        request = ScriptExecutionRequest(**request_data)
        assert request.host_id == "1"
        assert request.saved_script_id == "550e8400-e29b-41d4-a716-446655440010"
        assert request.shell_type is None

    def test_script_execution_request_missing_host_id(self):
        """Test validation fails when host_id is missing."""
        request_data = {
            "saved_script_id": "550e8400-e29b-41d4-a716-446655440010",
        }

        with pytest.raises(ValidationError):
            ScriptExecutionRequest(**request_data)


class TestSavedScriptResponseModel:
    """Test cases for SavedScriptResponse model."""

    def test_saved_script_response_creation(self):
        """Test creating SavedScriptResponse model."""
        now = datetime.now(timezone.utc)

        response_data = {
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "name": "Test Script",
            "description": "A test script",
            "content": "#!/bin/bash\necho 'Hello World'",
            "shell_type": "bash",
            "platform": "linux",
            "run_as_user": "root",
            "is_active": True,
            "created_by": "testuser",
            "created_at": now,
            "updated_at": now,
        }

        response = SavedScriptResponse(**response_data)

        assert response.id == "550e8400-e29b-41d4-a716-446655440001"
        assert response.name == "Test Script"
        assert response.description == "A test script"
        assert response.content == "#!/bin/bash\necho 'Hello World'"
        assert response.shell_type == "bash"
        assert response.platform == "linux"
        assert response.run_as_user == "root"
        assert response.is_active is True
        assert response.created_by == "testuser"
        assert response.created_at == now
        assert response.updated_at == now

    def test_saved_script_response_minimal_fields(self):
        """Test creating SavedScriptResponse with minimal fields."""
        now = datetime.now(timezone.utc)

        response_data = {
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "name": "Test Script",
            "description": None,
            "content": "echo 'test'",
            "shell_type": "bash",
            "platform": None,
            "run_as_user": None,
            "is_active": True,
            "created_by": "testuser",
            "created_at": now,
            "updated_at": now,
        }

        response = SavedScriptResponse(**response_data)

        assert response.id == "550e8400-e29b-41d4-a716-446655440001"
        assert response.name == "Test Script"
        assert response.description is None
        assert response.content == "echo 'test'"
        assert response.shell_type == "bash"
        assert response.platform is None
        assert response.run_as_user is None
        assert response.is_active is True
        assert response.created_by == "testuser"
        assert response.created_at == now
        assert response.updated_at == now

    def test_saved_script_response_missing_required_fields(self):
        """Test SavedScriptResponse validation fails for missing required fields."""
        now = datetime.now(timezone.utc)

        # Missing required fields should cause validation errors
        incomplete_data_sets = [
            # Missing id
            {
                "name": "Test Script",
                "content": "echo 'test'",
                "shell_type": "bash",
                "is_active": True,
                "created_by": "testuser",
                "created_at": now,
                "updated_at": now,
            },
            # Missing name
            {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "content": "echo 'test'",
                "shell_type": "bash",
                "is_active": True,
                "created_by": "testuser",
                "created_at": now,
                "updated_at": now,
            },
            # Missing content
            {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "name": "Test Script",
                "shell_type": "bash",
                "is_active": True,
                "created_by": "testuser",
                "created_at": now,
                "updated_at": now,
            },
        ]

        for incomplete_data in incomplete_data_sets:
            with pytest.raises(ValidationError):
                SavedScriptResponse(**incomplete_data)


class TestModelEdgeCases:
    """Test edge cases and error conditions for all models."""

    def test_saved_script_create_with_unicode_content(self):
        """Test SavedScriptCreate handles Unicode content correctly."""
        script_data = {
            "name": "Unicode Script",
            "content": "#!/bin/bash\necho '你好世界' # Hello World in Chinese",
            "shell_type": "bash",
        }

        script = SavedScriptCreate(**script_data)
        assert "你好世界" in script.content

    def test_saved_script_create_with_multiline_content(self):
        """Test SavedScriptCreate handles multiline content correctly."""
        multiline_content = """#!/bin/bash
# This is a test script
echo "Line 1"
echo "Line 2"
if [ "$1" = "test" ]; then
    echo "Test mode"
fi
"""
        script_data = {
            "name": "Multiline Script",
            "content": multiline_content,
            "shell_type": "bash",
        }

        script = SavedScriptCreate(**script_data)
        assert script.content == multiline_content

    def test_saved_script_update_with_boolean_field_false(self):
        """Test SavedScriptUpdate correctly handles False boolean values."""
        update_data = {"is_active": False}

        update = SavedScriptUpdate(**update_data)
        assert update.is_active is False

    def test_script_execution_request_with_integer_host_id(self):
        """Test ScriptExecutionRequest handles different integer types for host_id."""
        request_data = {
            "host_id": 12345,
            "saved_script_id": "550e8400-e29b-41d4-a716-446655467890",
        }

        request = ScriptExecutionRequest(**request_data)
        assert request.host_id == "12345"
        assert request.saved_script_id == "550e8400-e29b-41d4-a716-446655467890"

    def test_all_models_field_type_validation(self):
        """Test all models validate field types correctly."""
        # Test with wrong type for saved_script_id in ScriptExecutionRequest
        with pytest.raises(ValidationError):
            ScriptExecutionRequest(host_id=1, saved_script_id=123)

        # Test with wrong type for is_active in SavedScriptUpdate
        with pytest.raises(ValidationError):
            SavedScriptUpdate(is_active="not_a_boolean")

        # Test with wrong type for id in SavedScriptResponse
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError):
            SavedScriptResponse(
                id="not_an_integer",
                name="Test",
                content="test",
                shell_type="bash",
                is_active=True,
                created_by="user",
                created_at=now,
                updated_at=now,
            )


class TestValidatorFunctions:
    """Test individual validator functions in isolation."""

    def test_name_validator_edge_cases(self):
        """Test name validator with various edge cases."""
        # Test maximum allowed length (255 characters)
        max_length_name = "x" * 255
        script_data = {
            "name": max_length_name,
            "content": "echo 'test'",
            "shell_type": "bash",
        }
        script = SavedScriptCreate(**script_data)
        assert script.name == max_length_name

        # Test whitespace trimming with various whitespace types
        whitespace_cases = [
            "  Normal Name  ",
            "\t\tTab Name\t\t",
            "\n\nNewline Name\n\n",
            " \t\n Mixed Whitespace \n\t ",
        ]

        for name_with_whitespace in whitespace_cases:
            script_data = {
                "name": name_with_whitespace,
                "content": "echo 'test'",
                "shell_type": "bash",
            }
            script = SavedScriptCreate(**script_data)
            assert script.name.strip() == script.name

    def test_shell_type_validator_case_sensitivity(self):
        """Test shell_type validator case sensitivity."""
        # Should fail for different cases
        invalid_shells = ["BASH", "Bash", "PowerShell", "CMD"]

        for invalid_shell in invalid_shells:
            script_data = {
                "name": "Test Script",
                "content": "echo 'test'",
                "shell_type": invalid_shell,
            }

            with pytest.raises(ValidationError):
                SavedScriptCreate(**script_data)

    def test_content_validator_with_special_characters(self):
        """Test content validator with special characters and encoding."""
        special_contents = [
            "#!/bin/bash\necho 'Special chars: !@#$%^&*()_+-=[]{}|;:,.<>?'",
            "powershell.exe -Command \"Write-Host 'Windows script'\"",
            "echo 'Script with quotes: \"Hello\" and \\'World\\''",
            "#!/bin/bash\n# Script with backslashes: \\\\ and \\n",
        ]

        for content in special_contents:
            script_data = {
                "name": "Special Content Script",
                "content": content,
                "shell_type": "bash",
            }

            script = SavedScriptCreate(**script_data)
            assert script.content == content
