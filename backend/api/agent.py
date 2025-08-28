"""
This module implements the remote agent communication with the server over
WebSockets with real-time bidirectional communication capabilities.
Enhanced with security validation and secure communication protocols.
"""

import json
from datetime import datetime

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
        host.last_access = datetime.utcnow()
        host.active = True
        host.status = "up"
    else:
        # Create new host
        host = Host(
            fqdn=hostname,
            ipv4=ipv4,
            ipv6=ipv6,
            last_access=datetime.utcnow(),
            active=True,
            status="up",
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

    if hostname:
        # Update database
        host = await update_or_create_host(db, hostname, ipv4, ipv6)

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
    connection.last_seen = datetime.utcnow()

    # Update host status in database if hostname is known
    if connection.hostname:
        host = db.query(Host).filter(Host.fqdn == connection.hostname).first()
        if host:
            host.last_access = datetime.utcnow()
            host.status = "up"
            host.active = True
            db.commit()

    # Send heartbeat acknowledgment
    response = {
        "message_type": "ack",
        "message_id": message_data.get("message_id"),
        "data": {"status": "received"},
    }
    await connection.send_message(response)


async def handle_command_result(connection, message_data: dict):
    """Handle command result message from agent."""
    command_id = message_data.get("command_id")
    success = message_data.get("success")
    result = message_data.get("result")
    error = message_data.get("error")

    print(
        f"Command {command_id} result from {connection.hostname}: "
        f"success={success}, result={result}, error={error}"
    )

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
            print(f"Message received from agent {connection.agent_id}: {data}")

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

                # Handle different message types
                if message.message_type == MessageType.SYSTEM_INFO:
                    await handle_system_info(db, connection, message.data)

                elif message.message_type == MessageType.HEARTBEAT:
                    await handle_heartbeat(db, connection, message.data)

                elif message.message_type == MessageType.COMMAND_RESULT:
                    await handle_command_result(connection, message.data)

                elif message.message_type == MessageType.ERROR:
                    print(f"Agent {connection.agent_id} reported error: {message.data}")

                elif message.message_type == "config_ack":
                    # Handle configuration acknowledgment
                    await handle_config_acknowledgment(connection, message.data)

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
                # Unexpected error
                print(
                    f"Error processing message from agent {connection.agent_id}: {exc}"
                )
                error_msg = ErrorMessage("processing_error", str(exc))
                await connection.send_message(error_msg.to_dict())

    except WebSocketDisconnect:
        print(f"Agent {connection.agent_id} disconnected")
    finally:
        # Clean up
        connection_manager.disconnect(connection.agent_id)
        db.close()
