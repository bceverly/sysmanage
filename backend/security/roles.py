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
    # - General Host Operations (alphabetical)
    APPROVE_HOST_REGISTRATION = "Approve Host Registration"
    DELETE_HOST = "Delete Host"
    EDIT_TAGS = "Edit Tags"
    VIEW_HOST_DETAILS = "View Host Details"
    # - Host Power Operations (alphabetical)
    REBOOT_HOST = "Reboot Host"
    SHUTDOWN_HOST = "Shutdown Host"
    # - Host Service Operations (alphabetical)
    RESTART_HOST_SERVICE = "Restart Host Service"
    START_HOST_SERVICE = "Start Host Service"
    STOP_HOST_SERVICE = "Stop Host Service"

    # Integration Management Roles
    # - Queue Operations (alphabetical)
    DELETE_QUEUE_MESSAGE = "Delete Queue Message"
    # - Grafana Operations (alphabetical)
    ENABLE_GRAFANA_INTEGRATION = "Enable Grafana Integration"
    # - Graylog Operations (alphabetical)
    CONNECT_HOST_TO_GRAYLOG = "Connect Host to Graylog"
    ENABLE_GRAYLOG_INTEGRATION = "Enable Graylog Integration"
    # - OpenTelemetry Operations (alphabetical)
    DEPLOY_OPENTELEMETRY = "Deploy OpenTelemetry"
    RESTART_OPENTELEMETRY_SERVICE = "Restart OpenTelemetry Service"
    START_OPENTELEMETRY_SERVICE = "Start OpenTelemetry Service"
    STOP_OPENTELEMETRY_SERVICE = "Stop OpenTelemetry Service"

    # Package Management Roles
    # - Package Operations (alphabetical)
    ADD_PACKAGE = "Add Package"
    APPLY_HOST_OS_UPGRADE = "Apply Host OS Upgrade"
    APPLY_SOFTWARE_UPDATE = "Apply Software Update"
    # - Third-Party Repository Operations (alphabetical)
    ADD_THIRD_PARTY_REPOSITORY = "Add Third-Party Repository"
    DELETE_THIRD_PARTY_REPOSITORY = "Delete Third-Party Repository"
    DISABLE_THIRD_PARTY_REPOSITORY = "Disable Third-Party Repository"
    ENABLE_THIRD_PARTY_REPOSITORY = "Enable Third-Party Repository"

    # Report Management Roles
    GENERATE_PDF_REPORT = "Generate PDF Report"
    VIEW_REPORT = "View Report"

    # Script Management Roles
    # - Script CRUD Operations (alphabetical)
    ADD_SCRIPT = "Add Script"
    DELETE_SCRIPT = "Delete Script"
    EDIT_SCRIPT = "Edit Script"
    # - Script Execution Operations (alphabetical)
    DELETE_SCRIPT_EXECUTION = "Delete Script Execution"
    RUN_SCRIPT = "Run Script"

    # Secrets Management Roles
    # - Secret Operations (alphabetical)
    ADD_SECRET = "Add Secret"  # nosec B105 - RBAC role name, not a password
    DELETE_SECRET = "Delete Secret"  # nosec B105 - RBAC role name, not a password
    EDIT_SECRET = "Edit Secret"  # nosec B105 - RBAC role name, not a password
    # - Certificate Deployment (alphabetical)
    DEPLOY_CERTIFICATE = "Deploy Certificate"
    # - SSH Key Deployment (alphabetical)
    DEPLOY_SSH_KEY = "Deploy SSH Key"
    # - Vault Operations (alphabetical)
    START_VAULT = "Start Vault"
    STOP_VAULT = "Stop Vault"

    # Security Management Roles
    # - Antivirus Operations (alphabetical)
    DEPLOY_ANTIVIRUS = "Deploy Antivirus"
    DISABLE_ANTIVIRUS = "Disable Antivirus"
    ENABLE_ANTIVIRUS = "Enable Antivirus"
    MANAGE_ANTIVIRUS_DEFAULTS = "Manage Antivirus Defaults"
    REMOVE_ANTIVIRUS = "Remove Antivirus"
    # - Firewall Operations (alphabetical)
    DEPLOY_FIREWALL = "Deploy Firewall"
    DISABLE_FIREWALL = "Disable Firewall"
    EDIT_FIREWALL_PORTS = "Edit Firewall Ports"
    ENABLE_FIREWALL = "Enable Firewall"
    REMOVE_FIREWALL = "Remove Firewall"
    RESTART_FIREWALL = "Restart Firewall"
    # - User Security Role Management (alphabetical)
    EDIT_USER_SECURITY_ROLES = "Edit User Security Roles"
    VIEW_USER_SECURITY_ROLES = "View User Security Roles"

    # Ubuntu Pro Management Roles
    ATTACH_UBUNTU_PRO = "Attach Ubuntu Pro"
    CHANGE_UBUNTU_PRO_MASTER_KEY = "Change Ubuntu Pro Master Key"
    DETACH_UBUNTU_PRO = "Detach Ubuntu Pro"

    # User Management Roles
    # - User CRUD Operations (alphabetical)
    ADD_USER = "Add User"
    DELETE_USER = "Delete User"
    EDIT_USER = "Edit User"
    # - User Security Operations (alphabetical)
    LOCK_USER = "Lock User"
    RESET_USER_PASSWORD = (
        "Reset User Password"  # nosec B105 - RBAC role name, not a password
    )
    UNLOCK_USER = "Unlock User"

    # Audit Log Management Roles
    VIEW_AUDIT_LOG = "View Audit Log"
    EXPORT_AUDIT_LOG = "Export Audit Log"

    # Default Repository Management Roles
    ADD_DEFAULT_REPOSITORY = "Add Default Repository"
    REMOVE_DEFAULT_REPOSITORY = "Remove Default Repository"
    VIEW_DEFAULT_REPOSITORIES = "View Default Repositories"

    # Enabled Package Manager Management Roles
    ADD_ENABLED_PACKAGE_MANAGER = "Add Enabled Package Manager"
    REMOVE_ENABLED_PACKAGE_MANAGER = "Remove Enabled Package Manager"
    VIEW_ENABLED_PACKAGE_MANAGERS = "View Enabled Package Managers"

    # Firewall Role Management Roles
    ADD_FIREWALL_ROLE = "Add Firewall Role"
    EDIT_FIREWALL_ROLE = "Edit Firewall Role"
    DELETE_FIREWALL_ROLE = "Delete Firewall Role"
    VIEW_FIREWALL_ROLES = "View Firewall Roles"
    ASSIGN_HOST_FIREWALL_ROLES = "Assign Host Firewall Roles"

    # Host Account Management Roles
    # - Host Account (User) Operations (alphabetical)
    ADD_HOST_ACCOUNT = "Add Host Account"
    DELETE_HOST_ACCOUNT = "Delete Host Account"
    EDIT_HOST_ACCOUNT = "Edit Host Account"
    # - Host Group Operations (alphabetical)
    ADD_HOST_GROUP = "Add Host Group"
    DELETE_HOST_GROUP = "Delete Host Group"
    EDIT_HOST_GROUP = "Edit Host Group"


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
