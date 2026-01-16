"""
Tests for the audit service module.

This module tests the AuditService class which provides functionality
for logging user actions and system changes.
"""

import uuid
from datetime import datetime

import pytest

from backend.persistence.models import AuditLog
from backend.services.audit_service import (
    ActionType,
    AuditService,
    EntityType,
    Result,
)


class TestActionTypeEnum:
    """Test cases for ActionType enumeration."""

    def test_action_types_exist(self):
        """Verify all expected action types are defined."""
        assert ActionType.CREATE == "CREATE"
        assert ActionType.UPDATE == "UPDATE"
        assert ActionType.DELETE == "DELETE"
        assert ActionType.EXECUTE == "EXECUTE"
        assert ActionType.AGENT_MESSAGE == "AGENT_MESSAGE"
        assert ActionType.LOGIN == "LOGIN"
        assert ActionType.LOGOUT == "LOGOUT"
        assert ActionType.LOGIN_FAILED == "LOGIN_FAILED"
        assert ActionType.PASSWORD_RESET == "PASSWORD_RESET"
        assert ActionType.PERMISSION_CHANGE == "PERMISSION_CHANGE"


class TestEntityTypeEnum:
    """Test cases for EntityType enumeration."""

    def test_entity_types_exist(self):
        """Verify all expected entity types are defined."""
        assert EntityType.HOST == "host"
        assert EntityType.AGENT == "agent"
        assert EntityType.USER == "user"
        assert EntityType.PACKAGE == "package"
        assert EntityType.SCRIPT == "script"
        assert EntityType.SECRET == "secret"
        assert EntityType.TAG == "tag"
        assert EntityType.ROLE == "role"
        assert EntityType.REPOSITORY == "repository"
        assert EntityType.CERTIFICATE == "certificate"
        assert EntityType.FIREWALL == "firewall"
        assert EntityType.ANTIVIRUS == "antivirus"
        assert EntityType.UPDATE == "update"
        assert EntityType.SETTING == "setting"
        assert EntityType.SECURITY_ROLE == "security_role"
        assert EntityType.AUTHENTICATION == "authentication"


class TestResultEnum:
    """Test cases for Result enumeration."""

    def test_result_types_exist(self):
        """Verify all expected result types are defined."""
        assert Result.SUCCESS == "SUCCESS"
        assert Result.FAILURE == "FAILURE"
        assert Result.PENDING == "PENDING"


class TestAuditServiceLog:
    """Test cases for AuditService.log method."""

    def test_log_creates_audit_entry(self, session):
        """Test that log() creates an audit log entry."""
        entry = AuditService.log(
            db=session,
            action_type=ActionType.CREATE,
            entity_type=EntityType.HOST,
            description="Test audit entry",
            result=Result.SUCCESS,
        )

        assert entry is not None
        assert entry.id is not None
        assert entry.action_type == "CREATE"
        assert entry.entity_type == "host"
        assert entry.description == "Test audit entry"
        assert entry.result == "SUCCESS"

    def test_log_with_user_info(self, session):
        """Test that log() correctly stores user information."""
        user_id = uuid.uuid4()
        entry = AuditService.log(
            db=session,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.USER,
            description="User updated",
            user_id=user_id,
            username="testuser@example.com",
        )

        assert entry.user_id == user_id
        assert entry.username == "testuser@example.com"

    def test_log_with_entity_info(self, session):
        """Test that log() correctly stores entity information."""
        entity_id = str(uuid.uuid4())
        entry = AuditService.log(
            db=session,
            action_type=ActionType.DELETE,
            entity_type=EntityType.HOST,
            description="Host deleted",
            entity_id=entity_id,
            entity_name="test-host.example.com",
        )

        assert entry.entity_id == entity_id
        assert entry.entity_name == "test-host.example.com"

    def test_log_with_details(self, session):
        """Test that log() correctly stores additional details."""
        details = {"old_value": "foo", "new_value": "bar"}
        entry = AuditService.log(
            db=session,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.SETTING,
            description="Setting changed",
            details=details,
        )

        assert entry.details == details

    def test_log_with_client_info(self, session):
        """Test that log() correctly stores client information."""
        entry = AuditService.log(
            db=session,
            action_type=ActionType.LOGIN,
            entity_type=EntityType.AUTHENTICATION,
            description="User logged in",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0 Test Browser",
        )

        assert entry.ip_address == "192.168.1.100"
        assert entry.user_agent == "Mozilla/5.0 Test Browser"

    def test_log_with_error_message(self, session):
        """Test that log() correctly stores error information."""
        entry = AuditService.log(
            db=session,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.SCRIPT,
            description="Script execution failed",
            result=Result.FAILURE,
            error_message="Permission denied",
        )

        assert entry.result == "FAILURE"
        assert entry.error_message == "Permission denied"

    def test_log_with_category_and_entry_type(self, session):
        """Test that log() correctly stores category and entry type."""
        entry = AuditService.log(
            db=session,
            action_type=ActionType.CREATE,
            entity_type=EntityType.PACKAGE,
            description="Package installed",
            category="Packages",
            entry_type="Install",
        )

        assert entry.category == "Packages"
        assert entry.entry_type == "Install"

    def test_log_persists_to_database(self, session):
        """Test that log() persists the entry to the database."""
        entry = AuditService.log(
            db=session,
            action_type=ActionType.CREATE,
            entity_type=EntityType.HOST,
            description="Test persistence",
        )

        # Query the database to verify persistence
        stored_entry = session.query(AuditLog).filter(AuditLog.id == entry.id).first()
        assert stored_entry is not None
        assert stored_entry.description == "Test persistence"


class TestAuditServiceLogCreate:
    """Test cases for AuditService.log_create method."""

    def test_log_create_creates_entry(self, session):
        """Test that log_create() creates an audit log entry."""
        entry = AuditService.log_create(
            db=session,
            entity_type=EntityType.HOST,
            entity_name="new-host.example.com",
        )

        assert entry is not None
        assert entry.action_type == "CREATE"
        assert entry.entity_type == "host"
        assert entry.entity_name == "new-host.example.com"
        assert entry.result == "SUCCESS"
        assert "Created" in entry.description
        assert "new-host.example.com" in entry.description

    def test_log_create_with_user_info(self, session):
        """Test that log_create() correctly stores user information."""
        user_id = uuid.uuid4()
        entry = AuditService.log_create(
            db=session,
            entity_type=EntityType.USER,
            entity_name="newuser@example.com",
            user_id=user_id,
            username="admin@example.com",
        )

        assert entry.user_id == user_id
        assert entry.username == "admin@example.com"

    def test_log_create_with_details(self, session):
        """Test that log_create() correctly stores additional details."""
        details = {"source": "api", "version": "1.0"}
        entry = AuditService.log_create(
            db=session,
            entity_type=EntityType.SCRIPT,
            entity_name="test-script.sh",
            details=details,
        )

        assert entry.details == details


class TestAuditServiceLogUpdate:
    """Test cases for AuditService.log_update method."""

    def test_log_update_creates_entry(self, session):
        """Test that log_update() creates an audit log entry."""
        entry = AuditService.log_update(
            db=session,
            entity_type=EntityType.HOST,
            entity_name="updated-host.example.com",
        )

        assert entry is not None
        assert entry.action_type == "UPDATE"
        assert entry.entity_type == "host"
        assert entry.entity_name == "updated-host.example.com"
        assert entry.result == "SUCCESS"
        assert "Updated" in entry.description

    def test_log_update_with_entity_id(self, session):
        """Test that log_update() correctly stores entity ID."""
        entity_id = str(uuid.uuid4())
        entry = AuditService.log_update(
            db=session,
            entity_type=EntityType.SETTING,
            entity_name="max_connections",
            entity_id=entity_id,
        )

        assert entry.entity_id == entity_id


class TestAuditServiceLogDelete:
    """Test cases for AuditService.log_delete method."""

    def test_log_delete_creates_entry(self, session):
        """Test that log_delete() creates an audit log entry."""
        entry = AuditService.log_delete(
            db=session,
            entity_type=EntityType.HOST,
            entity_name="deleted-host.example.com",
        )

        assert entry is not None
        assert entry.action_type == "DELETE"
        assert entry.entity_type == "host"
        assert entry.entity_name == "deleted-host.example.com"
        assert entry.result == "SUCCESS"
        assert "Deleted" in entry.description

    def test_log_delete_with_all_parameters(self, session):
        """Test that log_delete() correctly stores all parameters."""
        user_id = uuid.uuid4()
        entity_id = str(uuid.uuid4())
        details = {"reason": "decommissioned"}

        entry = AuditService.log_delete(
            db=session,
            entity_type=EntityType.HOST,
            entity_name="old-host.example.com",
            user_id=user_id,
            username="admin@example.com",
            entity_id=entity_id,
            details=details,
            ip_address="10.0.0.1",
            user_agent="Admin CLI",
        )

        assert entry.user_id == user_id
        assert entry.username == "admin@example.com"
        assert entry.entity_id == entity_id
        assert entry.details == details
        assert entry.ip_address == "10.0.0.1"
        assert entry.user_agent == "Admin CLI"


class TestAuditServiceLogAgentMessage:
    """Test cases for AuditService.log_agent_message method."""

    def test_log_agent_message_creates_entry(self, session):
        """Test that log_agent_message() creates an audit log entry."""
        entry = AuditService.log_agent_message(
            db=session,
            host_name="agent-host.example.com",
            message_type="command",
            description="Command sent to agent",
        )

        assert entry is not None
        assert entry.action_type == "AGENT_MESSAGE"
        assert entry.entity_type == "host"
        assert entry.entity_name == "agent-host.example.com"
        assert entry.description == "Command sent to agent"
        assert entry.result == "SUCCESS"
        assert entry.details["message_type"] == "command"

    def test_log_agent_message_with_failure(self, session):
        """Test that log_agent_message() correctly logs failures."""
        entry = AuditService.log_agent_message(
            db=session,
            host_name="agent-host.example.com",
            message_type="reboot",
            description="Reboot command failed",
            result=Result.FAILURE,
            error_message="Host unreachable",
        )

        assert entry.result == "FAILURE"
        assert entry.error_message == "Host unreachable"

    def test_log_agent_message_preserves_existing_details(self, session):
        """Test that log_agent_message() preserves existing details."""
        details = {"package_name": "nginx", "version": "1.24"}
        entry = AuditService.log_agent_message(
            db=session,
            host_name="agent-host.example.com",
            message_type="install_package",
            description="Package installation",
            details=details,
        )

        assert entry.details["message_type"] == "install_package"
        assert entry.details["package_name"] == "nginx"
        assert entry.details["version"] == "1.24"

    def test_log_agent_message_with_host_id(self, session):
        """Test that log_agent_message() correctly stores host ID."""
        host_id = str(uuid.uuid4())
        entry = AuditService.log_agent_message(
            db=session,
            host_name="agent-host.example.com",
            message_type="status",
            description="Status request",
            host_id=host_id,
        )

        assert entry.entity_id == host_id


class TestAuditServiceMultipleEntries:
    """Test cases for multiple audit log entries."""

    def test_multiple_entries_have_unique_ids(self, session):
        """Test that multiple audit entries have unique IDs."""
        entries = []
        for i in range(5):
            entry = AuditService.log(
                db=session,
                action_type=ActionType.CREATE,
                entity_type=EntityType.HOST,
                description=f"Test entry {i}",
            )
            entries.append(entry)

        ids = [entry.id for entry in entries]
        assert len(ids) == len(set(ids))  # All IDs should be unique

    def test_entries_have_sequential_timestamps(self, session):
        """Test that multiple audit entries have increasing timestamps."""
        entries = []
        for i in range(3):
            entry = AuditService.log(
                db=session,
                action_type=ActionType.UPDATE,
                entity_type=EntityType.SETTING,
                description=f"Update {i}",
            )
            entries.append(entry)

        for i in range(len(entries) - 1):
            assert entries[i].timestamp <= entries[i + 1].timestamp
