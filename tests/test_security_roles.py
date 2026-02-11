"""
Tests for backend/api/security_roles.py module.
Tests security roles API endpoints.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


class TestSecurityRoleResponse:
    """Tests for SecurityRoleResponse model."""

    def test_model_structure(self):
        """Test SecurityRoleResponse model structure."""
        from backend.api.security_roles import SecurityRoleResponse

        role_id = uuid4()
        group_id = uuid4()

        response = SecurityRoleResponse(
            id=role_id,
            name="Test Role",
            description="Test description",
            group_id=group_id,
            group_name="Test Group",
        )

        assert response.id == role_id
        assert response.name == "Test Role"
        assert response.description == "Test description"
        assert response.group_id == group_id
        assert response.group_name == "Test Group"

    def test_model_without_description(self):
        """Test SecurityRoleResponse with null description."""
        from backend.api.security_roles import SecurityRoleResponse

        role_id = uuid4()
        group_id = uuid4()

        response = SecurityRoleResponse(
            id=role_id,
            name="Test Role",
            group_id=group_id,
            group_name="Test Group",
        )

        assert response.description is None


class TestSecurityRoleGroupResponse:
    """Tests for SecurityRoleGroupResponse model."""

    def test_model_structure(self):
        """Test SecurityRoleGroupResponse model structure."""
        from backend.api.security_roles import (
            SecurityRoleGroupResponse,
            SecurityRoleResponse,
        )

        group_id = uuid4()
        role_id = uuid4()

        role = SecurityRoleResponse(
            id=role_id,
            name="Test Role",
            description="Test description",
            group_id=group_id,
            group_name="Test Group",
        )

        group = SecurityRoleGroupResponse(
            id=group_id,
            name="Test Group",
            description="Group description",
            roles=[role],
        )

        assert group.id == group_id
        assert group.name == "Test Group"
        assert group.description == "Group description"
        assert len(group.roles) == 1
        assert group.roles[0].name == "Test Role"


class TestUserRolesRequest:
    """Tests for UserRolesRequest model."""

    def test_model_structure(self):
        """Test UserRolesRequest model structure."""
        from backend.api.security_roles import UserRolesRequest

        role_ids = [str(uuid4()), str(uuid4())]
        request = UserRolesRequest(role_ids=role_ids)

        assert request.role_ids == role_ids
        assert len(request.role_ids) == 2

    def test_empty_roles(self):
        """Test UserRolesRequest with empty roles."""
        from backend.api.security_roles import UserRolesRequest

        request = UserRolesRequest(role_ids=[])
        assert request.role_ids == []


class TestUserRolesResponse:
    """Tests for UserRolesResponse model."""

    def test_model_structure(self):
        """Test UserRolesResponse model structure."""
        from backend.api.security_roles import UserRolesResponse

        user_id = uuid4()
        role_ids = [str(uuid4()), str(uuid4())]

        response = UserRolesResponse(user_id=user_id, role_ids=role_ids)

        assert response.user_id == user_id
        assert response.role_ids == role_ids


class TestGetAllRoleGroups:
    """Tests for get_all_role_groups endpoint."""

    @patch("backend.api.security_roles.check_user_has_role")
    def test_get_all_role_groups_success(self, mock_check_role):
        """Test successful retrieval of role groups."""
        from backend.api.security_roles import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        # Setup mocks
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.userid = "test@example.com"

        mock_group = MagicMock()
        mock_group.id = uuid4()
        mock_group.name = "Test Group"
        mock_group.description = "Test description"

        mock_role = MagicMock()
        mock_role.id = uuid4()
        mock_role.name = "Test Role"
        mock_role.description = "Role description"
        mock_role.group_id = mock_group.id

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        mock_db.query.return_value.order_by.return_value.all.return_value = [mock_group]
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_role
        ]

        mock_check_role.return_value = True

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: "test@example.com"

        client = TestClient(app)
        response = client.get("/api/security-roles/groups")

        assert response.status_code == 200

    @patch("backend.api.security_roles.check_user_has_role")
    def test_get_all_role_groups_user_not_found(self, mock_check_role):
        """Test when current user not found."""
        from backend.api.security_roles import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: "test@example.com"

        client = TestClient(app)
        response = client.get("/api/security-roles/groups")

        assert response.status_code == 401

    @patch("backend.api.security_roles.check_user_has_role")
    def test_get_all_role_groups_permission_denied(self, mock_check_role):
        """Test when user lacks permission."""
        from backend.api.security_roles import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.userid = "test@example.com"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        mock_check_role.return_value = False

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: "test@example.com"

        client = TestClient(app)
        response = client.get("/api/security-roles/groups")

        assert response.status_code == 403


class TestGetUserRoles:
    """Tests for get_user_roles endpoint."""

    @patch("backend.api.security_roles.check_user_has_role")
    def test_get_user_roles_success(self, mock_check_role):
        """Test successful retrieval of user roles."""
        from backend.api.security_roles import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        user_id = uuid4()
        role_id = uuid4()

        mock_current_user = MagicMock()
        mock_current_user.id = uuid4()
        mock_current_user.userid = "admin@example.com"

        mock_target_user = MagicMock()
        mock_target_user.id = user_id
        mock_target_user.userid = "user@example.com"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_current_user,  # Current user lookup
            mock_target_user,  # Target user lookup
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [
            (role_id,)  # User roles
        ]

        mock_check_role.return_value = True

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: "admin@example.com"

        client = TestClient(app)
        response = client.get(f"/api/security-roles/user/{user_id}")

        assert response.status_code == 200

    @patch("backend.api.security_roles.check_user_has_role")
    def test_get_user_roles_user_not_found(self, mock_check_role):
        """Test when target user not found."""
        from backend.api.security_roles import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        user_id = uuid4()

        mock_current_user = MagicMock()
        mock_current_user.id = uuid4()
        mock_current_user.userid = "admin@example.com"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_current_user,  # Current user lookup
            None,  # Target user not found
        ]

        mock_check_role.return_value = True

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: "admin@example.com"

        client = TestClient(app)
        response = client.get(f"/api/security-roles/user/{user_id}")

        assert response.status_code == 404

    @patch("backend.api.security_roles.check_user_has_role")
    def test_get_user_roles_permission_denied(self, mock_check_role):
        """Test when user lacks permission."""
        from backend.api.security_roles import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        user_id = uuid4()

        mock_current_user = MagicMock()
        mock_current_user.id = uuid4()
        mock_current_user.userid = "user@example.com"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_current_user
        )

        mock_check_role.return_value = False

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: "user@example.com"

        client = TestClient(app)
        response = client.get(f"/api/security-roles/user/{user_id}")

        assert response.status_code == 403


class TestUpdateUserRoles:
    """Tests for update_user_roles endpoint."""

    @patch("backend.api.security_roles.AuditService")
    @patch("backend.api.security_roles.check_user_has_role")
    def test_update_user_roles_success(self, mock_check_role, mock_audit):
        """Test successful role update."""
        from backend.api.security_roles import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        user_id = uuid4()
        role_id = uuid4()

        mock_current_user = MagicMock()
        mock_current_user.id = uuid4()
        mock_current_user.userid = "admin@example.com"

        mock_target_user = MagicMock()
        mock_target_user.id = user_id
        mock_target_user.userid = "user@example.com"

        mock_role = MagicMock()
        mock_role.id = role_id
        mock_role.name = "Test Role"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_current_user,  # Current user lookup
            mock_target_user,  # Target user lookup
            mock_role,  # Role lookup during validation
            mock_role,  # Role lookup for audit log
        ]
        mock_db.query.return_value.filter.return_value.delete.return_value = 0

        mock_check_role.return_value = True

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: "admin@example.com"

        client = TestClient(app)
        response = client.put(
            f"/api/security-roles/user/{user_id}",
            json={"role_ids": [str(role_id)]},
        )

        assert response.status_code == 200

    @patch("backend.api.security_roles.check_user_has_role")
    def test_update_user_roles_invalid_uuid(self, mock_check_role):
        """Test with invalid UUID format."""
        from backend.api.security_roles import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        user_id = uuid4()

        mock_current_user = MagicMock()
        mock_current_user.id = uuid4()
        mock_current_user.userid = "admin@example.com"

        mock_target_user = MagicMock()
        mock_target_user.id = user_id
        mock_target_user.userid = "user@example.com"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_current_user,
            mock_target_user,
        ]

        mock_check_role.return_value = True

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: "admin@example.com"

        client = TestClient(app)
        response = client.put(
            f"/api/security-roles/user/{user_id}",
            json={"role_ids": ["not-a-valid-uuid"]},
        )

        assert response.status_code == 400
        assert "Invalid UUID format" in response.json()["detail"]

    @patch("backend.api.security_roles.check_user_has_role")
    def test_update_user_roles_role_not_found(self, mock_check_role):
        """Test with non-existent role."""
        from backend.api.security_roles import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        user_id = uuid4()
        role_id = uuid4()

        mock_current_user = MagicMock()
        mock_current_user.id = uuid4()
        mock_current_user.userid = "admin@example.com"

        mock_target_user = MagicMock()
        mock_target_user.id = user_id
        mock_target_user.userid = "user@example.com"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_current_user,
            mock_target_user,
            None,  # Role not found
        ]

        mock_check_role.return_value = True

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: "admin@example.com"

        client = TestClient(app)
        response = client.put(
            f"/api/security-roles/user/{user_id}",
            json={"role_ids": [str(role_id)]},
        )

        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]

    @patch("backend.api.security_roles.check_user_has_role")
    def test_update_user_roles_permission_denied(self, mock_check_role):
        """Test when user lacks permission."""
        from backend.api.security_roles import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        user_id = uuid4()

        mock_current_user = MagicMock()
        mock_current_user.id = uuid4()
        mock_current_user.userid = "user@example.com"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_current_user
        )

        mock_check_role.return_value = False

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: "user@example.com"

        client = TestClient(app)
        response = client.put(
            f"/api/security-roles/user/{user_id}",
            json={"role_ids": []},
        )

        assert response.status_code == 403

    def test_update_user_roles_current_user_not_found(self):
        """Test when current user not found."""
        from backend.api.security_roles import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        user_id = uuid4()

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: "unknown@example.com"

        client = TestClient(app)
        response = client.put(
            f"/api/security-roles/user/{user_id}",
            json={"role_ids": []},
        )

        assert response.status_code == 401

    @patch("backend.api.security_roles.check_user_has_role")
    def test_update_user_roles_target_user_not_found(self, mock_check_role):
        """Test when target user not found."""
        from backend.api.security_roles import router
        from backend.auth.auth_bearer import get_current_user
        from backend.persistence.db import get_db

        app = FastAPI()
        app.include_router(router)

        user_id = uuid4()

        mock_current_user = MagicMock()
        mock_current_user.id = uuid4()
        mock_current_user.userid = "admin@example.com"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_current_user,
            None,  # Target user not found
        ]

        mock_check_role.return_value = True

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: "admin@example.com"

        client = TestClient(app)
        response = client.put(
            f"/api/security-roles/user/{user_id}",
            json={"role_ids": []},
        )

        assert response.status_code == 404


class TestRouterConfiguration:
    """Tests for router configuration."""

    def test_router_prefix(self):
        """Test router has correct prefix."""
        from backend.api.security_roles import router

        assert router.prefix == "/api/security-roles"

    def test_router_tags(self):
        """Test router has correct tags."""
        from backend.api.security_roles import router

        assert "security-roles" in router.tags
