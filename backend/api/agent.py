"""
This module implements the remote agent communication with the server over
WebSockets with real-time bidirectional communication capabilities.
Enhanced with security validation and secure communication protocols.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from sqlalchemy.orm import Session

from backend.persistence.db import get_db
from backend.persistence.models import Host
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import ErrorMessage, MessageType, create_message
from backend.security.communication_security import websocket_security
from backend.config.config_push import config_push_manager

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
        if host.approval_status != "approved":
            error_msg = ErrorMessage(
                "host_not_approved",
                f"Host {hostname} is not approved for connection. Current status: {host.approval_status}",
            )
            await connection.send_message(error_msg.to_dict())
            # Close the WebSocket connection for unapproved hosts
            await connection.websocket.close(code=4003, reason="Host not approved")
            return

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
                "message": f"Host {hostname} registered successfully",
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
    else:
        # No hostname available for agent
        pass

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
    hostname = connection.hostname
    if not hostname:
        return

    print("=== OS Version Update Data Received ===")
    print(f"FQDN: {hostname}")
    print(f"Platform: {message_data.get('platform')}")
    print(f"Platform Release: {message_data.get('platform_release')}")
    print(f"Machine Architecture: {message_data.get('machine_architecture')}")
    print(f"Processor: {message_data.get('processor')}")
    print(f"OS Info: {message_data.get('os_info')}")
    print("=== End OS Version Data ===")

    # Update host with new OS version information
    host = db.query(Host).filter(Host.fqdn == hostname).first()

    if host:
        print("Updating existing host with OS version data...")
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
                print(f"Setting os_details to: {json.dumps(os_info)}")
                host.os_details = json.dumps(os_info)

            host.os_version_updated_at = datetime.now(timezone.utc)
            host.last_access = datetime.now(timezone.utc)

            print(
                f"Before commit - Platform: {host.platform}, Machine Arch: {host.machine_architecture}"
            )
            db.commit()
            print("Database commit successful")
            db.refresh(host)
            print(
                f"After refresh - Platform: {host.platform}, Machine Arch: {host.machine_architecture}"
            )

        except Exception as e:
            print(f"Error updating host with OS version data: {e}")
            db.rollback()
            raise

    # Send acknowledgment
    response = {
        "message_type": "ack",
        "message_id": message_data.get("message_id"),
        "data": {"status": "os_version_updated"},
    }
    await connection.send_message(response)


@router.websocket("/agent/connect")
async def agent_connect(websocket: WebSocket):
    """
    Handle secure WebSocket connections from agents with full bidirectional communication.
    Enhanced with authentication and message validation.
    """
    client_host = websocket.client.host if websocket.client else "unknown"

    # Check for authentication token in query parameters
    auth_token = websocket.query_params.get("token")
    connection_id = None

    if auth_token:
        is_valid, connection_id, error_msg = (
            websocket_security.validate_connection_token(auth_token, client_host)
        )
        if not is_valid:
            await websocket.close(
                code=4001, reason=f"Authentication failed: {error_msg}"
            )
            return
    else:
        await websocket.close(code=4000, reason="Authentication token required")
        return

    # Accept connection and register with connection manager
    connection = await connection_manager.connect(websocket)
    db = next(get_db())

    try:
        while True:
            # Receive message from agent
            data = await websocket.receive_text()
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
                # Processing message from agent

                # Handle different message types
                if message.message_type == MessageType.SYSTEM_INFO:
                    await handle_system_info(db, connection, message.data)

                elif message.message_type == MessageType.HEARTBEAT:
                    await handle_heartbeat(db, connection, message.data)

                elif message.message_type == MessageType.COMMAND_RESULT:
                    await handle_command_result(connection, message.data)

                elif message.message_type == MessageType.ERROR:
                    # Agent reported error
                    pass

                elif message.message_type == "config_ack":
                    # Handle configuration acknowledgment
                    await handle_config_acknowledgment(connection, message.data)

                elif message.message_type == MessageType.OS_VERSION_UPDATE:
                    # Handle OS version update from agent
                    await handle_os_version_update(db, connection, message.data)

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
        # Agent disconnected
        pass
    except RuntimeError as e:
        if "WebSocket is not connected" in str(e):
            # WebSocket was closed (e.g., due to unapproved host)
            pass
        else:
            raise
    finally:
        # Clean up
        connection_manager.disconnect(connection.agent_id)
        db.close()
