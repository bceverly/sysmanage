"""
This module houses the API routes for the host object in SysManage.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker
from cryptography import x509

from backend.auth.auth_bearer import JWTBearer
from backend.persistence import db, models
from backend.security.certificate_manager import certificate_manager
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import create_command_message

router = APIRouter()


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


@router.delete("/host/{host_id}", dependencies=[Depends(JWTBearer())])
async def delete_host(host_id: int):
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
            raise HTTPException(status_code=404, detail="Host not found")

        # Delete the record
        session.query(models.Host).filter(models.Host.id == host_id).delete()
        session.commit()

    return {"result": True}


@router.get("/host/{host_id}", dependencies=[Depends(JWTBearer())])
async def get_host(host_id: int):
    """
    This function retrieves a single host by its id
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        hosts = session.query(models.Host).filter(models.Host.id == host_id).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail="Host not found")

        return hosts[0]


@router.get("/host/by_fqdn/{fqdn}", dependencies=[Depends(JWTBearer())])
async def get_host_by_fqdn(fqdn: str):
    """
    This function retrieves a single host by fully qualified domain name
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        hosts = session.query(models.Host).filter(models.Host.fqdn == fqdn).all()

        # Check for failure
        if len(hosts) != 1:
            raise HTTPException(status_code=404, detail="Host not found")

        return hosts[0]


@router.get("/hosts", dependencies=[Depends(JWTBearer())])
async def get_all_hosts():
    """
    This function retrieves all hosts in the system
    """

    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        result = session.query(models.Host).all()
        return result


@router.post("/host", dependencies=[Depends(JWTBearer())])
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
            raise HTTPException(status_code=409, detail="Host already exists")

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


@router.post("/host/register")
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
        session.add(host)
        session.commit()
        session.refresh(host)

        return host


@router.put("/host/{host_id}", dependencies=[Depends(JWTBearer())])
async def update_host(host_id: int, host_data: Host):
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
            raise HTTPException(status_code=404, detail="Host not found")

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


@router.put("/host/{host_id}/approve", dependencies=[Depends(JWTBearer())])
async def approve_host(host_id: int):  # pylint: disable=duplicate-code
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
            raise HTTPException(status_code=404, detail="Host not found")

        if host.approval_status != "pending":
            raise HTTPException(status_code=400, detail="Host is not in pending status")

        # Generate client certificate for the approved host
        cert_pem, _ = certificate_manager.generate_client_certificate(
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


@router.put("/host/{host_id}/reject", dependencies=[Depends(JWTBearer())])
async def reject_host(host_id: int):  # pylint: disable=duplicate-code
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
            raise HTTPException(status_code=404, detail="Host not found")

        if host.approval_status != "pending":
            raise HTTPException(status_code=400, detail="Host is not in pending status")

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


@router.post("/host/{host_id}/request-os-update", dependencies=[Depends(JWTBearer())])
async def request_os_version_update(host_id: int):
    """
    Request an agent to update its OS version information.
    This sends a message via WebSocket to the agent requesting fresh OS data.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail="Host not found")

        if host.approval_status != "approved":
            raise HTTPException(status_code=400, detail="Host is not approved")

        # Create command message for OS version update request
        command_message = create_command_message(
            command_type="update_os_version", parameters={}
        )

        # Send command to agent via WebSocket
        success = await connection_manager.send_to_host(host_id, command_message)

        if not success:
            raise HTTPException(status_code=503, detail="Agent is not connected")

        return {"result": True, "message": "OS version update requested"}


@router.post("/host/{host_id}/update-hardware", dependencies=[Depends(JWTBearer())])
async def update_host_hardware(host_id: int, hardware_data: dict):
    """
    Update hardware information for a specific host.
    This endpoint receives hardware data from the agent and stores it in the database.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail="Host not found")

        # Update hardware fields
        if "cpu_vendor" in hardware_data:
            host.cpu_vendor = hardware_data["cpu_vendor"]
        if "cpu_model" in hardware_data:
            host.cpu_model = hardware_data["cpu_model"]
        if "cpu_cores" in hardware_data:
            host.cpu_cores = hardware_data["cpu_cores"]
        if "cpu_threads" in hardware_data:
            host.cpu_threads = hardware_data["cpu_threads"]
        if "cpu_frequency_mhz" in hardware_data:
            host.cpu_frequency_mhz = hardware_data["cpu_frequency_mhz"]
        if "memory_total_mb" in hardware_data:
            host.memory_total_mb = hardware_data["memory_total_mb"]
        # Handle normalized storage devices
        if "storage_devices" in hardware_data:
            # Delete existing storage devices for this host
            session.query(models.StorageDevice).filter(
                models.StorageDevice.host_id == host_id
            ).delete()

            # Add new storage devices
            for device_data in hardware_data["storage_devices"]:
                if not device_data.get("error"):  # Skip error entries
                    storage_device = models.StorageDevice(
                        host_id=host_id,
                        name=device_data.get("name"),
                        device_path=device_data.get("device_path"),
                        mount_point=device_data.get("mount_point"),
                        file_system=device_data.get("file_system"),
                        device_type=device_data.get("device_type"),
                        capacity_bytes=device_data.get("capacity_bytes"),
                        used_bytes=device_data.get("used_bytes"),
                        available_bytes=device_data.get("available_bytes"),
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    session.add(storage_device)

        # Handle normalized network interfaces
        if "network_interfaces" in hardware_data:
            # Delete existing network interfaces for this host
            session.query(models.NetworkInterface).filter(
                models.NetworkInterface.host_id == host_id
            ).delete()

            # Add new network interfaces
            for interface_data in hardware_data["network_interfaces"]:
                if not interface_data.get("error"):  # Skip error entries
                    network_interface = models.NetworkInterface(
                        host_id=host_id,
                        name=interface_data.get("name"),
                        interface_type=interface_data.get("interface_type"),
                        hardware_type=interface_data.get("hardware_type"),
                        mac_address=interface_data.get("mac_address"),
                        ipv4_address=interface_data.get("ipv4_address"),
                        ipv6_address=interface_data.get("ipv6_address"),
                        subnet_mask=interface_data.get("subnet_mask"),
                        is_active=interface_data.get("is_active", False),
                        speed_mbps=interface_data.get("speed_mbps"),
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    session.add(network_interface)

        # Keep backward compatibility for JSON fields (for migration period)
        if "storage_details" in hardware_data:
            host.storage_details = hardware_data["storage_details"]
        if "network_details" in hardware_data:
            host.network_details = hardware_data["network_details"]
        if "hardware_details" in hardware_data:
            host.hardware_details = hardware_data["hardware_details"]

        host.hardware_updated_at = datetime.now(timezone.utc)
        host.last_access = datetime.now(timezone.utc)

        session.commit()
        session.refresh(host)

        return {"result": True, "message": "Hardware information updated successfully"}


@router.get("/host/{host_id}/storage", dependencies=[Depends(JWTBearer())])
async def get_host_storage(host_id: int):
    """
    Get storage devices for a specific host from the normalized storage_devices table.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host first to ensure it exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail="Host not found")

        # Get storage devices
        storage_devices = (
            session.query(models.StorageDevice)
            .filter(models.StorageDevice.host_id == host_id)
            .all()
        )

        # Convert to dict format
        devices = []
        for device in storage_devices:
            devices.append(
                {
                    "id": device.id,
                    "name": device.name,
                    "device_path": device.device_path,
                    "mount_point": device.mount_point,
                    "file_system": device.file_system,
                    "device_type": device.device_type,
                    "capacity_bytes": device.capacity_bytes,
                    "used_bytes": device.used_bytes,
                    "available_bytes": device.available_bytes,
                    "is_physical": device.is_physical,
                    "created_at": (
                        device.created_at.isoformat() if device.created_at else None
                    ),
                    "updated_at": (
                        device.updated_at.isoformat() if device.updated_at else None
                    ),
                }
            )

        return devices


@router.get("/host/{host_id}/network", dependencies=[Depends(JWTBearer())])
async def get_host_network(host_id: int):
    """
    Get network interfaces for a specific host from the normalized network_interfaces table.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host first to ensure it exists
        host = session.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail="Host not found")

        # Get network interfaces
        network_interfaces = (
            session.query(models.NetworkInterface)
            .filter(models.NetworkInterface.host_id == host_id)
            .all()
        )

        # Convert to dict format
        interfaces = []
        for interface in network_interfaces:
            interfaces.append(
                {
                    "id": interface.id,
                    "name": interface.name,
                    "interface_type": interface.interface_type,
                    "hardware_type": interface.hardware_type,
                    "mac_address": interface.mac_address,
                    "ipv4_address": interface.ipv4_address,
                    "ipv6_address": interface.ipv6_address,
                    "subnet_mask": interface.subnet_mask,
                    "is_active": interface.is_active,
                    "speed_mbps": interface.speed_mbps,
                    "created_at": (
                        interface.created_at.isoformat()
                        if interface.created_at
                        else None
                    ),
                    "updated_at": (
                        interface.updated_at.isoformat()
                        if interface.updated_at
                        else None
                    ),
                }
            )

        return interfaces


@router.post(
    "/host/{host_id}/request-hardware-update", dependencies=[Depends(JWTBearer())]
)
async def request_hardware_update(host_id: int):
    """
    Request an agent to update its hardware information.
    This sends a message via WebSocket to the agent requesting fresh hardware data.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail="Host not found")

        if host.approval_status != "approved":
            raise HTTPException(status_code=400, detail="Host is not approved")

        # Create command message for hardware update request
        command_message = create_command_message(
            command_type="update_hardware", parameters={}
        )

        # Send command to agent via WebSocket
        success = await connection_manager.send_to_host(host_id, command_message)

        if not success:
            raise HTTPException(status_code=503, detail="Agent is not connected")

        return {"result": True, "message": "Hardware update requested"}


@router.post("/hosts/request-hardware-update", dependencies=[Depends(JWTBearer())])
async def request_hardware_update_bulk(host_ids: list[int]):
    """
    Request multiple agents to update their hardware information.
    This sends messages via WebSocket to the selected agents requesting fresh hardware data.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(  # pylint: disable=duplicate-code
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    results = []

    with session_local() as session:
        for host_id in host_ids:
            # Find the host
            host = session.query(models.Host).filter(models.Host.id == host_id).first()

            if not host:
                results.append(
                    {"host_id": host_id, "success": False, "error": "Host not found"}
                )
                continue

            if host.approval_status != "approved":
                results.append(
                    {
                        "host_id": host_id,
                        "success": False,
                        "error": "Host is not approved",
                    }
                )
                continue

            # Create command message for hardware update request
            command_message = create_command_message(
                command_type="update_hardware", parameters={}
            )

            # Send command to agent via WebSocket
            success = await connection_manager.send_to_host(host_id, command_message)

            if success:
                results.append(
                    {
                        "host_id": host_id,
                        "success": True,
                        "message": "Hardware update requested",
                    }
                )
            else:
                results.append(
                    {
                        "host_id": host_id,
                        "success": False,
                        "error": "Agent is not connected",
                    }
                )

    return {"results": results}
