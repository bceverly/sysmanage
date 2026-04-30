"""
This module houses the API routes for the host object in SysManage.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cryptography import x509
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

# Import the new router modules
from backend.api import (
    host_account_management,
    host_approval,
    host_data_updates,
    host_graylog,
    host_monitoring,
    host_operations,
    host_ubuntu_pro,
)
from backend.api.host_utils import validate_host_approval_status
from backend.api.error_constants import error_host_not_found, error_user_not_found
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

    # Message envelope fields (sent by agent, not stored)
    message_type: Optional[str] = None
    message_id: Optional[str] = None
    timestamp: Optional[str] = None

    # Registration data
    active: bool
    fqdn: str
    hostname: str
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    script_execution_enabled: Optional[bool] = None
    is_privileged: Optional[bool] = None
    enabled_shells: Optional[List[str]] = None
    agent_version: Optional[str] = None
    auto_approve_token: Optional[str] = None
    # Phase 8.1: optional pre-shared registration key.  When supplied
    # and valid, the server enrolls the host into the key's
    # access_group and (if the key has auto_approve=True) skips the
    # manual approval gate.
    registration_key: Optional[str] = None


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
            raise HTTPException(status_code=401, detail=error_user_not_found())

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
            raise HTTPException(status_code=404, detail=error_host_not_found())

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
            raise HTTPException(status_code=401, detail=error_user_not_found())

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
            raise HTTPException(status_code=404, detail=error_host_not_found())

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
            "timezone": getattr(host, "timezone", None),
            "cpu_vendor": host.cpu_vendor,
            "cpu_model": host.cpu_model,
            "cpu_cores": host.cpu_cores,
            "cpu_threads": host.cpu_threads,
            "cpu_frequency_mhz": host.cpu_frequency_mhz,
            "memory_total_mb": host.memory_total_mb,
            "reboot_required": host.reboot_required,
            "is_agent_privileged": host.is_agent_privileged,
            "agent_version": host.agent_version,
            "script_execution_enabled": getattr(
                host, "script_execution_enabled", False
            ),
            "enabled_shells": getattr(host, "enabled_shells", None),
            # Include parent host ID for child host filtering
            "parent_host_id": (
                str(getattr(host, "parent_host_id", None))
                if getattr(host, "parent_host_id", None)
                else None
            ),
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
            raise HTTPException(status_code=404, detail=error_host_not_found())

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
            "timezone": getattr(host, "timezone", None),
            "cpu_vendor": host.cpu_vendor,
            "cpu_model": host.cpu_model,
            "cpu_cores": host.cpu_cores,
            "cpu_threads": host.cpu_threads,
            "cpu_frequency_mhz": host.cpu_frequency_mhz,
            "memory_total_mb": host.memory_total_mb,
            "reboot_required": host.reboot_required,
            "is_agent_privileged": host.is_agent_privileged,
            "agent_version": host.agent_version,
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

        # Bulk-fetch the host→tag mapping in one query rather than
        # ``host.tags.all()`` per host (the dynamic relationship issued
        # 1+N queries — flagged in the Phase 6 N+1 audit).
        host_ids = [h.id for h in hosts]
        tags_by_host: dict = {}
        if host_ids:
            tag_rows = (
                session.query(models.HostTag.host_id, models.Tag)
                .join(models.Tag, models.Tag.id == models.HostTag.tag_id)
                .filter(models.HostTag.host_id.in_(host_ids))
                .all()
            )
            for hid, tag in tag_rows:
                tags_by_host.setdefault(hid, []).append(tag)

        # Convert to dictionaries with tags included
        result = []
        for host in hosts:
            host_tags = tags_by_host.get(host.id, [])

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
                "agent_version": host.agent_version,
                "script_execution_enabled": getattr(
                    host, "script_execution_enabled", False
                ),
                "enabled_shells": getattr(host, "enabled_shells", None),
                # Include parent host ID for child host filtering
                "parent_host_id": (
                    str(getattr(host, "parent_host_id", None))
                    if getattr(host, "parent_host_id", None)
                    else None
                ),
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
                # Include virtualization support info
                "virtualization_types": host.virtualization_types,
                "virtualization_capabilities": host.virtualization_capabilities,
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
            raise HTTPException(status_code=401, detail=error_user_not_found())
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


def _refresh_existing_host(session, existing_host, registration_data) -> "models.Host":
    """Update an already-registered host's network/active fields from a
    re-registration payload.  Script-execution capability is intentionally
    NOT touched — that's an admin-configured server-side setting."""
    print("Updating existing host with minimal registration data...")
    try:
        existing_host.active = registration_data.active
        existing_host.ipv4 = registration_data.ipv4
        existing_host.ipv6 = registration_data.ipv6
        existing_host.last_access = datetime.now(timezone.utc).replace(tzinfo=None)
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


def _validate_registration_key(session, raw_key):
    """Resolve a registration key string to a usable ``RegistrationKey``
    row.  Returns the row when valid, ``None`` when no key was supplied,
    raises 403 otherwise.  We deliberately don't leak which condition
    (revoked/expired/max-uses) failed."""
    if not raw_key:
        return None
    validated_key = (
        session.query(models.RegistrationKey)
        .filter(models.RegistrationKey.key == raw_key)
        .first()
    )
    if validated_key is None or not validated_key.is_usable():
        raise HTTPException(
            status_code=403,
            detail=_("Invalid or expired registration key"),
        )
    return validated_key


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
        existing_host = (
            session.query(models.Host)
            .filter(models.Host.fqdn == registration_data.fqdn)
            .first()
        )
        if existing_host:
            return _refresh_existing_host(session, existing_host, registration_data)

        # Phase 8.1: validate optional registration_key BEFORE creating
        # the host row, so a bad key never even creates a pending host.
        validated_key = _validate_registration_key(
            session, registration_data.registration_key
        )

        # Create new host with pending approval status and minimal data
        host = models.Host(
            fqdn=registration_data.fqdn,
            active=registration_data.active,
            ipv4=registration_data.ipv4,
            ipv6=registration_data.ipv6,
            last_access=datetime.now(timezone.utc),
        )

        # Auto-approve when the matched key allows it; otherwise pending.
        if validated_key is not None and validated_key.auto_approve:
            host.approval_status = "approved"
        else:
            host.approval_status = "pending"

        # NOTE: Script execution capability defaults to False for new hosts
        # This should only be enabled through explicit admin configuration after registration
        host.script_execution_enabled = False
        session.add(host)
        session.flush()  # need host.id for join-table inserts below

        # Phase 8.1: enroll into the key's access group + bump the
        # key's use_count + last_used_at.  All in one commit so the
        # invariant "use_count reflects successful enrollments" holds
        # even on a crash mid-registration.
        if validated_key is not None:
            if validated_key.access_group_id is not None:
                session.add(
                    models.HostAccessGroup(
                        host_id=host.id,
                        access_group_id=validated_key.access_group_id,
                    )
                )
            validated_key.use_count = (validated_key.use_count or 0) + 1
            validated_key.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)

        session.commit()
        session.refresh(host)

        # Audit log: enrollment via registration key carries enough
        # context that the operator can correlate to the matched key.
        if validated_key is not None:
            AuditService.log(
                db=session,
                action_type=ActionType.CREATE,
                entity_type=EntityType.HOST,
                entity_id=str(host.id),
                entity_name=host.fqdn,
                description=_(
                    "Host '%s' enrolled via registration key '%s' (auto_approve=%s)"
                )
                % (host.fqdn, validated_key.name, validated_key.auto_approve),
                result=Result.SUCCESS,
                details={
                    "registration_key_id": str(validated_key.id),
                    "registration_key_name": validated_key.name,
                    "access_group_id": (
                        str(validated_key.access_group_id)
                        if validated_key.access_group_id
                        else None
                    ),
                    "auto_approved": validated_key.auto_approve,
                },
            )

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
            raise HTTPException(status_code=401, detail=error_user_not_found())
        # See if we were passed a valid id
        hosts = session.query(models.Host).filter(models.Host.id == host_id).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail=error_host_not_found())

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


# Include the extracted routers
auth_router.include_router(host_approval.router, tags=["hosts"])
auth_router.include_router(host_data_updates.router, tags=["hosts"])
auth_router.include_router(host_graylog.router, tags=["hosts"])
auth_router.include_router(host_monitoring.router, tags=["hosts"])
auth_router.include_router(host_operations.router, tags=["hosts"])
auth_router.include_router(host_ubuntu_pro.router, tags=["hosts"])
auth_router.include_router(host_account_management.router, tags=["hosts"])
