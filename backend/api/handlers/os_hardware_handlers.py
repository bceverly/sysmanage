"""
OS and Hardware data handlers for SysManage agent communication.
Handles OS version, hardware, and Ubuntu Pro update messages.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import (
    AvailablePackage,
    Host,
    NetworkInterface,
    StorageDevice,
    UbuntuProInfo,
    UbuntuProService,
)
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

# Logger for debugging - use existing root logger configuration
debug_logger = logging.getLogger("debug_logger")

# Initialize queue operations
queue_ops = QueueOperations()


async def is_new_os_version_combination(
    db: Session, os_name: str, os_version: str
) -> bool:
    """
    Check if the given OS name and version combination represents a new combination
    that hasn't been seen before in the available packages.

    Returns True if this is a new combination that should trigger automatic package collection.
    """
    if not os_name or not os_version:
        return False

    # Check if we have any available packages for this OS/version combination
    existing_packages = (
        db.query(AvailablePackage)
        .filter(
            AvailablePackage.os_name == os_name,
            AvailablePackage.os_version == os_version,
        )
        .first()
    )

    return existing_packages is None


async def handle_os_version_update(db: Session, connection, message_data: dict):
    """Handle OS version update message from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    # Check if we have any way to identify the host
    has_hostname = hasattr(connection, "hostname") and connection.hostname
    has_ipv4 = hasattr(connection, "ipv4") and connection.ipv4
    has_websocket_client = (
        hasattr(connection, "websocket")
        and hasattr(connection.websocket, "client")
        and connection.websocket.client
    )

    # If we have no way to identify the host, return early without acknowledgment
    if not has_hostname and not has_ipv4 and not has_websocket_client:
        debug_logger.warning("OS version update received with no host identification")
        return {"message_type": "error", "error": _("No host identification available")}

    # For test compatibility - check for hostname instead of host_id if needed
    if not hasattr(connection, "host_id") or not connection.host_id:
        # Try to find host by hostname first
        if has_hostname:
            host = db.query(Host).filter(Host.fqdn == connection.hostname).first()
            if host:
                connection.host_id = host.id
            else:
                return {"message_type": "error", "error": _("Host not registered")}
        # If no hostname, try IP lookup via websocket client
        elif has_websocket_client:
            client_ip = connection.websocket.client.host
            host = db.query(Host).filter(Host.ipv4 == client_ip).first()
            if host:
                connection.host_id = host.id
                connection.hostname = host.fqdn
            else:
                return {"message_type": "error", "error": _("Host not registered")}
        else:
            return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Extract OS information mapping message fields to database columns
        os_info = {
            "platform": message_data.get("platform"),
            "platform_release": message_data.get("platform_release"),
            "platform_version": message_data.get("platform_version"),
            "machine_architecture": message_data.get("machine_architecture"),
            "processor": message_data.get("processor"),
        }

        # Remove None values
        os_info = {k: v for k, v in os_info.items() if v is not None}

        # Handle os_info nested data as JSON in os_details field
        os_details = message_data.get("os_info")
        if os_details:
            os_info["os_details"] = json.dumps(os_details)

        if os_info:
            # Get the host object for tests compatibility
            host = db.query(Host).filter(Host.id == connection.host_id).first()
            if host:
                # Update host object attributes for test compatibility
                for key, value in os_info.items():
                    if key != "os_details":  # Skip JSON field for direct assignment
                        setattr(host, key, value)
                if "os_details" in os_info:
                    host.os_details = os_info["os_details"]

                # Set timestamp
                host.os_version_updated_at = datetime.now(timezone.utc).replace(
                    tzinfo=None
                )

                # Process Ubuntu Pro information if present
                await handle_ubuntu_pro_update(db, connection, message_data, host)

                # Commit changes
                db.commit()
                db.refresh(host)

                # Check if this is a new OS/version combination and trigger automatic package collection
                # Use the same logic as package handlers to determine OS name from os_details JSON
                os_name = None
                os_version = None

                # Try to extract OS name from os_details JSON first (agent sends this)
                os_details = message_data.get("os_info")
                if os_details:
                    # Look for distribution name in os_info
                    os_name = os_details.get("distribution") or os_details.get("name")

                # Fall back to platform fields if not found in os_info
                if not os_name:
                    os_name = message_data.get("platform") or host.platform
                if not os_version:
                    os_version = (
                        message_data.get("platform_release") or host.platform_release
                    )

                if os_name and os_version:
                    is_new_combination = await is_new_os_version_combination(
                        db, os_name, os_version
                    )
                    if is_new_combination:
                        debug_logger.info(
                            "New OS/version combination detected: %s %s - triggering automatic package collection",
                            os_name,
                            os_version,
                        )

                        # Import necessary module for creating command message
                        from backend.websocket.messages import create_command_message

                        # Create command message to collect packages
                        command_message = create_command_message(
                            command_type="collect_available_packages", parameters={}
                        )

                        # Enqueue command to this host
                        try:
                            queue_ops.enqueue_message(
                                message_type="command",
                                message_data=command_message,
                                direction=QueueDirection.OUTBOUND,
                                host_id=host.id,
                                db=db,
                            )
                            debug_logger.info(
                                "Automatic package collection command queued for host %s (%s %s)",
                                host.fqdn,
                                os_name,
                                os_version,
                            )
                        except Exception as e:
                            debug_logger.error(
                                "Error queueing automatic package collection command for host %s: %s",
                                host.fqdn,
                                str(e),
                            )

            debug_logger.info(
                "OS version updated for host %s: %s", connection.host_id, os_info
            )

            # Send acknowledgment to agent
            ack_message = {
                "message_type": "ack",
                "message_id": message_data.get("message_id", "unknown"),
                "data": {"status": "os_version_updated"},
            }
            await connection.send_message(ack_message)

            return {
                "message_type": "success",
                "result": _("os_version_updated"),
            }

        return {
            "message_type": "error",
            "error": _("No OS information provided"),
        }

    except Exception as e:
        debug_logger.error("Error updating OS version: %s", e)
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to update OS version"),
        }


async def handle_hardware_update(db: Session, connection, message_data: dict):
    """Handle hardware information update message from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Map hardware data from agent message to database fields
        hardware_updates = {}

        # Map CPU information
        cpu_vendor = message_data.get("cpu_vendor")
        if cpu_vendor is not None:
            hardware_updates["cpu_vendor"] = cpu_vendor

        cpu_model = message_data.get("cpu_model")
        if cpu_model is not None:
            hardware_updates["cpu_model"] = cpu_model

        cpu_cores = message_data.get("cpu_cores")
        if cpu_cores is not None:
            hardware_updates["cpu_cores"] = cpu_cores

        cpu_threads = message_data.get("cpu_threads")
        if cpu_threads is not None:
            hardware_updates["cpu_threads"] = cpu_threads

        cpu_frequency_mhz = message_data.get("cpu_frequency_mhz")
        if cpu_frequency_mhz is not None:
            hardware_updates["cpu_frequency_mhz"] = cpu_frequency_mhz

        # Map memory information
        memory_total_mb = message_data.get("memory_total_mb")
        if memory_total_mb is not None:
            hardware_updates["memory_total_mb"] = memory_total_mb

        # Map JSON detail fields
        hardware_details = message_data.get("hardware_details")
        if hardware_details is not None:
            hardware_updates["hardware_details"] = (
                json.dumps(hardware_details)
                if isinstance(hardware_details, dict)
                else hardware_details
            )

        storage_details = message_data.get("storage_details")
        if storage_details is not None:
            hardware_updates["storage_details"] = (
                json.dumps(storage_details)
                if isinstance(storage_details, dict)
                else storage_details
            )

        network_details = message_data.get("network_details")
        if network_details is not None:
            hardware_updates["network_details"] = (
                json.dumps(network_details)
                if isinstance(network_details, dict)
                else network_details
            )

        # Update hardware information if we have any data
        if hardware_updates:
            hardware_updates["hardware_updated_at"] = datetime.now(
                timezone.utc
            ).replace(tzinfo=None)

            stmt = (
                update(Host)
                .where(Host.id == connection.host_id)
                .values(**hardware_updates)
            )
            db.execute(stmt)
            db.commit()  # Commit hardware updates immediately

            debug_logger.info(
                "Hardware fields updated for host %s: %s",
                connection.host_id,
                list(hardware_updates.keys()),
            )

        # Handle network interfaces
        network_interfaces = message_data.get("network_interfaces", [])
        if network_interfaces:
            # Delete existing interfaces for this host
            db.execute(
                delete(NetworkInterface).where(
                    NetworkInterface.host_id == connection.host_id
                )
            )

            # Add new interfaces
            for interface in network_interfaces:
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                # Extract IPv4 and IPv6 addresses from agent's ip_addresses list
                ip_addresses = interface.get("ip_addresses", [])
                ipv4_address = None
                ipv6_address = None

                for ip in ip_addresses:
                    if ":" in ip:  # IPv6
                        if not ipv6_address:  # Take first IPv6
                            ipv6_address = ip
                    elif "." in ip:  # IPv4
                        if not ipv4_address:  # Take first IPv4
                            ipv4_address = ip

                network_interface = NetworkInterface(
                    host_id=connection.host_id,
                    interface_name=interface.get("name"),
                    ipv4_address=ipv4_address or interface.get("ipv4_address"),
                    ipv6_address=ipv6_address or interface.get("ipv6_address"),
                    mac_address=interface.get("mac_address"),
                    # Map agent's is_active field to database's is_up field
                    is_up=interface.get("is_active", False),
                    last_updated=now,
                )
                db.add(network_interface)

        # Handle storage devices
        storage_devices = message_data.get("storage_devices", [])
        if storage_devices:
            # Delete existing storage devices for this host
            db.execute(
                delete(StorageDevice).where(StorageDevice.host_id == connection.host_id)
            )

            # Add new storage devices
            for device in storage_devices:
                now = datetime.now(timezone.utc).replace(tzinfo=None)

                # Determine if device is physical based on device type
                device_type = device.get("device_type", "unknown")

                # Note: Physical vs logical detection is now handled in host_utils.py
                # This legacy logic is kept for backwards compatibility

                storage_device = StorageDevice(
                    host_id=connection.host_id,
                    device_name=device.get("name"),
                    device_type=device_type,
                    total_size_bytes=device.get("total_size")
                    or device.get("capacity_bytes"),
                    used_size_bytes=device.get("used_size") or device.get("used_bytes"),
                    available_size_bytes=device.get("available_size")
                    or device.get("available_bytes"),
                    filesystem=device.get("filesystem"),
                    mount_point=device.get("mount_point"),
                    last_updated=now,
                )
                db.add(storage_device)

        db.commit()

        debug_logger.info("Hardware updated for host %s", connection.host_id)

        return {
            "message_type": "success",
            "result": _("hardware_updated"),
        }

    except Exception as e:
        debug_logger.error("Error updating hardware: %s", e)
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to update hardware information"),
        }


async def handle_ubuntu_pro_update(
    db: Session, connection, message_data: dict, host: Host
):
    """Handle Ubuntu Pro information update from agent OS version message."""
    try:
        # Extract Ubuntu Pro information from the os_info nested data
        os_details = message_data.get("os_info", {})
        ubuntu_pro_data = os_details.get("ubuntu_pro")

        if not ubuntu_pro_data:
            debug_logger.debug("No Ubuntu Pro data found for host %s", host.id)
            return

        debug_logger.info("Processing Ubuntu Pro data for host %s", host.id)

        # Clear existing Ubuntu Pro data for this host
        db.execute(delete(UbuntuProInfo).where(UbuntuProInfo.host_id == host.id))

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Parse expires field if present
        expires_at = None
        if ubuntu_pro_data.get("expires"):
            try:
                # Handle potential date parsing if needed
                expires_str = ubuntu_pro_data.get("expires")
                if expires_str and expires_str != "n/a":
                    # Ubuntu Pro dates are typically in ISO format
                    expires_at = datetime.fromisoformat(
                        expires_str.replace("Z", "+00:00")
                    )
            except (ValueError, AttributeError) as e:
                debug_logger.warning("Failed to parse Ubuntu Pro expires date: %s", e)

        # Create Ubuntu Pro info record
        ubuntu_pro_info = UbuntuProInfo(
            host_id=host.id,
            attached=ubuntu_pro_data.get("attached", False),
            subscription_name=ubuntu_pro_data.get("version"),
            expires=expires_at,
            account_name=ubuntu_pro_data.get("account_name"),
            contract_name=ubuntu_pro_data.get("contract_name"),
            tech_support_level=ubuntu_pro_data.get("tech_support_level"),
            created_at=now,
            updated_at=now,
        )
        db.add(ubuntu_pro_info)

        # Flush to get the ID for services
        db.flush()

        # Process Ubuntu Pro services
        services = ubuntu_pro_data.get("services", [])
        debug_logger.debug(
            "Processing %d Ubuntu Pro services for storage in database", len(services)
        )

        for i, service_data in enumerate(services):
            service_name = service_data.get("name", "")
            debug_logger.debug(
                "Storing service %d/%d: %s (status=%s, available=%s)",
                i + 1,
                len(services),
                service_name,
                service_data.get("status", "disabled"),
                service_data.get("available", False),
            )

            ubuntu_pro_service = UbuntuProService(
                ubuntu_pro_info_id=ubuntu_pro_info.id,
                service_name=service_name,
                status=service_data.get("status", "disabled"),
                entitled=str(service_data.get("entitled", False)).lower(),
                created_at=now,
                updated_at=now,
            )
            db.add(ubuntu_pro_service)

        debug_logger.debug(
            "Completed adding all %d Ubuntu Pro services to database session",
            len(services),
        )

        debug_logger.info(
            "Ubuntu Pro data processed for host %s: attached=%s, services=%d",
            host.id,
            ubuntu_pro_data.get("attached", False),
            len(services),
        )
    except Exception as e:
        debug_logger.error(
            "Error processing Ubuntu Pro data for host %s: %s", host.id, e
        )
        # Don't re-raise - let the main OS update continue
