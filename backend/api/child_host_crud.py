"""
Child host CRUD (Create, Read, Update, Delete) API endpoints.
"""

import json
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

from datetime import datetime, timezone

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
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config.config import get_config
from backend.i18n import _
from backend.persistence import db, models
from backend.persistence.models import ChildHostDistribution, HostChild
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

router = APIRouter()
queue_ops = QueueOperations()


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

        # Get the distribution info
        distribution = (
            session.query(ChildHostDistribution)
            .filter(ChildHostDistribution.id == request.distribution_id)
            .first()
        )
        if not distribution:
            raise HTTPException(status_code=404, detail=_("Distribution not found"))

        if not distribution.is_active:
            raise HTTPException(status_code=400, detail=_("Distribution is not active"))

        # Check if a child host with this name already exists
        existing = (
            session.query(HostChild)
            .filter(
                HostChild.parent_host_id == host.id,
                HostChild.child_name == request.hostname,
                HostChild.child_type == request.child_type,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=_("A child host with this name already exists"),
            )

        # Generate auto-approve token if requested
        auto_approve_token = None
        if request.auto_approve:
            auto_approve_token = str(uuid.uuid4())

        # Create the host_child record
        child_host = HostChild(
            parent_host_id=host.id,
            child_name=request.hostname,
            child_type=request.child_type,
            distribution=distribution.distribution_name,
            distribution_version=distribution.distribution_version,
            hostname=request.hostname,
            default_username=request.username,
            install_path=request.install_path,
            status="pending",
            auto_approve_token=auto_approve_token,
        )
        session.add(child_host)
        session.flush()  # Get the ID

        # Parse agent_install_commands if it's a JSON string
        agent_install_commands = []
        if distribution.agent_install_commands:
            if isinstance(distribution.agent_install_commands, str):
                try:
                    agent_install_commands = json.loads(
                        distribution.agent_install_commands
                    )
                except json.JSONDecodeError:
                    # If parsing fails, treat as empty
                    agent_install_commands = []
            elif isinstance(distribution.agent_install_commands, list):
                agent_install_commands = distribution.agent_install_commands

        # Get server URL from config for agent configuration
        config = get_config()
        api_host = config["api"].get("host", "localhost")
        api_port = config["api"].get("port", 8443)
        # Use the host's FQDN as the server URL since the agent needs to reach it
        # If api_host is 0.0.0.0, use the server's actual FQDN
        if api_host in (
            "0.0.0.0",
            "localhost",
            "127.0.0.1",
        ):  # nosec B104 - string comparison, not binding
            # Use the parent host's FQDN as the server URL
            # The agent will connect back to the same server
            import socket

            try:
                server_url = socket.getfqdn()
            except Exception:
                server_url = "localhost"
        else:
            server_url = api_host

        # Build parameters for the command
        parameters = {
            "child_host_id": str(child_host.id),
            "child_type": request.child_type,
            "distribution": distribution.distribution_name,
            "distribution_version": distribution.distribution_version,
            "install_identifier": distribution.install_identifier,
            "executable_name": distribution.executable_name,
            "hostname": request.hostname,
            "username": request.username,
            "password": request.password,
            "agent_install_method": distribution.agent_install_method,
            "agent_install_commands": agent_install_commands,
            "server_url": server_url,
            "server_port": api_port,
        }
        if request.install_path:
            parameters["install_path"] = request.install_path
        if auto_approve_token:
            parameters["auto_approve_token"] = auto_approve_token

        # Create command message
        command_message = create_command_message(
            command_type="create_child_host", parameters=parameters
        )

        # Queue the message for delivery to the agent
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Audit log
        audit_log(
            session,
            user,
            current_user,
            "CREATE",
            host_id,
            host.fqdn,
            f"Requested child host creation '{request.hostname}' "
            f"({request.child_type}) on host {host.fqdn}",
        )

        session.commit()

        # Build response message based on auto-approve setting
        if auto_approve_token:
            response_message = _(
                "Child host creation started. "
                "The host will be automatically approved when it connects."
            )
        else:
            response_message = _(
                "Child host creation started. "
                "After installation completes, you must approve the new host "
                "in the Hosts list."
            )

        return {
            "result": True,
            "child_host_id": str(child_host.id),
            "auto_approve": bool(auto_approve_token),
            "message": response_message,
        }


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
    """
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

        child_name = child.child_name
        child_type = child.child_type
        child_status = child.status

        # If status is "creating", "pending", or "failed", just delete the DB record
        # No need to send a command to the agent since nothing was created yet
        # or the creation failed before the child host was fully set up
        if child_status in ("creating", "pending", "failed"):
            # Store child info before deleting
            child_host_id = child.child_host_id
            child_hostname = child.hostname

            session.delete(child)

            # Also delete any registered host record for this child
            deleted_host_info = None
            if child_host_id:
                linked_host = (
                    session.query(models.Host)
                    .filter(models.Host.id == child_host_id)
                    .first()
                )
                if linked_host:
                    deleted_host_info = linked_host.fqdn
                    session.delete(linked_host)
            elif child_hostname:
                # Try to find host by fqdn matching the child hostname
                # Extract short hostname (first part before any dot)
                child_short_hostname = child_hostname.split(".")[0]

                matching_host = (
                    session.query(models.Host)
                    .filter(func.lower(models.Host.fqdn) == func.lower(child_hostname))
                    .first()
                )
                # Also try prefix match (hostname without domain)
                if not matching_host:
                    matching_host = (
                        session.query(models.Host)
                        .filter(
                            func.lower(models.Host.fqdn).like(
                                func.lower(child_hostname + ".%")
                            )
                        )
                        .first()
                    )
                # Try reverse prefix match (Host.fqdn is short, child_hostname is FQDN)
                if not matching_host:
                    matching_host = (
                        session.query(models.Host)
                        .filter(
                            func.lower(child_hostname).like(
                                func.lower(models.Host.fqdn) + ".%"
                            )
                        )
                        .first()
                    )
                # Try matching just the short hostname
                if not matching_host:
                    matching_host = (
                        session.query(models.Host)
                        .filter(
                            func.lower(models.Host.fqdn)
                            == func.lower(child_short_hostname)
                        )
                        .first()
                    )
                # Try matching short hostname as prefix of Host.fqdn
                if not matching_host:
                    matching_host = (
                        session.query(models.Host)
                        .filter(
                            func.lower(models.Host.fqdn).like(
                                func.lower(child_short_hostname + ".%")
                            )
                        )
                        .first()
                    )
                if matching_host:
                    deleted_host_info = matching_host.fqdn
                    session.delete(matching_host)
            else:
                # Final fallback: try matching by child_name
                # This handles cases where hostname was NULL (e.g., bhyve VMs
                # created before metadata storage was implemented)
                # Try child_name as exact FQDN match
                matching_host = (
                    session.query(models.Host)
                    .filter(func.lower(models.Host.fqdn) == func.lower(child_name))
                    .first()
                )
                # Try child_name as prefix of Host.fqdn
                if not matching_host:
                    matching_host = (
                        session.query(models.Host)
                        .filter(
                            func.lower(models.Host.fqdn).like(
                                func.lower(child_name + ".%")
                            )
                        )
                        .first()
                    )
                if matching_host:
                    deleted_host_info = matching_host.fqdn
                    session.delete(matching_host)

            # Audit log - use appropriate message based on status
            if child_status == "failed":
                description = (
                    f"Removed failed child host '{child_name}' "
                    f"({child_type}) from host {host.fqdn}"
                )
            else:
                description = (
                    f"Cancelled child host creation '{child_name}' "
                    f"({child_type}) on host {host.fqdn}"
                )
            if deleted_host_info:
                description += f" (also deleted host record: {deleted_host_info})"

            audit_log(
                session,
                user,
                current_user,
                "DELETE",
                host_id,
                host.fqdn,
                description,
            )

            session.commit()

            # Return appropriate message based on original status
            if child_status == "failed":
                return {
                    "result": True,
                    "message": _("Failed child host record removed."),
                }
            return {
                "result": True,
                "message": _("Child host creation cancelled and record removed."),
            }

        # For existing child hosts, send delete command to the agent
        # Update status to uninstalling
        child.status = "uninstalling"
        session.flush()

        # Build parameters for the command
        parameters = {
            "child_host_id": str(child.id),
            "child_type": child.child_type,
            "child_name": child.child_name,
        }

        # Include wsl_guid for WSL instances to prevent stale delete commands
        if child.child_type == "wsl" and child.wsl_guid:
            parameters["wsl_guid"] = child.wsl_guid

        # Create command message
        command_message = create_command_message(
            command_type="delete_child_host", parameters=parameters
        )

        # Queue the message for delivery to the agent
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )

        # Audit log
        audit_log(
            session,
            user,
            current_user,
            "DELETE",
            host_id,
            host.fqdn,
            f"Requested child host deletion '{child.child_name}' "
            f"({child.child_type}) on host {host.fqdn}",
        )

        session.commit()

        return {
            "result": True,
            "message": _(
                "Child host deletion requested. "
                "This will permanently remove the child host and all its data."
            ),
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
        verify_host_active(host)

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
            raise HTTPException(status_code=404, detail=_("Distribution not found"))

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
    """
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
                status_code=400,
                detail=_(
                    "A distribution with this type, name, and version already exists"
                ),
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        dist = ChildHostDistribution(
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
            raise HTTPException(status_code=404, detail=_("Distribution not found"))

        # Update only provided fields
        if request.child_type is not None:
            dist.child_type = request.child_type
        if request.distribution_name is not None:
            dist.distribution_name = request.distribution_name
        if request.distribution_version is not None:
            dist.distribution_version = request.distribution_version
        if request.display_name is not None:
            dist.display_name = request.display_name
        if request.install_identifier is not None:
            dist.install_identifier = request.install_identifier
        if request.executable_name is not None:
            dist.executable_name = request.executable_name
        if request.agent_install_method is not None:
            dist.agent_install_method = request.agent_install_method
        if request.agent_install_commands is not None:
            dist.agent_install_commands = request.agent_install_commands
        if request.is_active is not None:
            dist.is_active = request.is_active
        if request.min_agent_version is not None:
            dist.min_agent_version = request.min_agent_version
        if request.notes is not None:
            dist.notes = request.notes

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
            raise HTTPException(status_code=404, detail=_("Distribution not found"))

        session.delete(dist)
        session.commit()

        return {"result": True, "message": _("Distribution deleted successfully")}
