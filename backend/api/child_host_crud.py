"""
Child host CRUD (Create, Read, Update, Delete) API endpoints.

NOTE: Container/VM creation and deletion are Pro+ features. The actual implementation
is provided by the container_engine module. This file provides stub endpoints
for write operations that return license-required errors for community users.
Read-only listing operations remain open source.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

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
    get_host_or_404,
    get_user_with_role_check,
    verify_host_active,
)
from backend.api.error_constants import error_distribution_not_found
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import db
from backend.persistence.models import ChildHostDistribution, HostChild
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()


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
    Requires VIEW_CHILD_HOST permission.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        get_user_with_role_check(session, current_user, SecurityRoles.VIEW_CHILD_HOST)

        host = get_host_or_404(session, host_id)

        # Query child hosts for this parent
        child_hosts = (
            session.query(HostChild)
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
                status=child.status,
                installation_step=child.installation_step,
                error_message=child.error_message,
                created_at=child.created_at.isoformat() if child.created_at else None,
                installed_at=(
                    child.installed_at.isoformat() if child.installed_at else None
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
    Requires VIEW_CHILD_HOST permission.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        get_user_with_role_check(session, current_user, SecurityRoles.VIEW_CHILD_HOST)

        host = get_host_or_404(session, host_id)

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

        return ChildHostResponse(
            id=str(child.id),
            parent_host_id=str(child.parent_host_id),
            child_host_id=str(child.child_host_id) if child.child_host_id else None,
            child_name=child.child_name,
            child_type=child.child_type,
            distribution=child.distribution,
            distribution_version=child.distribution_version,
            hostname=child.hostname,
            status=child.status,
            installation_step=child.installation_step,
            error_message=child.error_message,
            created_at=child.created_at.isoformat() if child.created_at else None,
            installed_at=child.installed_at.isoformat() if child.installed_at else None,
        )


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

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        user = get_user_with_role_check(
            session, current_user, SecurityRoles.DELETE_CHILD_HOST
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
            raise HTTPException(status_code=404, detail=_("Child host not found"))

        parameters = {
            "child_name": child.child_name,
            "child_type": child.child_type,
        }

        # For WSL type, include the wsl_guid so the agent can target the right instance
        if child.child_type == "wsl" and child.wsl_guid:
            parameters["wsl_guid"] = child.wsl_guid

        queue_ops = QueueOperations()

        command_message = create_command_message(
            command_type="delete_child_host",
            parameters=parameters,
        )

        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Mark child as deleting
        child.status = "deleting"

        audit_log(
            session,
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
    Requires VIEW_CHILD_HOST permission.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        get_user_with_role_check(session, current_user, SecurityRoles.VIEW_CHILD_HOST)

        host = get_host_or_404(session, host_id)

        from backend.api.child_host_utils import verify_host_active
        from backend.websocket.messages import create_command_message
        from backend.websocket.queue_enums import QueueDirection
        from backend.websocket.queue_operations import QueueOperations

        verify_host_active(host)

        queue_ops = QueueOperations()

        # Create command message to list child hosts
        command_message = create_command_message(
            command_type="list_child_hosts", parameters={}
        )

        # Queue the message for delivery to the agent
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
                detail=_("Distribution '%s %s' already exists for type '%s'")
                % (
                    request.distribution_name,
                    request.distribution_version,
                    request.child_type,
                ),
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
