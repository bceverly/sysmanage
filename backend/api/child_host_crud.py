"""
Child host CRUD (Create, Read, Update, Delete) API endpoints.

NOTE: Container/VM creation and deletion are Pro+ features. The actual implementation
is provided by the container_engine module. This file provides stub endpoints
for write operations that return license-required errors for community users.
Read-only listing operations remain open source.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import joinedload, sessionmaker

from backend.api.child_host_models import (
    ChildHostResponse,
    CreateChildHostRequest,
    CreateDistributionRequest,
    DistributionDetailResponse,
    DistributionResponse,
    UpdateDistributionRequest,
)
from backend.api.child_host_utils import (
    audit_log,
    authorize_on_main,
    get_host_or_404,
    get_user_with_role_check,
    raise_engine_declined,
    verify_host_active,
)
from backend.api.error_constants import error_distribution_not_found
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import db
from backend.persistence.models import ChildHostDistribution, Host, HostChild
from backend.persistence.partitions import request_sessionmaker
from backend.security.roles import SecurityRoles

router = APIRouter()


def _effective_child_status(child) -> str:
    """Return the effective status for a child host.

    When a child host has a linked Host record (its own agent registered),
    use the linked Host's connectivity state so the child hosts screen is
    consistent with the main Hosts screen.  A bhyve VM process can be alive
    while the agent inside it is unreachable — in that case the status
    should reflect the agent state, not the hypervisor state.
    """
    if child.child_host_id and child.child_host:
        linked_host = child.child_host
        if not linked_host.active or linked_host.status == "down":
            return "stopped"
    return child.status


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


@router.get(
    "/host/{host_id}/children",
    dependencies=[Depends(JWTBearer())],
    response_model=List[ChildHostResponse],
)
async def list_child_hosts(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    List all child hosts on a parent host.
    Requires VIEW_CHILD_HOST permission and a Pro+ license.
    """
    _check_container_module()
    # Authz is server-global (User lives in the bootstrap DB); child-host data
    # is tenant-scoped — route it to the active tenant's database.
    authorize_on_main(current_user, SecurityRoles.VIEW_CHILD_HOST)
    session_local = request_sessionmaker()

    with session_local() as session:
        host = get_host_or_404(session, host_id)

        # Query child hosts for this parent
        child_hosts = (
            session.query(HostChild)
            .options(joinedload(HostChild.child_host))
            .filter(HostChild.parent_host_id == host.id)
            .order_by(HostChild.created_at.desc())
            .all()
        )

        return [
            ChildHostResponse(
                id=str(child.id),
                parent_host_id=str(child.parent_host_id),
                child_host_id=str(child.child_host_id) if child.child_host_id else None,
                child_name=child.child_name,
                child_type=child.child_type,
                distribution=child.distribution,
                distribution_version=child.distribution_version,
                hostname=child.hostname,
                status=_effective_child_status(child),
                installation_step=child.installation_step,
                error_message=child.error_message,
                created_at=child.created_at.isoformat() if child.created_at else None,
                installed_at=(
                    child.installed_at.isoformat() if child.installed_at else None
                ),
                reboot_required=(
                    child.child_host.reboot_required
                    if child.child_host_id and child.child_host
                    else False
                ),
                agent_version=(
                    child.child_host.agent_version
                    if child.child_host_id and child.child_host
                    else None
                ),
            )
            for child in child_hosts
        ]


@router.post(
    "/host/{host_id}/children",
    dependencies=[Depends(JWTBearer())],
)
async def create_child_host(
    host_id: str,
    request: CreateChildHostRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Create a new child host (VM, container, or WSL instance).
    Requires CREATE_CHILD_HOST permission.

    This is a Pro+ feature. Requires container_engine module.
    """
    _check_container_module()


@router.get(
    "/host/{host_id}/children/{child_id}",
    dependencies=[Depends(JWTBearer())],
    response_model=ChildHostResponse,
)
async def get_child_host(
    host_id: str,
    child_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Get details of a specific child host.
    Requires VIEW_CHILD_HOST permission and a Pro+ license.
    """
    _check_container_module()
    # Authz is server-global; child-host data is tenant-scoped.
    authorize_on_main(current_user, SecurityRoles.VIEW_CHILD_HOST)
    session_local = request_sessionmaker()

    with session_local() as session:
        host = get_host_or_404(session, host_id)

        child = (
            session.query(HostChild)
            .options(joinedload(HostChild.child_host))
            .filter(
                HostChild.id == child_id,
                HostChild.parent_host_id == host.id,
            )
            .first()
        )
        if not child:
            raise HTTPException(status_code=404, detail=_("Child host not found"))

        return ChildHostResponse(
            id=str(child.id),
            parent_host_id=str(child.parent_host_id),
            child_host_id=str(child.child_host_id) if child.child_host_id else None,
            child_name=child.child_name,
            child_type=child.child_type,
            distribution=child.distribution,
            distribution_version=child.distribution_version,
            hostname=child.hostname,
            status=_effective_child_status(child),
            installation_step=child.installation_step,
            error_message=child.error_message,
            created_at=child.created_at.isoformat() if child.created_at else None,
            installed_at=child.installed_at.isoformat() if child.installed_at else None,
            reboot_required=(
                child.child_host.reboot_required
                if child.child_host_id and child.child_host
                else False
            ),
            agent_version=(
                child.child_host.agent_version
                if child.child_host_id and child.child_host
                else None
            ),
        )


def _dispatch_delete_plan(plan, host_id: str, child_id: str, timeout: int) -> bool:
    """Enqueue a delete plan and register a child_host_op correlation."""
    from backend.services.proplus_dispatch import (
        enqueue_apply_plan,
        register_child_host_correlation,
    )

    message_id = enqueue_apply_plan(host_id=str(host_id), plan=plan, timeout=timeout)
    register_child_host_correlation(message_id, child_id, "delete", str(host_id))
    return True


def _try_bhyve_plan_based_deletion(vm_name: str, host_id: str, child_id: str) -> bool:
    """Dispatch a bhyve `vm stop` + `vm destroy -f` plan via the engine."""
    virt_engine = module_loader.get_module("virtualization_engine")
    if virt_engine is None:
        return False
    try:
        plan = virt_engine.build_bhyve_delete_plan(vm_name)
        return _dispatch_delete_plan(plan, host_id, child_id, 300)
    except Exception:  # nosec B110  pylint: disable=broad-exception-caught
        return False


def _try_vmm_plan_based_deletion(vm_name: str, host_id: str, child_id: str) -> bool:
    """Dispatch an OpenBSD vmctl stop + vm.conf removal plan via engine."""
    virt_engine = module_loader.get_module("virtualization_engine")
    if virt_engine is None:
        return False
    try:
        plan = virt_engine.build_vmm_delete_plan(vm_name)
        return _dispatch_delete_plan(plan, host_id, child_id, 300)
    except Exception:  # nosec B110  pylint: disable=broad-exception-caught
        return False


def _try_kvm_plan_based_deletion(vm_name: str, host_id: str, child_id: str) -> bool:
    """Dispatch a KVM destroy/undefine plan via the virtualization_engine.

    Returns True if the plan was dispatched, False if the engine isn't
    loaded (caller surfaces a 502 to the user — the agent stub does not honour the
    agent's native delete_child_host handler).
    """
    virt_engine = module_loader.get_module("virtualization_engine")
    if virt_engine is None:
        return False
    try:
        delete_req = virt_engine.VmDeleteRequest(vm_name=vm_name, purge_storage=True)
        plan = virt_engine.build_kvm_delete_plan(delete_req)
        return _dispatch_delete_plan(plan, host_id, child_id, 300)
    except Exception:  # nosec B110  pylint: disable=broad-exception-caught
        return False


def _try_lxd_plan_based_deletion(
    container_name: str, host_id: str, child_id: str
) -> bool:
    """Dispatch an `lxc delete --force` plan via the container_engine."""
    container_engine = module_loader.get_module("container_engine")
    if container_engine is None:
        return False
    try:
        plan = container_engine.build_lxd_delete_plan(container_name)
        return _dispatch_delete_plan(plan, host_id, child_id, 180)
    except Exception:  # nosec B110  pylint: disable=broad-exception-caught
        return False


def _try_wsl_plan_based_deletion(distro_name: str, host_id: str, child_id: str) -> bool:
    """Dispatch a `wsl --unregister` plan via the container_engine.

    NOTE: the engine plan does NOT verify the registry GUID before
    deleting (the legacy path does — see
    ``child_host_wsl_control._get_wsl_guid``).  Until a
    ``verify_guid`` step type is added to the apply_deployment_plan
    schema, callers should treat this as best-effort.
    """
    container_engine = module_loader.get_module("container_engine")
    if container_engine is None:
        return False
    try:
        plan = container_engine.build_wsl_delete_plan(distro_name)
        return _dispatch_delete_plan(plan, host_id, child_id, 180)
    except Exception:  # nosec B110  pylint: disable=broad-exception-caught
        return False


def _try_plan_based_deletion(child, host_id):
    """Dispatch ``child`` to the appropriate engine-path delete builder.

    Returns ``True`` if a plan was enqueued, ``False`` if the caller
    should surface a 502 to the user.  WSL with a recorded
    ``wsl_guid`` stays on the legacy path: the engine plan schema
    doesn't yet have a ``verify_guid`` step, and the legacy path's
    GUID-verify safety net is meaningful for that case.
    """
    cid = str(child.id)
    plan_dispatchers = {
        "kvm": _try_kvm_plan_based_deletion,
        "bhyve": _try_bhyve_plan_based_deletion,
        "vmm": _try_vmm_plan_based_deletion,
        "lxd": _try_lxd_plan_based_deletion,
    }
    dispatcher = plan_dispatchers.get(child.child_type)
    if dispatcher is not None:
        return dispatcher(child.child_name, host_id, cid)
    if child.child_type == "wsl" and not child.wsl_guid:
        return _try_wsl_plan_based_deletion(child.child_name, host_id, cid)
    return False


@router.delete(
    "/host/{host_id}/children/{child_id}",
    dependencies=[Depends(JWTBearer())],
)
async def delete_child_host(
    host_id: str,
    child_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Delete a child host.
    Requires DELETE_CHILD_HOST permission.

    This is a Pro+ feature. Requires container_engine module.
    """
    _check_container_module()

    # Authz is server-global; child-host data + audit are tenant-scoped.
    user = authorize_on_main(current_user, SecurityRoles.DELETE_CHILD_HOST)
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
            raise HTTPException(status_code=404, detail=_("Child host not found"))

        parameters = {
            "child_name": child.child_name,
            "child_type": child.child_type,
        }

        # For WSL type, include the wsl_guid so the agent can target the right instance
        if child.child_type == "wsl" and child.wsl_guid:
            parameters["wsl_guid"] = child.wsl_guid

        used_plan_path = _try_plan_based_deletion(child, host_id)

        if not used_plan_path:
            raise_engine_declined()

        # Plan-based path returns its result via the generic
        # ``apply_deployment_plan`` channel, not the delete-specific
        # handler that prunes the row.  Remove the HostChild
        # immediately so the UI reflects the delete; the plan still
        # runs async on the agent to destroy + undefine + purge
        # storage.  Cascade to the linked Host record (when the
        # agent inside the VM registered itself) so the deleted VM
        # also drops out of the main Hosts list.
        linked_host_id = child.child_host_id
        session.delete(child)
        if linked_host_id:
            linked_host = session.query(Host).filter(Host.id == linked_host_id).first()
            if linked_host:
                # Record a tombstone so any last-gasp /host/register
                # from the soon-to-be-destroyed VM (the agent inside
                # may still be alive for seconds after this cascade)
                # is absorbed instead of recreating a ghost row.  See
                # backend.api.recent_host_deletions for the race
                # this guards against.
                from backend.api.recent_host_deletions import (
                    record_recent_child_host_deletion,
                )

                record_recent_child_host_deletion(linked_host.fqdn, linked_host.ipv4)
                session.delete(linked_host)

        audit_log(
            user,
            current_user,
            "DELETE",
            str(host.id),
            host.fqdn,
            _("Child host deletion requested: %s") % child.child_name,
        )

        session.commit()

        return {
            "result": True,
            "message": _("Child host deletion requested"),
        }


@router.post(
    "/host/{host_id}/children/refresh",
    dependencies=[Depends(JWTBearer())],
)
async def refresh_child_hosts(
    host_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Request fresh child host status from the agent.
    This triggers the agent to run list_child_hosts and report current status.
    Requires VIEW_CHILD_HOST permission and a Pro+ license.
    """
    _check_container_module()
    # Authz is server-global; child-host data is tenant-scoped.
    authorize_on_main(current_user, SecurityRoles.VIEW_CHILD_HOST)
    session_local = request_sessionmaker()

    with session_local() as session:
        host = get_host_or_404(session, host_id)

        from backend.api.child_host_utils import verify_host_active

        verify_host_active(host)

        # Try the engine plan path first.
        used_plan_path = False
        container_engine = module_loader.get_module("container_engine")
        builder = (
            getattr(container_engine, "build_list_child_hosts_plan", None)
            if container_engine
            else None
        )
        if builder is not None:
            try:
                plan = builder()
                # pylint: disable=import-outside-toplevel
                from backend.services.proplus_dispatch import (
                    enqueue_apply_plan,
                    register_host_op_correlation,
                )

                msg_id = enqueue_apply_plan(host_id=str(host_id), plan=plan, timeout=60)
                register_host_op_correlation(msg_id, "list_child_hosts", str(host_id))
                used_plan_path = True
            except Exception:  # nosec B110
                pass

        if not used_plan_path:
            raise_engine_declined()

        session.commit()

        return {
            "result": True,
            "message": _("Child host refresh requested"),
        }


@router.get(
    "/child-host-distributions",
    dependencies=[Depends(JWTBearer())],
    response_model=List[DistributionResponse],
)
async def list_distributions(
    child_type: Optional[str] = None,
    current_user: str = Depends(get_current_user),
):
    """
    List available distributions for child hosts.
    Optionally filter by child_type (wsl, lxd, etc.).
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        query = session.query(ChildHostDistribution)

        if child_type:
            query = query.filter(ChildHostDistribution.child_type == child_type)

        # Only show active distributions
        query = query.filter(ChildHostDistribution.is_active == True)

        distributions = query.order_by(
            ChildHostDistribution.child_type,
            ChildHostDistribution.display_name,
        ).all()

        return [
            DistributionResponse(
                id=str(dist.id),
                child_type=dist.child_type,
                distribution_name=dist.distribution_name,
                distribution_version=dist.distribution_version,
                display_name=dist.display_name,
                is_active=dist.is_active,
            )
            for dist in distributions
        ]


@router.get(
    "/child-host-distributions/all",
    dependencies=[Depends(JWTBearer())],
    response_model=List[DistributionDetailResponse],
)
async def list_all_distributions(
    child_type: Optional[str] = None,
    current_user: str = Depends(get_current_user),
):
    """
    List all distributions for child hosts (admin view).
    Includes inactive distributions and full details.
    Requires CONFIGURE_CHILD_HOST permission.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        get_user_with_role_check(
            session, current_user, SecurityRoles.CONFIGURE_CHILD_HOST
        )

        query = session.query(ChildHostDistribution)

        if child_type:
            query = query.filter(ChildHostDistribution.child_type == child_type)

        distributions = query.order_by(
            ChildHostDistribution.child_type,
            ChildHostDistribution.display_name,
        ).all()

        return [
            DistributionDetailResponse(
                id=str(dist.id),
                child_type=dist.child_type,
                distribution_name=dist.distribution_name,
                distribution_version=dist.distribution_version,
                display_name=dist.display_name,
                install_identifier=dist.install_identifier,
                executable_name=dist.executable_name,
                agent_install_method=dist.agent_install_method,
                agent_install_commands=dist.agent_install_commands,
                is_active=dist.is_active,
                min_agent_version=dist.min_agent_version,
                notes=dist.notes,
                created_at=(dist.created_at.isoformat() if dist.created_at else None),
                updated_at=(dist.updated_at.isoformat() if dist.updated_at else None),
            )
            for dist in distributions
        ]


@router.get(
    "/child-host-distributions/{distribution_id}",
    dependencies=[Depends(JWTBearer())],
    response_model=DistributionDetailResponse,
)
async def get_distribution(
    distribution_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Get a single distribution by ID.
    Requires CONFIGURE_CHILD_HOST permission.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        get_user_with_role_check(
            session, current_user, SecurityRoles.CONFIGURE_CHILD_HOST
        )

        dist = (
            session.query(ChildHostDistribution)
            .filter(ChildHostDistribution.id == distribution_id)
            .first()
        )

        if not dist:
            raise HTTPException(status_code=404, detail=error_distribution_not_found())

        return DistributionDetailResponse(
            id=str(dist.id),
            child_type=dist.child_type,
            distribution_name=dist.distribution_name,
            distribution_version=dist.distribution_version,
            display_name=dist.display_name,
            install_identifier=dist.install_identifier,
            executable_name=dist.executable_name,
            agent_install_method=dist.agent_install_method,
            agent_install_commands=dist.agent_install_commands,
            is_active=dist.is_active,
            min_agent_version=dist.min_agent_version,
            notes=dist.notes,
            created_at=dist.created_at.isoformat() if dist.created_at else None,
            updated_at=dist.updated_at.isoformat() if dist.updated_at else None,
        )


@router.post(
    "/child-host-distributions",
    dependencies=[Depends(JWTBearer())],
    response_model=DistributionDetailResponse,
)
async def create_distribution(
    request: CreateDistributionRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Create a new distribution.
    Requires CONFIGURE_CHILD_HOST permission.

    This is a Pro+ feature. Requires container_engine module.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        get_user_with_role_check(
            session, current_user, SecurityRoles.CONFIGURE_CHILD_HOST
        )

        # Check for duplicate
        existing = (
            session.query(ChildHostDistribution)
            .filter(
                ChildHostDistribution.child_type == request.child_type,
                ChildHostDistribution.distribution_name == request.distribution_name,
                ChildHostDistribution.distribution_version
                == request.distribution_version,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=_(
                    "Distribution '%(name)s %(version)s' already exists for type '%(child_type)s'"
                )
                % {
                    "name": request.distribution_name,
                    "version": request.distribution_version,
                    "child_type": request.child_type,
                },
            )

        import uuid
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        dist = ChildHostDistribution(
            id=uuid.uuid4(),
            child_type=request.child_type,
            distribution_name=request.distribution_name,
            distribution_version=request.distribution_version,
            display_name=request.display_name,
            install_identifier=request.install_identifier,
            executable_name=request.executable_name,
            agent_install_method=request.agent_install_method,
            agent_install_commands=request.agent_install_commands,
            is_active=request.is_active,
            min_agent_version=request.min_agent_version,
            notes=request.notes,
            created_at=now,
            updated_at=now,
        )
        session.add(dist)
        session.commit()
        session.refresh(dist)

        return DistributionDetailResponse(
            id=str(dist.id),
            child_type=dist.child_type,
            distribution_name=dist.distribution_name,
            distribution_version=dist.distribution_version,
            display_name=dist.display_name,
            install_identifier=dist.install_identifier,
            executable_name=dist.executable_name,
            agent_install_method=dist.agent_install_method,
            agent_install_commands=dist.agent_install_commands,
            is_active=dist.is_active,
            min_agent_version=dist.min_agent_version,
            notes=dist.notes,
            created_at=dist.created_at.isoformat() if dist.created_at else None,
            updated_at=dist.updated_at.isoformat() if dist.updated_at else None,
        )


@router.put(
    "/child-host-distributions/{distribution_id}",
    dependencies=[Depends(JWTBearer())],
    response_model=DistributionDetailResponse,
)
async def update_distribution(
    distribution_id: str,
    request: UpdateDistributionRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Update an existing distribution.
    Requires CONFIGURE_CHILD_HOST permission.

    This is a Pro+ feature. Requires container_engine module.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        get_user_with_role_check(
            session, current_user, SecurityRoles.CONFIGURE_CHILD_HOST
        )

        dist = (
            session.query(ChildHostDistribution)
            .filter(ChildHostDistribution.id == distribution_id)
            .first()
        )
        if not dist:
            raise HTTPException(status_code=404, detail=error_distribution_not_found())

        from datetime import datetime, timezone

        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(dist, field, value)
        dist.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        session.commit()
        session.refresh(dist)

        return DistributionDetailResponse(
            id=str(dist.id),
            child_type=dist.child_type,
            distribution_name=dist.distribution_name,
            distribution_version=dist.distribution_version,
            display_name=dist.display_name,
            install_identifier=dist.install_identifier,
            executable_name=dist.executable_name,
            agent_install_method=dist.agent_install_method,
            agent_install_commands=dist.agent_install_commands,
            is_active=dist.is_active,
            min_agent_version=dist.min_agent_version,
            notes=dist.notes,
            created_at=dist.created_at.isoformat() if dist.created_at else None,
            updated_at=dist.updated_at.isoformat() if dist.updated_at else None,
        )


@router.delete(
    "/child-host-distributions/{distribution_id}",
    dependencies=[Depends(JWTBearer())],
)
async def delete_distribution(
    distribution_id: str,
    current_user: str = Depends(get_current_user),
):
    """
    Delete a distribution.
    Requires CONFIGURE_CHILD_HOST permission.

    This is a Pro+ feature. Requires container_engine module.
    """
    _check_container_module()

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        get_user_with_role_check(
            session, current_user, SecurityRoles.CONFIGURE_CHILD_HOST
        )

        dist = (
            session.query(ChildHostDistribution)
            .filter(ChildHostDistribution.id == distribution_id)
            .first()
        )
        if not dist:
            raise HTTPException(status_code=404, detail=error_distribution_not_found())

        session.delete(dist)
        session.commit()

        return {
            "result": True,
            "message": _("Distribution deleted"),
        }
