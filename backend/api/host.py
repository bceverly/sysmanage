"""
This module houses the API routes for the host object in SysManage.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from cryptography import x509
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

# Import the new router modules
from backend.api import host_data_updates, host_operations, host_ubuntu_pro
from backend.api.host_utils import validate_host_approval_status
from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence import db, models
from backend.security.certificate_manager import certificate_manager
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import (
    create_command_message,
    create_host_approved_message,
)

# Split into separate routers for different authentication requirements
public_router = APIRouter()  # Unauthenticated endpoints (no /api prefix)
auth_router = APIRouter()  # Authenticated endpoints (with /api prefix)

logger = logging.getLogger(__name__)

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
async def delete_host(host_id: str):
    """
    This function deletes a single host given an id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # See if we were passed a valid id
        hosts = session.query(models.Host).filter(models.Host.id == host_id).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Delete the record
        session.query(models.Host).filter(models.Host.id == host_id).delete()
        session.commit()

    return {"result": True}


@auth_router.get("/host/{host_id}", dependencies=[Depends(JWTBearer())])
async def get_host(host_id: str):
    """
    This function retrieves a single host by its id
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
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
            "last_access": host.last_access.isoformat() if host.last_access else None,
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
            "last_access": host.last_access.isoformat() if host.last_access else None,
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


@auth_router.get("/hosts", dependencies=[Depends(JWTBearer())])
async def get_all_hosts():
    """
    This function retrieves all hosts in the system
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
                    host.last_access.isoformat() if host.last_access else None
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


@auth_router.post("/host", dependencies=[Depends(JWTBearer())])
async def add_host(new_host: Host):
    """
    This function adds a new host to the system.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    # Add the data to the database
    with session_local() as session:
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

        return host


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
                existing_host.last_access = datetime.now(timezone.utc)

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
async def update_host(host_id: str, host_data: Host):
    """
    This function updates an existing host by id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    # Update the user
    with session_local() as session:
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

    return updated_host


@auth_router.put("/host/{host_id}/approve", dependencies=[Depends(JWTBearer())])
async def approve_host(host_id: str):  # pylint: disable=duplicate-code
    """
    Approve a pending host registration
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
        host.certificate_issued_at = datetime.now(timezone.utc)

        # Extract serial number for tracking

        cert = x509.load_pem_x509_certificate(cert_pem)
        host.certificate_serial = str(cert.serial_number)

        # Update approval status
        host.approval_status = "approved"
        host.last_access = datetime.now(timezone.utc)
        session.commit()

        # Send host approval notification to the agent via WebSocket
        try:
            approval_message = create_host_approved_message(
                host_id=host.id,
                host_token=host.host_token,
                approval_status="approved",
                certificate=host.client_certificate,
            )

            # Try to send the message to the agent if it's connected
            success = await connection_manager.send_to_host(host.id, approval_message)
            if success:
                print(
                    f"DEBUG: Successfully sent host approval notification to host {host.id} ({host.fqdn})",
                    flush=True,
                )
            else:
                print(
                    f"DEBUG: Host {host.id} ({host.fqdn}) not currently connected, approval message not sent",
                    flush=True,
                )
        except Exception as e:
            # Don't fail the approval process if we can't send the notification
            print(
                f"DEBUG: Error sending host approval notification to {host.id} ({host.fqdn}): {e}",
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
async def reject_host(host_id: str):  # pylint: disable=duplicate-code
    """
    Reject a pending host registration
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

        if host.approval_status != "pending":
            raise HTTPException(
                status_code=400, detail=_("Host is not in pending status")
            )

        # Update approval status
        host.approval_status = "rejected"
        host.last_access = datetime.now(timezone.utc)
        session.commit()

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

        # Send command to agent via WebSocket
        success = await connection_manager.send_to_host(host_id, command_message)

        if not success:
            raise HTTPException(status_code=503, detail=_("Agent is not connected"))

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

        # Send command to agent via WebSocket
        success = await connection_manager.send_to_host(host_id, command_message)

        if not success:
            raise HTTPException(status_code=503, detail=_("Agent is not connected"))

        return {"result": True, "message": _("Updates check requested")}


@auth_router.get("/host/{host_id}/certificates", dependencies=[Depends(JWTBearer())])
async def get_host_certificates(host_id: str):
    """
    Get SSL certificates collected from a host.
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

        # Get certificates for this host
        certificates = (
            session.query(models.HostCertificate)
            .filter(models.HostCertificate.host_id == host_id)
            .order_by(
                models.HostCertificate.not_after.asc()
            )  # Order by expiration date
            .all()
        )

        # Convert to dictionary format for JSON response
        certificate_data = []
        for cert in certificates:
            certificate_data.append(
                {
                    "id": cert.id,
                    "certificate_name": cert.certificate_name,
                    "subject": cert.subject,
                    "issuer": cert.issuer,
                    "not_before": (
                        cert.not_before.isoformat() if cert.not_before else None
                    ),
                    "not_after": cert.not_after.isoformat() if cert.not_after else None,
                    "serial_number": cert.serial_number,
                    "fingerprint_sha256": cert.fingerprint_sha256,
                    "is_ca": cert.is_ca,
                    "key_usage": cert.key_usage,
                    "file_path": cert.file_path,
                    "collected_at": (
                        cert.collected_at.isoformat() if cert.collected_at else None
                    ),
                    "is_expired": cert.is_expired,
                    "days_until_expiry": cert.days_until_expiry,
                    "common_name": cert.common_name,
                }
            )

        return {
            "host_id": host_id,
            "fqdn": host.fqdn,
            "total_certificates": len(certificate_data),
            "certificates": certificate_data,
        }


@auth_router.post(
    "/host/{host_id}/request-certificates-collection",
    dependencies=[Depends(JWTBearer())],
)
async def request_certificates_collection(host_id: str):
    """
    Request an agent to collect SSL certificates from the system.
    This sends a message via WebSocket to the agent requesting certificate collection.
    """
    logger.info("CERTIFICATE COLLECTION: Endpoint called for host_id: %s", host_id)

    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            logger.warning("CERTIFICATE COLLECTION: Host not found: %s", host_id)
            raise HTTPException(status_code=404, detail=_("Host not found"))

        logger.info(
            "CERTIFICATE COLLECTION: Found host %s (fqdn: %s)", host_id, host.fqdn
        )

        validate_host_approval_status(host)

        # Create command message for certificate collection request
        command_message = create_command_message(
            command_type="collect_certificates", parameters={}
        )

        logger.info(
            "CERTIFICATE COLLECTION: Created command message: %s", command_message
        )

        # Send command to agent via WebSocket
        success = await connection_manager.send_to_host(host_id, command_message)

        logger.info("CERTIFICATE COLLECTION: WebSocket send result: %s", success)

        if not success:
            logger.warning(
                "CERTIFICATE COLLECTION: Agent not connected for host: %s", host_id
            )
            raise HTTPException(status_code=503, detail=_("Agent is not connected"))

        logger.info(
            "CERTIFICATE COLLECTION: Successfully requested certificate collection for host: %s",
            host_id,
        )
        return {"result": True, "message": _("Certificate collection requested")}


# Include the extracted routers
auth_router.include_router(host_data_updates.router, tags=["hosts"])
auth_router.include_router(host_operations.router, tags=["hosts"])
auth_router.include_router(host_ubuntu_pro.router, tags=["hosts"])
