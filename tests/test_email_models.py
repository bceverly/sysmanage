"""
Comprehensive tests for Pydantic models in backend/api/email.py module.
Tests email request/response models and validation.
"""

import pytest
from pydantic import ValidationError

from backend.api.email import EmailConfigResponse, EmailTestRequest, EmailTestResponse


class TestEmailTestRequest:
    """Test EmailTestRequest model validation."""

    def test_valid_email_address(self):
        """Test EmailTestRequest with valid email address."""
        request = EmailTestRequest(to_address="test@example.com")
        assert request.to_address == "test@example.com"

    def test_valid_email_with_name(self):
        """Test EmailTestRequest with email containing name part."""
        request = EmailTestRequest(to_address="john.doe@company.org")
        assert request.to_address == "john.doe@company.org"

    def test_valid_subdomain_email(self):
        """Test EmailTestRequest with subdomain email."""
        request = EmailTestRequest(to_address="admin@mail.example.com")
        assert request.to_address == "admin@mail.example.com"

    def test_valid_plus_addressing(self):
        """Test EmailTestRequest with plus addressing."""
        request = EmailTestRequest(to_address="user+tag@example.com")
        assert request.to_address == "user+tag@example.com"

    def test_valid_international_domain(self):
        """Test EmailTestRequest with international domain."""
        request = EmailTestRequest(to_address="test@münchen.de")
        assert request.to_address == "test@münchen.de"

    def test_invalid_email_no_at_symbol(self):
        """Test EmailTestRequest with invalid email missing @ symbol."""
        with pytest.raises(ValidationError) as exc_info:
            EmailTestRequest(to_address="invalid-email.com")

        assert "value is not a valid email address" in str(exc_info.value)

    def test_invalid_email_no_domain(self):
        """Test EmailTestRequest with invalid email missing domain."""
        with pytest.raises(ValidationError) as exc_info:
            EmailTestRequest(to_address="user@")

        assert "value is not a valid email address" in str(exc_info.value)

    def test_invalid_email_no_local_part(self):
        """Test EmailTestRequest with invalid email missing local part."""
        with pytest.raises(ValidationError) as exc_info:
            EmailTestRequest(to_address="@example.com")

        assert "value is not a valid email address" in str(exc_info.value)

    def test_invalid_email_empty_string(self):
        """Test EmailTestRequest with empty string."""
        with pytest.raises(ValidationError) as exc_info:
            EmailTestRequest(to_address="")

        assert "value is not a valid email address" in str(exc_info.value)

    def test_invalid_email_spaces(self):
        """Test EmailTestRequest with email containing spaces."""
        with pytest.raises(ValidationError) as exc_info:
            EmailTestRequest(to_address="user name@example.com")

        assert "value is not a valid email address" in str(exc_info.value)

    def test_missing_to_address_field(self):
        """Test EmailTestRequest without required to_address field."""
        with pytest.raises(ValidationError) as exc_info:
            EmailTestRequest()

        assert "to_address" in str(exc_info.value)
        assert "Field required" in str(exc_info.value)

    def test_none_to_address(self):
        """Test EmailTestRequest with None value."""
        with pytest.raises(ValidationError) as exc_info:
            EmailTestRequest(to_address=None)

        assert "Input should be a valid string" in str(exc_info.value)

    def test_email_address_type_validation(self):
        """Test that to_address is properly typed as EmailStr."""
        request = EmailTestRequest(to_address="valid@example.com")

        # Should be a string type
        assert isinstance(request.to_address, str)
        assert request.to_address == "valid@example.com"


class TestEmailConfigResponse:
    """Test EmailConfigResponse model."""

    def test_valid_config_response_complete(self):
        """Test EmailConfigResponse with all fields."""
        response = EmailConfigResponse(
            enabled=True,
            smtp_host="smtp.example.com",
            smtp_port=587,
            from_address="noreply@example.com",
            from_name="System Admin",
            subject_prefix="[SysManage]",
            configured=True,
        )

        assert response.enabled is True
        assert response.smtp_host == "smtp.example.com"
        assert response.smtp_port == 587
        assert response.from_address == "noreply@example.com"
        assert response.from_name == "System Admin"
        assert response.subject_prefix == "[SysManage]"
        assert response.configured is True

    def test_valid_config_response_disabled(self):
        """Test EmailConfigResponse for disabled email service."""
        response = EmailConfigResponse(
            enabled=False,
            smtp_host="",
            smtp_port=25,
            from_address="",
            from_name="",
            subject_prefix="",
            configured=False,
        )

        assert response.enabled is False
        assert response.smtp_host == ""
        assert response.smtp_port == 25
        assert response.from_address == ""
        assert response.from_name == ""
        assert response.subject_prefix == ""
        assert response.configured is False

    def test_config_response_localhost_smtp(self):
        """Test EmailConfigResponse with localhost SMTP."""
        response = EmailConfigResponse(
            enabled=True,
            smtp_host="localhost",
            smtp_port=25,
            from_address="admin@localhost",
            from_name="Local Admin",
            subject_prefix="[Local]",
            configured=True,
        )

        assert response.smtp_host == "localhost"
        assert response.smtp_port == 25
        assert response.configured is True

    def test_config_response_non_standard_port(self):
        """Test EmailConfigResponse with non-standard port."""
        response = EmailConfigResponse(
            enabled=True,
            smtp_host="mail.example.com",
            smtp_port=465,  # SSL port
            from_address="secure@example.com",
            from_name="Secure Mailer",
            subject_prefix="[Secure]",
            configured=True,
        )

        assert response.smtp_port == 465

    def test_config_response_boolean_coercion(self):
        """Test that boolean fields handle coercion properly."""
        # Test with values that should be coerced to boolean
        response = EmailConfigResponse(
            enabled=1,  # Integer should be coerced to boolean
            smtp_host="smtp.example.com",
            smtp_port=587,
            from_address="test@example.com",
            from_name="Test",
            subject_prefix="[Test]",
            configured=0,  # Integer should be coerced to boolean
        )

        # Pydantic should coerce these to proper booleans
        assert isinstance(response.enabled, bool)
        assert isinstance(response.configured, bool)
        assert response.enabled is True
        assert response.configured is False

    def test_config_response_missing_fields(self):
        """Test EmailConfigResponse with missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            EmailConfigResponse(
                # Missing required fields
                smtp_host="smtp.example.com"
            )

        error_str = str(exc_info.value)
        assert "enabled" in error_str
        assert "Field required" in error_str

    def test_config_response_invalid_port_type(self):
        """Test EmailConfigResponse with invalid port type."""
        with pytest.raises(ValidationError) as exc_info:
            EmailConfigResponse(
                enabled=True,
                smtp_host="smtp.example.com",
                smtp_port="not-a-number",  # Should be int
                from_address="test@example.com",
                from_name="Test",
                subject_prefix="[Test]",
                configured=True,
            )

        assert "Input should be a valid integer" in str(exc_info.value)

    def test_config_response_port_range_validation(self):
        """Test EmailConfigResponse with various port numbers."""
        # Valid ports
        valid_ports = [25, 465, 587, 993, 995, 1025, 65535]

        for port in valid_ports:
            response = EmailConfigResponse(
                enabled=True,
                smtp_host="smtp.example.com",
                smtp_port=port,
                from_address="test@example.com",
                from_name="Test",
                subject_prefix="[Test]",
                configured=True,
            )
            assert response.smtp_port == port

    def test_config_response_empty_strings(self):
        """Test EmailConfigResponse with empty string fields."""
        response = EmailConfigResponse(
            enabled=False,
            smtp_host="",
            smtp_port=587,
            from_address="",
            from_name="",
            subject_prefix="",
            configured=False,
        )

        assert response.smtp_host == ""
        assert response.from_address == ""
        assert response.from_name == ""
        assert response.subject_prefix == ""

    def test_config_response_unicode_support(self):
        """Test EmailConfigResponse with Unicode characters."""
        response = EmailConfigResponse(
            enabled=True,
            smtp_host="smtp.münchen.de",
            smtp_port=587,
            from_address="test@münchen.de",
            from_name="Müller Admin 🚀",
            subject_prefix="[SysManage 中文]",
            configured=True,
        )

        assert "münchen" in response.smtp_host
        assert "Müller" in response.from_name
        assert "🚀" in response.from_name
        assert "中文" in response.subject_prefix


class TestEmailTestResponse:
    """Test EmailTestResponse model."""

    def test_successful_email_test_response(self):
        """Test EmailTestResponse for successful email test."""
        response = EmailTestResponse(
            success=True, message="Test email sent successfully to user@example.com"
        )

        assert response.success is True
        assert "sent successfully" in response.message
        assert "user@example.com" in response.message

    def test_failed_email_test_response(self):
        """Test EmailTestResponse for failed email test."""
        response = EmailTestResponse(
            success=False,
            message="Failed to send test email. SMTP authentication failed.",
        )

        assert response.success is False
        assert "Failed to send" in response.message
        assert "authentication failed" in response.message

    def test_email_test_response_with_error_details(self):
        """Test EmailTestResponse with detailed error information."""
        response = EmailTestResponse(
            success=False, message="Error sending test email: Connection refused (111)"
        )

        assert response.success is False
        assert "Connection refused" in response.message

    def test_email_test_response_service_disabled(self):
        """Test EmailTestResponse when email service is disabled."""
        response = EmailTestResponse(
            success=False,
            message="Email service is disabled. Enable it in the configuration file.",
        )

        assert response.success is False
        assert "service is disabled" in response.message

    def test_email_test_response_boolean_coercion(self):
        """Test that success field handles boolean coercion."""
        # Test with various boolean values that Pydantic v2 accepts
        test_cases = [
            (True, True),
            (False, False),
            (1, True),
            (0, False),
        ]

        for input_value, expected_bool in test_cases:
            response = EmailTestResponse(success=input_value, message="Test message")
            assert isinstance(response.success, bool)
            assert response.success == expected_bool

    def test_email_test_response_missing_fields(self):
        """Test EmailTestResponse with missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            EmailTestResponse(success=True)  # Missing message

        assert "message" in str(exc_info.value)
        assert "Field required" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            EmailTestResponse(message="Test")  # Missing success

        assert "success" in str(exc_info.value)
        assert "Field required" in str(exc_info.value)

    def test_email_test_response_empty_message(self):
        """Test EmailTestResponse with empty message."""
        response = EmailTestResponse(success=True, message="")

        assert response.success is True
        assert response.message == ""

    def test_email_test_response_long_message(self):
        """Test EmailTestResponse with very long message."""
        long_message = "Error details: " + "x" * 1000
        response = EmailTestResponse(success=False, message=long_message)

        assert response.success is False
        assert len(response.message) > 1000
        assert response.message.startswith("Error details:")

    def test_email_test_response_multiline_message(self):
        """Test EmailTestResponse with multiline message."""
        multiline_message = """Test email sent successfully.
        Recipients: user1@example.com, user2@example.com
        Delivery time: 2.3 seconds"""

        response = EmailTestResponse(success=True, message=multiline_message)

        assert response.success is True
        assert "\n" in response.message
        assert "Recipients:" in response.message


class TestEmailModelsIntegration:
    """Integration tests for email models."""

    def test_models_work_with_json_serialization(self):
        """Test that all email models can be JSON serialized."""
        import json

        # Test EmailTestRequest
        request = EmailTestRequest(to_address="test@example.com")
        request_dict = request.dict()
        json.dumps(request_dict)  # Should not raise

        # Test EmailConfigResponse
        config_response = EmailConfigResponse(
            enabled=True,
            smtp_host="smtp.example.com",
            smtp_port=587,
            from_address="admin@example.com",
            from_name="Admin",
            subject_prefix="[Test]",
            configured=True,
        )
        config_dict = config_response.dict()
        json.dumps(config_dict)  # Should not raise

        # Test EmailTestResponse
        test_response = EmailTestResponse(
            success=True, message="Email sent successfully"
        )
        test_dict = test_response.dict()
        json.dumps(test_dict)  # Should not raise

    def test_model_field_types_consistency(self):
        """Test that model fields have consistent types."""
        config_response = EmailConfigResponse(
            enabled=True,
            smtp_host="smtp.example.com",
            smtp_port=587,
            from_address="admin@example.com",
            from_name="Admin",
            subject_prefix="[Test]",
            configured=True,
        )

        # Check field types
        assert isinstance(config_response.enabled, bool)
        assert isinstance(config_response.smtp_host, str)
        assert isinstance(config_response.smtp_port, int)
        assert isinstance(config_response.from_address, str)
        assert isinstance(config_response.from_name, str)
        assert isinstance(config_response.subject_prefix, str)
        assert isinstance(config_response.configured, bool)

    def test_email_validation_consistency(self):
        """Test that email validation is consistent."""
        valid_emails = [
            "test@example.com",
            "user.name@domain.org",
            "admin+alerts@company.co.uk",
            "service@sub.domain.com",
        ]

        for email in valid_emails:
            request = EmailTestRequest(to_address=email)
            assert request.to_address == email

        invalid_emails = [
            "not-an-email",
            "@domain.com",
            "user@",
            "user name@domain.com",
            "",
        ]

        for email in invalid_emails:
            with pytest.raises(ValidationError):
                EmailTestRequest(to_address=email)

    def test_response_models_boolean_handling(self):
        """Test that response models handle booleans consistently."""
        config_response = EmailConfigResponse(
            enabled=True,
            smtp_host="test",
            smtp_port=587,
            from_address="test@example.com",
            from_name="Test",
            subject_prefix="[Test]",
            configured=False,
        )

        test_response = EmailTestResponse(success=True, message="Success")

        # Both should have proper boolean types
        assert isinstance(config_response.enabled, bool)
        assert isinstance(config_response.configured, bool)
        assert isinstance(test_response.success, bool)

        # Test boolean values are preserved
        assert config_response.enabled is True
        assert config_response.configured is False
        assert test_response.success is True
