"""
Data handlers for SysManage agent communication.
Handles OS version, hardware, user access, and software update messages.
"""

import json
import logging
from datetime import datetime, timezone

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
            hardware_updates["hardware_updated_at"] = datetime.now(timezone.utc)

            stmt = (
                update(Host)
                .where(Host.id == connection.host_id)
                .values(**hardware_updates)
            )
            db.execute(stmt)

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
                now = datetime.now(timezone.utc)
                network_interface = NetworkInterface(
                    host_id=connection.host_id,
                    name=interface.get("name"),
                    ipv4_address=interface.get("ipv4_address"),
                    ipv6_address=interface.get("ipv6_address"),
                    mac_address=interface.get("mac_address"),
                    # Note: 'status' field doesn't exist in NetworkInterface model - removed
                    is_active=(
                        interface.get("status") == "active"
                        if interface.get("status")
                        else False
                    ),
                    created_at=now,
                    updated_at=now,
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
                now = datetime.now(timezone.utc)

                # Determine if device is physical based on device type
                device_type = device.get("device_type", "unknown")

                # Logic to determine physical vs logical storage
                # Per requirements: disk image = logical, everything else = physical
                is_physical = True
                if device_type and device_type.lower() == "disk image":
                    is_physical = False

                storage_device = StorageDevice(
                    host_id=connection.host_id,
                    name=device.get("name"),  # Use correct field name
                    device_path=device.get("device_path"),  # Add device_path
                    device_type=device_type,
                    capacity_bytes=device.get(
                        "total_size"
                    ),  # Map total_size to capacity_bytes
                    used_bytes=device.get("used_size"),
                    available_bytes=device.get(
                        "available_size"
                    ),  # Map available_size to available_bytes
                    file_system=device.get(
                        "filesystem"
                    ),  # Map filesystem to file_system
                    mount_point=device.get("mount_point"),
                    is_physical=is_physical,  # Set based on device analysis
                    created_at=now,
                    updated_at=now,
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
        # Debug: log what keys we're receiving
        debug_logger.info("User access message keys: %s", list(message_data.keys()))

        # Handle user accounts - try both possible field names
        user_accounts = message_data.get("user_accounts", [])
        if not user_accounts:
            # Try alternate field name the agent might be using
            user_accounts = message_data.get("users", [])
            if user_accounts:
                debug_logger.info(
                    "Found %d users under 'users' key", len(user_accounts)
                )
        if user_accounts:
            # Delete existing user accounts for this host
            db.execute(
                delete(UserAccount).where(UserAccount.host_id == connection.host_id)
            )

            # Add new user accounts
            for account in user_accounts:
                now = datetime.now(timezone.utc)

                # Determine if this is a system user based on UID and username
                uid = account.get("uid", 0)
                username = account.get("username", "")

                # System user detection logic
                is_system_user = False
                if uid is not None:
                    # macOS: UIDs < 500 are typically system users
                    # Linux: UIDs < 1000 are typically system users
                    if uid < 500:
                        is_system_user = True

                # Also check for common system usernames
                system_usernames = {
                    "root",
                    "daemon",
                    "bin",
                    "sys",
                    "sync",
                    "games",
                    "man",
                    "lp",
                    "mail",
                    "news",
                    "uucp",
                    "proxy",
                    "www-data",
                    "backup",
                    "list",
                    "irc",
                    "gnats",
                    "nobody",
                    "systemd-network",
                    "systemd-resolve",
                    "syslog",
                    "messagebus",
                    "uuidd",
                    "dnsmasq",
                    "landscape",
                    "pollinate",
                    "sshd",
                    "chrony",
                    "_www",
                    "_taskgated",
                    "_networkd",
                    "_installassistant",
                    "_lp",
                    "_postfix",
                    "_scsd",
                    "_ces",
                    "_mcxalr",
                    "_appleevents",
                    "_geod",
                    "_devdocs",
                    "_sandbox",
                    "_mdnsresponder",
                    "_ard",
                    "_eppc",
                    "_cvs",
                    "_svn",
                    "_mysql",
                    "_pgsql",
                    "_krb_krbtgt",
                    "_krb_kadmin",
                    "_krb_changepw",
                    "_devicemgr",
                    "_spotlight",
                    "_windowserver",
                    "_securityagent",
                    "_calendar",
                    "_teamsserver",
                    "_update_sharing",
                    "_appstore",
                    "_lpd",
                    "_postdrop",
                    "_qtss",
                    "_coreaudiod",
                    "_screensaver",
                    "_locationd",
                    "_trustevaluationagent",
                    "_timezone",
                    "_cvmsroot",
                    "_usbmuxd",
                    "_dovecot",
                    "_dpaudio",
                    "_postgres",
                    "_krbtgt",
                    "_kadmin_admin",
                    "_kadmin_changepw",
                }

                if username in system_usernames or username.startswith("_"):
                    is_system_user = True

                user_account = UserAccount(
                    host_id=connection.host_id,
                    username=username,
                    uid=uid,
                    home_directory=account.get("home_directory"),
                    shell=account.get("shell"),
                    is_system_user=is_system_user,  # Set proper classification
                    created_at=now,
                    updated_at=now,
                )
                db.add(user_account)

        # Handle user groups - try both possible field names
        user_groups = message_data.get("user_groups", [])
        if not user_groups:
            # Try alternate field name the agent might be using
            user_groups = message_data.get("groups", [])
            if user_groups:
                debug_logger.info(
                    "Found %d groups under 'groups' key", len(user_groups)
                )
        if user_groups:
            # Delete existing user groups for this host
            db.execute(delete(UserGroup).where(UserGroup.host_id == connection.host_id))

            # Add new user groups
            for group in user_groups:
                now = datetime.now(timezone.utc)
                user_group = UserGroup(
                    host_id=connection.host_id,
                    group_name=group.get("group_name"),
                    gid=group.get("gid"),
                    is_system_group=group.get("is_system_group", False),
                    # Note: members field doesn't exist in UserGroup model - removed
                    # (use UserGroupMembership table for members relationships)
                    created_at=now,
                    updated_at=now,
                )
                db.add(user_group)

        # Update the user access timestamp on the host
        stmt = (
            update(Host)
            .where(Host.id == connection.host_id)
            .values(user_access_updated_at=datetime.now(timezone.utc))
        )
        db.execute(stmt)

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
                now = datetime.now(timezone.utc)
                software_package = SoftwarePackage(
                    host_id=connection.host_id,
                    package_name=package.get("package_name"),
                    version=package.get("version"),
                    package_manager=package.get("package_manager", "unknown"),
                    bundle_id=package.get("bundle_id"),
                    installation_path=package.get("installation_path"),
                    created_at=now,
                    updated_at=now,
                )
                db.add(software_package)

        # Update the software updated timestamp on the host
        stmt = (
            update(Host)
            .where(Host.id == connection.host_id)
            .values(software_updated_at=datetime.now(timezone.utc))
        )
        db.execute(stmt)

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

        # Debug: log first package update structure to understand data format
        if available_updates:
            debug_logger.info(
                "Sample package update structure: %s", available_updates[0]
            )

        for package_update in available_updates:
            now = datetime.now(timezone.utc)
            # Debug: log all keys in this package update
            debug_logger.info(
                "Package update keys for %s: %s",
                package_update.get("package_name", "unknown"),
                list(package_update.keys()),
            )

            # Handle case where new_version is None - skip if no version available
            new_version = package_update.get("new_version") or package_update.get(
                "available_version"
            )
            debug_logger.info(
                "Package %s: new_version=%s, available_version=%s, resolved=%s",
                package_update.get("package_name", "unknown"),
                package_update.get("new_version"),
                package_update.get("available_version"),
                new_version,
            )

            if not new_version:
                debug_logger.warning(
                    "Skipping package update %s - no new version available",
                    package_update.get("package_name", "unknown"),
                )
                continue

            package_update_record = PackageUpdate(
                host_id=connection.host_id,
                package_name=package_update.get("package_name"),
                current_version=package_update.get("current_version"),
                available_version=new_version,  # Use validated version
                package_manager=package_update.get("package_manager", "unknown"),
                is_security_update=package_update.get("is_security_update", False),
                status="available",
                # Required timestamp fields
                detected_at=now,
                updated_at=now,
                last_checked_at=now,
            )
            db.add(package_update_record)
            # Note: Removed duplicate 'db.add(package_update)' line

        # Only update host's last access timestamp if this is from a live connection
        # (not from background queue processing of old messages)
        if not hasattr(connection, 'is_mock_connection') or not connection.is_mock_connection:
            stmt = (
                update(Host)
                .where(Host.id == connection.host_id)
                .values(last_access=text("NOW()"))
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


async def handle_script_execution_result(db: Session, connection, message_data: dict):
    """Handle script execution result from agent."""
    debug_logger.info(
        "Processing script execution result from %s", message_data.get("hostname")
    )

    try:
        hostname = message_data.get("hostname")
        execution_id = message_data.get("execution_id")

        if not hostname:
            debug_logger.error("No hostname provided in script execution result")
            return {"message_type": "error", "error": _("Hostname is required")}

        if not execution_id:
            debug_logger.error("No execution_id provided in script execution result")
            return {"message_type": "error", "error": _("Execution ID is required")}

        # Find the host (case-insensitive)
        host = db.query(Host).filter(Host.fqdn.ilike(hostname)).first()
        if not host:
            debug_logger.error("Host not found: %s", hostname)
            return {
                "message_type": "error",
                "error": _("Host not found: %s") % hostname,
            }

        # Find existing script execution log entry by execution_id
        from backend.persistence.models import ScriptExecutionLog

        execution_log = (
            db.query(ScriptExecutionLog)
            .filter(ScriptExecutionLog.execution_id == execution_id)
            .first()
        )

        if execution_log:
            # Update existing entry
            debug_logger.info(
                "Updating existing script execution log for execution_id: %s",
                execution_id,
            )
            execution_log.status = (
                "completed" if message_data.get("success", False) else "failed"
            )
            execution_log.exit_code = message_data.get("exit_code")
            execution_log.stdout_output = message_data.get("stdout", "")
            execution_log.stderr_output = message_data.get("stderr", "")
            execution_log.execution_time = message_data.get("execution_time")
            execution_log.shell_used = message_data.get("shell_used")
            execution_log.error_message = message_data.get("error")
            execution_log.timed_out = message_data.get("timeout", False)
            execution_log.completed_at = datetime.now(timezone.utc)
            execution_log.updated_at = datetime.now(timezone.utc)

            # Set started_at if not already set
            if not execution_log.started_at:
                execution_log.started_at = execution_log.completed_at

        else:
            # Create new entry (fallback for cases where execution wasn't properly logged)
            debug_logger.warning(
                "No existing execution log found for execution_id: %s, creating new entry",
                execution_id,
            )
            execution_log = ScriptExecutionLog(
                host_id=host.id,
                saved_script_id=message_data.get(
                    "script_id"
                ),  # May be None for ad-hoc scripts
                script_name=message_data.get("script_name", "Unknown"),
                script_content="",  # Not available in result message
                shell_type=message_data.get("shell_used", "bash"),
                run_as_user=None,  # Not available in result message
                requested_by="system",  # Fallback value
                execution_id=execution_id,
                status="completed" if message_data.get("success", False) else "failed",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                exit_code=message_data.get("exit_code"),
                stdout_output=message_data.get("stdout", ""),
                stderr_output=message_data.get("stderr", ""),
                error_message=message_data.get("error"),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(execution_log)

        db.commit()

        debug_logger.info(
            "Successfully stored script execution result for host %s (execution_id: %s)",
            hostname,
            execution_id,
        )

        return {
            "message_type": "script_execution_result_stored",
            "execution_log_id": execution_log.id,
            "host_id": host.id,
        }

    except Exception as e:
        debug_logger.error("Error storing script execution result: %s", e)
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to store script execution result: %s") % str(e),
        }


async def handle_reboot_status_update(db: Session, connection, message_data: dict):
    """Handle reboot status update from an agent."""
    try:
        hostname = message_data.get("hostname")
        reboot_required = message_data.get("reboot_required", False)

        if not hostname:
            return {
                "message_type": "error",
                "error": _("Hostname is required for reboot status update"),
            }

        debug_logger.info("Processing reboot status update from %s", hostname)

        # Find the host
        host = db.query(Host).filter(Host.fqdn == hostname).first()
        if not host:
            debug_logger.error("Host not found: %s", hostname)
            return {
                "message_type": "error",
                "error": _("Host not found: %s") % hostname,
            }

        # Update the reboot status
        host.reboot_required = reboot_required
        host.reboot_required_updated_at = datetime.now(timezone.utc)

        db.commit()

        debug_logger.info(
            "Successfully updated reboot status for host %s: reboot_required=%s",
            hostname,
            reboot_required,
        )

        return {
            "message_type": "reboot_status_updated",
            "host_id": host.id,
            "reboot_required": reboot_required,
        }

    except Exception as e:
        debug_logger.error("Error updating reboot status: %s", e)
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to update reboot status: %s") % str(e),
        }
