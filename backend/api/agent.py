"""
This module implements the remote agent communication with the server over
WebSockets with real-time bidirectional communication capabilities.
Enhanced with security validation and secure communication protocols.
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.db import get_db
from backend.persistence.models import (
    Host,
    StorageDevice,
    NetworkInterface,
    UserAccount,
    UserGroup,
    UserGroupMembership,
)
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import ErrorMessage, MessageType, create_message
from backend.security.communication_security import websocket_security
from backend.config.config_push import config_push_manager

# Set up debug logger
debug_logger = logging.getLogger("websocket_debug")
debug_logger.setLevel(logging.INFO)

# Ensure we have a console handler for debug output
if not debug_logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("[WEBSOCKET] %(message)s")
    console_handler.setFormatter(formatter)
    debug_logger.addHandler(console_handler)

debug_logger.info("agent.py module loaded with WebSocket debug logging")


def _process_user_accounts(db: Session, host_id: int, users_data: list):
    """Process user accounts data for a host."""
    for user_data in users_data:
        if not user_data.get("error"):  # Skip error entries
            user_account = UserAccount(
                host_id=host_id,
                username=user_data.get("username"),
                uid=user_data.get("uid"),
                home_directory=user_data.get("home_directory"),
                shell=user_data.get("shell"),
                is_system_user=user_data.get("is_system_user", False),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(user_account)


def _process_user_groups(db: Session, host_id: int, groups_data: list):
    """Process user groups data for a host."""
    for group_data in groups_data:
        if not group_data.get("error"):  # Skip error entries
            user_group = UserGroup(
                host_id=host_id,
                group_name=group_data.get("group_name"),
                gid=group_data.get("gid"),
                is_system_group=group_data.get("is_system_group", False),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(user_group)


def _process_user_group_memberships(
    db: Session, host_id: int, users_data: list, user_id_map: dict, group_id_map: dict
):
    """Process user-group memberships for a host."""
    for user_data in users_data:
        if not user_data.get("error") and "groups" in user_data:
            username = user_data.get("username")
            if username in user_id_map:
                user_account_id = user_id_map[username]
                for group_name in user_data.get("groups", []):
                    if group_name in group_id_map:
                        group_id = group_id_map[group_name]
                        membership = UserGroupMembership(
                            host_id=host_id,
                            user_account_id=user_account_id,
                            user_group_id=group_id,
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc),
                        )
                        db.add(membership)


router = APIRouter()


@router.post("/agent/auth")
async def authenticate_agent(request: Request):
    """
    Generate authentication token for agent WebSocket connection.
    This endpoint should be called before establishing WebSocket connection.
    """
    client_host = request.client.host if request.client else "unknown"

    # Check rate limiting
    if websocket_security.is_connection_rate_limited(client_host):
        return {"error": "Rate limit exceeded", "retry_after": 900}

    # Record connection attempt
    websocket_security.record_connection_attempt(client_host)

    # For now, we'll extract hostname from headers or use IP
    # In a full implementation, this might come from client certificates
    agent_hostname = request.headers.get("x-agent-hostname", client_host)

    # Generate connection token
    token = websocket_security.generate_connection_token(agent_hostname, client_host)

    return {
        "connection_token": token,
        "expires_in": 3600,
        "websocket_endpoint": "/api/agent/connect",
    }


async def update_or_create_host(
    db: Session, hostname: str, ipv4: str = None, ipv6: str = None
):
    """
    Update existing host record or create a new one.
    """
    host = db.query(Host).filter(Host.fqdn == hostname).first()

    if host:
        # Update existing host
        host.ipv4 = ipv4
        host.ipv6 = ipv6
        host.last_access = datetime.now(timezone.utc)
        host.active = True
        host.status = "up"
        # Don't modify approval_status for existing hosts - preserve the current status
    else:
        # Create new host with pending approval status
        host = Host(
            fqdn=hostname,
            ipv4=ipv4,
            ipv6=ipv6,
            last_access=datetime.now(timezone.utc),
            active=True,
            status="up",
            approval_status="pending",  # New hosts need approval
        )
        db.add(host)

    db.commit()
    db.refresh(host)
    return host


async def handle_system_info(db: Session, connection, message_data: dict):
    """Handle system info message from agent."""
    hostname = message_data.get("hostname")
    ipv4 = message_data.get("ipv4")
    ipv6 = message_data.get("ipv6")
    platform = message_data.get("platform")

    # System info received from agent

    if hostname:
        # Update database
        host = await update_or_create_host(db, hostname, ipv4, ipv6)

        # Check approval status
        debug_logger.info("Host %s approval status: %s", hostname, host.approval_status)
        if host.approval_status != "approved":
            debug_logger.info("Rejecting connection - host not approved")
            error_msg = ErrorMessage(
                "host_not_approved",
                f"Host {hostname} is not approved for connection. Current status: {host.approval_status}",
            )
            await connection.send_message(error_msg.to_dict())
            # Close the WebSocket connection for unapproved hosts
            await connection.websocket.close(code=4003, reason="Host not approved")
            return

        debug_logger.info("Host %s approved, allowing connection", hostname)

        # Register agent in connection manager
        connection_manager.register_agent(
            connection.agent_id, hostname, ipv4, ipv6, platform
        )

        # Send acknowledgment
        response = {
            "message_type": "ack",
            "message_id": message_data.get("message_id"),
            "data": {
                "status": "success",
                "message": _("Host {hostname} registered successfully").format(
                    hostname=hostname
                ),
                "host_id": host.id,
            },
        }
        await connection.send_message(response)
    else:
        error_msg = ErrorMessage(
            "missing_hostname", "Hostname is required for registration"
        )
        await connection.send_message(error_msg.to_dict())


async def handle_heartbeat(db: Session, connection, message_data: dict):
    """Handle heartbeat message from agent."""
    # Update last seen time in connection manager
    connection.last_seen = datetime.now(timezone.utc)

    # Get hostname from message data (new) or connection (fallback)
    hostname = message_data.get("hostname") or connection.hostname
    ipv4 = message_data.get("ipv4") or connection.ipv4
    ipv6 = message_data.get("ipv6") or connection.ipv6

    # Update host status in database if hostname is known
    if hostname:
        # Updating/creating host record
        # Update connection info if provided in heartbeat
        if not connection.hostname and hostname:
            connection.hostname = hostname
            connection.ipv4 = ipv4
            connection.ipv6 = ipv6
            # Register in connection manager
            connection_manager.register_agent(
                connection.agent_id, hostname, ipv4, ipv6, connection.platform
            )

        # Use the same logic as system_info to ensure consistency
        await update_or_create_host(db, hostname, ipv4, ipv6)
    # Note: No hostname available for agent - no database update needed

    # Send heartbeat acknowledgment
    response = {
        "message_type": "ack",
        "message_id": message_data.get("message_id"),
        "data": {"status": "received"},
    }
    await connection.send_message(response)


async def handle_command_result(connection, message_data: dict):
    """Handle command result message from agent."""
    # Command result received from agent
    # Variables available: command_id, success, result, error from message_data

    # Send acknowledgment
    response = {
        "message_type": "ack",
        "message_id": message_data.get("message_id"),
        "data": {"status": "received"},
    }
    await connection.send_message(response)


async def handle_config_acknowledgment(connection, message_data: dict):
    """Handle configuration acknowledgment from agent."""
    hostname = connection.hostname
    version = message_data.get("version", 0)
    success = message_data.get("success", False)
    error = message_data.get("error")

    if hostname:
        config_push_manager.handle_config_acknowledgment(
            hostname, version, success, error
        )

    # Send acknowledgment
    response = {
        "message_type": "ack",
        "message_id": message_data.get("message_id"),
        "data": {"status": "config_ack_received"},
    }
    await connection.send_message(response)


async def handle_os_version_update(db: Session, connection, message_data: dict):
    """Handle OS version update message from agent."""
    debug_logger.info(
        "handle_os_version_update called with connection.hostname: %s",
        getattr(connection, "hostname", "NO HOSTNAME ATTR"),
    )
    debug_logger.info("Message data keys: %s", list(message_data.keys()))
    debug_logger.info("Connection ipv4: %s", getattr(connection, "ipv4", "NO IPV4"))
    debug_logger.info(
        "Connection websocket client: %s",
        getattr(connection.websocket, "client", "NO WEBSOCKET CLIENT"),
    )

    # Try to get hostname from connection first, then from message data
    hostname = connection.hostname or message_data.get("hostname")

    # If no hostname, try to find the host by IP address
    if not hostname:
        client_ip = getattr(connection, "ipv4", None)
        if (
            not client_ip
            and hasattr(connection.websocket, "client")
            and connection.websocket.client
        ):
            # Try to get IP from websocket client
            client_ip = connection.websocket.client.host
            debug_logger.info("Got IP from websocket.client.host: %s", client_ip)

        if client_ip:
            debug_logger.info("No hostname, looking up host by IP: %s", client_ip)
            try:
                host = db.query(Host).filter(Host.ipv4 == client_ip).first()
                if host:
                    hostname = host.fqdn
                    debug_logger.info("Found host by IP lookup: %s", hostname)
            except Exception as e:
                debug_logger.error("Error looking up host by IP: %s", e)

    if not hostname:
        debug_logger.info("No hostname found via any method, returning early")
        return

    # Debug: Log the complete raw message data
    debug_logger.info("=== RAW OS VERSION MESSAGE DATA ===")
    debug_logger.info("Full message_data: %s", json.dumps(message_data, indent=2))
    debug_logger.info("=== END RAW DATA ===")

    debug_logger.info("=== OS Version Update Data Received ===")
    debug_logger.info("FQDN: %s", hostname)
    debug_logger.info("Platform: %s", message_data.get("platform"))
    debug_logger.info("Platform Release: %s", message_data.get("platform_release"))
    debug_logger.info(
        "Machine Architecture: %s", message_data.get("machine_architecture")
    )
    debug_logger.info("Processor: %s", message_data.get("processor"))
    debug_logger.info("OS Info: %s", message_data.get("os_info"))
    debug_logger.info("=== End OS Version Data ===")

    # Update host with new OS version information
    host = db.query(Host).filter(Host.fqdn == hostname).first()

    if host:
        debug_logger.info("Updating existing host with OS version data...")
        try:
            # Update OS version fields
            host.platform = message_data.get("platform")
            host.platform_release = message_data.get("platform_release")
            host.platform_version = message_data.get("platform_version")
            host.machine_architecture = message_data.get("machine_architecture")
            host.processor = message_data.get("processor")

            # Store additional OS info as JSON
            os_info = message_data.get("os_info", {})
            if os_info:
                debug_logger.info("Setting os_details to: %s", json.dumps(os_info))
                host.os_details = json.dumps(os_info)

            host.os_version_updated_at = datetime.now(timezone.utc)
            host.last_access = datetime.now(timezone.utc)

            debug_logger.info(
                "Before commit - Platform: %s, Machine Arch: %s",
                host.platform,
                host.machine_architecture,
            )
            db.commit()
            debug_logger.info("Database commit successful")
            db.refresh(host)
            debug_logger.info(
                "After refresh - Platform: %s, Machine Arch: %s",
                host.platform,
                host.machine_architecture,
            )

        except Exception as e:
            debug_logger.error("Error updating host with OS version data: %s", e)
            db.rollback()
            raise

    # Send acknowledgment
    response = {
        "message_type": "ack",
        "message_id": message_data.get("message_id"),
        "data": {"status": "os_version_updated"},
    }
    await connection.send_message(response)


async def handle_hardware_update(db: Session, connection, message_data: dict):
    """Handle hardware update message from agent."""
    # Try to get hostname from connection first, then from message data
    hostname = connection.hostname or message_data.get("hostname")
    if not hostname:
        debug_logger.info(
            "Hardware update received but no hostname available - skipping"
        )
        return
    debug_logger.info("=== Hardware Update Data Received ===")
    debug_logger.info("FQDN: %s", hostname)
    debug_logger.info(
        "CPU: %s %s", message_data.get("cpu_vendor"), message_data.get("cpu_model")
    )
    debug_logger.info("Memory: %s MB", message_data.get("memory_total_mb"))
    if "storage_devices" in message_data:
        debug_logger.info("Storage devices: %s", len(message_data["storage_devices"]))
    if "network_interfaces" in message_data:
        debug_logger.info(
            "Network interfaces: %s", len(message_data["network_interfaces"])
        )
    debug_logger.info("=== End Hardware Data ===")

    # Update host with new hardware information
    host = db.query(Host).filter(Host.fqdn == hostname).first()

    if host:
        debug_logger.info("Updating existing host with hardware data...")
        try:
            # Update hardware fields
            host.cpu_vendor = message_data.get("cpu_vendor")
            host.cpu_model = message_data.get("cpu_model")
            host.cpu_cores = message_data.get("cpu_cores")
            host.cpu_threads = message_data.get("cpu_threads")
            host.cpu_frequency_mhz = message_data.get("cpu_frequency_mhz")
            host.memory_total_mb = message_data.get("memory_total_mb")
            host.storage_details = message_data.get("storage_details")
            host.network_details = message_data.get("network_details")
            host.hardware_details = message_data.get("hardware_details")

            # Handle normalized storage devices
            if "storage_devices" in message_data:
                debug_logger.info(
                    "Processing %s storage devices...",
                    len(message_data["storage_devices"]),
                )
                # Delete existing storage devices for this host
                db.query(StorageDevice).filter(
                    StorageDevice.host_id == host.id
                ).delete()

                # Add new storage devices
                for device_data in message_data["storage_devices"]:
                    if not device_data.get("error"):  # Skip error entries
                        storage_device = StorageDevice(
                            host_id=host.id,
                            name=device_data.get("name"),
                            device_path=device_data.get("device_path"),
                            mount_point=device_data.get("mount_point"),
                            file_system=device_data.get("file_system"),
                            device_type=device_data.get("device_type"),
                            capacity_bytes=device_data.get("capacity_bytes"),
                            used_bytes=device_data.get("used_bytes"),
                            available_bytes=device_data.get("available_bytes"),
                            is_physical=device_data.get(
                                "is_physical", True
                            ),  # Default to True for backward compatibility
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc),
                        )
                        db.add(storage_device)
                debug_logger.info("Storage devices processing complete")

            # Handle normalized network interfaces
            if "network_interfaces" in message_data:
                debug_logger.info(
                    "Processing %s network interfaces...",
                    len(message_data["network_interfaces"]),
                )
                # Delete existing network interfaces for this host
                db.query(NetworkInterface).filter(
                    NetworkInterface.host_id == host.id
                ).delete()

                # Add new network interfaces
                for interface_data in message_data["network_interfaces"]:
                    if not interface_data.get("error"):  # Skip error entries
                        network_interface = NetworkInterface(
                            host_id=host.id,
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
                        db.add(network_interface)
                debug_logger.info("Network interfaces processing complete")

            host.hardware_updated_at = datetime.now(timezone.utc)
            host.last_access = datetime.now(timezone.utc)

            db.commit()
            debug_logger.info("Hardware data committed to database")
            db.refresh(host)

        except Exception as e:
            debug_logger.error("Error updating host with hardware data: %s", e)
            db.rollback()
            raise

    # Send acknowledgment
    response = {
        "message_type": "ack",
        "message_id": message_data.get("message_id"),
        "data": {"status": "hardware_updated"},
    }
    await connection.send_message(response)


async def handle_user_access_update(db: Session, connection, message_data: dict):
    """Handle user access update message from agent."""
    # Try to get hostname from connection first, then from message data
    hostname = connection.hostname or message_data.get("hostname")
    if not hostname:
        debug_logger.info(
            "User access update received but no hostname available - skipping"
        )
        return
    debug_logger.info("=== User Access Update Data Received ===")
    debug_logger.info("FQDN: %s", hostname)
    debug_logger.info("Platform: %s", message_data.get("platform"))
    debug_logger.info("Total users: %s", message_data.get("total_users", 0))
    debug_logger.info("Total groups: %s", message_data.get("total_groups", 0))
    debug_logger.info("System users: %s", message_data.get("system_users", 0))
    debug_logger.info("Regular users: %s", message_data.get("regular_users", 0))
    if "users" in message_data:
        debug_logger.info("Users data: %s", len(message_data["users"]))
    if "groups" in message_data:
        debug_logger.info("Groups data: %s", len(message_data["groups"]))
    debug_logger.info("=== End User Access Data ===")

    # Update host with new user access information
    host = db.query(Host).filter(Host.fqdn == hostname).first()

    if host:
        debug_logger.info("Updating existing host with user access data...")
        try:
            # Handle normalized user accounts
            if "users" in message_data:
                debug_logger.info(
                    "Processing %s user accounts...",
                    len(message_data["users"]),
                )
                # Delete existing user accounts for this host
                db.query(UserAccount).filter(UserAccount.host_id == host.id).delete()

                # Add new user accounts
                _process_user_accounts(db, host.id, message_data["users"])
                debug_logger.info("User accounts processing complete")

            # Handle normalized user groups
            if "groups" in message_data:
                debug_logger.info(
                    "Processing %s user groups...",
                    len(message_data["groups"]),
                )
                # Delete existing user groups for this host
                db.query(UserGroup).filter(UserGroup.host_id == host.id).delete()

                # Add new user groups
                _process_user_groups(db, host.id, message_data["groups"])
                debug_logger.info("User groups processing complete")

            # Handle user-group memberships
            debug_logger.info("Processing user-group memberships...")

            # Delete existing memberships for this host
            db.query(UserGroupMembership).filter(
                UserGroupMembership.host_id == host.id
            ).delete()

            # Build mapping of usernames to user_account IDs and group names to user_group IDs
            user_id_map = {}
            group_id_map = {}

            for user_account in (
                db.query(UserAccount).filter(UserAccount.host_id == host.id).all()
            ):
                user_id_map[user_account.username] = user_account.id

            for user_group in (
                db.query(UserGroup).filter(UserGroup.host_id == host.id).all()
            ):
                group_id_map[user_group.group_name] = user_group.id

            # Process group memberships from user data
            if "users" in message_data:
                _process_user_group_memberships(
                    db, host.id, message_data["users"], user_id_map, group_id_map
                )

            debug_logger.info("User-group memberships processing complete")

            host.last_access = datetime.now(timezone.utc)

            db.commit()
            debug_logger.info("User access data committed to database")
            db.refresh(host)

        except Exception as e:
            debug_logger.error("Error updating host with user access data: %s", e)
            db.rollback()
            raise

    # Send acknowledgment
    response = {
        "message_type": "ack",
        "message_id": message_data.get("message_id"),
        "data": {"status": "user_access_updated"},
    }
    await connection.send_message(response)


@router.websocket("/agent/connect")
async def agent_connect(websocket: WebSocket):
    """
    Handle secure WebSocket connections from agents with full bidirectional communication.
    Enhanced with authentication and message validation.
    """
    debug_logger.info("WebSocket connection attempt started")
    client_host = websocket.client.host if websocket.client else "unknown"
    debug_logger.info("Client host: %s", client_host)

    # Check for authentication token in query parameters
    auth_token = websocket.query_params.get("token")
    debug_logger.info("Auth token present: %s", bool(auth_token))
    connection_id = None

    if auth_token:
        debug_logger.info("Validating auth token...")
        is_valid, connection_id, error_msg = (
            websocket_security.validate_connection_token(auth_token, client_host)
        )
        debug_logger.info(
            "Token validation result - Valid: %s, Error: %s", is_valid, error_msg
        )
        if not is_valid:
            debug_logger.info("Closing connection due to auth failure")
            await websocket.close(
                code=4001, reason=f"Authentication failed: {error_msg}"
            )
            return
    else:
        debug_logger.info("No auth token provided, closing connection")
        await websocket.close(code=4000, reason="Authentication token required")
        return

    # Accept connection and register with connection manager
    debug_logger.info("About to accept WebSocket connection...")
    connection = await connection_manager.connect(websocket)
    debug_logger.info(
        "WebSocket connection established, connection ID: %s", connection.agent_id
    )
    debug_logger.info("Connection object created, waiting for messages...")
    db = next(get_db())

    try:
        while True:
            # Receive message from agent
            data = await websocket.receive_text()
            debug_logger.info("Received WebSocket message: %s...", data[:100])
            # Message received from agent

            try:
                raw_message = json.loads(data)

                # Validate message integrity and structure
                if not websocket_security.validate_message_integrity(
                    raw_message, connection_id or connection.agent_id
                ):
                    error_msg = ErrorMessage(
                        "message_validation_failed",
                        "Message failed security validation",
                    )
                    await connection.send_message(error_msg.to_dict())
                    continue

                message = create_message(raw_message)
                debug_logger.info("Received message type: %s", message.message_type)
                # Processing message from agent

                # Handle different message types
                if message.message_type == MessageType.SYSTEM_INFO:
                    debug_logger.info("Calling handle_system_info")
                    await handle_system_info(db, connection, message.data)

                elif message.message_type == MessageType.HEARTBEAT:
                    debug_logger.info("Calling handle_heartbeat")
                    await handle_heartbeat(db, connection, message.data)

                elif message.message_type == MessageType.COMMAND_RESULT:
                    debug_logger.info("Calling handle_command_result")
                    await handle_command_result(connection, message.data)

                elif message.message_type == MessageType.ERROR:
                    debug_logger.info("Processing ERROR message type")
                    # Agent reported error - no action needed

                elif message.message_type == "config_ack":
                    debug_logger.info("Calling handle_config_acknowledgment")
                    # Handle configuration acknowledgment
                    await handle_config_acknowledgment(connection, message.data)

                elif message.message_type == MessageType.OS_VERSION_UPDATE:
                    debug_logger.info("Calling handle_os_version_update")
                    try:
                        # Handle OS version update from agent
                        await handle_os_version_update(db, connection, message.data)
                        debug_logger.info(
                            "handle_os_version_update completed successfully"
                        )
                    except Exception as e:
                        debug_logger.error("Error in handle_os_version_update: %s", e)
                        raise

                elif message.message_type == MessageType.HARDWARE_UPDATE:
                    debug_logger.info("Calling handle_hardware_update")
                    try:
                        # Handle hardware update from agent
                        await handle_hardware_update(db, connection, message.data)
                        debug_logger.info(
                            "handle_hardware_update completed successfully"
                        )
                    except Exception as e:
                        debug_logger.error("Error in handle_hardware_update: %s", e)
                        raise

                elif message.message_type == MessageType.USER_ACCESS_UPDATE:
                    debug_logger.info("Calling handle_user_access_update")
                    try:
                        # Handle user access update from agent
                        await handle_user_access_update(db, connection, message.data)
                        debug_logger.info(
                            "handle_user_access_update completed successfully"
                        )
                    except Exception as e:
                        debug_logger.error("Error in handle_user_access_update: %s", e)
                        raise

                else:
                    # Unknown message type - send error
                    error_msg = ErrorMessage(
                        "unknown_message_type",
                        f"Unknown message type: {message.message_type}",
                    )
                    await connection.send_message(error_msg.to_dict())

            except json.JSONDecodeError:
                # Invalid JSON - send error
                error_msg = ErrorMessage("invalid_json", "Message must be valid JSON")
                await connection.send_message(error_msg.to_dict())

            except Exception as exc:
                # Error processing message from agent
                error_msg = ErrorMessage("processing_error", str(exc))
                await connection.send_message(error_msg.to_dict())

    except WebSocketDisconnect:
        # Agent disconnected - normal cleanup handled in finally
        debug_logger.info("Agent disconnected")
    except RuntimeError as e:
        if "WebSocket is not connected" in str(e):
            # WebSocket was closed (e.g., due to unapproved host) - normal cleanup handled in finally
            debug_logger.info("WebSocket connection closed")
        else:
            raise
    finally:
        # Clean up
        connection_manager.disconnect(connection.agent_id)
        db.close()
