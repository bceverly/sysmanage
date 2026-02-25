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
from backend.licensing.module_loader import module_loader
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


def _check_container_module():
    """Check if container_engine Pro+ module is available."""
    container_engine = module_loader.get_module("container_engine")
    if container_engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Container/VM management requires a SysManage Professional+ license. "
                "Please upgrade to access this feature."
            ),
        )


def _parse_agent_install_commands(distribution):
    """Parse agent_install_commands from a distribution record."""
    if not distribution or not distribution.agent_install_commands:
        return []
    if isinstance(distribution.agent_install_commands, str):
        try:
            return json.loads(distribution.agent_install_commands)
        except json.JSONDecodeError:
            return []
    if isinstance(distribution.agent_install_commands, list):
        return distribution.agent_install_commands
    return []


def _get_cloud_image_url(distribution):
    """Get cloud image URL from a distribution record, with HTTPS fallback."""
    if distribution and distribution.cloud_image_url:
        return distribution.cloud_image_url
    if distribution and distribution.install_identifier:
        # Fallback: use install_identifier if it's an HTTPS URL
        if distribution.install_identifier.startswith("https://"):
            return distribution.install_identifier
    return None


def _validate_platform_for_child_type(host, child_type):
    """Validate that the host platform supports the requested child type."""
    if child_type == "wsl":
        if not host.platform or "Windows" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=_("WSL is only supported on Windows hosts"),
            )
    elif child_type == "kvm":
        if not host.platform or "Linux" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=_("KVM is only supported on Linux hosts"),
            )


def _determine_child_name(request):
    """Determine the child host name based on child type and request fields."""
    name_configs = {
        "lxd": (
            "container_name",
            _("Container name is required for LXD containers"),
        ),
        "vmm": (
            "vm_name",
            _("VM name is required for VMM virtual machines"),
        ),
        "kvm": (
            "vm_name",
            _("VM name is required for KVM virtual machines"),
        ),
        "bhyve": (
            "vm_name",
            _("VM name is required for bhyve virtual machines"),
        ),
    }

    config = name_configs.get(request.child_type)
    if config:
        field_name, error_message = config
        child_name = getattr(request, field_name, None)
        if not child_name:
            raise HTTPException(status_code=400, detail=error_message)
        return child_name

    # WSL uses distribution as the name
    return request.distribution


def _resolve_server_url(api_host):
    """Resolve a routable server URL for child host agent configuration.

    If the API host is a listen-all or loopback address, determine the
    actual routable IP so child hosts (e.g. LXD containers) can connect
    back to the server.
    """
    if api_host not in (
        "0.0.0.0",  # nosec B104  # string comparison, not binding
        "localhost",
        "127.0.0.1",
    ):
        return api_host

    import socket

    server_url = "localhost"
    try:
        fqdn = socket.getfqdn()
        resolved_ip = socket.gethostbyname(fqdn)
        if not resolved_ip.startswith("127."):
            return resolved_ip
        # FQDN resolves to loopback; detect actual outbound IP using a
        # UDP socket.  connect() on SOCK_DGRAM merely selects the route
        # — no packet is sent, so the destination address is irrelevant.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))  # NOSONAR  # nosec B104
            server_url = sock.getsockname()[0]
        finally:
            sock.close()
    except Exception:  # nosec B110
        pass

    return server_url


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
    _check_container_module()

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
        _validate_platform_for_child_type(host, request.child_type)

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
        child_name = _determine_child_name(request)

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

        agent_install_commands = _parse_agent_install_commands(distribution)

        # Get server URL from config for agent configuration
        config = get_config()
        api_host = config["api"].get("host", "localhost")
        api_port = config["api"].get("port", 8443)

        # Determine if server is using HTTPS (based on SSL certificate config)
        key_file = config["api"].get("keyFile")
        cert_file = config["api"].get("certFile")
        use_https = bool(key_file and cert_file)

        # Use the actual server IP for the agent to connect back.
        # Child hosts (especially LXD containers) may not be able to resolve
        # the parent's FQDN, so prefer a routable IP address.
        server_url = _resolve_server_url(api_host)

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
        if request.child_type in ("vmm", "kvm", "bhyve"):
            # VMM/KVM/bhyve use OS-specific hash format
            password_hash = hash_password_for_os(
                request.password, request.distribution or ""
            )
        else:
            # WSL and LXD use bcrypt
            password_hash = bcrypt.hashpw(
                request.password.encode("utf-8"), bcrypt.gensalt(rounds=12)
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
            cloud_image_url = _get_cloud_image_url(distribution)
            if cloud_image_url:
                command_params["cloud_image_url"] = cloud_image_url

        # For bhyve, include vm_name, cloud_image_url, memory, disk_size, cpus
        if request.child_type == "bhyve":
            command_params["vm_name"] = request.vm_name
            command_params["memory"] = request.memory or "1G"
            command_params["disk_size"] = request.disk_size or "20G"
            command_params["cpus"] = request.cpus or 1
            cloud_image_url = _get_cloud_image_url(distribution)
            if cloud_image_url:
                command_params["cloud_image_url"] = cloud_image_url

        # Include auto_approve_token if set
        if auto_approve_token:
            command_params["auto_approve_token"] = auto_approve_token

        # Try plan-based creation for LXD/WSL if container_engine supports it
        used_plan_based = False
        if request.child_type in ("lxd", "wsl"):
            try:
                container_engine = module_loader.get_module("container_engine")
                if container_engine is not None:
                    service_cls = getattr(
                        container_engine, "ContainerEngineServiceImpl", None
                    )
                    if service_cls and hasattr(
                        service_cls, "create_container_with_plan"
                    ):
                        import logging as _logging

                        _ce_logger = _logging.getLogger("container_engine")
                        service = service_cls(
                            db=session, models=models, logger=_ce_logger
                        )
                        steps = service.create_container_with_plan(
                            child_type=request.child_type,
                            params=command_params,
                            host_id=host_id,
                            db_session=session,
                        )
                        if steps is not None:
                            used_plan_based = True
            except Exception:  # nosec B110
                pass  # Fall through to legacy path

        if not used_plan_based:
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
