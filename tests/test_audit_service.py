"""
Tests for backend/services/audit_service.py module.
Tests audit logging service functionality.
"""

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


class TestActionTypeEnum:
    """Tests for ActionType enumeration."""

    def test_create_value(self):
        """Test CREATE action type value."""
        from backend.services.audit_service import ActionType

        assert ActionType.CREATE.value == "CREATE"

    def test_update_value(self):
        """Test UPDATE action type value."""
        from backend.services.audit_service import ActionType

        assert ActionType.UPDATE.value == "UPDATE"

    def test_delete_value(self):
        """Test DELETE action type value."""
        from backend.services.audit_service import ActionType

        assert ActionType.DELETE.value == "DELETE"

    def test_execute_value(self):
        """Test EXECUTE action type value."""
        from backend.services.audit_service import ActionType

        assert ActionType.EXECUTE.value == "EXECUTE"

    def test_agent_message_value(self):
        """Test AGENT_MESSAGE action type value."""
        from backend.services.audit_service import ActionType

        assert ActionType.AGENT_MESSAGE.value == "AGENT_MESSAGE"

    def test_login_value(self):
        """Test LOGIN action type value."""
        from backend.services.audit_service import ActionType

        assert ActionType.LOGIN.value == "LOGIN"

    def test_logout_value(self):
        """Test LOGOUT action type value."""
        from backend.services.audit_service import ActionType

        assert ActionType.LOGOUT.value == "LOGOUT"

    def test_login_failed_value(self):
        """Test LOGIN_FAILED action type value."""
        from backend.services.audit_service import ActionType

        assert ActionType.LOGIN_FAILED.value == "LOGIN_FAILED"

    def test_password_reset_value(self):
        """Test PASSWORD_RESET action type value."""
        from backend.services.audit_service import ActionType

        assert ActionType.PASSWORD_RESET.value == "PASSWORD_RESET"

    def test_permission_change_value(self):
        """Test PERMISSION_CHANGE action type value."""
        from backend.services.audit_service import ActionType

        assert ActionType.PERMISSION_CHANGE.value == "PERMISSION_CHANGE"

    def test_is_string_enum(self):
        """Test that ActionType is a string enum."""
        from backend.services.audit_service import ActionType

        assert isinstance(ActionType.CREATE, str)
        assert ActionType.CREATE == "CREATE"


class TestEntityTypeEnum:
    """Tests for EntityType enumeration."""

    def test_host_value(self):
        """Test HOST entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.HOST.value == "host"

    def test_agent_value(self):
        """Test AGENT entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.AGENT.value == "agent"

    def test_user_value(self):
        """Test USER entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.USER.value == "user"

    def test_package_value(self):
        """Test PACKAGE entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.PACKAGE.value == "package"

    def test_script_value(self):
        """Test SCRIPT entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.SCRIPT.value == "script"

    def test_secret_value(self):
        """Test SECRET entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.SECRET.value == "secret"

    def test_tag_value(self):
        """Test TAG entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.TAG.value == "tag"

    def test_role_value(self):
        """Test ROLE entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.ROLE.value == "role"

    def test_repository_value(self):
        """Test REPOSITORY entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.REPOSITORY.value == "repository"

    def test_certificate_value(self):
        """Test CERTIFICATE entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.CERTIFICATE.value == "certificate"

    def test_firewall_value(self):
        """Test FIREWALL entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.FIREWALL.value == "firewall"

    def test_antivirus_value(self):
        """Test ANTIVIRUS entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.ANTIVIRUS.value == "antivirus"

    def test_update_value(self):
        """Test UPDATE entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.UPDATE.value == "update"

    def test_setting_value(self):
        """Test SETTING entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.SETTING.value == "setting"

    def test_security_role_value(self):
        """Test SECURITY_ROLE entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.SECURITY_ROLE.value == "security_role"

    def test_authentication_value(self):
        """Test AUTHENTICATION entity type value."""
        from backend.services.audit_service import EntityType

        assert EntityType.AUTHENTICATION.value == "authentication"


class TestResultEnum:
    """Tests for Result enumeration."""

    def test_success_value(self):
        """Test SUCCESS result value."""
        from backend.services.audit_service import Result

        assert Result.SUCCESS.value == "SUCCESS"

    def test_failure_value(self):
        """Test FAILURE result value."""
        from backend.services.audit_service import Result

        assert Result.FAILURE.value == "FAILURE"

    def test_pending_value(self):
        """Test PENDING result value."""
        from backend.services.audit_service import Result

        assert Result.PENDING.value == "PENDING"


class TestAuditServiceLog:
    """Tests for AuditService.log method."""

    @patch("backend.services.audit_service.AuditLog")
    def test_log_creates_entry(self, mock_audit_log_class):
        """Test that log creates an audit entry."""
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        mock_session = MagicMock()
        mock_entry = MagicMock()
        mock_audit_log_class.return_value = mock_entry

        result = AuditService.log(
            db=mock_session,
            action_type=ActionType.CREATE,
            entity_type=EntityType.HOST,
            description="Created host 'test-host'",
        )

        mock_session.add.assert_called_once_with(mock_entry)
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once_with(mock_entry)
        assert result == mock_entry

    @patch("backend.services.audit_service.AuditLog")
    def test_log_with_all_parameters(self, mock_audit_log_class):
        """Test log with all optional parameters."""
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        mock_session = MagicMock()
        mock_entry = MagicMock()
        mock_audit_log_class.return_value = mock_entry

        user_id = uuid.uuid4()
        result = AuditService.log(
            db=mock_session,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.USER,
            description="Updated user settings",
            result=Result.SUCCESS,
            user_id=user_id,
            username="admin@example.com",
            entity_id="user-123",
            entity_name="testuser",
            details={"changed": "password"},
            ip_address="192.168.1.1",
            error_message=None,
            user_agent="TestBrowser/1.0",
            category="user_management",
            entry_type="config_change",
        )

        assert result == mock_entry
        mock_session.add.assert_called_once()

    @patch("backend.services.audit_service.AuditLog")
    def test_log_with_failure_result(self, mock_audit_log_class):
        """Test log with failure result and error message."""
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        mock_session = MagicMock()
        mock_entry = MagicMock()
        mock_audit_log_class.return_value = mock_entry

        AuditService.log(
            db=mock_session,
            action_type=ActionType.DELETE,
            entity_type=EntityType.HOST,
            description="Failed to delete host",
            result=Result.FAILURE,
            error_message="Permission denied",
        )

        mock_session.add.assert_called_once()


class TestAuditServiceLogCreate:
    """Tests for AuditService.log_create method."""

    @patch("backend.services.audit_service.AuditService.log")
    def test_log_create_calls_log(self, mock_log):
        """Test that log_create calls log with correct parameters."""
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
        )

        mock_session = MagicMock()
        user_id = uuid.uuid4()

        AuditService.log_create(
            db=mock_session,
            entity_type=EntityType.HOST,
            entity_name="new-host",
            user_id=user_id,
            username="admin",
            entity_id="host-123",
            details={"os": "Ubuntu"},
            ip_address="10.0.0.1",
            user_agent="Browser/1.0",
        )

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == ActionType.CREATE
        assert call_kwargs["entity_type"] == EntityType.HOST
        assert call_kwargs["entity_name"] == "new-host"
        assert call_kwargs["user_id"] == user_id


class TestAuditServiceLogUpdate:
    """Tests for AuditService.log_update method."""

    @patch("backend.services.audit_service.AuditService.log")
    def test_log_update_calls_log(self, mock_log):
        """Test that log_update calls log with correct parameters."""
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
        )

        mock_session = MagicMock()

        AuditService.log_update(
            db=mock_session,
            entity_type=EntityType.USER,
            entity_name="testuser",
            details={"old_email": "old@test.com", "new_email": "new@test.com"},
        )

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == ActionType.UPDATE
        assert call_kwargs["entity_type"] == EntityType.USER


class TestAuditServiceLogDelete:
    """Tests for AuditService.log_delete method."""

    @patch("backend.services.audit_service.AuditService.log")
    def test_log_delete_calls_log(self, mock_log):
        """Test that log_delete calls log with correct parameters."""
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
        )

        mock_session = MagicMock()

        AuditService.log_delete(
            db=mock_session,
            entity_type=EntityType.TAG,
            entity_name="obsolete-tag",
            entity_id="tag-456",
        )

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == ActionType.DELETE
        assert call_kwargs["entity_type"] == EntityType.TAG
        assert call_kwargs["entity_name"] == "obsolete-tag"


class TestAuditServiceLogAgentMessage:
    """Tests for AuditService.log_agent_message method."""

    @patch("backend.services.audit_service.AuditService.log")
    def test_log_agent_message_calls_log(self, mock_log):
        """Test that log_agent_message calls log with correct parameters."""
        from backend.services.audit_service import (
            ActionType,
            AuditService,
            EntityType,
            Result,
        )

        mock_session = MagicMock()

        AuditService.log_agent_message(
            db=mock_session,
            host_name="production-server",
            message_type="INSTALL_PACKAGE",
            description="Installing nginx on production-server",
            host_id="host-789",
            details={"package": "nginx"},
            result=Result.PENDING,
        )

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == ActionType.AGENT_MESSAGE
        assert call_kwargs["entity_type"] == EntityType.HOST
        assert call_kwargs["entity_name"] == "production-server"
        assert call_kwargs["details"]["message_type"] == "INSTALL_PACKAGE"

    @patch("backend.services.audit_service.AuditService.log")
    def test_log_agent_message_with_empty_details(self, mock_log):
        """Test log_agent_message initializes details when None."""
        from backend.services.audit_service import AuditService

        mock_session = MagicMock()

        AuditService.log_agent_message(
            db=mock_session,
            host_name="test-host",
            message_type="RESTART",
            description="Restarting service",
            details=None,
        )

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["details"]["message_type"] == "RESTART"

    @patch("backend.services.audit_service.AuditService.log")
    def test_log_agent_message_with_error(self, mock_log):
        """Test log_agent_message with error result."""
        from backend.services.audit_service import AuditService, Result

        mock_session = MagicMock()

        AuditService.log_agent_message(
            db=mock_session,
            host_name="failing-host",
            message_type="UPDATE_PACKAGE",
            description="Failed to update package",
            result=Result.FAILURE,
            error_message="Connection timeout",
        )

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["result"] == Result.FAILURE
        assert call_kwargs["error_message"] == "Connection timeout"
