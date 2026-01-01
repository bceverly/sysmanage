"""
Virtualization management API endpoints.
Handles WSL, LXD, VMM, and KVM status, enabling, and creating child hosts.

This module is the main router that includes sub-routers for:
- Status endpoints (child_host_virtualization_status)
- Enable/Initialize endpoints (child_host_virtualization_enable)
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
from backend.api.child_host_virtualization_enable import (
    router as enable_router,
)
from backend.api.child_host_virtualization_status import (
    router as status_router,
)
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config.config import get_config
from backend.i18n import _
from backend.persistence import db, models
from backend.persistence.models import ChildHostDistribution
from backend.security.roles import SecurityRoles
from backend.utils.password_hash import hash_password_for_os
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

# Main router that includes sub-routers
router = APIRouter()
queue_ops = QueueOperations()

# Include status endpoints router
router.include_router(status_router)

# Include enable/initialize endpoints router
router.include_router(enable_router)


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

        # Verify platform compatibility for child type
        if request.child_type == "wsl":
            if not host.platform or "Windows" not in host.platform:
                raise HTTPException(
                    status_code=400,
                    detail=_("WSL is only supported on Windows hosts"),
                )
        elif request.child_type == "kvm":
            if not host.platform or "Linux" not in host.platform:
                raise HTTPException(
                    status_code=400,
                    detail=_("KVM is only supported on Linux hosts"),
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
        # For LXD, use container_name; for VMM/KVM, use vm_name; for WSL, use distribution
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
        elif request.child_type == "kvm":
            child_name = request.vm_name
            if not child_name:
                raise HTTPException(
                    status_code=400,
                    detail=_("VM name is required for KVM virtual machines"),
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
        # Use appropriate hash format based on target OS:
        # - Debian/Ubuntu: SHA-512 crypt ($6$...) for preseed/cloud-init
        # - Alpine/OpenBSD: bcrypt ($2b$...)
        # - WSL: bcrypt (default)
        if request.child_type == "vmm":
            # VMM uses OS-specific hash format
            password_hash = hash_password_for_os(
                request.password, request.distribution or ""
            )
        elif request.child_type == "kvm":
            # KVM cloud-init uses SHA-512 crypt format for most Linux distros
            password_hash = hash_password_for_os(
                request.password, request.distribution or ""
            )
        else:
            # WSL and LXD use bcrypt
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
            # VMM needs separate root password - use OS-appropriate hash
            root_pwd = (
                request.root_password if request.root_password else request.password
            )
            root_password_hash = hash_password_for_os(
                root_pwd, request.distribution or ""
            )
            command_params["root_password_hash"] = root_password_hash

        # For KVM, include vm_name, cloud_image_url, memory, disk_size, cpus
        if request.child_type == "kvm":
            command_params["vm_name"] = request.vm_name
            command_params["memory"] = request.memory or "2G"
            command_params["disk_size"] = request.disk_size or "20G"
            command_params["cpus"] = request.cpus or 2
            # Get cloud_image_url from the distribution record
            if distribution and distribution.cloud_image_url:
                command_params["cloud_image_url"] = distribution.cloud_image_url
            elif distribution and distribution.install_identifier:
                # Fallback: use install_identifier if it's a URL
                if distribution.install_identifier.startswith("http"):
                    command_params["cloud_image_url"] = distribution.install_identifier

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

        # Log the action with full details for debugging
        audit_log(
            session,
            user,
            current_user,
            "CREATE",
            str(host.id),
            host.fqdn,
            _("Child host creation requested: %s (%s)")
            % (child_name, request.distribution),
            details={
                "child_name": child_name,
                "child_type": request.child_type,
                "distribution": request.distribution,
                "hostname": request.hostname,
                "vm_name": (
                    request.vm_name if request.child_type in ("vmm", "kvm") else None
                ),
                "container_name": (
                    request.container_name if request.child_type == "lxd" else None
                ),
                "memory": request.memory if request.child_type == "kvm" else None,
                "disk_size": request.disk_size if request.child_type == "kvm" else None,
                "cpus": request.cpus if request.child_type == "kvm" else None,
            },
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
