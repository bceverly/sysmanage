"""
Security roles enumeration and permission checking.

This module provides an enumeration of all security roles in the system
and utilities for checking user permissions.
"""

from enum import Enum
from typing import List, Optional, Set
from uuid import UUID

from sqlalchemy.orm import Session

from backend.persistence.models import SecurityRole, UserSecurityRole


class SecurityRoles(str, Enum):
    """
    Enumeration of all security roles in SysManage.

    These correspond to the roles defined in the database migration
    54fcacb0e742_add_security_roles_and_permissions.py

    The string values are the exact role names as stored in the database.
    """

    # Host Management Roles
    APPROVE_HOST_REGISTRATION = "Approve Host Registration"
    DELETE_HOST = "Delete Host"
    VIEW_HOST_DETAILS = "View Host Details"
    REBOOT_HOST = "Reboot Host"
    SHUTDOWN_HOST = "Shutdown Host"
    EDIT_TAGS = "Edit Tags"
    STOP_HOST_SERVICE = "Stop Host Service"
    START_HOST_SERVICE = "Start Host Service"
    RESTART_HOST_SERVICE = "Restart Host Service"

    # Package Management Roles
    ADD_PACKAGE = "Add Package"
    APPLY_SOFTWARE_UPDATE = "Apply Software Update"
    APPLY_HOST_OS_UPGRADE = "Apply Host OS Upgrade"

    # Secrets Management Roles
    DEPLOY_SSH_KEY = "Deploy SSH Key"
    DEPLOY_CERTIFICATE = "Deploy Certificate"
    ADD_SECRET = "Add Secret"  # nosec B105 - RBAC role name, not a password
    DELETE_SECRET = "Delete Secret"  # nosec B105 - RBAC role name, not a password
    EDIT_SECRET = "Edit Secret"  # nosec B105 - RBAC role name, not a password
    STOP_VAULT = "Stop Vault"
    START_VAULT = "Start Vault"

    # User Management Roles
    ADD_USER = "Add User"
    EDIT_USER = "Edit User"
    LOCK_USER = "Lock User"
    UNLOCK_USER = "Unlock User"
    DELETE_USER = "Delete User"
    RESET_USER_PASSWORD = (
        "Reset User Password"  # nosec B105 - RBAC role name, not a password
    )

    # Script Management Roles
    ADD_SCRIPT = "Add Script"
    EDIT_SCRIPT = "Edit Script"
    DELETE_SCRIPT = "Delete Script"
    RUN_SCRIPT = "Run Script"
    DELETE_SCRIPT_EXECUTION = "Delete Script Execution"

    # Report Management Roles
    VIEW_REPORT = "View Report"
    GENERATE_PDF_REPORT = "Generate PDF Report"

    # Integration Management Roles
    DELETE_QUEUE_MESSAGE = "Delete Queue Message"
    ENABLE_GRAFANA_INTEGRATION = "Enable Grafana Integration"

    # Ubuntu Pro Management Roles
    ATTACH_UBUNTU_PRO = "Attach Ubuntu Pro"
    DETACH_UBUNTU_PRO = "Detach Ubuntu Pro"
    CHANGE_UBUNTU_PRO_MASTER_KEY = "Change Ubuntu Pro Master Key"


class UserRoleCache:
    """
    Cache of user security roles for quick permission checking.

    This is typically populated at login time and attached to the user session.
    """

    def __init__(self, user_id: UUID, role_names: Set[str]):
        """
        Initialize the role cache.

        Args:
            user_id: The UUID of the user
            role_names: Set of role names the user has
        """
        self.user_id = user_id
        self._role_names = role_names
        self._role_enums = self._convert_to_enums(role_names)

    def _convert_to_enums(self, role_names: Set[str]) -> Set[SecurityRoles]:
        """Convert role name strings to enum values."""
        role_enums = set()
        for role_name in role_names:
            try:
                # Find the matching enum value
                role_enum = SecurityRoles(role_name)
                role_enums.add(role_enum)
            except ValueError:
                # Role name doesn't match any enum - log warning but continue
                pass
        return role_enums

    def has_role(self, role: SecurityRoles) -> bool:
        """
        Check if the user has a specific security role.

        Args:
            role: The SecurityRoles enum value to check

        Returns:
            True if the user has the role, False otherwise
        """
        return role in self._role_enums

    def has_any_role(self, roles: List[SecurityRoles]) -> bool:
        """
        Check if the user has any of the specified roles.

        Args:
            roles: List of SecurityRoles enum values to check

        Returns:
            True if the user has at least one of the roles, False otherwise
        """
        return any(role in self._role_enums for role in roles)

    def has_all_roles(self, roles: List[SecurityRoles]) -> bool:
        """
        Check if the user has all of the specified roles.

        Args:
            roles: List of SecurityRoles enum values to check

        Returns:
            True if the user has all of the roles, False otherwise
        """
        return all(role in self._role_enums for role in roles)

    def get_roles(self) -> Set[SecurityRoles]:
        """
        Get all roles the user has as enum values.

        Returns:
            Set of SecurityRoles enum values
        """
        return self._role_enums.copy()

    def get_role_names(self) -> Set[str]:
        """
        Get all role names the user has as strings.

        Returns:
            Set of role name strings
        """
        return self._role_names.copy()


def load_user_roles(db: Session, user_id: UUID) -> UserRoleCache:
    """
    Load all security roles for a user from the database.

    This should be called at login time to populate the user's role cache.

    Args:
        db: Database session
        user_id: UUID of the user

    Returns:
        UserRoleCache object containing the user's roles
    """
    # Query all role IDs for the user
    user_role_ids = (
        db.query(UserSecurityRole.role_id)
        .filter(UserSecurityRole.user_id == user_id)
        .all()
    )

    role_ids = [role_id for (role_id,) in user_role_ids]

    if not role_ids:
        # User has no roles
        return UserRoleCache(user_id, set())

    # Get the role names for these IDs
    roles = db.query(SecurityRole.name).filter(SecurityRole.id.in_(role_ids)).all()

    role_names = {role_name for (role_name,) in roles}

    return UserRoleCache(user_id, role_names)


def check_user_has_role(db: Session, user_id: UUID, role: SecurityRoles) -> bool:
    """
    Check if a user has a specific security role.

    This is a direct database query - prefer using UserRoleCache.has_role()
    for better performance when checking multiple roles.

    Args:
        db: Database session
        user_id: UUID of the user
        role: SecurityRoles enum value to check

    Returns:
        True if the user has the role, False otherwise
    """
    # First, find the role ID for the given role name
    role_record = (
        db.query(SecurityRole.id).filter(SecurityRole.name == role.value).first()
    )

    if not role_record:
        # Role doesn't exist in database
        return False

    role_id = role_record[0]

    # Check if user has this role
    user_has_role = (
        db.query(UserSecurityRole)
        .filter(
            UserSecurityRole.user_id == user_id, UserSecurityRole.role_id == role_id
        )
        .first()
    ) is not None

    return user_has_role
