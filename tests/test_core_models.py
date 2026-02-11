"""
Tests for backend/persistence/models/core.py module.
Tests core models including GUID type, Host, User, and security models.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestGUID:
    """Tests for GUID TypeDecorator."""

    def test_load_dialect_impl_postgresql(self):
        """Test load_dialect_impl returns UUID for PostgreSQL."""
        from backend.persistence.models.core import GUID

        guid = GUID()
        mock_dialect = MagicMock()
        mock_dialect.name = "postgresql"
        mock_dialect.type_descriptor = MagicMock(return_value="pg_uuid")

        result = guid.load_dialect_impl(mock_dialect)

        assert result == "pg_uuid"
        mock_dialect.type_descriptor.assert_called_once()

    def test_load_dialect_impl_sqlite(self):
        """Test load_dialect_impl returns String(36) for SQLite."""
        from backend.persistence.models.core import GUID

        guid = GUID()
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"
        mock_dialect.type_descriptor = MagicMock(return_value="sqlite_string")

        result = guid.load_dialect_impl(mock_dialect)

        assert result == "sqlite_string"
        mock_dialect.type_descriptor.assert_called_once()

    def test_process_bind_param_none(self):
        """Test process_bind_param returns None for None input."""
        from backend.persistence.models.core import GUID

        guid = GUID()
        mock_dialect = MagicMock()
        mock_dialect.name = "postgresql"

        result = guid.process_bind_param(None, mock_dialect)

        assert result is None

    def test_process_bind_param_postgresql_uuid(self):
        """Test process_bind_param keeps UUID for PostgreSQL."""
        from backend.persistence.models.core import GUID

        guid = GUID()
        mock_dialect = MagicMock()
        mock_dialect.name = "postgresql"
        test_uuid = uuid.uuid4()

        result = guid.process_bind_param(test_uuid, mock_dialect)

        assert result == test_uuid

    def test_process_bind_param_postgresql_string(self):
        """Test process_bind_param converts string to str for PostgreSQL."""
        from backend.persistence.models.core import GUID

        guid = GUID()
        mock_dialect = MagicMock()
        mock_dialect.name = "postgresql"
        test_str = "550e8400-e29b-41d4-a716-446655440000"

        result = guid.process_bind_param(test_str, mock_dialect)

        assert result == test_str
        assert isinstance(result, str)

    def test_process_bind_param_sqlite(self):
        """Test process_bind_param converts to string for SQLite."""
        from backend.persistence.models.core import GUID

        guid = GUID()
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"
        test_uuid = uuid.uuid4()

        result = guid.process_bind_param(test_uuid, mock_dialect)

        assert result == str(test_uuid)
        assert isinstance(result, str)

    def test_process_result_value_none(self):
        """Test process_result_value returns None for None input."""
        from backend.persistence.models.core import GUID

        guid = GUID()
        mock_dialect = MagicMock()

        result = guid.process_result_value(None, mock_dialect)

        assert result is None

    def test_process_result_value_uuid(self):
        """Test process_result_value returns UUID as-is."""
        from backend.persistence.models.core import GUID

        guid = GUID()
        mock_dialect = MagicMock()
        test_uuid = uuid.uuid4()

        result = guid.process_result_value(test_uuid, mock_dialect)

        assert result == test_uuid

    def test_process_result_value_string(self):
        """Test process_result_value converts string to UUID."""
        from backend.persistence.models.core import GUID

        guid = GUID()
        mock_dialect = MagicMock()
        test_str = "550e8400-e29b-41d4-a716-446655440000"

        result = guid.process_result_value(test_str, mock_dialect)

        assert isinstance(result, uuid.UUID)
        assert str(result) == test_str

    def test_process_literal_param_none(self):
        """Test process_literal_param returns None for None."""
        from backend.persistence.models.core import GUID

        guid = GUID()
        mock_dialect = MagicMock()

        result = guid.process_literal_param(None, mock_dialect)

        assert result is None

    def test_process_literal_param_uuid(self):
        """Test process_literal_param converts UUID to string."""
        from backend.persistence.models.core import GUID

        guid = GUID()
        mock_dialect = MagicMock()
        test_uuid = uuid.uuid4()

        result = guid.process_literal_param(test_uuid, mock_dialect)

        assert result == str(test_uuid)

    def test_python_type_property(self):
        """Test python_type property returns uuid.UUID."""
        from backend.persistence.models.core import GUID

        guid = GUID()

        assert guid.python_type is uuid.UUID


class TestGenerateSecureHostToken:
    """Tests for generate_secure_host_token function."""

    def test_generates_valid_token(self):
        """Test generates a token with correct format."""
        from backend.persistence.models.core import generate_secure_host_token

        token = generate_secure_host_token()

        # Should be UUID-entropy format
        parts = token.split("-")
        # UUID4 has 5 parts, plus 1 entropy part = 6 parts
        assert len(parts) == 6

        # Verify first 5 parts form valid UUID
        uuid_str = "-".join(parts[:5])
        uuid.UUID(uuid_str)  # Should not raise

        # Entropy should be 16 hex chars (8 bytes)
        entropy = parts[5]
        assert len(entropy) == 16
        int(entropy, 16)  # Should be valid hex

    def test_generates_unique_tokens(self):
        """Test generates unique tokens each call."""
        from backend.persistence.models.core import generate_secure_host_token

        tokens = [generate_secure_host_token() for _ in range(100)]

        assert len(tokens) == len(set(tokens))


class TestBearerTokenModel:
    """Tests for BearerToken model."""

    def test_table_name(self):
        """Test BearerToken table name."""
        from backend.persistence.models.core import BearerToken

        assert BearerToken.__tablename__ == "bearer_token"

    def test_columns_exist(self):
        """Test BearerToken has expected columns."""
        from backend.persistence.models.core import BearerToken

        assert hasattr(BearerToken, "id")
        assert hasattr(BearerToken, "token")
        assert hasattr(BearerToken, "created_at")


class TestHostModel:
    """Tests for Host model."""

    def test_table_name(self):
        """Test Host table name."""
        from backend.persistence.models.core import Host

        assert Host.__tablename__ == "host"

    def test_columns_exist(self):
        """Test Host has expected columns."""
        from backend.persistence.models.core import Host

        assert hasattr(Host, "id")
        assert hasattr(Host, "active")
        assert hasattr(Host, "fqdn")
        assert hasattr(Host, "ipv4")
        assert hasattr(Host, "ipv6")
        assert hasattr(Host, "host_token")
        assert hasattr(Host, "last_access")
        assert hasattr(Host, "status")
        assert hasattr(Host, "approval_status")
        assert hasattr(Host, "platform")
        assert hasattr(Host, "platform_release")
        assert hasattr(Host, "machine_architecture")
        assert hasattr(Host, "cpu_vendor")
        assert hasattr(Host, "cpu_model")
        assert hasattr(Host, "cpu_cores")
        assert hasattr(Host, "memory_total_mb")
        assert hasattr(Host, "reboot_required")
        assert hasattr(Host, "is_agent_privileged")
        assert hasattr(Host, "script_execution_enabled")
        assert hasattr(Host, "virtualization_types")
        assert hasattr(Host, "parent_host_id")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.core import Host

        host = Host()
        host.id = uuid.uuid4()
        host.fqdn = "server.example.com"
        host.active = True

        repr_str = repr(host)

        assert "Host" in repr_str
        # Checking repr output format, not URL validation - false positive for CodeQL
        assert "server.example.com" in repr_str  # noqa: S105
        assert "True" in repr_str


class TestUserModel:
    """Tests for User model."""

    def test_table_name(self):
        """Test User table name."""
        from backend.persistence.models.core import User

        assert User.__tablename__ == "user"

    def test_columns_exist(self):
        """Test User has expected columns."""
        from backend.persistence.models.core import User

        assert hasattr(User, "id")
        assert hasattr(User, "active")
        assert hasattr(User, "userid")
        assert hasattr(User, "hashed_password")
        assert hasattr(User, "last_access")
        assert hasattr(User, "is_locked")
        assert hasattr(User, "failed_login_attempts")
        assert hasattr(User, "locked_at")
        assert hasattr(User, "first_name")
        assert hasattr(User, "last_name")
        assert hasattr(User, "profile_image")
        assert hasattr(User, "profile_image_type")
        assert hasattr(User, "is_admin")
        assert hasattr(User, "last_login_at")
        assert hasattr(User, "created_at")
        assert hasattr(User, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.core import User

        user = User()
        user.id = uuid.uuid4()
        user.userid = "admin"
        user.active = True
        user.is_admin = True

        repr_str = repr(user)

        assert "User" in repr_str
        assert "admin" in repr_str
        assert "True" in repr_str

    def test_has_role_no_cache(self):
        """Test has_role returns False when cache not loaded."""
        from backend.persistence.models.core import User

        user = User()
        user._role_cache = None

        result = user.has_role("some_role")

        assert result is False

    def test_has_role_with_cache(self):
        """Test has_role delegates to cache."""
        from backend.persistence.models.core import User

        user = User()
        mock_cache = MagicMock()
        mock_cache.has_role.return_value = True
        user._role_cache = mock_cache

        result = user.has_role("some_role")

        assert result is True
        mock_cache.has_role.assert_called_once_with("some_role")

    def test_has_any_role_no_cache(self):
        """Test has_any_role returns False when cache not loaded."""
        from backend.persistence.models.core import User

        user = User()
        user._role_cache = None

        result = user.has_any_role(["role1", "role2"])

        assert result is False

    def test_has_any_role_with_cache(self):
        """Test has_any_role delegates to cache."""
        from backend.persistence.models.core import User

        user = User()
        mock_cache = MagicMock()
        mock_cache.has_any_role.return_value = True
        user._role_cache = mock_cache

        result = user.has_any_role(["role1", "role2"])

        assert result is True
        mock_cache.has_any_role.assert_called_once_with(["role1", "role2"])

    def test_has_all_roles_no_cache(self):
        """Test has_all_roles returns False when cache not loaded."""
        from backend.persistence.models.core import User

        user = User()
        user._role_cache = None

        result = user.has_all_roles(["role1", "role2"])

        assert result is False

    def test_has_all_roles_with_cache(self):
        """Test has_all_roles delegates to cache."""
        from backend.persistence.models.core import User

        user = User()
        mock_cache = MagicMock()
        mock_cache.has_all_roles.return_value = True
        user._role_cache = mock_cache

        result = user.has_all_roles(["role1", "role2"])

        assert result is True
        mock_cache.has_all_roles.assert_called_once_with(["role1", "role2"])

    def test_get_roles_no_cache(self):
        """Test get_roles returns empty set when cache not loaded."""
        from backend.persistence.models.core import User

        user = User()
        user._role_cache = None

        result = user.get_roles()

        assert result == set()

    def test_get_roles_with_cache(self):
        """Test get_roles delegates to cache."""
        from backend.persistence.models.core import User

        user = User()
        mock_cache = MagicMock()
        mock_cache.get_roles.return_value = {"role1", "role2"}
        user._role_cache = mock_cache

        result = user.get_roles()

        assert result == {"role1", "role2"}
        mock_cache.get_roles.assert_called_once()


class TestSecurityRoleGroupModel:
    """Tests for SecurityRoleGroup model."""

    def test_table_name(self):
        """Test SecurityRoleGroup table name."""
        from backend.persistence.models.core import SecurityRoleGroup

        assert SecurityRoleGroup.__tablename__ == "security_role_groups"

    def test_columns_exist(self):
        """Test SecurityRoleGroup has expected columns."""
        from backend.persistence.models.core import SecurityRoleGroup

        assert hasattr(SecurityRoleGroup, "id")
        assert hasattr(SecurityRoleGroup, "name")
        assert hasattr(SecurityRoleGroup, "description")
        assert hasattr(SecurityRoleGroup, "created_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.core import SecurityRoleGroup

        group = SecurityRoleGroup()
        group.id = uuid.uuid4()
        group.name = "host_management"

        repr_str = repr(group)

        assert "SecurityRoleGroup" in repr_str
        assert "host_management" in repr_str


class TestSecurityRoleModel:
    """Tests for SecurityRole model."""

    def test_table_name(self):
        """Test SecurityRole table name."""
        from backend.persistence.models.core import SecurityRole

        assert SecurityRole.__tablename__ == "security_roles"

    def test_columns_exist(self):
        """Test SecurityRole has expected columns."""
        from backend.persistence.models.core import SecurityRole

        assert hasattr(SecurityRole, "id")
        assert hasattr(SecurityRole, "name")
        assert hasattr(SecurityRole, "description")
        assert hasattr(SecurityRole, "group_id")
        assert hasattr(SecurityRole, "created_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.core import SecurityRole

        role = SecurityRole()
        role.id = uuid.uuid4()
        role.name = "view_hosts"
        role.group_id = uuid.uuid4()

        repr_str = repr(role)

        assert "SecurityRole" in repr_str
        assert "view_hosts" in repr_str


class TestUserSecurityRoleModel:
    """Tests for UserSecurityRole model."""

    def test_table_name(self):
        """Test UserSecurityRole table name."""
        from backend.persistence.models.core import UserSecurityRole

        assert UserSecurityRole.__tablename__ == "user_security_roles"

    def test_columns_exist(self):
        """Test UserSecurityRole has expected columns."""
        from backend.persistence.models.core import UserSecurityRole

        assert hasattr(UserSecurityRole, "id")
        assert hasattr(UserSecurityRole, "user_id")
        assert hasattr(UserSecurityRole, "role_id")
        assert hasattr(UserSecurityRole, "granted_at")
        assert hasattr(UserSecurityRole, "granted_by")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.core import UserSecurityRole

        usr = UserSecurityRole()
        usr.user_id = uuid.uuid4()
        usr.role_id = uuid.uuid4()

        repr_str = repr(usr)

        assert "UserSecurityRole" in repr_str
        assert str(usr.user_id) in repr_str
        assert str(usr.role_id) in repr_str


class TestUserDataGridColumnPreferenceModel:
    """Tests for UserDataGridColumnPreference model."""

    def test_table_name(self):
        """Test UserDataGridColumnPreference table name."""
        from backend.persistence.models.core import UserDataGridColumnPreference

        assert (
            UserDataGridColumnPreference.__tablename__
            == "user_datagrid_column_preferences"
        )

    def test_columns_exist(self):
        """Test UserDataGridColumnPreference has expected columns."""
        from backend.persistence.models.core import UserDataGridColumnPreference

        assert hasattr(UserDataGridColumnPreference, "id")
        assert hasattr(UserDataGridColumnPreference, "user_id")
        assert hasattr(UserDataGridColumnPreference, "grid_identifier")
        assert hasattr(UserDataGridColumnPreference, "hidden_columns")
        assert hasattr(UserDataGridColumnPreference, "created_at")
        assert hasattr(UserDataGridColumnPreference, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.core import UserDataGridColumnPreference

        pref = UserDataGridColumnPreference()
        pref.user_id = uuid.uuid4()
        pref.grid_identifier = "hosts-grid"

        repr_str = repr(pref)

        assert "UserDataGridColumnPreference" in repr_str
        assert "hosts-grid" in repr_str


class TestUserDashboardCardPreferenceModel:
    """Tests for UserDashboardCardPreference model."""

    def test_table_name(self):
        """Test UserDashboardCardPreference table name."""
        from backend.persistence.models.core import UserDashboardCardPreference

        assert (
            UserDashboardCardPreference.__tablename__
            == "user_dashboard_card_preference"
        )

    def test_columns_exist(self):
        """Test UserDashboardCardPreference has expected columns."""
        from backend.persistence.models.core import UserDashboardCardPreference

        assert hasattr(UserDashboardCardPreference, "id")
        assert hasattr(UserDashboardCardPreference, "user_id")
        assert hasattr(UserDashboardCardPreference, "card_identifier")
        assert hasattr(UserDashboardCardPreference, "visible")
        assert hasattr(UserDashboardCardPreference, "created_at")
        assert hasattr(UserDashboardCardPreference, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.core import UserDashboardCardPreference

        pref = UserDashboardCardPreference()
        pref.user_id = uuid.uuid4()
        pref.card_identifier = "hosts"
        pref.visible = True

        repr_str = repr(pref)

        assert "UserDashboardCardPreference" in repr_str
        assert "hosts" in repr_str
        assert "True" in repr_str


class TestAuditLogModel:
    """Tests for AuditLog model."""

    def test_table_name(self):
        """Test AuditLog table name."""
        from backend.persistence.models.core import AuditLog

        assert AuditLog.__tablename__ == "audit_log"

    def test_columns_exist(self):
        """Test AuditLog has expected columns."""
        from backend.persistence.models.core import AuditLog

        assert hasattr(AuditLog, "id")
        assert hasattr(AuditLog, "timestamp")
        assert hasattr(AuditLog, "user_id")
        assert hasattr(AuditLog, "username")
        assert hasattr(AuditLog, "action_type")
        assert hasattr(AuditLog, "entity_type")
        assert hasattr(AuditLog, "entity_id")
        assert hasattr(AuditLog, "entity_name")
        assert hasattr(AuditLog, "description")
        assert hasattr(AuditLog, "details")
        assert hasattr(AuditLog, "ip_address")
        assert hasattr(AuditLog, "user_agent")
        assert hasattr(AuditLog, "result")
        assert hasattr(AuditLog, "error_message")
        assert hasattr(AuditLog, "category")
        assert hasattr(AuditLog, "entry_type")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.core import AuditLog

        log = AuditLog()
        log.id = uuid.uuid4()
        log.username = "admin"
        log.action_type = "UPDATE"
        log.entity_type = "host"

        repr_str = repr(log)

        assert "AuditLog" in repr_str
        assert "admin" in repr_str
        assert "UPDATE" in repr_str
        assert "host" in repr_str


class TestCoreModuleConstants:
    """Tests for module constants."""

    def test_constants_exist(self):
        """Test module-level constants exist."""
        from backend.persistence.models.core import CASCADE_DELETE_ORPHAN, USER_ID_FK

        assert CASCADE_DELETE_ORPHAN == "all, delete-orphan"
        assert USER_ID_FK == "user.id"
