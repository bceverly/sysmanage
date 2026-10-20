# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Which commands a maintenance window holds (Phase 14.2).

A window exists to schedule CHANGE: installs, updates, reboots, service
control, file deploys, scripts.  It used to hold every ``command`` message,
so with an all-hosts allow window the server also stopped asking agents for
package lists, facts and reports -- host data went stale until the window
opened (production, 2026-10-16: ``configure_network_discovery``,
``collect_available_packages`` and ``run_query_pack`` rows were held).

Both sets are explicit so a test can prove every command type the server
sends is in exactly one of them.  Anything in neither -- a new command
nobody classified -- is GATED: holding a read until the window opens costs
freshness, releasing a change outside it breaks the operator's promise.
"""

import json
from typing import Any, Dict, Optional, Tuple

# Commands that only read the host or report about it.  They never change
# the host's software, configuration, processes, users or clock.
WINDOW_EXEMPT_COMMANDS = frozenset(
    {
        # inventory / "send me your X" reports
        "get_system_info",
        "get_installed_packages",
        "get_available_updates",
        "check_updates",
        "collect_available_packages",
        "update_hardware",
        "update_os_version",
        "update_user_access",
        "refresh_user_access",
        "update_software_inventory",
        "collect_roles",
        "collect_certificates",
        "collect_processes",
        "collect_diagnostics",
        "check_reboot_status",
        "get_service_status",
        "get_capabilities",
        # virtualization: queries only
        "check_virtualization_support",
        "list_child_hosts",
        "child_host_status",
        "list_kvm_networks",
        "list_third_party_repositories",
        # facts and scans that only read
        "run_query_pack",
        "run_malware_scan",  # reads files; quarantine_file is the change
        "evaluate_package_compliance",  # checks packages against a profile
        # changes only what the agent itself observes and reports (passive
        # listening on the host's own segments), not the host
        "configure_network_discovery",
    }
)

# Commands that change something.  Listed (rather than "everything else") so
# the classification test catches a command that is in neither set.
WINDOW_GATED_COMMANDS = frozenset(
    {
        "execute_shell",
        "execute_script",
        "execute_command_sequence",
        "generic_command",
        "install_package",
        "install_packages",
        "uninstall_packages",
        "update_system",
        "apply_updates",
        "os_release_upgrade",
        "enable_package_manager",
        "add_third_party_repository",
        "delete_third_party_repositories",
        "enable_third_party_repositories",
        "disable_third_party_repositories",
        "install_gpg_key",
        "remove_gpg_key",
        "restart_service",
        "service_control",
        "reboot",
        "reboot_system",
        "shutdown_system",
        "kill_process",
        "change_hostname",
        "create_host_user",
        "create_host_group",
        "delete_host_user",
        "delete_host_group",
        "update_agent",
        "update_child_agent",
        "deploy_files",
        "apply_deployment_plan",
        # check-mode runs are exempt -- see is_window_gated
        "apply_config_profile",
        "quarantine_file",
        "restore_file",
        "resync_clock",
        # Phase 24 backups: configure installs root-owned job files, a run
        # can pause services (quiesce) or seal/prune on the storage host, a
        # restore writes files -- read-only runs are exempt in is_window_gated
        "backup_configure",
        "backup_run",
        "backup_restore",
        "attach_to_graylog",
        "fips_enable",
        "fips_disable",
        "ubuntu_pro_attach",
        "ubuntu_pro_detach",
        "ubuntu_pro_enable_service",
        "ubuntu_pro_disable_service",
        # sync_custom_metrics ships the commands a metric runs on the host on
        # its own schedule -- new definitions are new code running there
        "sync_custom_metrics",
        # an active sweep reads nothing on the host but puts traffic on a
        # network the operator may not own (IDS, contracts -- see 21.6), so
        # it waits for the window the operator set aside for disruption
        "run_network_sweep",
        # child hosts and hypervisor setup
        "create_child_host",
        "delete_child_host",
        "start_child_host",
        "stop_child_host",
        "restart_child_host",
        "configure_child_network",
        "initialize_lxd",
        "initialize_vmm",
        "initialize_kvm",
        "initialize_bhyve",
        "disable_bhyve",
        "enable_kvm_modules",
        "disable_kvm_modules",
        "setup_kvm_networking",
        "enable_wsl",
    }
)

# backup_run actions that only read the repository or the host.
_READ_ONLY_BACKUP = frozenset({"snapshots", "estimate", "check"})

# Message types other than "command" that are change actions.
_GATED_MESSAGE_TYPES = frozenset({"update_request"})


def _command_of(message_data: Optional[str]) -> Tuple[Optional[str], Dict[str, Any]]:
    """``(command_type, parameters)`` from a queued envelope, or (None, {})."""
    try:
        payload = json.loads(message_data or "{}")
    except (TypeError, ValueError):
        return None, {}
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None, {}
    params = data.get("parameters")
    return data.get("command_type"), params if isinstance(params, dict) else {}


def is_window_gated(message_type: str, message_data: Optional[str]) -> bool:
    """Whether a closed maintenance window must hold this outbound message.

    Control-plane pushes (logging/config updates, notices) are never held;
    ``update_request`` always is.  A command is held unless its type is
    known to only read -- an unreadable or unknown command is held."""
    if message_type in _GATED_MESSAGE_TYPES:
        return True
    if message_type != "command":
        return False
    command_type, params = _command_of(message_data)
    if command_type == "apply_config_profile" and params.get("check_mode") is True:
        return False  # a check-mode run reports drift and changes nothing
    if command_type == "backup_run" and params.get("action") in _READ_ONLY_BACKUP:
        return False  # lists, measures or verifies; changes nothing
    return command_type not in WINDOW_EXEMPT_COMMANDS
