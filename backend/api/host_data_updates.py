"""
Host data update endpoints for hardware, users, and software information.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import sessionmaker

from backend.api.host_utils import validate_host_approval_status
from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence import db, models
from backend.api.host_utils import (
    get_host_network_interfaces,
    get_host_software_packages,
    get_host_storage_devices,
    get_host_ubuntu_pro_info,
    get_host_user_groups,
    get_host_users_with_groups,
)
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import create_command_message

router = APIRouter()


@router.post("/host/{host_id}/update-hardware", dependencies=[Depends(JWTBearer())])
async def update_host_hardware(host_id: str, hardware_data: dict):
    """
    Update hardware information for a specific host.
    This endpoint receives hardware data from the agent and stores it in the database.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

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
                        device_name=device_data.get("name"),
                        mount_point=device_data.get("mount_point"),
                        filesystem=device_data.get("file_system"),
                        device_type=device_data.get("device_type"),
                        total_size_bytes=device_data.get("capacity_bytes"),
                        used_size_bytes=device_data.get("used_bytes"),
                        available_size_bytes=device_data.get("available_bytes"),
                        last_updated=datetime.now(timezone.utc),
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
                        interface_name=interface_data.get("name"),
                        interface_type=interface_data.get("interface_type")
                        or interface_data.get("hardware_type"),
                        mac_address=interface_data.get("mac_address"),
                        ipv4_address=interface_data.get("ipv4_address"),
                        ipv6_address=interface_data.get("ipv6_address"),
                        netmask=interface_data.get("subnet_mask"),
                        is_up=interface_data.get("is_active", False),
                        speed_mbps=interface_data.get("speed_mbps"),
                        last_updated=datetime.now(timezone.utc),
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

        return {
            "result": True,
            "message": _("Hardware information updated successfully"),
        }


@router.get("/host/{host_id}/storage", dependencies=[Depends(JWTBearer())])
async def get_host_storage(host_id: str):
    """
    Get storage devices for a specific host from the normalized storage_devices table.
    """
    return get_host_storage_devices(host_id)


@router.get("/host/{host_id}/network", dependencies=[Depends(JWTBearer())])
async def get_host_network(host_id: str):
    """
    Get network interfaces for a specific host from the normalized network_interfaces table.
    """
    return get_host_network_interfaces(host_id)


@router.post(
    "/host/{host_id}/request-hardware-update", dependencies=[Depends(JWTBearer())]
)
async def request_hardware_update(host_id: str):
    """
    Request an agent to update its hardware information.
    This sends a message via WebSocket to the agent requesting fresh hardware data.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        validate_host_approval_status(host)

        # Create command message for hardware update request
        command_message = create_command_message(
            command_type="update_hardware", parameters={}
        )

        # Send command to agent via WebSocket
        success = await connection_manager.send_to_host(host_id, command_message)

        if not success:
            raise HTTPException(status_code=503, detail=_("Agent is not connected"))

        return {"result": True, "message": _("Hardware update requested")}


@router.post("/hosts/request-hardware-update", dependencies=[Depends(JWTBearer())])
async def request_hardware_update_bulk(host_ids: list[str]):
    """
    Request multiple agents to update their hardware information.
    This sends messages via WebSocket to the selected agents requesting fresh hardware data.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
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


@router.get("/host/{host_id}/users", dependencies=[Depends(JWTBearer())])
async def get_host_users(host_id: str):
    """
    Get user accounts for a specific host from the normalized user_accounts table.
    """
    return get_host_users_with_groups(host_id)


@router.get("/host/{host_id}/groups", dependencies=[Depends(JWTBearer())])
async def get_host_groups(host_id: str):
    """
    Get user groups for a specific host from the normalized user_groups table.
    """
    return get_host_user_groups(host_id)


@router.post(
    "/host/{host_id}/request-user-access-update", dependencies=[Depends(JWTBearer())]
)
async def request_user_access_update(host_id: str):
    """
    Request an agent to update its user access information.
    This sends a message via WebSocket to the agent requesting fresh user and group data.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the host
        host = session.query(models.Host).filter(models.Host.id == host_id).first()

        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        validate_host_approval_status(host)

        # Create command message for user access update request
        command_message = create_command_message(
            command_type="update_user_access", parameters={}
        )

        # Send command to agent via WebSocket
        success = await connection_manager.send_to_host(host_id, command_message)

        if not success:
            raise HTTPException(status_code=503, detail=_("Agent is not connected"))

        return {"result": True, "message": _("User access update requested")}


@router.get("/host/{host_id}/software", dependencies=[Depends(JWTBearer())])
async def get_host_software(host_id: str):
    """
    Get software packages for a specific host from the software_packages table.
    """
    return get_host_software_packages(host_id)


@router.get("/host/{host_id}/ubuntu-pro", dependencies=[Depends(JWTBearer())])
async def get_host_ubuntu_pro(host_id: str):
    """
    Get Ubuntu Pro information for a specific host from the ubuntu_pro_info table.
    """
    return get_host_ubuntu_pro_info(host_id)
