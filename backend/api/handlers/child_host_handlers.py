"""
Child Host data handlers for SysManage.

This module re-exports child host handlers from the child_host subpackage
for backwards compatibility. The handlers are organized into logical modules:

- virtualization: Virtualization support and WSL enablement
- listing: Child host discovery and synchronization
- creation: Child host creation progress and completion
- control: Start, stop, restart, and delete operations
"""

# Re-export all handlers from the child_host package
from backend.api.handlers.child_host import (
    # Virtualization handlers
    handle_virtualization_support_update,
    handle_wsl_enable_result,
    handle_lxd_initialize_result,
    handle_vmm_initialize_result,
    handle_kvm_initialize_result,
    handle_bhyve_initialize_result,
    handle_kvm_modules_enable_result,
    handle_kvm_modules_disable_result,
    # Listing handlers
    handle_child_hosts_list_update,
    # Creation handlers
    handle_child_host_creation_progress,
    handle_child_host_created,
    # Control handlers
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
    "handle_kvm_initialize_result",
    "handle_bhyve_initialize_result",
    "handle_kvm_modules_enable_result",
    "handle_kvm_modules_disable_result",
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
