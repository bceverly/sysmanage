"""
Data handlers for SysManage agent communication.

This package contains handlers for processing various types of agent messages,
organized into logical modules:
- os_hardware_handlers: OS version, hardware, and Ubuntu Pro updates
- user_access_handlers: User accounts and groups with Windows SID support
- software_package_handlers: Software inventory, package updates, and repositories
- infrastructure_handlers: Script execution, reboot status, certificates, and roles
- child_host_handlers: Child host (VM, container, WSL) management

All handlers are re-exported here for backwards compatibility.
"""

# Import from child_host_handlers
from backend.api.handlers.child_host_handlers import (
    handle_child_host_created,
    handle_child_host_creation_progress,
    handle_child_hosts_list_update,
    handle_virtualization_support_update,
    handle_wsl_enable_result,
)

# Import from infrastructure_handlers
from backend.api.handlers.infrastructure_handlers import (
    handle_host_certificates_update,
    handle_host_role_data_update,
    handle_reboot_status_update,
    handle_script_execution_result,
)

# Import from os_hardware_handlers
from backend.api.handlers.os_hardware_handlers import (
    handle_hardware_update,
    handle_os_version_update,
    handle_ubuntu_pro_update,
    is_new_os_version_combination,
)

# Import from software_package_handlers
from backend.api.handlers.software_package_handlers import (
    handle_antivirus_status_update,
    handle_commercial_antivirus_status_update,
    handle_firewall_status_update,
    handle_graylog_status_update,
    handle_package_collection,
    handle_package_updates_update,
    handle_software_update,
    handle_third_party_repository_update,
)

# Import from user_access_handlers
from backend.api.handlers.user_access_handlers import (
    SYSTEM_USERNAMES,
    handle_user_access_update,
)

__all__ = [
    # OS and Hardware handlers
    "is_new_os_version_combination",
    "handle_os_version_update",
    "handle_hardware_update",
    "handle_ubuntu_pro_update",
    # User Access handlers
    "SYSTEM_USERNAMES",
    "handle_user_access_update",
    # Software and Package handlers
    "handle_software_update",
    "handle_package_updates_update",
    "handle_package_collection",
    "handle_third_party_repository_update",
    "handle_antivirus_status_update",
    "handle_commercial_antivirus_status_update",
    "handle_firewall_status_update",
    "handle_graylog_status_update",
    # Infrastructure handlers
    "handle_script_execution_result",
    "handle_reboot_status_update",
    "handle_host_certificates_update",
    "handle_host_role_data_update",
    # Child host handlers
    "handle_virtualization_support_update",
    "handle_child_hosts_list_update",
    "handle_child_host_creation_progress",
    "handle_child_host_created",
    "handle_wsl_enable_result",
]
