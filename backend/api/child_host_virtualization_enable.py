"""
Virtualization enable/initialize API endpoints.
Handles enabling and initializing virtualization platforms (WSL, LXD, VMM, KVM).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api.child_host_models import ConfigureKvmNetworkingRequest
from backend.api.child_host_utils import (
    audit_log,
    get_host_or_404,
    get_user_with_role_check,
    verify_host_active,
)
from backend.api.error_constants import error_kvm_linux_only
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import db
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()
queue_ops = QueueOperations()


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
    Requires ENABLE_WSL permission.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(session, current_user, SecurityRoles.ENABLE_WSL)

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
    Requires ENABLE_LXD permission.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(session, current_user, SecurityRoles.ENABLE_LXD)

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
    Requires ENABLE_VMM permission.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(session, current_user, SecurityRoles.ENABLE_VMM)

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
    "/host/{host_id}/virtualization/initialize-kvm",
    dependencies=[Depends(JWTBearer())],
)
async def initialize_kvm(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Initialize KVM/libvirt on a Linux host.
    Installs libvirt packages if not installed, enables and starts libvirtd,
    and configures the default network.
    Requires ENABLE_KVM permission.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(session, current_user, SecurityRoles.ENABLE_KVM)

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        # Verify it's a Linux host (KVM is Linux-only)
        if not host.platform or "Linux" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=error_kvm_linux_only(),
            )

        # Verify the agent is privileged (needed to install/start libvirtd)
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Agent must be running with root privileges to initialize KVM"
                ),
            )

        # Queue a command to initialize KVM
        command_message = create_command_message(
            command_type="initialize_kvm", parameters={}
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
            _("KVM initialization requested"),
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "KVM initialization requested. The agent will install libvirt "
                "and configure KVM for virtual machine management."
            ),
        }


@router.post(
    "/host/{host_id}/virtualization/initialize-bhyve",
    dependencies=[Depends(JWTBearer())],
)
async def initialize_bhyve(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Initialize bhyve on a FreeBSD host.
    Loads vmm.ko and configures /boot/loader.conf for persistence.
    Requires ENABLE_BHYVE permission.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.ENABLE_BHYVE
        )

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        # Verify it's a FreeBSD host (bhyve is FreeBSD-only)
        if not host.platform or "FreeBSD" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=_("bhyve is only supported on FreeBSD hosts"),
            )

        # Verify the agent is privileged (needed to load vmm.ko)
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Agent must be running with root privileges to initialize bhyve"
                ),
            )

        # Queue a command to initialize bhyve
        command_message = create_command_message(
            command_type="initialize_bhyve", parameters={}
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
            _("bhyve initialization requested"),
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "bhyve initialization requested. The agent will load vmm.ko "
                "and configure the system for bhyve virtual machines."
            ),
        }


@router.post(
    "/host/{host_id}/virtualization/disable-bhyve",
    dependencies=[Depends(JWTBearer())],
)
async def disable_bhyve(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Disable bhyve on a FreeBSD host.
    Unloads vmm.ko and removes the persistent configuration from /boot/loader.conf.
    Note: This will fail if any VMs are running.
    Requires ENABLE_BHYVE permission.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.ENABLE_BHYVE
        )

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        # Verify it's a FreeBSD host (bhyve is FreeBSD-only)
        if not host.platform or "FreeBSD" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=_("bhyve is only supported on FreeBSD hosts"),
            )

        # Verify the agent is privileged (needed to unload vmm.ko)
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_("Agent must be running with root privileges to disable bhyve"),
            )

        # Queue a command to disable bhyve
        command_message = create_command_message(
            command_type="disable_bhyve", parameters={}
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
            "DELETE",
            str(host.id),
            host.fqdn,
            _("bhyve disable requested"),
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "bhyve disable requested. The agent will unload vmm.ko "
                "and update the system configuration. This will fail if any VMs are running."
            ),
        }


@router.post(
    "/host/{host_id}/virtualization/enable-kvm-modules",
    dependencies=[Depends(JWTBearer())],
)
async def enable_kvm_modules(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Enable KVM kernel modules on a Linux host.
    Loads the kvm and kvm_intel/kvm_amd kernel modules via modprobe.
    Requires ENABLE_KVM permission.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(session, current_user, SecurityRoles.ENABLE_KVM)

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        # Verify it's a Linux host (KVM is Linux-only)
        if not host.platform or "Linux" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=error_kvm_linux_only(),
            )

        # Verify the agent is privileged (needed to run modprobe)
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Agent must be running with root privileges to enable KVM modules"
                ),
            )

        # Queue a command to enable KVM modules
        command_message = create_command_message(
            command_type="enable_kvm_modules", parameters={}
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
            _("KVM modules enable requested"),
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "KVM modules enable requested. The agent will load the KVM "
                "kernel modules via modprobe."
            ),
        }


@router.post(
    "/host/{host_id}/virtualization/disable-kvm-modules",
    dependencies=[Depends(JWTBearer())],
)
async def disable_kvm_modules(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Disable KVM kernel modules on a Linux host.
    Unloads the kvm and kvm_intel/kvm_amd kernel modules via modprobe -r.
    Note: This will fail if any VMs are running.
    Requires ENABLE_KVM permission.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(session, current_user, SecurityRoles.ENABLE_KVM)

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        # Verify it's a Linux host (KVM is Linux-only)
        if not host.platform or "Linux" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=error_kvm_linux_only(),
            )

        # Verify the agent is privileged (needed to run modprobe)
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Agent must be running with root privileges to disable KVM modules"
                ),
            )

        # Queue a command to disable KVM modules
        command_message = create_command_message(
            command_type="disable_kvm_modules", parameters={}
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
            "DELETE",
            str(host.id),
            host.fqdn,
            _("KVM modules disable requested"),
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "KVM modules disable requested. The agent will unload the KVM "
                "kernel modules via modprobe -r. This will fail if any VMs are running."
            ),
        }


@router.post(
    "/host/{host_id}/virtualization/configure-kvm-networking",
    dependencies=[Depends(JWTBearer())],
)
async def configure_kvm_networking(
    host_id: str,
    request: ConfigureKvmNetworkingRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Configure KVM networking on a Linux host.
    Supports NAT (default) and bridged networking modes.
    Requires ENABLE_KVM permission.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(session, current_user, SecurityRoles.ENABLE_KVM)

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        # Verify it's a Linux host (KVM is Linux-only)
        if not host.platform or "Linux" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=_("KVM networking is only supported on Linux hosts"),
            )

        # Verify the agent is privileged (needed to configure networking)
        if not host.is_agent_privileged:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Agent must be running with root privileges to configure KVM networking"
                ),
            )

        # Validate bridged mode requires bridge interface
        if request.mode == "bridged" and not request.bridge:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Bridge interface name is required for bridged networking mode"
                ),
            )

        # Queue a command to configure KVM networking
        parameters = {
            "mode": request.mode,
        }
        if request.network_name:
            parameters["network_name"] = request.network_name
        if request.bridge:
            parameters["bridge"] = request.bridge

        command_message = create_command_message(
            command_type="setup_kvm_networking", parameters=parameters
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
            "UPDATE",
            str(host.id),
            host.fqdn,
            _("KVM networking configuration requested: %s mode") % request.mode,
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "KVM networking configuration requested. The agent will configure "
                "the %s network."
            )
            % request.mode,
        }


@router.get(
    "/host/{host_id}/virtualization/kvm-networks",
    dependencies=[Depends(JWTBearer())],
)
async def list_kvm_networks(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    List KVM/libvirt networks on a Linux host.
    Also returns available Linux bridges for bridged networking setup.
    Requires VIEW_CHILD_HOSTS permission.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        get_user_with_role_check(session, current_user, SecurityRoles.VIEW_CHILD_HOSTS)

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        # Verify it's a Linux host (KVM is Linux-only)
        if not host.platform or "Linux" not in host.platform:
            raise HTTPException(
                status_code=400,
                detail=_("KVM networks are only available on Linux hosts"),
            )

        # Queue a command to list KVM networks
        command_message = create_command_message(
            command_type="list_kvm_networks", parameters={}
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
                "KVM network list requested. Results will be returned shortly."
            ),
        }
