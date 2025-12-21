"""
Virtualization management API endpoints.
Handles WSL status, LXD status, enabling WSL/LXD, and creating child hosts.
"""

import json
import uuid
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api.child_host_models import CreateWslChildHostRequest
from backend.api.child_host_utils import (
    audit_log,
    get_host_or_404,
    get_user_with_role_check,
    verify_host_active,
)
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config.config import get_config
from backend.i18n import _
from backend.persistence import db, models
from backend.persistence.models import ChildHostDistribution
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
    import json

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

        if is_linux:
            # For Linux hosts, assume LXD is available (Ubuntu 22.04+)
            # and needs initialization if no stored data
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
                return {
                    "supported_types": ["lxd"],
                    "capabilities": {
                        "lxd": {
                            "available": True,
                            "installed": True,
                            "initialized": True,
                            "needs_install": False,
                            "needs_init": False,
                        }
                    },
                    "reboot_required": False,
                }

            # No stored data and no containers - assume LXD available but needs setup
            return {
                "supported_types": ["lxd"],
                "capabilities": {
                    "lxd": {
                        "available": True,
                        "installed": False,
                        "initialized": False,
                        "needs_install": True,
                        "needs_init": True,
                    }
                },
                "reboot_required": False,
            }

        # Check for OpenBSD (VMM support)
        is_openbsd = host.platform and "OpenBSD" in host.platform
        if is_openbsd:
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

        # Unknown platform
        return {
            "supported_types": [],
            "capabilities": {},
            "reboot_required": False,
        }


@router.post(
    "/host/{host_id}/virtualization/enable-wsl",
    dependencies=[Depends(JWTBearer())],
)
async def enable_wsl(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Enable WSL on a Windows host.
    Requires CREATE_CHILD_HOST permission.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.CREATE_CHILD_HOST
        )

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        # Verify it's a Windows host
        if not host.platform or "Windows" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=_("WSL is only supported on Windows hosts"),
            )

        # Verify the agent is privileged (needed to enable WSL)
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Agent must be running with administrator privileges to enable WSL"
                ),
            )

        # Queue a command to enable WSL
        command_message = create_command_message(
            command_type="enable_wsl", parameters={}
        )

        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Log the action
        audit_log(
            session,
            user,
            current_user,
            "CREATE",
            str(host.id),
            host.fqdn,
            _("WSL enablement requested"),
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "WSL enablement requested. A reboot may be required "
                "to complete the installation."
            ),
        }


@router.post(
    "/host/{host_id}/virtualization/initialize-lxd",
    dependencies=[Depends(JWTBearer())],
)
async def initialize_lxd(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Initialize LXD on an Ubuntu host.
    Installs LXD via snap if not installed, and runs lxd init --auto.
    Requires CREATE_CHILD_HOST permission.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.CREATE_CHILD_HOST
        )

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        # Verify it's a Linux host (LXD is Linux-only)
        if not host.platform or "Linux" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=_("LXD is only supported on Linux hosts"),
            )

        # Verify the agent is privileged (needed to install/init LXD)
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Agent must be running with root privileges to initialize LXD"
                ),
            )

        # Queue a command to initialize LXD
        command_message = create_command_message(
            command_type="initialize_lxd", parameters={}
        )

        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Log the action
        audit_log(
            session,
            user,
            current_user,
            "CREATE",
            str(host.id),
            host.fqdn,
            _("LXD initialization requested"),
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "LXD initialization requested. The agent will install and "
                "configure LXD automatically."
            ),
        }


@router.post(
    "/host/{host_id}/virtualization/initialize-vmm",
    dependencies=[Depends(JWTBearer())],
)
async def initialize_vmm(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Initialize VMM/vmd on an OpenBSD host.
    Enables and starts the vmd daemon for virtual machine management.
    Requires CREATE_CHILD_HOST permission.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.CREATE_CHILD_HOST
        )

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        # Verify it's an OpenBSD host (VMM is OpenBSD-only)
        if not host.platform or "OpenBSD" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=_("VMM is only supported on OpenBSD hosts"),
            )

        # Verify the agent is privileged (needed to enable/start vmd)
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Agent must be running with root privileges to initialize VMM"
                ),
            )

        # Queue a command to initialize VMM
        command_message = create_command_message(
            command_type="initialize_vmm", parameters={}
        )

        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Log the action
        audit_log(
            session,
            user,
            current_user,
            "CREATE",
            str(host.id),
            host.fqdn,
            _("VMM initialization requested"),
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "VMM initialization requested. The agent will enable and "
                "start the vmd daemon."
            ),
        }


@router.post(
    "/host/{host_id}/virtualization/create-child",
    dependencies=[Depends(JWTBearer())],
)
async def create_child_host_request(
    host_id: str,
    request: CreateWslChildHostRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Request creation of a new child host (WSL instance).
    Requires CREATE_CHILD_HOST permission.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.CREATE_CHILD_HOST
        )

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        # Verify it's a Windows host for WSL
        if request.child_type == "wsl":
            if not host.platform or "Windows" not in host.platform:
                raise HTTPException(
                    status_code=400,
                    detail=_("WSL is only supported on Windows hosts"),
                )

        # Verify the agent is privileged
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Agent must be running with administrator privileges "
                    "to create child hosts"
                ),
            )

        # Determine the child name based on type
        # For LXD, use container_name; for VMM, use vm_name; for WSL, use distribution
        if request.child_type == "lxd":
            child_name = request.container_name
            if not child_name:
                raise HTTPException(
                    status_code=400,
                    detail=_("Container name is required for LXD containers"),
                )
        elif request.child_type == "vmm":
            child_name = request.vm_name
            if not child_name:
                raise HTTPException(
                    status_code=400,
                    detail=_("VM name is required for VMM virtual machines"),
                )
        else:
            # WSL uses distribution as the name
            child_name = request.distribution

        # Check for existing child host with same name
        existing = (
            session.query(models.HostChild)
            .filter(
                models.HostChild.parent_host_id == host_id,
                models.HostChild.child_name == child_name,
                models.HostChild.child_type == request.child_type,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail=_("A child host named '%s' already exists on this host")
                % child_name,
            )

        # Look up the distribution to get agent install commands
        # Match by install_identifier which is like "Ubuntu-24.04"
        distribution = (
            session.query(ChildHostDistribution)
            .filter(
                ChildHostDistribution.child_type == request.child_type,
                ChildHostDistribution.install_identifier == request.distribution,
                ChildHostDistribution.is_active == True,  # noqa: E712
            )
            .first()
        )

        # Parse agent_install_commands if it's a JSON string
        agent_install_commands = []
        if distribution and distribution.agent_install_commands:
            if isinstance(distribution.agent_install_commands, str):
                try:
                    agent_install_commands = json.loads(
                        distribution.agent_install_commands
                    )
                except json.JSONDecodeError:
                    agent_install_commands = []
            elif isinstance(distribution.agent_install_commands, list):
                agent_install_commands = distribution.agent_install_commands

        # Get server URL from config for agent configuration
        config = get_config()
        api_host = config["api"].get("host", "localhost")
        api_port = config["api"].get("port", 8443)

        # Determine if server is using HTTPS (based on SSL certificate config)
        key_file = config["api"].get("keyFile")
        cert_file = config["api"].get("certFile")
        use_https = bool(key_file and cert_file)

        # Use the actual server FQDN for the agent to connect back
        if api_host in (
            "0.0.0.0",
            "localhost",
            "127.0.0.1",
        ):  # nosec B104 - string comparison, not binding
            import socket

            try:
                server_url = socket.getfqdn()
            except Exception:
                server_url = "localhost"
        else:
            server_url = api_host

        # Generate auto-approve token if requested
        auto_approve_token = None
        if request.auto_approve:
            auto_approve_token = str(uuid.uuid4())

        # Create a placeholder HostChild record with "creating" status
        # This provides immediate feedback in the UI while the agent works
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        new_child = models.HostChild(
            parent_host_id=host_id,
            child_name=child_name,
            child_type=request.child_type,
            hostname=request.hostname,
            default_username=request.username,
            status="creating",
            distribution=distribution.distribution_name if distribution else None,
            distribution_version=(
                distribution.distribution_version if distribution else None
            ),
            auto_approve_token=auto_approve_token,
            created_at=now,
            updated_at=now,
        )
        session.add(new_child)
        session.flush()  # Get the ID assigned

        # Hash password before sending to agent (security: avoid clear text in transit)
        # Use bcrypt for all platforms - agent expects pre-hashed passwords
        password_hash = bcrypt.hashpw(
            request.password.encode("utf-8"), bcrypt.gensalt(rounds=8)
        ).decode("utf-8")

        # Queue a command to create the child host
        command_params = {
            "child_type": request.child_type,
            "distribution": request.distribution,
            "hostname": request.hostname,
            "username": request.username,
            "password_hash": password_hash,  # Send hashed, not clear text
            "agent_install_commands": agent_install_commands,
            "server_url": server_url,
            "server_port": api_port,
            "use_https": use_https,
            "child_host_id": str(new_child.id),  # Pass ID for status updates
        }
        # For LXD, include container_name
        if request.child_type == "lxd":
            command_params["container_name"] = request.container_name

        # For VMM, include vm_name, iso_url, and root_password_hash
        if request.child_type == "vmm":
            command_params["vm_name"] = request.vm_name
            if request.iso_url:
                command_params["iso_url"] = request.iso_url
            # VMM needs separate root password - hash it too
            root_pwd = (
                request.root_password if request.root_password else request.password
            )
            root_password_hash = bcrypt.hashpw(
                root_pwd.encode("utf-8"), bcrypt.gensalt(rounds=8)
            ).decode("utf-8")
            command_params["root_password_hash"] = root_password_hash

        # Include auto_approve_token if set
        if auto_approve_token:
            command_params["auto_approve_token"] = auto_approve_token

        command_message = create_command_message(
            command_type="create_child_host",
            parameters=command_params,
        )

        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Log the action
        audit_log(
            session,
            user,
            current_user,
            "CREATE",
            str(host.id),
            host.fqdn,
            _("Child host creation requested: %s") % request.distribution,
        )

        session.commit()

        # Build response message based on auto-approve setting
        if auto_approve_token:
            response_message = _(
                "Child host creation requested. This may take several minutes. "
                "The host will be automatically approved when it connects."
            )
        else:
            response_message = _(
                "Child host creation requested. This may take several minutes."
            )

        return {
            "result": True,
            "success": True,
            "message": response_message,
            "child_host_id": str(new_child.id),
            "auto_approve": bool(auto_approve_token),
        }
