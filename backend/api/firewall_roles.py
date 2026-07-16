# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
This module houses the API routes for firewall role management in SysManage.
Firewall roles define sets of open ports that can be assigned to hosts.
Uses default-deny policy, so only open ports need to be specified.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from backend.api.error_constants import (
    error_firewall_role_not_found,
    error_host_not_found,
    error_invalid_firewall_role_id,
    error_view_firewall_roles_required,
)
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import db as db_module
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services.audit_service import AuditService, EntityType

from backend.utils.verbosity_logger import sanitize_log
from backend.api.firewall_roles_helpers import (
    COMMON_PORTS,
    CommonPortsResponse,
    FirewallRoleCreate,
    FirewallRoleResponse,
    FirewallRoleUpdate,
    HostFirewallRoleCreate,
    HostFirewallRoleResponse,
    get_host_firewall_ports,
    get_role_ports,
    queue_apply_firewall_roles,
    queue_remove_firewall_ports,
    role_to_response_dict,
    update_firewall_status_remove_ports,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Firewall Role CRUD Endpoints
# ============================================================================


@router.get(
    "/common-ports",
    response_model=CommonPortsResponse,
    responses={401: {"description": "Authentication required"}},
)
async def get_common_ports(
    dependencies: Annotated[dict, Depends(JWTBearer())],
):
    """Get list of common ports for the dropdown."""
    return CommonPortsResponse(ports=COMMON_PORTS)


@router.get("/", response_model=List[FirewallRoleResponse])
async def get_firewall_roles(
    db_session: Session = Depends(get_tenant_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(require_authenticated_user),
):
    """Get all firewall roles."""
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the firewall role data routes to the
    # tenant engine via ``db_session``.
    if not current_user.has_role(SecurityRoles.VIEW_FIREWALL_ROLES):
        raise HTTPException(
            status_code=403,
            detail=error_view_firewall_roles_required(),
        )

    try:
        roles = (
            db_session.query(models.FirewallRole)
            .order_by(models.FirewallRole.name)
            .all()
        )

        return [role_to_response_dict(role) for role in roles]

    except Exception as err:
        logger.exception("Error getting firewall roles: %s", err)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve firewall roles: %s") % str(err),
        ) from err


@router.get("/{role_id}", response_model=FirewallRoleResponse)
async def get_firewall_role(
    role_id: str,
    db_session: Session = Depends(get_tenant_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(require_authenticated_user),
):
    """Get a specific firewall role by ID."""
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the firewall role data routes to the
    # tenant engine via ``db_session``.
    if not current_user.has_role(SecurityRoles.VIEW_FIREWALL_ROLES):
        raise HTTPException(
            status_code=403,
            detail=error_view_firewall_roles_required(),
        )

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail=error_invalid_firewall_role_id(),
        ) from err

    try:
        role = (
            db_session.query(models.FirewallRole)
            .filter(models.FirewallRole.id == role_uuid)
            .first()
        )

        if not role:
            raise HTTPException(
                status_code=404,
                detail=error_firewall_role_not_found(),
            )

        return role_to_response_dict(role)

    except HTTPException:
        raise
    except Exception as err:
        logger.exception(
            "Error getting firewall role %s: %s", sanitize_log(role_id), err
        )
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve firewall role: %s") % str(err),
        ) from err


@router.post("/", response_model=FirewallRoleResponse, status_code=201)
async def create_firewall_role(  # NOSONAR
    role_data: FirewallRoleCreate,
    request: Request,
    db_session: Session = Depends(get_tenant_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(require_authenticated_user),
):
    """Create a new firewall role."""
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the firewall role data routes to the tenant engine via
    # ``db_session``.
    if not current_user.has_role(SecurityRoles.ADD_FIREWALL_ROLE):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: ADD_FIREWALL_ROLE role required"),
        )
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    try:
        # Check if role name already exists
        existing = (
            db_session.query(models.FirewallRole)
            .filter(models.FirewallRole.name == role_data.name)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=_("Firewall role '%s' already exists") % role_data.name,
            )

        # Create new firewall role
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        new_role = models.FirewallRole(
            name=role_data.name,
            created_at=now,
            created_by=current_user.id,
        )
        db_session.add(new_role)
        db_session.flush()  # Get the ID

        # Add open ports
        for port_data in role_data.open_ports:
            open_port = models.FirewallRoleOpenPort(
                firewall_role_id=new_role.id,
                port_number=port_data.port_number,
                tcp=port_data.tcp,
                udp=port_data.udp,
                ipv4=port_data.ipv4,
                ipv6=port_data.ipv6,
            )
            db_session.add(open_port)

        db_session.commit()
        db_session.refresh(new_role)

        logger.info("Firewall role created: %s", sanitize_log(role_data.name))

        # Log audit entry (on the main engine)
        with session_local() as audit_session:
            AuditService.log_create(
                db=audit_session,
                entity_type=EntityType.SETTING,
                entity_name=f"Firewall Role: {role_data.name}",
                user_id=current_user.id,
                username=current_user.userid,
                entity_id=str(new_role.id),
                details={
                    "name": role_data.name,
                    "open_ports_count": len(role_data.open_ports),
                },
                ip_address=request.client.host if request.client else None,
            )

        return role_to_response_dict(new_role)

    except HTTPException:
        raise
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except Exception as err:
        logger.exception("Error creating firewall role: %s", err)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to create firewall role: %s") % str(err),
        ) from err


@router.put("/{role_id}", response_model=FirewallRoleResponse)
async def update_firewall_role(  # NOSONAR
    role_id: str,
    role_data: FirewallRoleUpdate,
    request: Request,
    db_session: Session = Depends(get_tenant_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(require_authenticated_user),
):
    """Update an existing firewall role."""
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the firewall role data routes to the tenant engine via
    # ``db_session``.
    if not current_user.has_role(SecurityRoles.EDIT_FIREWALL_ROLE):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: EDIT_FIREWALL_ROLE role required"),
        )
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail=error_invalid_firewall_role_id(),
        ) from err

    try:
        role = (
            db_session.query(models.FirewallRole)
            .filter(models.FirewallRole.id == role_uuid)
            .first()
        )

        if not role:
            raise HTTPException(
                status_code=404,
                detail=error_firewall_role_not_found(),
            )

        # Check if name is being changed and already exists
        if role_data.name and role_data.name != role.name:
            existing = (
                db_session.query(models.FirewallRole)
                .filter(
                    models.FirewallRole.name == role_data.name,
                    models.FirewallRole.id != role_uuid,
                )
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=_("Firewall role '%s' already exists") % role_data.name,
                )
            role.name = role_data.name

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        role.updated_at = now
        role.updated_by = current_user.id

        # Update open ports if provided
        if role_data.open_ports is not None:
            # Delete existing open ports
            db_session.query(models.FirewallRoleOpenPort).filter(
                models.FirewallRoleOpenPort.firewall_role_id == role_uuid
            ).delete()

            # Add new open ports
            for port_data in role_data.open_ports:
                open_port = models.FirewallRoleOpenPort(
                    firewall_role_id=role.id,
                    port_number=port_data.port_number,
                    tcp=port_data.tcp,
                    udp=port_data.udp,
                    ipv4=port_data.ipv4,
                    ipv6=port_data.ipv6,
                )
                db_session.add(open_port)

        db_session.commit()
        db_session.refresh(role)

        logger.info("Firewall role updated: %s", sanitize_log(role.name))

        # Log audit entry (on the main engine)
        with session_local() as audit_session:
            AuditService.log_update(
                db=audit_session,
                entity_type=EntityType.SETTING,
                entity_name=f"Firewall Role: {role.name}",
                user_id=current_user.id,
                username=current_user.userid,
                entity_id=str(role.id),
                details={
                    "name": role.name,
                    "open_ports_count": len(role.open_ports),
                },
                ip_address=request.client.host if request.client else None,
            )

        return role_to_response_dict(role)

    except HTTPException:
        raise
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except Exception as err:
        logger.exception(
            "Error updating firewall role %s: %s", sanitize_log(role_id), err
        )
        raise HTTPException(
            status_code=500,
            detail=_("Failed to update firewall role: %s") % str(err),
        ) from err


@router.delete("/{role_id}")
async def delete_firewall_role(
    role_id: str,
    request: Request,
    db_session: Session = Depends(get_tenant_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(require_authenticated_user),
):
    """Delete a firewall role."""
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the firewall role data routes to the tenant engine via
    # ``db_session``.
    if not current_user.has_role(SecurityRoles.DELETE_FIREWALL_ROLE):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: DELETE_FIREWALL_ROLE role required"),
        )
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail=error_invalid_firewall_role_id(),
        ) from err

    try:
        role = (
            db_session.query(models.FirewallRole)
            .filter(models.FirewallRole.id == role_uuid)
            .first()
        )

        if not role:
            raise HTTPException(
                status_code=404,
                detail=error_firewall_role_not_found(),
            )

        role_name = role.name

        db_session.delete(role)
        db_session.commit()

        logger.info("Firewall role deleted: %s", role_name)

        # Log audit entry (on the main engine)
        with session_local() as audit_session:
            AuditService.log_delete(
                db=audit_session,
                entity_type=EntityType.SETTING,
                entity_name=f"Firewall Role: {role_name}",
                user_id=current_user.id,
                username=current_user.userid,
                entity_id=role_id,
                details={"name": role_name},
                ip_address=request.client.host if request.client else None,
            )

        return {"message": _("Firewall role deleted successfully")}

    except HTTPException:
        raise
    except Exception as err:
        logger.exception(
            "Error deleting firewall role %s: %s", sanitize_log(role_id), err
        )
        raise HTTPException(
            status_code=500,
            detail=_("Failed to delete firewall role: %s") % str(err),
        ) from err


# ============================================================================
# Host Firewall Role Assignment Endpoints
# ============================================================================


@router.get("/host/{host_id}/roles", response_model=List[HostFirewallRoleResponse])
async def get_host_firewall_roles(  # NOSONAR
    host_id: str,
    db_session: Session = Depends(get_tenant_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(require_authenticated_user),
):
    """Get all firewall roles assigned to a host."""
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the host/role data routes to the
    # tenant engine via ``db_session``.
    if not current_user.has_role(SecurityRoles.VIEW_FIREWALL_ROLES):
        raise HTTPException(
            status_code=403,
            detail=error_view_firewall_roles_required(),
        )

    try:
        host_uuid = uuid.UUID(host_id)
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid host ID format"),
        ) from err

    try:
        # Check if host exists
        host = db_session.query(models.Host).filter(models.Host.id == host_uuid).first()
        if not host:
            raise HTTPException(
                status_code=404,
                detail=error_host_not_found(),
            )

        # Get all firewall role assignments for this host
        assignments = (
            db_session.query(models.HostFirewallRole)
            .filter(models.HostFirewallRole.host_id == host_uuid)
            .all()
        )

        result = []
        for assignment in assignments:
            result.append(
                {
                    "id": str(assignment.id),
                    "firewall_role_id": str(assignment.firewall_role_id),
                    "firewall_role_name": assignment.firewall_role.name,
                    "created_at": assignment.created_at,
                }
            )

        return result

    except HTTPException:
        raise
    except Exception as err:
        logger.exception(
            "Error getting host firewall roles for %s: %s", sanitize_log(host_id), err
        )
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve host firewall roles: %s") % str(err),
        ) from err


@router.get("/host/{host_id}/expected-ports")
async def get_host_expected_ports(  # NOSONAR
    host_id: str,
    db_session: Session = Depends(get_tenant_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(require_authenticated_user),
):
    """
    Get the expected open ports for a host based on assigned firewall roles.

    Returns the ports that should be open based on all assigned firewall roles.
    This is useful for displaying expected state before the agent applies the rules.
    """
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the host/role data routes to the
    # tenant engine via ``db_session``.
    if not current_user.has_role(SecurityRoles.VIEW_FIREWALL_ROLES):
        raise HTTPException(
            status_code=403,
            detail=error_view_firewall_roles_required(),
        )

    try:
        host_uuid = uuid.UUID(host_id)
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid host ID format"),
        ) from err

    try:
        # Check if host exists
        host = db_session.query(models.Host).filter(models.Host.id == host_uuid).first()
        if not host:
            raise HTTPException(
                status_code=404,
                detail=error_host_not_found(),
            )

        # Get the expected ports from all assigned firewall roles
        ports = get_host_firewall_ports(db_session, host_uuid)

        # Convert to the format expected by the frontend (matching firewall status format)
        ipv4_ports = []
        for port_entry in ports["ipv4_ports"]:
            protocols = []
            if port_entry.get("tcp"):
                protocols.append("tcp")
            if port_entry.get("udp"):
                protocols.append("udp")
            ipv4_ports.append(
                {
                    "port": str(port_entry["port"]),
                    "protocols": protocols,
                }
            )

        ipv6_ports = []
        for port_entry in ports["ipv6_ports"]:
            protocols = []
            if port_entry.get("tcp"):
                protocols.append("tcp")
            if port_entry.get("udp"):
                protocols.append("udp")
            ipv6_ports.append(
                {
                    "port": str(port_entry["port"]),
                    "protocols": protocols,
                }
            )

        return {
            "ipv4_ports": ipv4_ports,
            "ipv6_ports": ipv6_ports,
        }

    except HTTPException:
        raise
    except Exception as err:
        logger.exception(
            "Error getting expected ports for host %s: %s", sanitize_log(host_id), err
        )
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve expected ports: %s") % str(err),
        ) from err


@router.post(
    "/host/{host_id}/roles",
    response_model=HostFirewallRoleResponse,
    status_code=201,
)
async def assign_firewall_role_to_host(
    host_id: str,
    role_data: HostFirewallRoleCreate,
    request: Request,
    db_session: Session = Depends(get_tenant_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(require_authenticated_user),
):
    """Assign a firewall role to a host."""
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the host/role data routes to the tenant engine via
    # ``db_session``.
    if not current_user.has_role(SecurityRoles.ASSIGN_HOST_FIREWALL_ROLES):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: ASSIGN_HOST_FIREWALL_ROLES role required"),
        )
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    try:
        host_uuid = uuid.UUID(host_id)
        role_uuid = uuid.UUID(role_data.firewall_role_id)
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid ID format"),
        ) from err

    try:
        # Check if host exists
        host = db_session.query(models.Host).filter(models.Host.id == host_uuid).first()
        if not host:
            raise HTTPException(
                status_code=404,
                detail=error_host_not_found(),
            )

        # Check if firewall role exists
        firewall_role = (
            db_session.query(models.FirewallRole)
            .filter(models.FirewallRole.id == role_uuid)
            .first()
        )
        if not firewall_role:
            raise HTTPException(
                status_code=404,
                detail=error_firewall_role_not_found(),
            )

        # Check if assignment already exists
        existing = (
            db_session.query(models.HostFirewallRole)
            .filter(
                models.HostFirewallRole.host_id == host_uuid,
                models.HostFirewallRole.firewall_role_id == role_uuid,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=_("Firewall role already assigned to this host"),
            )

        # Create the assignment
        new_assignment = models.HostFirewallRole(
            host_id=host_uuid,
            firewall_role_id=role_uuid,
            created_by=current_user.id,
        )
        db_session.add(new_assignment)
        db_session.commit()
        db_session.refresh(new_assignment)

        logger.info(
            "Firewall role %s assigned to host %s",
            firewall_role.name,
            host.fqdn,
        )

        # Log audit entry (on the main engine)
        with session_local() as audit_session:
            AuditService.log_create(
                db=audit_session,
                entity_type=EntityType.HOST,
                entity_name=f"Host Firewall Role: {firewall_role.name} -> {host.fqdn}",
                user_id=current_user.id,
                username=current_user.userid,
                entity_id=str(new_assignment.id),
                details={
                    "host_id": str(host_uuid),
                    "host_fqdn": host.fqdn,
                    "firewall_role_id": str(role_uuid),
                    "firewall_role_name": firewall_role.name,
                },
                ip_address=request.client.host if request.client else None,
            )

        # Queue message to apply firewall roles to the agent
        queue_apply_firewall_roles(db_session, host)
        db_session.commit()  # Commit the queued message

        return {
            "id": str(new_assignment.id),
            "firewall_role_id": str(new_assignment.firewall_role_id),
            "firewall_role_name": firewall_role.name,
            "created_at": new_assignment.created_at,
        }

    except HTTPException:
        raise
    except Exception as err:
        logger.exception(
            "Error assigning firewall role to host %s: %s",
            sanitize_log(host_id),
            err,
        )
        raise HTTPException(
            status_code=500,
            detail=_("Failed to assign firewall role: %s") % str(err),
        ) from err


@router.delete("/host/{host_id}/roles/{assignment_id}")
async def remove_firewall_role_from_host(
    host_id: str,
    assignment_id: str,
    request: Request,
    db_session: Session = Depends(get_tenant_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(require_authenticated_user),
):
    """Remove a firewall role assignment from a host."""
    # Authorization is resolved on the MAIN engine by require_authenticated_user
    # (user/role data is server-global); the audit trail also stays on the main
    # engine, while the host/role data routes to the tenant engine via
    # ``db_session``.
    if not current_user.has_role(SecurityRoles.ASSIGN_HOST_FIREWALL_ROLES):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: ASSIGN_HOST_FIREWALL_ROLES role required"),
        )
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )

    try:
        host_uuid = uuid.UUID(host_id)
        assignment_uuid = uuid.UUID(assignment_id)
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid ID format"),
        ) from err

    try:
        # Get the assignment
        assignment = (
            db_session.query(models.HostFirewallRole)
            .filter(
                models.HostFirewallRole.id == assignment_uuid,
                models.HostFirewallRole.host_id == host_uuid,
            )
            .first()
        )
        if not assignment:
            raise HTTPException(
                status_code=404,
                detail=_("Firewall role assignment not found"),
            )

        # Get details for audit log and ports to remove
        host = assignment.host
        firewall_role = assignment.firewall_role
        role_name = firewall_role.name if firewall_role else "Unknown"
        host_fqdn = host.fqdn if host else "Unknown"

        # Capture the ports from this specific role BEFORE deleting the assignment
        ports_to_remove = {"ipv4_ports": [], "ipv6_ports": []}
        if firewall_role:
            ports_to_remove = get_role_ports(firewall_role)

        db_session.delete(assignment)
        db_session.commit()

        logger.info(
            "Firewall role %s removed from host %s",
            role_name,
            host_fqdn,
        )

        # Log audit entry (on the main engine)
        with session_local() as audit_session:
            AuditService.log_delete(
                db=audit_session,
                entity_type=EntityType.HOST,
                entity_name=f"Host Firewall Role: {role_name} -> {host_fqdn}",
                user_id=current_user.id,
                username=current_user.userid,
                entity_id=assignment_id,
                details={
                    "host_id": str(host_uuid),
                    "host_fqdn": host_fqdn,
                    "firewall_role_name": role_name,
                },
                ip_address=request.client.host if request.client else None,
            )

        # If there are ports to remove, send them to the agent and update status
        if host and (ports_to_remove["ipv4_ports"] or ports_to_remove["ipv6_ports"]):
            # Queue message to remove ONLY the specific ports from this role
            queue_remove_firewall_ports(db_session, host, ports_to_remove)

            # Immediately update the firewall_status in the DB (don't wait for agent)
            update_firewall_status_remove_ports(db_session, host.id, ports_to_remove)

            db_session.commit()  # Commit the queued message and status update

        return {"message": _("Firewall role removed from host successfully")}

    except HTTPException:
        raise
    except Exception as err:
        logger.exception(
            "Error removing firewall role from host %s: %s",
            sanitize_log(host_id),
            err,
        )
        raise HTTPException(
            status_code=500,
            detail=_("Failed to remove firewall role: %s") % str(err),
        ) from err
