"""
This module houses the API routes for the host object in SysManage.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cryptography import x509
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

# Import the new router modules
from backend.api import (
    host_data_updates,
    host_monitoring,
    host_operations,
    host_ubuntu_pro,
)
from backend.api.host_utils import validate_host_approval_status
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.certificate_manager import certificate_manager
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.websocket.messages import (
    create_command_message,
    create_host_approved_message,
)
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

# Split into separate routers for different authentication requirements
public_router = APIRouter()  # Unauthenticated endpoints (no /api prefix)
auth_router = APIRouter()  # Authenticated endpoints (with /api prefix)

logger = logging.getLogger(__name__)
queue_ops = QueueOperations()

# Backward compatibility - this allows existing imports to still work
router = public_router  # Default to public router for backward compatibility


class HostRegistration(BaseModel):
    """
    This class represents the minimal JSON payload for agent registration.
    Only contains essential connection information.
    """

    class Config:
        extra = "forbid"  # Forbid extra fields to enforce data separation

    active: bool
    fqdn: str
    hostname: str
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    script_execution_enabled: Optional[bool] = None


class HostRegistrationLegacy(BaseModel):
    """
    Legacy registration model for backward compatibility.
    Contains all fields for comprehensive registration.
    """

    active: bool
    fqdn: str
    hostname: str
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    platform: Optional[str] = None
    platform_release: Optional[str] = None
    platform_version: Optional[str] = None
    architecture: Optional[str] = None
    processor: Optional[str] = None
    machine_architecture: Optional[str] = None
    python_version: Optional[str] = None
    os_info: Optional[Dict[str, Any]] = None


class Host(BaseModel):
    """
    This class represents the JSON payload to the /host POST/PUT requests.
    """

    active: bool
    fqdn: str
    ipv4: str
    ipv6: str


@auth_router.delete("/host/{host_id}", dependencies=[Depends(JWTBearer())])
async def delete_host(host_id: str, current_user: str = Depends(get_current_user)):
    """
    This function deletes a single host given an id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Check if user has permission to delete hosts
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=_("User not found"))

        # Load role cache if not already loaded
        if user._role_cache is None:
            user.load_role_cache(session)

        # Check for DELETE_HOST role
        if not user.has_role(SecurityRoles.DELETE_HOST):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: DELETE_HOST role required"),
            )

        # See if we were passed a valid id
        hosts = session.query(models.Host).filter(models.Host.id == host_id).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        deleted_host = hosts[0]
        # Extract values before deletion to avoid ObjectDeletedError
        deleted_fqdn = deleted_host.fqdn

        # Delete the record
        session.query(models.Host).filter(models.Host.id == host_id).delete()
        session.commit()

        # Audit log host deletion
        AuditService.log_delete(
            db=session,
            user_id=user.id,
            username=current_user,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=deleted_fqdn,
        )

    return {"result": True}


@auth_router.get("/host/{host_id}", dependencies=[Depends(JWTBearer())])
async def get_host(host_id: str, current_user: str = Depends(get_current_user)):
    """
    This function retrieves a single host by its id
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Check if user has permission to view host details
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=_("User not found"))

        # Load role cache if not already loaded
        if user._role_cache is None:
            user.load_role_cache(session)

        # Check for VIEW_HOST_DETAILS role
        if not user.has_role(SecurityRoles.VIEW_HOST_DETAILS):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: VIEW_HOST_DETAILS role required"),
            )

        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Get tags using the dynamic relationship
        host_tags = host.tags.all()

        # Calculate update counts from package_updates relationship
        package_updates = host.package_updates
        security_updates_count = sum(
            1
            for update in package_updates
            if getattr(update, "is_security_update", False)
        )
        system_updates_count = sum(
            1
            for update in package_updates
            if getattr(update, "is_system_update", False)
        )
        total_updates_count = len(package_updates)

        # Return as dictionary with all fields
        return {
            "id": str(host.id),
            "active": host.active,
            "fqdn": host.fqdn,
            "ipv4": host.ipv4,
            "ipv6": host.ipv6,
            "last_access": (
                host.last_access.replace(tzinfo=timezone.utc).isoformat()
                if host.last_access
                else None
            ),
            "status": host.status,
            "approval_status": host.approval_status,
            "platform": host.platform,
            "platform_release": host.platform_release,
            "platform_version": host.platform_version,
            "machine_architecture": host.machine_architecture,
            "processor": host.processor,
            "cpu_vendor": host.cpu_vendor,
            "cpu_model": host.cpu_model,
            "cpu_cores": host.cpu_cores,
            "cpu_threads": host.cpu_threads,
            "cpu_frequency_mhz": host.cpu_frequency_mhz,
            "memory_total_mb": host.memory_total_mb,
            "reboot_required": host.reboot_required,
            "is_agent_privileged": host.is_agent_privileged,
            "script_execution_enabled": getattr(
                host, "script_execution_enabled", False
            ),
            "enabled_shells": getattr(host, "enabled_shells", None),
            # Include update counts
            "security_updates_count": security_updates_count,
            "system_updates_count": system_updates_count,
            "total_updates_count": total_updates_count,
            # Include tags
            "tags": [
                {"id": str(tag.id), "name": tag.name, "description": tag.description}
                for tag in host_tags
            ],
        }


@auth_router.get("/host/by_fqdn/{fqdn}", dependencies=[Depends(JWTBearer())])
async def get_host_by_fqdn_endpoint(fqdn: str):
    """
    This function retrieves a single host by fully qualified domain name
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        host = session.query(models.Host).filter(models.Host.fqdn == fqdn).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Get tags using the dynamic relationship
        host_tags = host.tags.all()

        # Calculate update counts from package_updates relationship
        package_updates = host.package_updates
        security_updates_count = sum(
            1
            for update in package_updates
            if getattr(update, "is_security_update", False)
        )
        system_updates_count = sum(
            1
            for update in package_updates
            if getattr(update, "is_system_update", False)
        )
        total_updates_count = len(package_updates)

        # Return as dictionary with all fields
        return {
            "id": str(host.id),
            "active": host.active,
            "fqdn": host.fqdn,
            "ipv4": host.ipv4,
            "ipv6": host.ipv6,
            "last_access": (
                host.last_access.replace(tzinfo=timezone.utc).isoformat()
                if host.last_access
                else None
            ),
            "status": host.status,
            "approval_status": host.approval_status,
            "platform": host.platform,
            "platform_release": host.platform_release,
            "platform_version": host.platform_version,
            "machine_architecture": host.machine_architecture,
            "processor": host.processor,
            "cpu_vendor": host.cpu_vendor,
            "cpu_model": host.cpu_model,
            "cpu_cores": host.cpu_cores,
            "cpu_threads": host.cpu_threads,
            "cpu_frequency_mhz": host.cpu_frequency_mhz,
            "memory_total_mb": host.memory_total_mb,
            "reboot_required": host.reboot_required,
            "is_agent_privileged": host.is_agent_privileged,
            "script_execution_enabled": getattr(
                host, "script_execution_enabled", False
            ),
            "enabled_shells": getattr(host, "enabled_shells", None),
            # Include update counts
            "security_updates_count": security_updates_count,
            "system_updates_count": system_updates_count,
            "total_updates_count": total_updates_count,
            # Include tags
            "tags": [
                {"id": str(tag.id), "name": tag.name, "description": tag.description}
                for tag in host_tags
            ],
        }


def _get_all_hosts_sync():
    """
    Synchronous helper function to retrieve all hosts.
    This runs in a thread pool to avoid blocking the event loop.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        hosts = session.query(models.Host).all()

        # Convert to dictionaries with tags included
        result = []
        for host in hosts:
            # Get tags using the dynamic relationship (.all() method)
            host_tags = host.tags.all()

            # Calculate update counts from package_updates relationship
            package_updates = host.package_updates
            security_updates_count = sum(
                1
                for update in package_updates
                if getattr(update, "is_security_update", False)
            )
            system_updates_count = sum(
                1
                for update in package_updates
                if getattr(update, "is_system_update", False)
            )
            total_updates_count = len(package_updates)

            host_dict = {
                "id": str(host.id),
                "active": host.active,
                "fqdn": host.fqdn,
                "ipv4": host.ipv4,
                "ipv6": host.ipv6,
                "last_access": (
                    host.last_access.replace(tzinfo=timezone.utc).isoformat()
                    if host.last_access
                    else None
                ),
                "status": host.status,
                "approval_status": host.approval_status,
                "platform": host.platform,
                "platform_release": host.platform_release,
                "platform_version": host.platform_version,
                "machine_architecture": host.machine_architecture,
                "processor": host.processor,
                "cpu_vendor": host.cpu_vendor,
                "cpu_model": host.cpu_model,
                "cpu_cores": host.cpu_cores,
                "cpu_threads": host.cpu_threads,
                "cpu_frequency_mhz": host.cpu_frequency_mhz,
                "memory_total_mb": host.memory_total_mb,
                "reboot_required": host.reboot_required,
                "is_agent_privileged": host.is_agent_privileged,
                "script_execution_enabled": getattr(
                    host, "script_execution_enabled", False
                ),
                "enabled_shells": getattr(host, "enabled_shells", None),
                # Include update counts
                "security_updates_count": security_updates_count,
                "system_updates_count": system_updates_count,
                "total_updates_count": total_updates_count,
                # Include tags
                "tags": [
                    {
                        "id": str(tag.id),
                        "name": tag.name,
                        "description": tag.description,
                    }
                    for tag in host_tags
                ],
            }
            result.append(host_dict)

        return result


@auth_router.get("/hosts", dependencies=[Depends(JWTBearer())])
async def get_all_hosts():
    """
    This function retrieves all hosts in the system.
    Runs the database query in a thread pool to avoid blocking the event loop.
    """
    # Run the synchronous database operation in a thread pool
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_all_hosts_sync)


@auth_router.post("/host", dependencies=[Depends(JWTBearer())])
async def add_host(new_host: Host, current_user: str = Depends(get_current_user)):
    """
    This function adds a new host to the system.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    # Add the data to the database
    with session_local() as session:
        # Get the user object for audit logging
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=_("User not found"))
        # See if we are trying to add a duplicate host
        check_duplicate = (
            session.query(models.Host).filter(models.Host.fqdn == new_host.fqdn).all()
        )
        if len(check_duplicate) > 0:
            raise HTTPException(status_code=409, detail=_("Host already exists"))

        # Host doesn't exist so proceed with adding it
        host = models.Host(
            fqdn=new_host.fqdn,
            active=new_host.active,
            ipv4=new_host.ipv4,
            ipv6=new_host.ipv6,
            last_access=datetime.now(timezone.utc),
        )
        host.approval_status = "approved"  # Manually created hosts are pre-approved
        session.add(host)
        session.commit()
        session.refresh(host)

        # Audit log host creation
        AuditService.log_create(
            db=session,
            user_id=user.id,
            username=current_user,
            entity_type=EntityType.HOST,
            entity_id=str(host.id),
            entity_name=host.fqdn,
            details={
                "active": new_host.active,
                "ipv4": new_host.ipv4,
                "ipv6": new_host.ipv6,
            },
        )

        # Return dictionary to avoid detached object issues
        return {
            "id": str(host.id),
            "active": host.active,
            "fqdn": host.fqdn,
            "ipv4": host.ipv4,
            "ipv6": host.ipv6,
            "last_access": (
                host.last_access.replace(tzinfo=timezone.utc).isoformat()
                if host.last_access
                else None
            ),
            "status": host.status,
            "approval_status": host.approval_status,
        }


@public_router.post("/host/register")
async def register_host(registration_data: HostRegistration):
    """
    Register a new host (agent) with the system.
    This endpoint does not require authentication for initial registration.
    """
    print("=== Minimal Host Registration Data Received ===")
    print(f"FQDN: {registration_data.fqdn}")
    print(f"Hostname: {registration_data.hostname}")
    print(f"Active: {registration_data.active}")
    print(f"IPv4: {registration_data.ipv4}")
    print(f"IPv6: {registration_data.ipv6}")
    print(f"Script Execution Enabled: {registration_data.script_execution_enabled}")
    print("=== End Minimal Registration Data ===")

    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Check if host already exists by FQDN
        existing_host = (
            session.query(models.Host)
            .filter(models.Host.fqdn == registration_data.fqdn)
            .first()
        )

        if existing_host:
            # Update existing host with minimal registration information
            print("Updating existing host with minimal registration data...")
            try:
                existing_host.active = registration_data.active
                existing_host.ipv4 = registration_data.ipv4
                existing_host.ipv6 = registration_data.ipv6
                existing_host.last_access = datetime.now(timezone.utc).replace(
                    tzinfo=None
                )

                # NOTE: Script execution capability should not be overwritten during re-registration
                # This prevents agents from overwriting server-configured script execution settings
                # Script execution should only be set through explicit admin configuration

                print(
                    f"Before commit - FQDN: {existing_host.fqdn}, Active: {existing_host.active}"
                )
                session.commit()
                print("Database commit successful")
                session.refresh(existing_host)
                print("After refresh - Host updated with minimal data")

                return existing_host
            except Exception as e:
                print(f"Error updating existing host: {e}")
                session.rollback()
                raise

        # Create new host with pending approval status and minimal data
        host = models.Host(
            fqdn=registration_data.fqdn,
            active=registration_data.active,
            ipv4=registration_data.ipv4,
            ipv6=registration_data.ipv6,
            last_access=datetime.now(timezone.utc),
        )
        host.approval_status = "pending"

        # NOTE: Script execution capability defaults to False for new hosts
        # This should only be enabled through explicit admin configuration after registration
        host.script_execution_enabled = False
        session.add(host)
        session.commit()
        session.refresh(host)

        return host


@auth_router.put("/host/{host_id}", dependencies=[Depends(JWTBearer())])
async def update_host(
    host_id: str, host_data: Host, current_user: str = Depends(get_current_user)
):
    """
    This function updates an existing host by id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    # Update the user
    with session_local() as session:
        # Get the user object for audit logging
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=_("User not found"))
        # See if we were passed a valid id
        hosts = session.query(models.Host).filter(models.Host.id == host_id).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Update the values
        session.query(models.Host).filter(models.Host.id == host_id).update(
            {
                models.Host.active: host_data.active,
                models.Host.fqdn: host_data.fqdn,
                models.Host.ipv4: host_data.ipv4,
                models.Host.ipv6: host_data.ipv6,
                models.Host.last_access: datetime.now(timezone.utc),
            }
        )
        session.commit()

        # Get updated host data after commit
        updated_host = (
            session.query(models.Host).filter(models.Host.id == host_id).first()
        )

        # Audit log host update
        AuditService.log_update(
            db=session,
            user_id=user.id,
            username=current_user,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host_data.fqdn,
            details={
                "active": host_data.active,
                "ipv4": host_data.ipv4,
                "ipv6": host_data.ipv6,
            },
        )

        # Return dictionary to avoid detached object issues
        return {
            "id": str(updated_host.id),
            "active": updated_host.active,
            "fqdn": updated_host.fqdn,
            "ipv4": updated_host.ipv4,
            "ipv6": updated_host.ipv6,
            "last_access": (
                updated_host.last_access.replace(tzinfo=timezone.utc).isoformat()
                if updated_host.last_access
                else None
            ),
            "status": updated_host.status,
            "approval_status": updated_host.approval_status,
        }


@auth_router.put("/host/{host_id}/approve", dependencies=[Depends(JWTBearer())])
async def approve_host(
    host_id: str, current_user: str = Depends(get_current_user)
):  # pylint: disable=duplicate-code
    """
    Approve a pending host registration
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Check if user has permission to approve hosts
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=_("User not found"))

        # Load role cache if not already loaded
        if user._role_cache is None:
            user.load_role_cache(session)

        # Check for APPROVE_HOST_REGISTRATION role
        if not user.has_role(SecurityRoles.APPROVE_HOST_REGISTRATION):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: APPROVE_HOST_REGISTRATION role required"),
            )
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        if host.approval_status != "pending":
            raise HTTPException(
                status_code=400, detail=_("Host is not in pending status")
            )

        # Generate client certificate for the approved host
        cert_pem, _unused = certificate_manager.generate_client_certificate(
            host.fqdn, host.id
        )

        # Store certificate information in host record
        host.client_certificate = cert_pem.decode("utf-8")
        host.certificate_issued_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # Extract serial number for tracking

        cert = x509.load_pem_x509_certificate(cert_pem)
        host.certificate_serial = str(cert.serial_number)

        # Update approval status
        host.approval_status = "approved"
        host.last_access = datetime.now(timezone.utc).replace(tzinfo=None)
        session.commit()

        # Audit log host approval
        AuditService.log_update(
            db=session,
            user_id=user.id,
            username=current_user,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
        )

        # Send host approval notification to the agent via WebSocket
        try:
            approval_message = create_host_approved_message(
                host_id=str(host.id),
                host_token=host.host_token,
                approval_status="approved",
                certificate=host.client_certificate,
            )

            # Enqueue the message to be sent to the agent
            queue_ops.enqueue_message(
                message_type="host_approved",
                message_data=approval_message,
                direction=QueueDirection.OUTBOUND,
                host_id=str(host.id),
                db=session,
            )
            # Commit the session to persist the queued message
            session.commit()
            print(
                f"DEBUG: Enqueued host approval notification for host {host.id} ({host.fqdn})",
                flush=True,
            )
        except Exception as e:
            # Don't fail the approval process if we can't enqueue the notification
            print(
                f"DEBUG: Error enqueuing host approval notification to {host.id} ({host.fqdn}): {e}",
                flush=True,
            )

        ret_host = models.Host(
            id=host.id,
            active=host.active,
            fqdn=host.fqdn,
            ipv4=host.ipv4,
            ipv6=host.ipv6,
            status=host.status,
            approval_status=host.approval_status,
            last_access=host.last_access,
        )

        return ret_host


@auth_router.put("/host/{host_id}/reject", dependencies=[Depends(JWTBearer())])
async def reject_host(
    host_id: str, current_user: str = Depends(get_current_user)
):  # pylint: disable=duplicate-code
    """
    Reject a pending host registration
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Get the user object for audit logging
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=_("User not found"))
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        if host.approval_status != "pending":
            raise HTTPException(
                status_code=400, detail=_("Host is not in pending status")
            )

        # Update approval status
        host.approval_status = "rejected"
        host.last_access = datetime.now(timezone.utc).replace(tzinfo=None)
        session.commit()

        # Audit log host rejection
        AuditService.log_update(
            db=session,
            user_id=user.id,
            username=current_user,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            entity_name=host.fqdn,
        )

        ret_host = models.Host(
            id=host.id,
            active=host.active,
            fqdn=host.fqdn,
            ipv4=host.ipv4,
            ipv6=host.ipv6,
            status=host.status,
            approval_status=host.approval_status,
            last_access=host.last_access,
        )

        return ret_host


@auth_router.post(
    "/host/{host_id}/request-os-update", dependencies=[Depends(JWTBearer())]
)
async def request_os_version_update(host_id: str):
    """
    Request an agent to update its OS version information.
    This sends a message via WebSocket to the agent requesting fresh OS data.
    """
    # Get a fresh session to avoid transaction warnings
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        validate_host_approval_status(host)

        # Create command message for OS version update request
        command_message = create_command_message(
            command_type="update_os_version", parameters={}
        )

        # Enqueue command to agent via message queue
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )
        # Commit the session to persist the queued message
        session.commit()

        return {"result": True, "message": _("OS version update requested")}


@auth_router.post(
    "/host/{host_id}/request-updates-check", dependencies=[Depends(JWTBearer())]
)
async def request_updates_check(host_id: str):
    """
    Request an agent to check for available updates.
    This sends a message via WebSocket to the agent requesting an update check.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        validate_host_approval_status(host)

        # Create command message for updates check request
        command_message = create_command_message(
            command_type="check_updates", parameters={}
        )

        # Enqueue command to agent via message queue
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            db=session,
        )
        # Commit the session to persist the queued message
        session.commit()

        return {"result": True, "message": _("Updates check requested")}


# Include the extracted routers
auth_router.include_router(host_data_updates.router, tags=["hosts"])
auth_router.include_router(host_monitoring.router, tags=["hosts"])
auth_router.include_router(host_operations.router, tags=["hosts"])
auth_router.include_router(host_ubuntu_pro.router, tags=["hosts"])
