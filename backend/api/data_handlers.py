"""
Data handlers for SysManage agent communication.
Handles OS version, hardware, user access, and software update messages.
"""

# pylint: disable=too-many-lines

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, text, update
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import (
    AntivirusStatus,
    AvailablePackage,
    Host,
    HostCertificate,
    HostRole,
    NetworkInterface,
    PackageUpdate,
    SoftwarePackage,
    StorageDevice,
    ThirdPartyRepository,
    UbuntuProInfo,
    UbuntuProService,
    UserAccount,
    UserGroup,
)

# Logger for debugging - use existing root logger configuration
debug_logger = logging.getLogger("debug_logger")
debug_logger.setLevel(logging.DEBUG)


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

                        # Import necessary modules for sending command
                        from backend.websocket.connection_manager import (
                            connection_manager,
                        )
                        from backend.websocket.messages import create_command_message

                        # Create command message to collect packages
                        command_message = create_command_message(
                            command_type="collect_available_packages", parameters={}
                        )

                        # Send command to this host
                        try:
                            success = await connection_manager.send_to_host(
                                host.id, command_message
                            )
                            if success:
                                debug_logger.info(
                                    "Automatic package collection command sent to host %s (%s %s)",
                                    host.fqdn,
                                    os_name,
                                    os_version,
                                )
                            else:
                                debug_logger.warning(
                                    "Failed to send automatic package collection command to host %s - host may not be connected",
                                    host.fqdn,
                                )
                        except Exception as e:
                            debug_logger.error(
                                "Error sending automatic package collection command to host %s: %s",
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


def _create_user_account_with_security_id(connection, account, now):
    """Create a UserAccount with proper Windows SID handling."""
    uid = account.get("uid", 0)
    username = account.get("username", "")

    # Initialize values
    is_system_user = False
    uid_value = None
    security_id_value = None
    shell_value = account.get("shell")

    if uid is not None and uid != "":
        # Handle both integer UIDs (Unix) and string SIDs (Windows)
        try:
            # Try to convert to integer (Unix UID)
            uid_int = int(uid)
            uid_value = uid_int
            debug_logger.info("DEBUG: User %s - Unix UID: %s", username, uid_int)

            # macOS: UIDs < 500 are typically system users
            # Linux: UIDs < 1000 are typically system users
            if uid_int < 500:
                is_system_user = True

        except (ValueError, TypeError):
            # This is a Windows SID (string)
            security_id_value = str(uid)
            debug_logger.info(
                "DEBUG: User %s - Windows SID: %s", username, security_id_value
            )

            # Windows system account classification by SID pattern
            if security_id_value.startswith("S-1-5-"):
                try:
                    # Check RID (last part of SID) - system accounts typically have RIDs < 1000
                    rid = int(security_id_value.split("-")[-1])
                    if rid < 1000:
                        is_system_user = True
                except (ValueError, IndexError):
                    pass

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
        # Windows system accounts
        "system",
        "local service",
        "network service",
        "administrator",
        # macOS system accounts (starting with _)
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
    }
    if username.lower() in system_usernames:
        is_system_user = True

    return UserAccount(
        host_id=connection.host_id,
        username=username,
        uid=uid_value,  # Integer UID for Unix systems, None for Windows
        security_id=security_id_value,  # Windows SID string, None for Unix
        home_directory=account.get("home_directory"),
        shell=shell_value,  # nosec B604 - Database field assignment, not shell execution
        is_system_user=is_system_user,
        created_at=now,
        updated_at=now,
    )


def _create_user_group_with_security_id(connection, group, now):
    """Create a UserGroup with proper Windows SID handling."""
    gid = group.get("gid")
    group_name = group.get("group_name")

    # Initialize values
    is_system_group = group.get("is_system_group", False)
    gid_value = None
    security_id_value = None

    debug_logger.info(
        "DEBUG: Processing group %s with gid: %s (type: %s)", group_name, gid, type(gid)
    )

    if gid is not None:
        try:
            # Try to convert to integer (Unix GID)
            gid_int = int(gid)
            gid_value = gid_int
            debug_logger.info("DEBUG: Group %s - Unix GID: %s", group_name, gid_int)

        except (ValueError, TypeError):
            # This is a Windows SID (string)
            if isinstance(gid, str) and gid.startswith("S-1-"):
                security_id_value = str(gid)
                debug_logger.info(
                    "DEBUG: Group %s - Windows SID: %s", group_name, security_id_value
                )
            else:
                debug_logger.info(
                    "DEBUG: Group %s - unknown gid format, storing as None", group_name
                )
    else:
        debug_logger.info("DEBUG: Group %s - no gid provided", group_name)

    return UserGroup(
        host_id=connection.host_id,
        group_name=group_name,
        gid=gid_value,  # Integer GID for Unix systems, None for Windows
        security_id=security_id_value,  # Windows SID string, None for Unix
        is_system_group=is_system_group,
        created_at=now,
        updated_at=now,
    )


async def handle_user_access_update(db: Session, connection, message_data: dict):
    """Handle user access information update message from agent with Windows SID support."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Handle user accounts
        user_accounts = message_data.get("user_accounts", [])
        if not user_accounts:
            user_accounts = message_data.get("users", [])

        if user_accounts:
            debug_logger.info("Found %d users under 'users' key", len(user_accounts))

            # Delete existing user accounts for this host
            db.execute(
                delete(UserAccount).where(UserAccount.host_id == connection.host_id)
            )

            # Add new user accounts with security_id support
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for account in user_accounts:
                user_account = _create_user_account_with_security_id(
                    connection, account, now
                )
                db.add(user_account)

        # Handle user groups
        user_groups = message_data.get("user_groups", [])
        if not user_groups:
            user_groups = message_data.get("groups", [])

        if user_groups:
            debug_logger.info("Found %d groups under 'groups' key", len(user_groups))

            # Delete existing user groups for this host
            db.execute(delete(UserGroup).where(UserGroup.host_id == connection.host_id))

            # Add new user groups with security_id support
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for group in user_groups:
                user_group = _create_user_group_with_security_id(connection, group, now)
                db.add(user_group)

        # Commit the transaction
        db.commit()
        debug_logger.info(
            "Successfully processed user access update with security_id support"
        )

        return {
            "message_type": "success",
            "result": "user_access_updated",
        }

    except Exception as e:
        import traceback

        debug_logger.error("Error updating user access: %s", e)
        debug_logger.error("Full traceback: %s", traceback.format_exc())
        db.rollback()
        return {
            "message_type": "error",
            "error": "Failed to update user access information",
        }


async def handle_user_access_update_legacy(db: Session, connection, message_data: dict):
    """Handle user access information update message from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

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
                now = datetime.now(timezone.utc).replace(tzinfo=None)

                # Determine if this is a system user based on UID and username
                uid = account.get("uid", 0)
                username = account.get("username", "")

                # System user detection logic
                is_system_user = False
                if uid is not None and uid != "":
                    # Handle both integer UIDs (Unix) and string SIDs (Windows)
                    try:
                        # Ensure uid is not a string before comparison
                        uid_int = int(uid)
                        debug_logger.info(
                            "DEBUG: Successfully converted uid %s to int %s (type: %s)",
                            uid,
                            uid_int,
                            type(uid_int),
                        )
                        # macOS: UIDs < 500 are typically system users
                        # Linux: UIDs < 1000 are typically system users
                        # Force reload trigger
                        if isinstance(uid_int, int) and uid_int < 500:
                            is_system_user = True
                    except (ValueError, TypeError) as e:
                        # For Windows SIDs (strings), use different logic
                        # Windows system accounts typically have well-known SIDs
                        debug_logger.info(
                            "DEBUG: Failed to convert uid %s to int: %s (type: %s)",
                            uid,
                            e,
                            type(uid),
                        )
                        uid_str = str(uid)
                        # Windows system account classification by SID pattern
                        if uid_str.startswith("S-1-5-"):
                            # Check RID (last part of SID) - system accounts typically have RIDs < 1000
                            try:
                                rid = int(uid_str.split("-")[-1])
                                if isinstance(rid, int) and rid < 1000:
                                    is_system_user = True
                            except (ValueError, IndexError):
                                pass

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

                # Handle uid field - only store integers, Windows SIDs in shell field
                # Fixed: Type error when comparing string SIDs with integer column
                uid_value = None
                shell_value = account.get("shell")  # Default shell value

                # DEBUG: Log what we received
                debug_logger.info(
                    "DEBUG: User %s - uid received: %s (type: %s)",
                    username,
                    uid,
                    type(uid),
                )

                if uid is not None:
                    try:
                        uid_value = int(uid)
                        debug_logger.info(
                            "DEBUG: User %s - converted to integer UID: %s",
                            username,
                            uid_value,
                        )
                    except (ValueError, TypeError):
                        # Windows SIDs are strings, store in shell field for later retrieval
                        # since shell field is unused for Windows and can hold string data
                        uid_value = None
                        shell_value = str(uid)  # Store Windows SID in shell field
                        debug_logger.info(
                            "DEBUG: User %s - storing SID in shell field: %s",
                            username,
                            shell_value,
                        )
                else:
                    debug_logger.info("DEBUG: User %s - uid is None/empty", username)

                user_account = UserAccount(
                    host_id=connection.host_id,
                    username=username,
                    uid=uid_value,
                    home_directory=account.get("home_directory"),
                    shell=shell_value,  # nosec B604 - May contain Windows SID
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
                now = datetime.now(timezone.utc).replace(tzinfo=None)

                # Handle gid field - store integers for Unix, for Windows store a hash of the SID
                gid_value = None
                gid = group.get("gid")
                debug_logger.info(
                    "DEBUG: Processing group %s with gid: %s (type: %s)",
                    group.get("group_name"),
                    gid,
                    type(gid),
                )

                if gid is not None:
                    try:
                        gid_value = int(gid)
                        debug_logger.info(
                            "DEBUG: Group %s - stored integer GID: %s",
                            group.get("group_name"),
                            gid_value,
                        )
                    except (ValueError, TypeError):
                        # For Windows SIDs, create a numeric hash to store in the integer gid field
                        # This allows us to distinguish between groups while maintaining schema compatibility
                        if isinstance(gid, str) and gid.startswith("S-1-"):
                            # Create a consistent hash of the SID that fits in integer range
                            import hashlib

                            hash_object = hashlib.md5(
                                gid.encode(), usedforsecurity=False
                            )  # nosec B324
                            # Convert to positive integer within reasonable range
                            gid_value = int(hash_object.hexdigest()[:8], 16)
                            debug_logger.info(
                                "DEBUG: Group %s - Windows SID %s hashed to GID: %s",
                                group.get("group_name"),
                                gid,
                                gid_value,
                            )
                        else:
                            gid_value = None
                            debug_logger.info(
                                "DEBUG: Group %s - unknown gid format, storing as None",
                                group.get("group_name"),
                            )
                else:
                    debug_logger.info(
                        "DEBUG: Group %s - no gid provided", group.get("group_name")
                    )

                user_group = UserGroup(
                    host_id=connection.host_id,
                    group_name=group.get("group_name"),
                    gid=gid_value,
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
        import traceback

        debug_logger.error("Error updating user access: %s", e)
        debug_logger.error("Full traceback: %s", traceback.format_exc())
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to update user access information"),
        }


async def handle_software_update(db: Session, connection, message_data: dict):
    """Handle software inventory update message from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

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
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                software_package = SoftwarePackage(
                    host_id=connection.host_id,
                    package_name=package.get("package_name"),
                    package_version=package.get("version") or "unknown",
                    package_manager=package.get("package_manager", "unknown"),
                    package_description=package.get("description"),
                    architecture=package.get("architecture"),
                    install_path=package.get("installation_path"),
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
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

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
            now = datetime.now(timezone.utc).replace(tzinfo=None)
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

            # Map agent data to database model fields
            is_security = package_update.get("is_security_update", False)
            is_system = package_update.get("is_system_update", False)

            # Determine update type based on agent flags
            if is_security:
                update_type = "security"
            elif is_system:
                update_type = "system"
            else:
                update_type = "enhancement"

            package_update_record = PackageUpdate(
                host_id=connection.host_id,
                package_name=package_update.get("package_name"),
                current_version=package_update.get("current_version") or "unknown",
                available_version=new_version,  # Use validated version
                package_manager=package_update.get("package_manager", "unknown"),
                update_type=update_type,
                size_bytes=package_update.get("update_size"),
                requires_reboot=False,  # Default, could be enhanced later
                # Required timestamp fields
                discovered_at=now,
                created_at=now,
                updated_at=now,
            )
            try:
                db.add(package_update_record)
                debug_logger.info(
                    "Added package update: %s %s -> %s (%s)",
                    package_update.get("package_name"),
                    package_update.get("current_version"),
                    new_version,
                    update_type,
                )
            except Exception as e:
                debug_logger.error(
                    "Failed to add package update %s: %s",
                    package_update.get("package_name", "unknown"),
                    str(e),
                )

        # Only update host's last access timestamp if this is from a live connection
        # (not from background queue processing of old messages)
        if (
            not hasattr(connection, "is_mock_connection")
            or not connection.is_mock_connection
        ):
            stmt = (
                update(Host)
                .where(Host.id == connection.host_id)
                .values(last_access=datetime.now(timezone.utc).replace(tzinfo=None))
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
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    debug_logger.info(
        "Processing script execution result from %s", message_data.get("hostname")
    )

    try:
        execution_id = message_data.get("execution_id")
        execution_uuid = message_data.get("execution_uuid")

        if not execution_id:
            debug_logger.error("No execution_id provided in script execution result")
            return {"message_type": "error", "error": _("Execution ID is required")}

        # Check for duplicate execution UUID to prevent duplicate processing
        if execution_uuid:
            from backend.persistence.models import ScriptExecutionLog

            # Check if we've already processed this execution UUID
            existing_execution = (
                db.query(ScriptExecutionLog)
                .filter(ScriptExecutionLog.execution_uuid == execution_uuid)
                .filter(ScriptExecutionLog.status.in_(["completed", "failed"]))
                .first()
            )

            if existing_execution:
                debug_logger.error(
                    "Duplicate script execution result received for UUID %s, ignoring",
                    execution_uuid,
                )
                return {
                    "message_type": "error",
                    "error": _("Script execution result with UUID %s already processed")
                    % execution_uuid,
                }

        # Use connection object's host_id if available (from message processor)
        # Otherwise fall back to hostname lookup for direct WebSocket calls
        host = None
        if hasattr(connection, "host_id") and connection.host_id:
            host = db.query(Host).filter(Host.id == connection.host_id).first()

        # Fallback to hostname lookup if no host_id or host not found
        if not host:
            hostname = message_data.get("hostname")
            if not hostname:
                debug_logger.error("No hostname provided and no host_id in connection")
                return {"message_type": "error", "error": _("Hostname is required")}

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
            execution_log.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            execution_log.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

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
            host.fqdn,
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
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

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
        host.reboot_required_updated_at = datetime.now(timezone.utc).replace(
            tzinfo=None
        )

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


async def handle_package_collection(db: Session, connection, message_data: dict):
    """Handle package collection result from agent."""
    debug_logger.info(
        "Processing package collection result from %s",
        getattr(connection, "hostname", "unknown"),
    )

    try:
        # Extract package data from the message
        packages = message_data.get("packages", {})
        os_name = message_data.get("os_name", "Unknown")
        os_version = message_data.get("os_version", "Unknown")
        hostname = message_data.get("hostname")
        total_packages = message_data.get("total_packages", 0)

        debug_logger.info(
            "Package collection data: OS=%s %s, hostname=%s, total_packages=%d, package_managers=%s",
            os_name,
            os_version,
            hostname,
            total_packages,
            list(packages.keys()) if packages else "none",
        )

        if not packages:
            debug_logger.warning("No package data received in command result")
            return {
                "message_type": "package_collection_result_ack",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "no_data",
            }

        # Clear existing packages for this OS/version combination
        debug_logger.info("Clearing existing packages for %s %s", os_name, os_version)
        delete_stmt = delete(AvailablePackage).where(
            AvailablePackage.os_name == os_name,
            AvailablePackage.os_version == os_version,
        )
        db.execute(delete_stmt)

        # Process each package manager's packages
        total_inserted = 0
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for package_manager, package_list in packages.items():
            debug_logger.info(
                "Processing %d packages from %s", len(package_list), package_manager
            )

            batch_packages = []
            for package in package_list:
                available_package = AvailablePackage(
                    os_name=os_name,
                    os_version=os_version,
                    package_manager=package_manager,
                    package_name=package.get("name", ""),
                    package_version=package.get("version", ""),
                    package_description=package.get("description", ""),
                    last_updated=now,
                    created_at=now,
                )
                batch_packages.append(available_package)

                # Insert in batches to avoid memory issues
                if len(batch_packages) >= 1000:
                    db.add_all(batch_packages)
                    db.flush()
                    total_inserted += len(batch_packages)
                    batch_packages = []

            # Insert remaining packages
            if batch_packages:
                db.add_all(batch_packages)
                db.flush()
                total_inserted += len(batch_packages)

            debug_logger.info(
                "Completed processing %s packages, total inserted so far: %d",
                package_manager,
                total_inserted,
            )

        # Commit all changes
        db.commit()

        debug_logger.info(
            "Successfully stored %d packages for %s %s",
            total_inserted,
            os_name,
            os_version,
        )

        return {
            "message_type": "package_collection_result_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
            "packages_stored": total_inserted,
        }

    except Exception as e:
        debug_logger.error(
            "Error processing package collection result from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()

        return {
            "message_type": "error",
            "error": f"Failed to process package collection result: {str(e)}",
        }


async def handle_host_certificates_update(db: Session, connection, message_data: dict):
    """Handle host certificates update message from agent."""
    from backend.utils.host_validation import validate_host_id

    try:
        # Check for host_id in message data (agent-provided)
        agent_host_id = message_data.get("host_id")
        if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
            return {"message_type": "error", "error": "host_not_registered"}

        # Find the host by hostname or other connection attributes
        host = None
        if hasattr(connection, "hostname") and connection.hostname:
            host = db.query(Host).filter(Host.fqdn == connection.hostname).first()

        if not host and agent_host_id:
            host = db.query(Host).filter(Host.id == agent_host_id).first()

        if not host:
            debug_logger.warning(
                "Could not identify host for certificates update from connection %s",
                getattr(connection, "hostname", "unknown"),
            )
            return {"message_type": "error", "error": "host_identification_failed"}

        # Get certificates data from message
        certificates_data = message_data.get("certificates", [])
        collected_at = message_data.get("collected_at")

        debug_logger.info(
            "Processing %d certificates for host %s (%s)",
            len(certificates_data),
            host.fqdn,
            host.id,
        )

        # Clear existing certificates for this host
        db.query(HostCertificate).filter(HostCertificate.host_id == host.id).delete()

        # Process and store new certificates
        certificates_processed = 0
        for cert_data in certificates_data:
            try:
                # Parse dates
                not_before = None
                not_after = None

                if cert_data.get("not_before"):
                    not_before = datetime.fromisoformat(
                        cert_data["not_before"].replace("Z", "+00:00")
                    )
                if cert_data.get("not_after"):
                    not_after = datetime.fromisoformat(
                        cert_data["not_after"].replace("Z", "+00:00")
                    )

                collected_at_dt = None
                if collected_at:
                    collected_at_dt = datetime.fromisoformat(
                        collected_at.replace("Z", "+00:00")
                    )

                # Create certificate record
                certificate = HostCertificate(
                    host_id=host.id,
                    file_path=cert_data.get("file_path", ""),
                    certificate_name=cert_data.get("certificate_name"),
                    subject=cert_data.get("subject"),
                    issuer=cert_data.get("issuer"),
                    not_before=not_before,
                    not_after=not_after,
                    serial_number=cert_data.get("serial_number"),
                    fingerprint_sha256=cert_data.get("fingerprint_sha256"),
                    is_ca=cert_data.get("is_ca", False),
                    key_usage=cert_data.get("key_usage"),
                    collected_at=collected_at_dt or datetime.now(timezone.utc),
                )

                db.add(certificate)
                certificates_processed += 1

            except Exception as e:
                debug_logger.warning(
                    "Failed to process certificate %s for host %s: %s",
                    cert_data.get("file_path", "unknown"),
                    host.fqdn,
                    e,
                )
                continue

        # Commit all changes
        db.commit()

        debug_logger.info(
            "Successfully stored %d certificates for host %s",
            certificates_processed,
            host.fqdn,
        )

        return {
            "message_type": "certificates_update_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
            "certificates_stored": certificates_processed,
        }

    except Exception as e:
        debug_logger.error(
            "Error processing certificates update from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()

        return {
            "message_type": "error",
            "error": f"Failed to process certificates update: {str(e)}",
        }


async def handle_host_role_data_update(db: Session, connection, message_data: dict):
    """Handle host role data update message from agent."""
    from backend.utils.host_validation import validate_host_id

    try:
        # Check for host_id in message data (agent-provided)
        agent_host_id = message_data.get("host_id")
        if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
            return {"message_type": "error", "error": "host_not_registered"}

        # Find the host by hostname or other connection attributes
        host = None
        if hasattr(connection, "hostname") and connection.hostname:
            host = db.query(Host).filter(Host.fqdn == connection.hostname).first()
        if not host and agent_host_id:
            host = db.query(Host).filter(Host.id == agent_host_id).first()

        if not host:
            debug_logger.warning(
                "Could not identify host for role data update from connection %s",
                getattr(connection, "hostname", "unknown"),
            )
            return {"message_type": "error", "error": "host_identification_failed"}

        # Get role data from message
        roles_data = message_data.get("roles", [])
        collection_timestamp = message_data.get("collection_timestamp")

        debug_logger.info(
            "Processing %d server roles for host %s (%s)",
            len(roles_data),
            host.fqdn,
            host.id,
        )

        # Clear existing roles for this host
        db.query(HostRole).filter(HostRole.host_id == host.id).delete()

        # Process and store new roles
        roles_processed = 0
        for role_data in roles_data:
            try:
                # Parse collection timestamp
                detected_at = None
                if collection_timestamp:
                    detected_at = datetime.fromisoformat(
                        collection_timestamp.replace("Z", "+00:00")
                    )

                # Create role record
                role = HostRole(
                    host_id=host.id,
                    role=role_data.get("role", ""),
                    package_name=role_data.get("package_name", ""),
                    package_version=role_data.get("package_version"),
                    service_name=role_data.get("service_name"),
                    service_status=role_data.get("service_status"),
                    is_active=role_data.get("is_active", False),
                    detected_at=detected_at or datetime.now(timezone.utc),
                )

                db.add(role)
                roles_processed += 1

            except Exception as e:
                debug_logger.warning(
                    "Failed to process role %s for host %s: %s",
                    role_data.get("role", "unknown"),
                    host.fqdn,
                    e,
                )
                continue

        # Commit all changes
        db.commit()

        debug_logger.info(
            "Successfully stored %d server roles for host %s",
            roles_processed,
            host.fqdn,
        )

        return {
            "message_type": "role_data_update_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
            "roles_stored": roles_processed,
        }

    except Exception as e:
        debug_logger.error(
            "Error processing role data update from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()
        return {
            "message_type": "error",
            "error": f"Failed to process role data update: {str(e)}",
        }


async def handle_third_party_repository_update(
    db: Session, connection, message_data: dict
):
    """Handle third-party repository update message from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Handle third-party repositories
        repositories = message_data.get("repositories", [])

        debug_logger.info(
            "Processing third-party repository update from %s with %d repositories",
            getattr(connection, "hostname", "unknown"),
            len(repositories),
        )

        # Delete existing repositories for this host
        db.execute(
            delete(ThirdPartyRepository).where(
                ThirdPartyRepository.host_id == connection.host_id
            )
        )

        # Add new repositories
        repos_added = 0
        for repo in repositories:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            repository = ThirdPartyRepository(
                host_id=connection.host_id,
                name=repo.get("name", ""),
                type=repo.get("type", "unknown"),
                url=repo.get("url"),
                enabled=repo.get("enabled", True),
                file_path=repo.get("file_path"),
                last_updated=now,
            )
            db.add(repository)
            repos_added += 1

        # Update host timestamp
        host = db.query(Host).filter(Host.id == connection.host_id).first()
        if host:
            # We don't have a specific timestamp field for third-party repos yet,
            # but we can use last_access or add one in the future
            pass

        db.commit()

        debug_logger.info(
            "Successfully stored %d third-party repositories for host %s",
            repos_added,
            getattr(connection, "hostname", "unknown"),
        )

        return {
            "message_type": "third_party_repository_update_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
            "repositories_stored": repos_added,
        }

    except Exception as e:
        debug_logger.error(
            "Error processing third-party repository update from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()
        return {
            "message_type": "error",
            "error": f"Failed to process third-party repository update: {str(e)}",
        }


async def handle_antivirus_status_update(db: Session, connection, message_data: dict):
    """Handle antivirus status update message from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Extract antivirus status information
        software_name = message_data.get("software_name")
        install_path = message_data.get("install_path")
        version = message_data.get("version")
        enabled = message_data.get("enabled")

        debug_logger.info(
            "Processing antivirus status update from %s: software=%s, enabled=%s",
            getattr(connection, "hostname", "unknown"),
            software_name,
            enabled,
        )

        # Delete existing antivirus status for this host (if any)
        db.execute(
            delete(AntivirusStatus).where(AntivirusStatus.host_id == connection.host_id)
        )

        # Add new antivirus status (only if software is detected)
        if software_name:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            antivirus_status = AntivirusStatus(
                host_id=connection.host_id,
                software_name=software_name,
                install_path=install_path,
                version=version,
                enabled=enabled,
                last_updated=now,
            )
            db.add(antivirus_status)

        db.commit()

        debug_logger.info(
            "Successfully stored antivirus status for host %s",
            getattr(connection, "hostname", "unknown"),
        )

        return {
            "message_type": "antivirus_status_update_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
        }

    except Exception as e:
        debug_logger.error(
            "Error processing antivirus status update from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()
        return {
            "message_type": "error",
            "error": f"Failed to process antivirus status update: {str(e)}",
        }
