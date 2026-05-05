"""
Child host control API endpoints (start, stop, restart).

NOTE: Container/VM lifecycle control is a Pro+ feature. The actual implementation
is provided by the container_engine module. This file provides stub endpoints
that return license-required errors for community users.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api.child_host_utils import (
    audit_log,
    get_host_or_404,
    get_user_with_role_check,
    verify_host_active,
)
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import db
from backend.persistence.models import HostChild
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()

MSG_CHILD_HOST_NOT_FOUND = "Child host not found"

# Per-action timeout (seconds) for the engine apply_deployment_plan envelope.
# The plan itself carries per-command timeouts; this is the outer ceiling.
_LIFECYCLE_ENGINE_TIMEOUT = 300


def _check_container_module():
    """Check if container_engine Pro+ module is available."""
    container_engine = module_loader.get_module("container_engine")
    if container_engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Container lifecycle management requires a SysManage Professional+ license. "
                "Please upgrade to access this feature."
            ),
        )


def _build_lifecycle_plan(child_type: str, action: str, name: str):
    """Pick the right engine + builder and return the plan, or None.

    Returns None when no engine plan-builder exists for ``child_type``,
    which is the signal for callers to fall back to the legacy WS path.
    """
    if action not in ("start", "stop", "restart"):
        return None

    if child_type in ("kvm", "bhyve", "vmm"):
        virt_engine = module_loader.get_module("virtualization_engine")
        if virt_engine is None:
            return None
        if child_type == "kvm":
            return virt_engine.build_kvm_lifecycle_plan(action=action, vm_name=name)
        if child_type == "bhyve":
            return virt_engine.build_bhyve_lifecycle_plan(action=action, vm_name=name)
        return virt_engine.build_vmm_lifecycle_plan(action=action, vm_name=name)

    if child_type in ("lxd", "wsl"):
        container_engine = module_loader.get_module("container_engine")
        if container_engine is None:
            return None
        if child_type == "lxd":
            return container_engine.build_lxd_lifecycle_plan(
                action=action, container_name=name
            )
        return container_engine.build_wsl_lifecycle_plan(
            action=action, distro_name=name
        )

    return None


def _try_update_agent_plan_dispatch(
    child_type: str,
    child_name: str,
    distribution_id: str,
    host_id: str,
    child_id: str,
    session,
) -> bool:
    """Dispatch an update-agent plan via container_engine for LXD/WSL.

    KVM/bhyve/VMM child hosts have their own registered agent — operators
    should use the standard update-agent flow on the linked Host rather
    than this child-host shortcut.  Returns False for those types so the
    caller falls through to the legacy WS dispatch.
    """
    if child_type not in ("lxd", "wsl"):
        return False
    container_engine = module_loader.get_module("container_engine")
    if container_engine is None:
        return False
    builder_name = (
        "build_lxd_update_agent_plan"
        if child_type == "lxd"
        else "build_wsl_update_agent_plan"
    )
    builder = getattr(container_engine, builder_name, None)
    if builder is None:
        return False

    # Look up the child's distribution to get the install commands.
    # pylint: disable=import-outside-toplevel
    from backend.persistence.models import ChildHostDistribution
    import json as _json

    install_commands = []
    if distribution_id:
        dist = (
            session.query(ChildHostDistribution)
            .filter(ChildHostDistribution.id == distribution_id)
            .first()
        )
        if dist and dist.agent_install_commands:
            try:
                install_commands = _json.loads(dist.agent_install_commands) or []
            except (TypeError, ValueError):
                install_commands = []

    if not install_commands:
        return False
    try:
        plan = builder(child_name, install_commands)
        # pylint: disable=import-outside-toplevel
        from backend.services.proplus_dispatch import (
            enqueue_apply_plan,
            register_child_host_correlation,
        )

        message_id = enqueue_apply_plan(
            host_id=str(host_id), plan=plan, timeout=_LIFECYCLE_ENGINE_TIMEOUT * 4
        )
        register_child_host_correlation(
            message_id, str(child_id), "update_agent", str(host_id)
        )
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.getLogger(__name__).warning(
            "update_agent plan path failed for %s/%s on host %s: %s",
            child_type,
            child_name,
            host_id,
            exc,
        )
        return False


def _try_lifecycle_plan_dispatch(
    child_type: str,
    action: str,
    vm_name: str,
    host_id: str,
    child_id: str = "",
) -> bool:
    """Dispatch a lifecycle action via a Pro+ engine plan path.

    Tries virtualization_engine for kvm/bhyve/vmm and container_engine for
    lxd/wsl.  Returns True if a plan was queued, False to fall back to the
    legacy multi-step WS dispatch (which routes to the agent's native
    ``child_host_<type>_lifecycle`` handlers).

    When ``child_id`` is supplied the dispatch is registered with the Pro+
    correlation map so the result handler updates the HostChild row's
    status; when omitted the operation runs but its outcome won't update
    the database.
    """
    try:
        plan = _build_lifecycle_plan(child_type, action, vm_name)
        if plan is None:
            return False

        # pylint: disable=import-outside-toplevel
        from backend.services.proplus_dispatch import (
            enqueue_apply_plan,
            register_child_host_correlation,
        )

        message_id = enqueue_apply_plan(
            host_id=str(host_id), plan=plan, timeout=_LIFECYCLE_ENGINE_TIMEOUT
        )
        if child_id:
            register_child_host_correlation(
                message_id, str(child_id), action, str(host_id)
            )
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.getLogger(__name__).warning(
            "Lifecycle plan path failed for %s/%s on host %s; falling back to "
            "legacy WS dispatch: %s",
            child_type,
            action,
            host_id,
            exc,
        )
        return False


@router.post(
    "/host/{host_id}/children/{child_id}/start",
    dependencies=[Depends(JWTBearer())],
)
async def start_child_host(
    host_id: str,
    child_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Start a stopped child host.
    Requires START_CHILD_HOST permission.

    This is a Pro+ feature. Requires container_engine module.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.START_CHILD_HOST
        )

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        child = (
            session.query(HostChild)
            .filter(
                HostChild.id == child_id,
                HostChild.parent_host_id == host.id,
            )
            .first()
        )
        if not child:
            raise HTTPException(status_code=404, detail=_(MSG_CHILD_HOST_NOT_FOUND))

        used_plan_path = _try_lifecycle_plan_dispatch(
            child.child_type, "start", child.child_name, host_id, str(child.id)
        )

        if not used_plan_path:
            # LEGACY: superseded by engine path for kvm/bhyve/vmm.  Still
            # active for lxd/wsl until their lifecycle plan-builders land
            # (audit PR-04, PR-06).
            queue_ops = QueueOperations()

            command_message = create_command_message(
                command_type="start_child_host",
                parameters={
                    "child_name": child.child_name,
                    "child_type": child.child_type,
                },
            )

            queue_ops.enqueue_message(
                message_type="command",
                message_data=command_message,
                direction=QueueDirection.OUTBOUND,
                host_id=host_id,
                db=session,
            )

        audit_log(
            session,
            user,
            current_user,
            "UPDATE",
            str(host.id),
            host.fqdn,
            _("Child host start requested: %s") % child.child_name,
        )

        session.commit()

        return {
            "result": True,
            "message": _("Child host start requested"),
        }


@router.post(
    "/host/{host_id}/children/{child_id}/stop",
    dependencies=[Depends(JWTBearer())],
)
async def stop_child_host(
    host_id: str,
    child_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Stop a running child host.
    Requires STOP_CHILD_HOST permission.

    This is a Pro+ feature. Requires container_engine module.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.STOP_CHILD_HOST
        )

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        child = (
            session.query(HostChild)
            .filter(
                HostChild.id == child_id,
                HostChild.parent_host_id == host.id,
            )
            .first()
        )
        if not child:
            raise HTTPException(status_code=404, detail=_(MSG_CHILD_HOST_NOT_FOUND))

        used_plan_path = _try_lifecycle_plan_dispatch(
            child.child_type, "stop", child.child_name, host_id, str(child.id)
        )

        if not used_plan_path:
            # LEGACY: superseded by engine path for kvm/bhyve/vmm.  Still
            # active for lxd/wsl until their lifecycle plan-builders land
            # (audit PR-04, PR-06).
            queue_ops = QueueOperations()

            command_message = create_command_message(
                command_type="stop_child_host",
                parameters={
                    "child_name": child.child_name,
                    "child_type": child.child_type,
                },
            )

            queue_ops.enqueue_message(
                message_type="command",
                message_data=command_message,
                direction=QueueDirection.OUTBOUND,
                host_id=host_id,
                db=session,
            )

        audit_log(
            session,
            user,
            current_user,
            "UPDATE",
            str(host.id),
            host.fqdn,
            _("Child host stop requested: %s") % child.child_name,
        )

        session.commit()

        return {
            "result": True,
            "message": _("Child host stop requested"),
        }


@router.post(
    "/host/{host_id}/children/{child_id}/restart",
    dependencies=[Depends(JWTBearer())],
)
async def restart_child_host(
    host_id: str,
    child_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Restart a child host.
    Requires RESTART_CHILD_HOST permission.

    This is a Pro+ feature. Requires container_engine module.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.RESTART_CHILD_HOST
        )

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        child = (
            session.query(HostChild)
            .filter(
                HostChild.id == child_id,
                HostChild.parent_host_id == host.id,
            )
            .first()
        )
        if not child:
            raise HTTPException(status_code=404, detail=_(MSG_CHILD_HOST_NOT_FOUND))

        used_plan_path = _try_lifecycle_plan_dispatch(
            child.child_type, "restart", child.child_name, host_id, str(child.id)
        )

        if not used_plan_path:
            # LEGACY: superseded by engine path for kvm/bhyve/vmm.  Still
            # active for lxd/wsl until their lifecycle plan-builders land
            # (audit PR-04, PR-06).
            queue_ops = QueueOperations()

            command_message = create_command_message(
                command_type="restart_child_host",
                parameters={
                    "child_name": child.child_name,
                    "child_type": child.child_type,
                },
            )

            queue_ops.enqueue_message(
                message_type="command",
                message_data=command_message,
                direction=QueueDirection.OUTBOUND,
                host_id=host_id,
                db=session,
            )

        audit_log(
            session,
            user,
            current_user,
            "UPDATE",
            str(host.id),
            host.fqdn,
            _("Child host restart requested: %s") % child.child_name,
        )

        session.commit()

        return {
            "result": True,
            "message": _("Child host restart requested"),
        }


@router.post(
    "/host/{host_id}/children/{child_id}/update-agent",
    dependencies=[Depends(JWTBearer())],
)
async def update_child_agent(
    host_id: str,
    child_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Update the sysmanage-agent on a child host via its parent.
    Requires UPDATE_AGENT permission.

    No license check — agent update should work for community users too.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.UPDATE_AGENT
        )

        host = get_host_or_404(session, host_id)
        verify_host_active(host)

        child = (
            session.query(HostChild)
            .filter(
                HostChild.id == child_id,
                HostChild.parent_host_id == host.id,
            )
            .first()
        )
        if not child:
            raise HTTPException(status_code=404, detail=_(MSG_CHILD_HOST_NOT_FOUND))

        # Look up the distribution_id for the engine path (it needs the
        # install commands stored on the distribution row).
        distribution_id = None
        if child.distribution and child.distribution_version:
            from backend.persistence.models import ChildHostDistribution

            dist_row = (
                session.query(ChildHostDistribution)
                .filter(
                    ChildHostDistribution.child_type == child.child_type,
                    ChildHostDistribution.distribution_name == child.distribution,
                    ChildHostDistribution.distribution_version
                    == child.distribution_version,
                )
                .first()
            )
            if dist_row:
                distribution_id = str(dist_row.id)

        used_plan_path = _try_update_agent_plan_dispatch(
            child.child_type,
            child.child_name,
            distribution_id or "",
            host_id,
            str(child.id),
            session,
        )

        if not used_plan_path:
            # LEGACY: superseded by container_engine.build_lxd_update_agent_plan /
            # build_wsl_update_agent_plan for LXD/WSL.  KVM/bhyve/VMM child
            # hosts route here intentionally — once their inner agent
            # registers, operators should use the standard Host-level
            # update-agent flow rather than this child-host shortcut.
            queue_ops = QueueOperations()

            command_message = create_command_message(
                command_type="update_child_agent",
                parameters={
                    "child_name": child.child_name,
                    "child_type": child.child_type,
                    "distribution": child.distribution,
                },
            )

            queue_ops.enqueue_message(
                message_type="command",
                message_data=command_message,
                direction=QueueDirection.OUTBOUND,
                host_id=host_id,
                db=session,
            )

        audit_log(
            session,
            user,
            current_user,
            "UPDATE",
            str(host.id),
            host.fqdn,
            _("Child agent update requested: %s") % child.child_name,
        )

        session.commit()

        return {
            "result": True,
            "message": _("Child agent update requested"),
        }
