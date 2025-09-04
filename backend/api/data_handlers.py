"""
Data handlers for SysManage agent communication.
Handles OS version, hardware, user access, and software update messages.
"""

import json
import logging

from sqlalchemy import text, update, delete
from sqlalchemy.orm import Session

from backend.persistence.models import (
    Host,
    NetworkInterface,
    StorageDevice,
    UserAccount,
    UserGroup,
    SoftwarePackage,
    PackageUpdate,
)
from backend.i18n import _

# Logger for debugging
debug_logger = logging.getLogger("debug_logger")
debug_logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler("logs/backend.log")
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
debug_logger.addHandler(file_handler)


async def handle_os_version_update(db: Session, connection, message_data: dict):
    """Handle OS version update message from agent."""
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
        # Try to find host by hostname for tests
        if has_hostname:
            host = db.query(Host).filter(Host.fqdn == connection.hostname).first()
            if host:
                connection.host_id = host.id
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
                from datetime import datetime, timezone

                host.os_version_updated_at = datetime.now(timezone.utc)

                # Commit changes
                db.commit()
                db.refresh(host)

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
    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Update basic host hardware info
        hardware_info = {
            "cpu_info": message_data.get("cpu_info"),
            "memory_total": message_data.get("memory_total"),
            "memory_available": message_data.get("memory_available"),
            "disk_usage": message_data.get("disk_usage"),
        }

        # Remove None values
        hardware_info = {k: v for k, v in hardware_info.items() if v is not None}

        if hardware_info:
            stmt = (
                update(Host)
                .where(Host.id == connection.host_id)
                .values(**hardware_info)
            )
            db.execute(stmt)

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
                network_interface = NetworkInterface(
                    host_id=connection.host_id,
                    name=interface.get("name"),
                    ipv4_address=interface.get("ipv4_address"),
                    ipv6_address=interface.get("ipv6_address"),
                    mac_address=interface.get("mac_address"),
                    status=interface.get("status", "unknown"),
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
                storage_device = StorageDevice(
                    host_id=connection.host_id,
                    device_name=device.get("device_name"),
                    device_type=device.get("device_type", "unknown"),
                    total_size=device.get("total_size"),
                    used_size=device.get("used_size"),
                    filesystem=device.get("filesystem"),
                    mount_point=device.get("mount_point"),
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


async def handle_user_access_update(db: Session, connection, message_data: dict):
    """Handle user access information update message from agent."""
    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Handle user accounts
        user_accounts = message_data.get("user_accounts", [])
        if user_accounts:
            # Delete existing user accounts for this host
            db.execute(
                delete(UserAccount).where(UserAccount.host_id == connection.host_id)
            )

            # Add new user accounts
            for account in user_accounts:
                user_account = UserAccount(
                    host_id=connection.host_id,
                    username=account.get("username"),
                    uid=account.get("uid"),
                    gid=account.get("gid"),
                    home_directory=account.get("home_directory"),
                    shell=account.get("shell"),
                    full_name=account.get("full_name", ""),
                )
                db.add(user_account)

        # Handle user groups
        user_groups = message_data.get("user_groups", [])
        if user_groups:
            # Delete existing user groups for this host
            db.execute(delete(UserGroup).where(UserGroup.host_id == connection.host_id))

            # Add new user groups
            for group in user_groups:
                user_group = UserGroup(
                    host_id=connection.host_id,
                    group_name=group.get("group_name"),
                    gid=group.get("gid"),
                    members=json.dumps(group.get("members", [])),
                )
                db.add(user_group)

        db.commit()

        debug_logger.info("User access updated for host %s", connection.host_id)

        return {
            "message_type": "success",
            "result": _("user_access_updated"),
        }

    except Exception as e:
        debug_logger.error("Error updating user access: %s", e)
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to update user access information"),
        }


async def handle_software_update(db: Session, connection, message_data: dict):
    """Handle software inventory update message from agent."""
    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Handle software packages
        software_packages = message_data.get("software_packages", [])
        if software_packages:
            # Delete existing software packages for this host
            db.execute(
                delete(SoftwarePackage).where(
                    SoftwarePackage.host_id == connection.host_id
                )
            )

            # Add new software packages
            for package in software_packages:
                software_package = SoftwarePackage(
                    host_id=connection.host_id,
                    package_name=package.get("package_name"),
                    version=package.get("version"),
                    package_manager=package.get("package_manager", "unknown"),
                    bundle_id=package.get("bundle_id"),
                    installation_path=package.get("installation_path"),
                )
                db.add(software_package)

        db.commit()

        debug_logger.info(
            "Software inventory updated for host %s: %d packages",
            connection.host_id,
            len(software_packages),
        )

        return {
            "message_type": "success",
            "result": _("software_inventory_updated"),
        }

    except Exception as e:
        debug_logger.error("Error updating software inventory: %s", e)
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to update software inventory"),
        }


async def handle_package_updates_update(db: Session, connection, message_data: dict):
    """Handle package updates information from agent."""
    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Clear existing updates for this host first
        db.execute(
            delete(PackageUpdate).where(PackageUpdate.host_id == connection.host_id)
        )

        # Process available updates
        available_updates = message_data.get("available_updates", [])
        total_updates = len(available_updates)

        debug_logger.info(
            "Processing %d package updates for host %s",
            total_updates,
            connection.host_id,
        )

        for package_update in available_updates:
            package_update_record = PackageUpdate(
                host_id=connection.host_id,
                package_name=package_update.get("package_name"),
                current_version=package_update.get("current_version"),
                new_version=package_update.get("new_version"),
                update_type=package_update.get("update_type", "application"),
                package_manager=package_update.get("package_manager", "unknown"),
                is_security_update=package_update.get("is_security_update", False),
                description=package_update.get("description"),
                status="available",
            )
            db.add(package_update_record)
            db.add(package_update)

        # Update host's last update check timestamp
        stmt = (
            update(Host)
            .where(Host.id == connection.host_id)
            .values(last_update_check=text("NOW()"))
        )
        db.execute(stmt)

        db.commit()

        debug_logger.info(
            "Package updates stored successfully for host %s: %d updates",
            connection.host_id,
            total_updates,
        )

        return {
            "message_type": "success",
            "updates_processed": total_updates,
        }

    except Exception as e:
        debug_logger.error("Error storing package updates: %s", e)
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to store updates: %s") % str(e),
        }
