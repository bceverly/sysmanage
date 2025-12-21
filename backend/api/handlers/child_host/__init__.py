"""
Child host handlers package.

This package contains handlers for child host related messages from agents,
split into logical modules for maintainability.
"""

from backend.api.handlers.child_host.virtualization import (
    handle_virtualization_support_update,
    handle_wsl_enable_result,
    handle_lxd_initialize_result,
    handle_vmm_initialize_result,
)
from backend.api.handlers.child_host.listing import (
    handle_child_hosts_list_update,
)
from backend.api.handlers.child_host.creation import (
    handle_child_host_creation_progress,
    handle_child_host_created,
)
from backend.api.handlers.child_host.control import (
    handle_child_host_start_result,
    handle_child_host_stop_result,
    handle_child_host_restart_result,
    handle_child_host_delete_result,
)

__all__ = [
    # Virtualization
    "handle_virtualization_support_update",
    "handle_wsl_enable_result",
    "handle_lxd_initialize_result",
    "handle_vmm_initialize_result",
    # Listing
    "handle_child_hosts_list_update",
    # Creation
    "handle_child_host_creation_progress",
    "handle_child_host_created",
    # Control
    "handle_child_host_start_result",
    "handle_child_host_stop_result",
    "handle_child_host_restart_result",
    "handle_child_host_delete_result",
]
