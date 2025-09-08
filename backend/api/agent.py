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
from backend.websocket.queue_manager import server_queue_manager, QueueDirection
from backend.api.message_handlers import (
    handle_system_info,
    handle_command_result,
    handle_config_acknowledgment,
    handle_heartbeat,
)
from backend.api.update_handlers import handle_update_apply_result

# pylint: disable=unused-import
from backend.api.data_handlers import (
    handle_os_version_update,
)
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
            debug_logger.warning(
                "WEBSOCKET_PROTOCOL_ERROR: Authentication failed from %s: %s",
                client_host,
                error_msg,
            )
            await websocket.close(
                code=4001, reason=_("Authentication failed: %s") % error_msg
            )
            return
    else:
        debug_logger.warning(
            "WEBSOCKET_PROTOCOL_ERROR: No auth token provided from %s", client_host
        )
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
                message_size = len(data)
                debug_logger.info(
                    "Received message type: %s (size: %d bytes)",
                    message.message_type,
                    message_size,
                )
                # Processing message from agent

                # Handle different message types
                if message.message_type == MessageType.SYSTEM_INFO:
                    await _handle_system_info_message(message, connection, db)

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

                elif message.message_type in [
                    MessageType.OS_VERSION_UPDATE,
                    MessageType.HARDWARE_UPDATE,
                    MessageType.USER_ACCESS_UPDATE,
                    MessageType.SOFTWARE_INVENTORY_UPDATE,
                    MessageType.PACKAGE_UPDATES_UPDATE,
                ]:
                    # Process inventory message using helper function to reduce nesting
                    debug_logger.info(
                        "Received inventory message type: %s", message.message_type
                    )
                    await _process_inventory_message(message, connection, db)
                elif message.message_type == MessageType.UPDATE_APPLY_RESULT:
                    await _handle_update_result_message(message, connection, db)

                elif message.message_type == MessageType.SCRIPT_EXECUTION_RESULT:
                    debug_logger.info(
                        "CRAZY_LOG: SCRIPT_EXECUTION_RESULT message received"
                    )
                    debug_logger.info(
                        "CRAZY_LOG: SCRIPT_EXECUTION_RESULT message data keys: %s",
                        list(message.data.keys()) if message.data else [],
                    )
                    debug_logger.info(
                        "CRAZY_LOG: SCRIPT_EXECUTION_RESULT message data: %s",
                        message.data,
                    )

                    # Queue script execution results for reliable processing
                    debug_logger.info(
                        "CRAZY_LOG: About to validate host for script execution result"
                    )
                    host, error_msg = await _validate_and_get_host(
                        message.data, connection, db
                    )
                    debug_logger.info(
                        "CRAZY_LOG: Host validation result - host: %s, error_msg: %s",
                        host,
                        error_msg,
                    )

                    if error_msg:
                        debug_logger.info(
                            "CRAZY_LOG: Host validation failed - sending error message"
                        )
                        await connection.send_message(error_msg.to_dict())
                        return

                    hostname = host.fqdn
                    debug_logger.info(
                        "CRAZY_LOG: Host %s - enqueueing script execution result",
                        hostname,
                    )

                    # Enqueue the message for processing by message processor
                    from backend.websocket.queue_manager import Priority

                    try:
                        queue_message_id = server_queue_manager.enqueue_message(
                            message_type=message.message_type,
                            message_data=message.data,
                            direction=QueueDirection.INBOUND,
                            host_id=host.id,
                            priority=Priority.HIGH,
                            db=db,
                        )
                        debug_logger.info(
                            "Enqueued script execution result from host %s (message_id: %s)",
                            hostname,
                            queue_message_id,
                        )

                        # Send acknowledgment back to agent
                        ack_msg = {
                            "message_type": "script_execution_result_queued",
                            "message_id": queue_message_id,
                        }
                        await connection.send_message(ack_msg)

                    except Exception as e:
                        debug_logger.error(
                            "Error enqueueing script execution result: %s", e
                        )
                        error_msg = ErrorMessage(
                            "queue_error", f"Failed to queue script result: {str(e)}"
                        )
                        await connection.send_message(error_msg.to_dict())

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
                debug_logger.error("Error processing message: %s", exc, exc_info=True)
                error_msg = ErrorMessage("processing_error", str(exc))
                try:
                    await connection.send_message(error_msg.to_dict())
                except Exception as send_exc:
                    debug_logger.error("Failed to send error message: %s", send_exc)

    except WebSocketDisconnect as e:
        # Agent disconnected - normal cleanup handled in finally
        debug_logger.info(
            "WEBSOCKET_COMMUNICATION_ERROR: Agent disconnected normally - WebSocketDisconnect: %s",
            e,
        )
    except RuntimeError as e:
        if "WebSocket is not connected" in str(e):
            # WebSocket was closed (e.g., due to unapproved host) - normal cleanup handled in finally
            debug_logger.info(
                "WEBSOCKET_COMMUNICATION_ERROR: WebSocket connection closed - RuntimeError: %s",
                e,
            )
        else:
            debug_logger.error(
                "WEBSOCKET_UNKNOWN_ERROR: Unexpected RuntimeError in WebSocket handler: %s",
                e,
                exc_info=True,
            )
            raise
    except Exception as e:
        debug_logger.error(
            "WEBSOCKET_UNKNOWN_ERROR: Unexpected exception in WebSocket handler: %s",
            e,
            exc_info=True,
        )
        raise
    finally:
        # Clean up
        connection_manager.disconnect(connection.agent_id)
        db.close()


async def _validate_and_get_host(message_data, connection, db):
    """
    Validate host registration and approval status for inventory messages.

    Returns:
        tuple: (host_object, error_message) - host_object is None if validation fails
    """
    debug_logger.info(
        "CRAZY_LOG: _validate_and_get_host called with message_data keys: %s",
        list(message_data.keys()) if message_data else [],
    )
    hostname = message_data.get("hostname")
    host_id = message_data.get("host_id")
    debug_logger.info(
        "CRAZY_LOG: _validate_and_get_host extracted hostname=%s, host_id=%s",
        hostname,
        host_id,
    )

    if not hostname:
        debug_logger.error("CRAZY_LOG: Message missing hostname - cannot validate host")
        error_msg = ErrorMessage(
            "missing_hostname",
            _("Message must include hostname for host validation"),
        )
        return None, error_msg

    # Look up host in database
    from backend.persistence.models import Host

    # Refresh the database session to ensure we see the latest data
    debug_logger.info("CRAZY_LOG: Refreshing database session")
    db.expunge_all()
    db.commit()

    # If host_id is provided, validate it first
    if host_id is not None:
        debug_logger.info("CRAZY_LOG: Validating message with host_id: %s", host_id)
        host = db.query(Host).filter(Host.id == host_id).first()
        debug_logger.info("CRAZY_LOG: Host lookup by host_id result: %s", host)

        if not host:
            debug_logger.warning(
                "Host ID %s not found - sending stale host_id error", host_id
            )
            error_msg = ErrorMessage(
                "host_not_registered",
                _("Host ID no longer valid - please re-register"),
            )
            return None, error_msg

        # Verify that the host_id matches the hostname (case-insensitive)
        if host.fqdn.lower() != hostname.lower():
            debug_logger.warning(
                "Host ID %s hostname mismatch (expected: %s, got: %s) - sending error",
                host_id,
                host.fqdn,
                hostname,
            )
            error_msg = ErrorMessage(
                "host_not_registered",
                _("Host ID and hostname mismatch - please re-register"),
            )
            return None, error_msg

        debug_logger.info(
            "Host ID validation successful for host %s (ID: %s)", hostname, host_id
        )
    else:
        # No host_id provided, fall back to hostname lookup (case-insensitive)
        debug_logger.info("No host_id provided, validating by hostname: %s", hostname)
        from sqlalchemy import func

        host = db.query(Host).filter(func.lower(Host.fqdn) == hostname.lower()).first()

    if not host:
        debug_logger.warning(
            "Host %s not registered - sending registration required error", hostname
        )
        error_msg = ErrorMessage(
            "host_not_registered",
            _("Host must register before sending inventory data"),
        )
        return None, error_msg

    if host.approval_status != "approved":
        debug_logger.warning(
            "Host %s not approved (status: %s) - sending approval required error",
            hostname,
            host.approval_status,
        )
        error_msg = ErrorMessage(
            "host_not_approved", _("Host registration pending approval")
        )
        return None, error_msg

    return host, None


async def _handle_system_info_message(message, connection, db):
    """Handle system info message with error handling."""
    debug_logger.info("Calling handle_system_info")
    try:
        response = await handle_system_info(db, connection, message.data)
        if response:
            await connection.send_message(response)
            debug_logger.info(
                "handle_system_info response sent: %s",
                response.get("message_type"),
            )
        debug_logger.info("handle_system_info completed successfully")
    except Exception as e:
        debug_logger.error("Error in handle_system_info: %s", e, exc_info=True)
        raise


async def _handle_update_result_message(message, connection, db):
    """Handle update apply result message with error handling."""
    debug_logger.info("Received update apply result from agent")
    try:
        # Handle update application results from agent directly (time-sensitive)
        await handle_update_apply_result(db, connection, message.data)
        debug_logger.info("Update apply result processed successfully")
    except Exception as e:
        debug_logger.error("Error processing update apply result: %s", e)
        raise


async def _process_inventory_message(message, connection, db):
    """Process inventory message after host validation."""
    # Validate host first
    host, error_msg = await _validate_and_get_host(message.data, connection, db)
    if error_msg:
        await connection.send_message(error_msg.to_dict())
        return

    hostname = host.fqdn
    debug_logger.info("Host %s registered and approved - enqueueing message", hostname)
    debug_logger.info(
        "DEBUG: About to enqueue with host.id=%s, host object type=%s",
        host.id,
        type(host),
    )

    # Log detailed message information
    data_keys = list(message.data.keys()) if message.data else []
    data_size = len(str(message.data)) if message.data else 0
    debug_logger.info(
        "SERVER_DEBUG: Enqueueing message type=%s, data_keys=%s, data_size=%d bytes, host_id=%s",
        message.message_type,
        data_keys,
        data_size,
        host.id,
    )

    # Log specific data for different message types
    if message.message_type == "hardware_update":
        cpu_vendor = message.data.get("cpu_vendor", "N/A")
        cpu_model = message.data.get("cpu_model", "N/A")
        memory_mb = message.data.get("memory_total_mb", "N/A")
        storage_count = len(message.data.get("storage_devices", []))
        debug_logger.info(
            "SERVER_DEBUG: Hardware data - CPU: %s %s, Memory: %s MB, Storage devices: %d",
            cpu_vendor,
            cpu_model,
            memory_mb,
            storage_count,
        )
    elif message.message_type == "software_inventory_update":
        total_packages = message.data.get("total_packages", 0)
        software_packages = message.data.get("software_packages", [])
        debug_logger.info(
            "SERVER_DEBUG: Software data - Total packages: %d, First package: %s",
            total_packages,
            software_packages[0] if software_packages else "None",
        )
    elif message.message_type == "user_access_update":
        total_users = message.data.get("total_users", 0)
        total_groups = message.data.get("total_groups", 0)
        debug_logger.info(
            "SERVER_DEBUG: User access data - Users: %d, Groups: %d",
            total_users,
            total_groups,
        )

    try:
        message_id = server_queue_manager.enqueue_message(
            message_type=message.message_type,
            message_data=message.data,
            direction=QueueDirection.INBOUND,
            host_id=host.id,
            db=db,
        )
        debug_logger.info(
            "SERVER_DEBUG: Message enqueued successfully with queue_id=%s for host %s (message_type=%s)",
            message_id,
            hostname,
            message.message_type,
        )

        # Commit the database session to persist the enqueued message
        db.commit()
        debug_logger.info("SERVER_DEBUG: Database committed for message %s", message_id)

        # Send success acknowledgment to agent
        ack_message = {
            "message_type": "ack",
            "message_id": message.data.get("message_id", "unknown"),
            "queue_id": message_id,
            "status": "queued",
        }
        await connection.send_message(ack_message)
        debug_logger.info(
            "SERVER_DEBUG: Successfully processed and acknowledged message %s",
            message.message_type,
        )

    except Exception as e:
        debug_logger.error("Error enqueueing message %s: %s", message.message_type, e)
        error_msg = ErrorMessage("queue_error", f"Failed to queue message: {str(e)}")
        await connection.send_message(error_msg.to_dict())
