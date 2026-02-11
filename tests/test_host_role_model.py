"""
Tests for backend/persistence/models/host_role.py module.
Tests HostRole model structure and methods.
"""

import uuid
from datetime import datetime, timezone

import pytest


class TestHostRoleModel:
    """Tests for HostRole model."""

    def test_host_role_table_name(self):
        """Test HostRole table name."""
        from backend.persistence.models.host_role import HostRole

        assert HostRole.__tablename__ == "host_roles"

    def test_host_role_columns_exist(self):
        """Test HostRole has expected columns."""
        from backend.persistence.models.host_role import HostRole

        assert hasattr(HostRole, "id")
        assert hasattr(HostRole, "host_id")
        assert hasattr(HostRole, "role")
        assert hasattr(HostRole, "package_name")
        assert hasattr(HostRole, "package_version")
        assert hasattr(HostRole, "service_name")
        assert hasattr(HostRole, "service_status")
        assert hasattr(HostRole, "is_active")
        assert hasattr(HostRole, "detected_at")
        assert hasattr(HostRole, "updated_at")


class TestHostRoleRepr:
    """Tests for HostRole __repr__ method."""

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.host_role import HostRole

        role = HostRole()
        role.host_id = uuid.uuid4()
        role.role = "Web Server"
        role.package_name = "nginx"

        repr_str = repr(role)

        assert "HostRole" in repr_str
        assert "Web Server" in repr_str
        assert "nginx" in repr_str


class TestHostRoleToDict:
    """Tests for HostRole.to_dict method."""

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all fields."""
        from backend.persistence.models.host_role import HostRole

        role = HostRole()
        role.id = 1
        role.host_id = uuid.uuid4()
        role.role = "Database Server"
        role.package_name = "postgresql"
        role.package_version = "14.5"
        role.service_name = "postgresql"
        role.service_status = "running"
        role.is_active = True
        role.detected_at = datetime.now(timezone.utc)
        role.updated_at = datetime.now(timezone.utc)

        result = role.to_dict()

        assert result["id"] == 1
        assert result["role"] == "Database Server"
        assert result["package_name"] == "postgresql"
        assert result["package_version"] == "14.5"
        assert result["service_name"] == "postgresql"
        assert result["service_status"] == "running"
        assert result["is_active"] is True
        assert result["detected_at"] is not None
        assert result["updated_at"] is not None

    def test_to_dict_with_none_dates(self):
        """Test to_dict handles None dates."""
        from backend.persistence.models.host_role import HostRole

        role = HostRole()
        role.id = 2
        role.host_id = uuid.uuid4()
        role.role = "Web Server"
        role.package_name = "apache2"
        role.detected_at = None
        role.updated_at = None

        result = role.to_dict()

        assert result["detected_at"] is None
        assert result["updated_at"] is None
