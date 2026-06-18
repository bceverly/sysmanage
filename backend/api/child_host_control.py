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
    authorize_on_main,
    get_host_or_404,
    raise_engine_declined,
    verify_host_active,
)
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import db
from backend.persistence.models import HostChild
from backend.persistence.partitions import request_sessionmaker
from backend.security.roles import SecurityRoles
from backend.utils.verbosity_logger import sanitize_log

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
    which is the signal for the caller to surface a 502.
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


def _resolve_agent_install_commands(session, distribution_id: str) -> list:
    """Engine-first / DB-fallback resolution of per-distro install
    recipes for the LXD/WSL update-agent path.

    Phase 11.8 made ``virtualization_engine._AGENT_INSTALL`` the
    source of truth for per-distro install recipes; the DB row's
    ``agent_install_commands`` column is a back-compat fallback for
    OSS-only deployments that don't have the Pro+ engine loaded.
    Without the engine-first lookup, an LXD/WSL host whose DB row
    still carries the legacy curl-and-dpkg recipe would re-install
    via direct download instead of routing through the PPA/Copr/OBS
    channel the rest of the upgrade machinery (apt-get upgrade,
    dnf upgrade) expects — leaving future upgrades silently broken.

    Returns an empty list when neither source produces a recipe.
    """
    # pylint: disable=import-outside-toplevel
    from backend.persistence.models import ChildHostDistribution

    if not distribution_id:
        return []
    dist = (
        session.query(ChildHostDistribution)
        .filter(ChildHostDistribution.id == distribution_id)
        .first()
    )
    if dist is None:
        return []

    # Engine-first, DB-fallback (see helpers below).
    return _engine_install_commands(dist) or _db_install_commands(dist)


def _engine_install_commands(dist) -> list:
    """Engine-resolved per-distro install recipe, or ``[]`` if unavailable."""
    virt_engine = module_loader.get_module("virtualization_engine")
    if virt_engine is None:
        return []
    try:
        engine_cmds = virt_engine.get_agent_install_commands(
            getattr(dist, "distribution_name", "") or "",
            getattr(dist, "distribution_version", "") or "",
        )
    except Exception:  # pylint: disable=broad-exception-caught
        return []
    return list(engine_cmds) if engine_cmds else []


def _db_install_commands(dist) -> list:
    """DB-stored per-distro install recipe fallback, or ``[]`` if absent/invalid."""
    # pylint: disable=import-outside-toplevel
    import json as _json

    if not dist.agent_install_commands:
        return []
    try:
        return _json.loads(dist.agent_install_commands) or []
    except (TypeError, ValueError):
        return []


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
    caller surfaces a 502 to the user.
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

    install_commands = _resolve_agent_install_commands(session, distribution_id)
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
            sanitize_log(host_id),
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
    lxd/wsl.  Returns True if a plan was queued, False on engine declination
    (caller surfaces a 502 to the user).

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
            "Lifecycle plan path failed for %s/%s on host %s; engine path declined: %s",
            child_type,
            action,
            sanitize_log(host_id),
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

    # Authz is server-global; child-host data + audit are tenant-scoped.
    user = authorize_on_main(current_user, SecurityRoles.START_CHILD_HOST)
    session_local = request_sessionmaker()

    with session_local() as session:
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
            raise_engine_declined()

        audit_log(
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

    # Authz is server-global; child-host data + audit are tenant-scoped.
    user = authorize_on_main(current_user, SecurityRoles.STOP_CHILD_HOST)
    session_local = request_sessionmaker()

    with session_local() as session:
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
            raise_engine_declined()

        audit_log(
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

    # Authz is server-global; child-host data + audit are tenant-scoped.
    user = authorize_on_main(current_user, SecurityRoles.RESTART_CHILD_HOST)
    session_local = request_sessionmaker()

    with session_local() as session:
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
            raise_engine_declined()

        audit_log(
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
    Requires UPDATE_AGENT permission and a Pro+ license (child hosts
    are a Pro+ feature; the route would otherwise operate on records
    that cannot exist in an OSS deployment).
    """
    _check_container_module()
    # Authz is server-global; child-host data + audit are tenant-scoped.
    user = authorize_on_main(current_user, SecurityRoles.UPDATE_AGENT)
    session_local = request_sessionmaker()
    # ChildHostDistribution is server-global reference data — its lookups (here
    # and inside _try_update_agent_plan_dispatch) run on the bootstrap engine,
    # not the tenant database, which carries no copy of the distribution rows.
    ref_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())

    with session_local() as session:
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

        # Resolve the distribution_id + install recipe on the server-global
        # engine (the engine path needs the install commands stored on the
        # distribution row).
        with ref_local() as ref_session:
            distribution_id = None
            if child.distribution and child.distribution_version:
                from backend.persistence.models import ChildHostDistribution

                dist_row = (
                    ref_session.query(ChildHostDistribution)
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
                ref_session,
            )

        if not used_plan_path:
            raise_engine_declined()

        audit_log(
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
