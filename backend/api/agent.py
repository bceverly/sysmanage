"""
This module implements the remote agent communication with the server over
WebSockets with real-time bidirectional communication capabilities.
Enhanced with security validation and secure communication protocols.
"""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request

from backend.i18n import _
from backend.persistence.db import get_db
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import ErrorMessage, MessageType, create_message
from backend.api.message_handlers import (
    handle_system_info,
    handle_command_result,
    handle_config_acknowledgment,
)
from backend.api.update_handlers import handle_update_apply_result
from backend.security.communication_security import websocket_security
from backend.config.config_push import config_push_manager

# Import handlers for backward compatibility with tests
from backend.api.data_handlers import (
    handle_os_version_update,
    handle_hardware_update,
    handle_user_access_update,
    handle_software_update,
    handle_package_updates_update,
)
from backend.api.message_handlers import handle_heartbeat

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

# Ensure config_push_manager is available for tests
__all__ = ["config_push_manager"]


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
        return {"error": _("Rate limit exceeded"), "retry_after": 900}

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
                code=4001, reason=_("Authentication failed: %s") % error_msg
            )
            return
    else:
        debug_logger.info("No auth token provided, closing connection")
        await websocket.close(code=4000, reason=_("Authentication token required"))
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
                        _("Message failed security validation"),
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

                elif message.message_type == MessageType.SOFTWARE_INVENTORY_UPDATE:
                    debug_logger.info("Calling handle_software_update")
                    try:
                        # Handle software inventory update from agent
                        await handle_software_update(db, connection, message.data)
                        debug_logger.info(
                            "handle_software_update completed successfully"
                        )
                    except Exception as e:
                        debug_logger.error("Error in handle_software_update: %s", e)
                        raise
                elif message.message_type == MessageType.PACKAGE_UPDATES_UPDATE:
                    debug_logger.info("Calling handle_package_updates_update")
                    try:
                        # Handle package updates update from agent
                        await handle_package_updates_update(
                            db, connection, message.data
                        )
                        debug_logger.info(
                            "handle_package_updates_update completed successfully"
                        )
                    except Exception as e:
                        debug_logger.error(
                            "Error in handle_package_updates_update: %s", e
                        )
                        raise
                elif message.message_type == MessageType.UPDATE_APPLY_RESULT:
                    debug_logger.info("Received update apply result from agent")
                    try:
                        # Handle update application results from agent
                        await handle_update_apply_result(db, connection, message.data)
                        debug_logger.info("Update apply result processed successfully")
                    except Exception as e:
                        debug_logger.error(
                            "Error processing update apply result: %s", e
                        )
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
                error_msg = ErrorMessage(
                    "invalid_json", _("Message must be valid JSON")
                )
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
