"""
Virtualization status API endpoints.
Handles checking virtualization support and status for hosts.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api.child_host_utils import (
    get_host_or_404,
    get_user_with_role_check,
    verify_host_active,
)
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()
queue_ops = QueueOperations()


@router.get(
    "/host/{host_id}/virtualization",
    dependencies=[Depends(JWTBearer())],
)
async def get_virtualization_support(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Get virtualization capabilities for a host.
    Requires VIEW_CHILD_HOST permission.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        get_user_with_role_check(session, current_user, SecurityRoles.VIEW_CHILD_HOST)

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        # Queue a command to check virtualization support
        command_message = create_command_message(
            command_type="check_virtualization_support", parameters={}
        )

        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "Virtualization support check requested. "
                "Results will be available shortly."
            ),
        }


@router.get(
    "/host/{host_id}/virtualization/status",
    dependencies=[Depends(JWTBearer())],
)
async def get_virtualization_status(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Get the current virtualization status for a host.
    Returns cached virtualization info from the last agent report.
    Requires VIEW_CHILD_HOST permission.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        get_user_with_role_check(session, current_user, SecurityRoles.VIEW_CHILD_HOST)

        host = get_host_or_404(session, host_id)

        is_windows = host.platform and "Windows" in host.platform

        # Check if reboot is required for WSL enablement
        reboot_required = (
            host.reboot_required
            and host.reboot_required_reason == "WSL feature enablement pending"
        )

        # If we have stored virtualization data from agent, use it
        if host.virtualization_capabilities:
            try:
                capabilities = json.loads(host.virtualization_capabilities)
                supported_types = (
                    json.loads(host.virtualization_types)
                    if host.virtualization_types
                    else []
                )

                # Override reboot status from stored data if WSL needs enable
                wsl_caps = capabilities.get("wsl", {})
                if wsl_caps.get("needs_enable") and not reboot_required:
                    # WSL needs to be enabled but no reboot pending yet
                    pass  # Keep needs_enable from capabilities

                return {
                    "supported_types": supported_types,
                    "capabilities": capabilities,
                    "reboot_required": reboot_required,
                }
            except json.JSONDecodeError:
                pass  # Fall through to inference logic

        # Fallback: infer from platform and child hosts if no stored data
        is_linux = host.platform and "Linux" in host.platform

        if is_windows:
            return _get_windows_virtualization_status(session, host_id, reboot_required)

        if is_linux:
            return _get_linux_virtualization_status(session, host_id)

        # Check for OpenBSD (VMM support)
        is_openbsd = host.platform and "OpenBSD" in host.platform
        if is_openbsd:
            return _get_openbsd_virtualization_status(session, host_id)

        # Unknown platform
        return {
            "supported_types": [],
            "capabilities": {},
            "reboot_required": False,
        }


def _get_windows_virtualization_status(
    session, host_id: str, reboot_required: bool
) -> dict:
    """Get virtualization status for Windows hosts (WSL)."""
    wsl_enabled = False
    wsl_available = True
    needs_enable = False

    # Check if there are any WSL child hosts - if so, WSL is enabled
    child_hosts = (
        session.query(models.HostChild)
        .filter(
            models.HostChild.parent_host_id == host_id,
            models.HostChild.child_type == "wsl",
        )
        .count()
    )
    if child_hosts > 0:
        wsl_enabled = True
    else:
        # WSL is available but may need enabling
        needs_enable = True

    if reboot_required:
        # WSL enablement in progress, waiting for reboot
        needs_enable = False

    return {
        "supported_types": ["wsl"],
        "capabilities": {
            "wsl": {
                "available": wsl_available,
                "enabled": wsl_enabled,
                "needs_enable": needs_enable and not wsl_enabled,
            }
        },
        "reboot_required": reboot_required,
    }


def _get_linux_virtualization_status(session, host_id: str) -> dict:
    """Get virtualization status for Linux hosts (LXD and KVM)."""
    # For Linux hosts, check both LXD and KVM capabilities
    # Linux can have multiple hypervisors simultaneously
    supported_types = []
    capabilities = {}

    # Check LXD (Ubuntu 22.04+)
    lxd_child_hosts = (
        session.query(models.HostChild)
        .filter(
            models.HostChild.parent_host_id == host_id,
            models.HostChild.child_type == "lxd",
        )
        .count()
    )

    # If there are LXD containers, LXD must be installed and initialized
    if lxd_child_hosts > 0:
        supported_types.append("lxd")
        capabilities["lxd"] = {
            "available": True,
            "installed": True,
            "initialized": True,
            "needs_install": False,
            "needs_init": False,
        }
    else:
        # No stored data and no containers - assume LXD available but needs setup
        supported_types.append("lxd")
        capabilities["lxd"] = {
            "available": True,
            "installed": False,
            "initialized": False,
            "needs_install": True,
            "needs_init": True,
        }

    # Check KVM
    kvm_child_hosts = (
        session.query(models.HostChild)
        .filter(
            models.HostChild.parent_host_id == host_id,
            models.HostChild.child_type == "kvm",
        )
        .count()
    )

    # If there are KVM VMs, KVM must be installed and initialized
    if kvm_child_hosts > 0:
        supported_types.append("kvm")
        capabilities["kvm"] = {
            "available": True,
            "installed": True,
            "enabled": True,
            "running": True,
            "initialized": True,
            "needs_install": False,
            "needs_enable": False,
            "needs_init": False,
        }
    else:
        # No stored data and no VMs - assume KVM may be available
        # The actual availability will come from agent-reported data
        supported_types.append("kvm")
        capabilities["kvm"] = {
            "available": True,  # Assume available, agent will confirm
            "installed": False,
            "enabled": False,
            "running": False,
            "initialized": False,
            "needs_install": True,
            "needs_enable": True,
            "needs_init": True,
        }

    return {
        "supported_types": supported_types,
        "capabilities": capabilities,
        "reboot_required": False,
    }


def _get_openbsd_virtualization_status(session, host_id: str) -> dict:
    """Get virtualization status for OpenBSD hosts (VMM)."""
    # For OpenBSD hosts, check VMM availability
    vmm_child_hosts = (
        session.query(models.HostChild)
        .filter(
            models.HostChild.parent_host_id == host_id,
            models.HostChild.child_type == "vmm",
        )
        .count()
    )

    # If there are VMM VMs, VMM must be enabled and running
    if vmm_child_hosts > 0:
        return {
            "supported_types": ["vmm"],
            "capabilities": {
                "vmm": {
                    "available": True,
                    "enabled": True,
                    "running": True,
                    "initialized": True,
                    "kernel_supported": True,
                    "needs_enable": False,
                }
            },
            "reboot_required": False,
        }

    # No stored data and no VMs - assume VMM available but needs setup
    return {
        "supported_types": ["vmm"],
        "capabilities": {
            "vmm": {
                "available": True,
                "enabled": False,
                "running": False,
                "initialized": False,
                "kernel_supported": True,
                "needs_enable": True,
            }
        },
        "reboot_required": False,
    }
