"""
Tests for the security roles module.

This module tests the SecurityRoles enumeration and UserRoleCache class
which provide role-based access control functionality.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from backend.security.roles import (
    SecurityRoles,
    UserRoleCache,
    check_user_has_role,
    load_user_roles,
)


class TestSecurityRolesEnum:
    """Test cases for SecurityRoles enumeration."""

    def test_host_management_roles_exist(self):
        """Verify host management roles are defined."""
        assert SecurityRoles.APPROVE_HOST_REGISTRATION == "Approve Host Registration"
        assert SecurityRoles.DELETE_HOST == "Delete Host"
        assert SecurityRoles.EDIT_TAGS == "Edit Tags"
        assert SecurityRoles.VIEW_HOST_DETAILS == "View Host Details"
        assert SecurityRoles.REBOOT_HOST == "Reboot Host"
        assert SecurityRoles.SHUTDOWN_HOST == "Shutdown Host"
        assert SecurityRoles.RESTART_HOST_SERVICE == "Restart Host Service"
        assert SecurityRoles.START_HOST_SERVICE == "Start Host Service"
        assert SecurityRoles.STOP_HOST_SERVICE == "Stop Host Service"

    def test_package_management_roles_exist(self):
        """Verify package management roles are defined."""
        assert SecurityRoles.ADD_PACKAGE == "Add Package"
        assert SecurityRoles.APPLY_SOFTWARE_UPDATE == "Apply Software Update"
        assert SecurityRoles.APPLY_HOST_OS_UPGRADE == "Apply Host OS Upgrade"
        assert SecurityRoles.ADD_THIRD_PARTY_REPOSITORY == "Add Third-Party Repository"
        assert (
            SecurityRoles.DELETE_THIRD_PARTY_REPOSITORY
            == "Delete Third-Party Repository"
        )

    def test_user_management_roles_exist(self):
        """Verify user management roles are defined."""
        assert SecurityRoles.ADD_USER == "Add User"
        assert SecurityRoles.EDIT_USER == "Edit User"
        assert SecurityRoles.DELETE_USER == "Delete User"
        assert SecurityRoles.LOCK_USER == "Lock User"
        assert SecurityRoles.UNLOCK_USER == "Unlock User"
        assert SecurityRoles.RESET_USER_PASSWORD == "Reset User Password"

    def test_virtualization_roles_exist(self):
        """Verify virtualization roles are defined."""
        assert SecurityRoles.CREATE_CHILD_HOST == "Create Child Host"
        assert SecurityRoles.DELETE_CHILD_HOST == "Delete Child Host"
        assert SecurityRoles.START_CHILD_HOST == "Start Child Host"
        assert SecurityRoles.STOP_CHILD_HOST == "Stop Child Host"
        assert SecurityRoles.RESTART_CHILD_HOST == "Restart Child Host"
        assert SecurityRoles.VIEW_CHILD_HOST == "View Child Host"
        assert SecurityRoles.ENABLE_KVM == "Enable KVM"
        assert SecurityRoles.ENABLE_LXD == "Enable LXD"
        assert SecurityRoles.ENABLE_BHYVE == "Enable bhyve"
        assert SecurityRoles.ENABLE_VMM == "Enable VMM"
        assert SecurityRoles.ENABLE_WSL == "Enable WSL"

    def test_firewall_roles_exist(self):
        """Verify firewall roles are defined."""
        assert SecurityRoles.ADD_FIREWALL_ROLE == "Add Firewall Role"
        assert SecurityRoles.EDIT_FIREWALL_ROLE == "Edit Firewall Role"
        assert SecurityRoles.DELETE_FIREWALL_ROLE == "Delete Firewall Role"
        assert SecurityRoles.VIEW_FIREWALL_ROLES == "View Firewall Roles"
        assert SecurityRoles.DEPLOY_FIREWALL == "Deploy Firewall"
        assert SecurityRoles.ENABLE_FIREWALL == "Enable Firewall"
        assert SecurityRoles.DISABLE_FIREWALL == "Disable Firewall"

    def test_secret_management_roles_exist(self):
        """Verify secret management roles are defined."""
        assert SecurityRoles.ADD_SECRET == "Add Secret"
        assert SecurityRoles.EDIT_SECRET == "Edit Secret"
        assert SecurityRoles.DELETE_SECRET == "Delete Secret"
        assert SecurityRoles.DEPLOY_SSH_KEY == "Deploy SSH Key"
        assert SecurityRoles.DEPLOY_CERTIFICATE == "Deploy Certificate"

    def test_role_is_string_enum(self):
        """Verify SecurityRoles is a string enum."""
        assert isinstance(SecurityRoles.DELETE_HOST, str)
        assert SecurityRoles.DELETE_HOST.value == "Delete Host"

    def test_role_can_be_created_from_value(self):
        """Verify roles can be created from their string values."""
        role = SecurityRoles("Delete Host")
        assert role == SecurityRoles.DELETE_HOST


class TestUserRoleCache:
    """Test cases for UserRoleCache class."""

    def test_init_with_roles(self):
        """Test UserRoleCache initialization with role names."""
        user_id = uuid.uuid4()
        role_names = {"Delete Host", "Reboot Host"}
        cache = UserRoleCache(user_id, role_names)

        assert cache.user_id == user_id
        assert cache.get_role_names() == role_names

    def test_init_with_empty_roles(self):
        """Test UserRoleCache initialization with no roles."""
        user_id = uuid.uuid4()
        cache = UserRoleCache(user_id, set())

        assert cache.user_id == user_id
        assert cache.get_role_names() == set()
        assert cache.get_roles() == set()

    def test_has_role_returns_true_when_user_has_role(self):
        """Test has_role returns True when user has the role."""
        user_id = uuid.uuid4()
        role_names = {"Delete Host", "Reboot Host"}
        cache = UserRoleCache(user_id, role_names)

        assert cache.has_role(SecurityRoles.DELETE_HOST) is True
        assert cache.has_role(SecurityRoles.REBOOT_HOST) is True

    def test_has_role_returns_false_when_user_lacks_role(self):
        """Test has_role returns False when user doesn't have the role."""
        user_id = uuid.uuid4()
        role_names = {"Delete Host"}
        cache = UserRoleCache(user_id, role_names)

        assert cache.has_role(SecurityRoles.REBOOT_HOST) is False
        assert cache.has_role(SecurityRoles.ADD_USER) is False

    def test_has_any_role_returns_true_with_matching_role(self):
        """Test has_any_role returns True when user has at least one role."""
        user_id = uuid.uuid4()
        role_names = {"Delete Host"}
        cache = UserRoleCache(user_id, role_names)

        result = cache.has_any_role(
            [
                SecurityRoles.DELETE_HOST,
                SecurityRoles.REBOOT_HOST,
            ]
        )
        assert result is True

    def test_has_any_role_returns_false_with_no_matching_roles(self):
        """Test has_any_role returns False when user has none of the roles."""
        user_id = uuid.uuid4()
        role_names = {"Edit Tags"}
        cache = UserRoleCache(user_id, role_names)

        result = cache.has_any_role(
            [
                SecurityRoles.DELETE_HOST,
                SecurityRoles.REBOOT_HOST,
            ]
        )
        assert result is False

    def test_has_all_roles_returns_true_when_user_has_all(self):
        """Test has_all_roles returns True when user has all specified roles."""
        user_id = uuid.uuid4()
        role_names = {"Delete Host", "Reboot Host", "View Host Details"}
        cache = UserRoleCache(user_id, role_names)

        result = cache.has_all_roles(
            [
                SecurityRoles.DELETE_HOST,
                SecurityRoles.REBOOT_HOST,
            ]
        )
        assert result is True

    def test_has_all_roles_returns_false_when_user_lacks_some(self):
        """Test has_all_roles returns False when user lacks some roles."""
        user_id = uuid.uuid4()
        role_names = {"Delete Host"}
        cache = UserRoleCache(user_id, role_names)

        result = cache.has_all_roles(
            [
                SecurityRoles.DELETE_HOST,
                SecurityRoles.REBOOT_HOST,
            ]
        )
        assert result is False

    def test_get_roles_returns_copy_of_role_enums(self):
        """Test get_roles returns a copy of the role enums."""
        user_id = uuid.uuid4()
        role_names = {"Delete Host", "Reboot Host"}
        cache = UserRoleCache(user_id, role_names)

        roles = cache.get_roles()
        assert SecurityRoles.DELETE_HOST in roles
        assert SecurityRoles.REBOOT_HOST in roles
        assert len(roles) == 2

        # Verify it's a copy (modifying it doesn't affect cache)
        roles.add(SecurityRoles.ADD_USER)
        assert SecurityRoles.ADD_USER not in cache.get_roles()

    def test_get_role_names_returns_copy_of_names(self):
        """Test get_role_names returns a copy of the role names."""
        user_id = uuid.uuid4()
        role_names = {"Delete Host"}
        cache = UserRoleCache(user_id, role_names)

        names = cache.get_role_names()
        assert "Delete Host" in names

        # Verify it's a copy
        names.add("Fake Role")
        assert "Fake Role" not in cache.get_role_names()

    def test_handles_unknown_role_names(self):
        """Test that unknown role names are silently ignored."""
        user_id = uuid.uuid4()
        role_names = {"Delete Host", "Unknown Role That Doesn't Exist"}
        cache = UserRoleCache(user_id, role_names)

        # Should still have the valid role
        assert cache.has_role(SecurityRoles.DELETE_HOST) is True
        # Role names are preserved as-is
        assert "Unknown Role That Doesn't Exist" in cache.get_role_names()


class TestLoadUserRoles:
    """Test cases for load_user_roles function."""

    def test_load_user_roles_returns_cache(self, session):
        """Test load_user_roles returns a UserRoleCache object."""
        from backend.persistence.models import SecurityRole, User, UserSecurityRole
        from argon2 import PasswordHasher

        # Create a test user
        ph = PasswordHasher()
        user = User(
            userid="roletest@example.com",
            hashed_password=ph.hash("password"),
            first_name="Test",
            last_name="User",
            active=True,
        )
        session.add(user)
        session.commit()

        # Load roles (user has no roles yet)
        cache = load_user_roles(session, user.id)

        assert isinstance(cache, UserRoleCache)
        assert cache.user_id == user.id
        assert cache.get_role_names() == set()


class TestCheckUserHasRole:
    """Test cases for check_user_has_role function."""

    def test_returns_false_when_role_not_in_database(self, session):
        """Test returns False when the role doesn't exist in database."""
        user_id = uuid.uuid4()

        # Create a mock that returns None for role lookup
        result = check_user_has_role(session, user_id, SecurityRoles.DELETE_HOST)

        # Without roles seeded, this should return False
        assert result is False
