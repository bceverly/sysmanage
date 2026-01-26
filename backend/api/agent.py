"""
This module implements the remote agent communication with the server over
WebSockets with real-time bidirectional communication capabilities.
Enhanced with security validation and secure communication protocols.
"""

import json
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

# pylint: disable=unused-import
from backend.api.handlers import handle_os_version_update
from backend.api.message_handlers import (
    handle_command_result,
    handle_config_acknowledgment,
    handle_diagnostic_result,
    handle_heartbeat,
    handle_installation_status,
    handle_system_info,
    validate_host_authentication,
)
from backend.api.update_handlers import handle_update_apply_result
from backend.config.config_push import config_push_manager
from backend.i18n import _
from backend.persistence.db import get_db
from backend.persistence.models import InstallationPackage, InstallationRequest
from backend.security.communication_security import websocket_security
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.utils.verbosity_logger import get_logger
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import ErrorMessage, MessageType, create_message
from backend.websocket.queue_manager import QueueDirection, server_queue_manager

# Set up logger with verbosity support
logger = get_logger("websocket.agent")
logger.info("Agent WebSocket module initialized")

# Ensure config_push_manager is available for tests
__all__ = ["config_push_manager"]


router = APIRouter()  # For authenticated endpoints (will get /api prefix)
public_router = APIRouter()  # For public endpoints (no prefix)


@public_router.post("/agent/auth")
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
    logger.info("WebSocket connection attempt started")
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info(
        "Client host: %s", client_host
    )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure

    # Check for authentication token in query parameters
    auth_token = websocket.query_params.get("token")
    logger.info("Auth token present", extra={"token_present": bool(auth_token)})
    connection_id = None

    # Get database session for audit logging
    db = next(get_db())

    if auth_token:
        logger.info("Validating auth token...")
        is_valid, connection_id, error_msg = (
            websocket_security.validate_connection_token(auth_token, client_host)
        )
        logger.info("Token validation result", extra={"is_valid": is_valid})
        if not is_valid and error_msg:
            logger.debug("Token validation error details available")
        if not is_valid:
            logger.warning(
                "WEBSOCKET_PROTOCOL_ERROR: Authentication failed",
                extra={"client_host": client_host},
            )

            # Log authentication failure
            AuditService.log(
                db=db,
                action_type=ActionType.AGENT_MESSAGE,
                entity_type=EntityType.AGENT,
                entity_id=None,
                entity_name="unknown",
                description=_("Agent WebSocket authentication failed from %s")
                % client_host,
                result=Result.FAILURE,
                details={"client_host": client_host},
                error_message=error_msg,
                ip_address=client_host,
            )

            db.close()
            await websocket.close(
                code=4001, reason=_("Authentication failed: %s") % error_msg
            )
            return
    else:
        logger.warning(
            "WEBSOCKET_PROTOCOL_ERROR: No auth token provided",
            extra={"client_host": client_host},
        )

        # Log missing token
        AuditService.log(
            db=db,
            action_type=ActionType.AGENT_MESSAGE,
            entity_type=EntityType.AGENT,
            entity_id=None,
            entity_name="unknown",
            description=_("Agent WebSocket connection attempted without token from %s")
            % client_host,
            result=Result.FAILURE,
            details={"client_host": client_host},
            error_message="No authentication token provided",
            ip_address=client_host,
        )

        db.close()
        await websocket.close(code=4000, reason=_("Authentication token required"))
        return

    # Accept connection and register with connection manager
    logger.info("About to accept WebSocket connection...")
    connection = await connection_manager.connect(websocket)
    logger.info(
        "WebSocket connection established, connection ID: %s", connection.agent_id
    )
    logger.info("Connection object created, waiting for messages...")
    # db session already opened above for audit logging, continue using it

    try:
        while True:
            # Receive message from agent
            data = await websocket.receive_text()
            logger.info("Received WebSocket message: %s...", data[:100])
            await _process_websocket_message(data, connection, db, connection_id)

    except WebSocketDisconnect as e:
        # Agent disconnected - normal cleanup handled in finally
        logger.info(
            "WEBSOCKET_COMMUNICATION_ERROR: Agent disconnected normally - WebSocketDisconnect: %s",
            e,
        )
    except RuntimeError as e:
        if "WebSocket is not connected" in str(e):
            # WebSocket was closed (e.g., due to unapproved host) - normal cleanup handled in finally
            logger.info(
                "WEBSOCKET_COMMUNICATION_ERROR: WebSocket connection closed - RuntimeError: %s",
                e,
            )
        else:
            logger.error(
                "WEBSOCKET_UNKNOWN_ERROR: Unexpected RuntimeError in WebSocket handler: %s",
                e,
                exc_info=True,
            )
            raise
    except Exception as e:
        logger.error(
            "WEBSOCKET_UNKNOWN_ERROR: Unexpected exception in WebSocket handler: %s",
            e,
            exc_info=True,
        )
        raise
    finally:
        # Clean up
        connection_manager.disconnect(connection.agent_id)
        db.close()


async def _process_websocket_message(data, connection, db, connection_id):
    """Process a single WebSocket message from the agent."""
    try:
        raw_message = json.loads(data)

        # Validate message integrity and structure
        is_valid, validation_error = websocket_security.validate_message_integrity(
            raw_message, connection_id or connection.agent_id
        )
        if not is_valid:
            error_msg = ErrorMessage(
                "message_validation_failed",
                validation_error or _("Message failed security validation"),
            )
            await connection.send_message(error_msg.to_dict())
            return

        message = create_message(raw_message)
        message_size = len(data)
        logger.info(
            "Received message type: %s (size: %d bytes)",
            message.message_type,
            message_size,
        )

        # Handle time-sensitive messages immediately (heartbeats, system_info)
        # These should not be queued as they need immediate processing
        if message.message_type in [MessageType.HEARTBEAT, MessageType.SYSTEM_INFO]:
            await _handle_message_by_type(message, connection, db)
        else:
            # Queue all other messages for background processing
            _enqueue_inbound_message(message, connection, db)

    except json.JSONDecodeError:
        # Invalid JSON - send error
        error_msg = ErrorMessage("invalid_json", _("Message must be valid JSON"))
        await connection.send_message(error_msg.to_dict())

    except Exception as exc:
        # Error processing message from agent
        logger.error("Error processing message: %s", exc, exc_info=True)
        error_msg = ErrorMessage("processing_error", str(exc))
        try:
            await connection.send_message(error_msg.to_dict())
        except Exception as send_exc:
            logger.error("Failed to send error message: %s", send_exc)


def _enqueue_inbound_message(message, connection, db):
    """
    Enqueue an inbound message for background processing.
    WebSocket thread should ONLY queue messages, not process them.
    """
    from backend.websocket.queue_enums import Priority, QueueDirection
    from backend.websocket.queue_operations import QueueOperations

    queue_ops = QueueOperations()

    # Store connection information in the message data for later use
    message_data = message.data.copy() if message.data else {}
    message_data["_connection_info"] = {
        "agent_id": connection.agent_id,
        "hostname": connection.hostname,
        "ipv4": connection.ipv4,
        "ipv6": connection.ipv6,
        "platform": connection.platform,
    }

    # Enqueue for background processing
    queue_ops.enqueue_message(
        message_type=message.message_type,
        message_data=message_data,
        direction=QueueDirection.INBOUND,
        host_id=None,  # Will be determined during processing
        priority=(
            Priority.HIGH
            if message.message_type == MessageType.SYSTEM_INFO
            else Priority.NORMAL
        ),
        message_id=message.message_id,
        db=db,
    )

    logger.info(
        "Enqueued %s message from connection %s for background processing",
        message.message_type,
        connection.agent_id,
    )


async def _handle_message_by_type(message, connection, db):
    """
    Handle time-sensitive messages that need immediate processing.

    Note: This function is ONLY called for HEARTBEAT and SYSTEM_INFO messages.
    All other message types are queued and processed by the inbound processor.
    """
    if message.message_type == MessageType.SYSTEM_INFO:
        await _handle_system_info_message(message, connection, db)

    elif message.message_type == MessageType.HEARTBEAT:
        logger.info("Calling handle_heartbeat")
        # Add message_id to the data so the handler can access it
        heartbeat_data = message.data.copy()
        heartbeat_data["message_id"] = message.message_id
        await handle_heartbeat(db, connection, heartbeat_data)

    else:
        # This should never happen - log a warning
        logger.warning(
            "Unexpected message type in _handle_message_by_type: %s. "
            "This function should only be called for HEARTBEAT and SYSTEM_INFO messages.",
            message.message_type,
        )


async def _handle_script_execution_result(message, connection, db):
    """Handle script execution result message."""
    logger.debug("Processing script execution result message")
    logger.debug(
        "Script execution result data keys: %s",
        list(message.data.keys()) if message.data else [],
    )

    # Queue script execution results for reliable processing
    host, error_msg = await _validate_and_get_host(message.data, connection, db)
    if error_msg:
        logger.warning("Host validation failed for script execution result")
        await connection.send_message(error_msg.to_dict())
        return

    hostname = host.fqdn
    logger.info("Enqueueing script execution result for host: %s", hostname)

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
        logger.info(
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
        logger.error("Error enqueueing script execution result: %s", e)
        error_msg = ErrorMessage(
            "queue_error", f"Failed to queue script result: {str(e)}"
        )
        await connection.send_message(error_msg.to_dict())


async def _handle_diagnostic_result_msg(message, connection, db):
    """Handle diagnostic collection result message."""
    logger.info("Diagnostic collection result received")
    logger.info(
        "Diagnostic result data keys: %s",
        list(message.data.keys()) if message.data else [],
    )

    # Handle diagnostic collection result directly (no queuing needed)
    try:
        response = await handle_diagnostic_result(db, connection, message.data)
        logger.info("Diagnostic collection result processed successfully")
        # Send acknowledgment back to agent
        if response:
            await connection.send_message(response)
    except Exception as e:
        logger.error("Error processing diagnostic collection result: %s", e)
        error_msg = ErrorMessage(
            "diagnostic_error",
            f"Failed to process diagnostic result: {str(e)}",
        )
        await connection.send_message(error_msg.to_dict())


def _extract_host_identifier(message_data, connection, db):
    """Extract hostname and host_id from message data or connection."""
    hostname = message_data.get("hostname")
    host_id = message_data.get("host_id")

    # Fall back to connection hostname
    if not hostname and not host_id and connection and connection.hostname:
        hostname = connection.hostname
        logger.debug("Using connection hostname for validation: %s", hostname)

    # Try to look up by IP address
    if not hostname and not host_id and connection:
        hostname = _lookup_host_by_ip(connection, db)

    return hostname, host_id


def _lookup_host_by_ip(connection, db):
    """Look up host by IP address and return hostname if found."""
    from backend.persistence.models import Host

    if connection.ipv4:
        logger.debug("Attempting host lookup by IPv4: %s", connection.ipv4)
        host_by_ip = db.query(Host).filter(Host.ipv4 == connection.ipv4).first()
        if host_by_ip:
            logger.debug("Found host by IPv4 address: %s", host_by_ip.fqdn)
            return host_by_ip.fqdn

    if connection.ipv6:
        logger.debug("Attempting host lookup by IPv6: %s", connection.ipv6)
        host_by_ip = db.query(Host).filter(Host.ipv6 == connection.ipv6).first()
        if host_by_ip:
            logger.debug("Found host by IPv6 address: %s", host_by_ip.fqdn)
            return host_by_ip.fqdn

    return None


def _get_connection_info(connection):
    """Gather connection info for audit logging."""
    connection_info = {}
    if not connection:
        return connection_info

    attrs = ["hostname", "ipv4", "ipv6", "platform", "agent_id"]
    for attr in attrs:
        value = getattr(connection, attr, None)
        if value:
            key = f"connection_{attr}" if attr != "agent_id" else attr
            connection_info[key] = value
    return connection_info


def _validate_hostname_match(hostname, host):
    """Validate that hostname matches the host record."""
    if not hostname:
        return True

    hostname_lower = hostname.lower()
    fqdn_lower = host.fqdn.lower()
    short_name = fqdn_lower.split(".")[0]

    return hostname_lower in {fqdn_lower, short_name}


def _log_missing_host_info(db, message_data, connection):
    """Log audit entry for missing host info."""
    connection_info = _get_connection_info(connection)
    AuditService.log(
        db=db,
        action_type=ActionType.AGENT_MESSAGE,
        entity_type=EntityType.AGENT,
        entity_id=None,
        entity_name="unknown",
        description=_("Agent message validation failed: missing hostname and host_id"),
        result=Result.FAILURE,
        details={
            "message_data_keys": list(message_data.keys()) if message_data else [],
            **connection_info,
        },
        error_message="Message missing both hostname and host_id",
    )


def _log_unregistered_host(db, hostname, host_id):
    """Log audit entry for unregistered host."""
    host_name = hostname or f"host_id:{host_id}"
    AuditService.log(
        db=db,
        action_type=ActionType.AGENT_MESSAGE,
        entity_type=EntityType.AGENT,
        entity_id=None,
        entity_name=host_name,
        description=_("Agent message from unregistered host: {hostname}").format(
            hostname=host_name
        ),
        result=Result.FAILURE,
        details={"hostname": hostname, "host_id": str(host_id) if host_id else None},
        error_message="Host not registered",
    )


def _log_unapproved_host(db, host, hostname):
    """Log audit entry for unapproved host."""
    AuditService.log(
        db=db,
        action_type=ActionType.AGENT_MESSAGE,
        entity_type=EntityType.HOST,
        entity_id=str(host.id),
        entity_name=hostname,
        description=_("Agent message from unapproved host: {hostname}").format(
            hostname=hostname
        ),
        result=Result.FAILURE,
        details={"hostname": hostname, "approval_status": host.approval_status},
        error_message="Host not approved",
    )


async def _validate_and_get_host(message_data, connection, db):  # NOSONAR
    """
    Validate host registration and approval status for inventory messages.

    Returns:
        tuple: (host_object, error_message) - host_object is None if validation fails
    """
    from backend.persistence.models import Host
    from sqlalchemy import func

    logger.debug(
        "Validating host with message data keys: %s",
        list(message_data.keys()) if message_data else [],
    )

    hostname, host_id = _extract_host_identifier(message_data, connection, db)
    logger.debug("Extracted hostname=%s, host_id=%s for validation", hostname, host_id)

    # Must have either hostname or host_id
    if not hostname and not host_id:
        logger.error("Message missing both hostname and host_id - cannot validate host")
        _log_missing_host_info(db, message_data, connection)
        return None, ErrorMessage(
            "missing_host_info",
            _("Message must include hostname or host_id for host validation"),
        )

    # Refresh database session
    db.expire_all()
    db.flush()

    # Look up host
    host = None
    if host_id is not None:
        logger.debug("Validating message with host_id: %s", host_id)
        host = db.query(Host).filter(Host.id == host_id).first()

        if not host:
            logger.warning(
                "Host ID %s not found - sending stale host_id error", host_id
            )
            return None, ErrorMessage(
                "host_not_registered", _("Host ID no longer valid - please re-register")
            )

        if not _validate_hostname_match(hostname, host):
            logger.warning(
                "Host ID %s hostname mismatch (expected: %s, got: %s)",
                host_id,
                host.fqdn,
                hostname,
            )
            return None, ErrorMessage(
                "host_not_registered",
                _("Host ID and hostname mismatch - please re-register"),
            )

        logger.info(
            "Host ID validation successful for host %s (ID: %s)", host.fqdn, host_id
        )
    else:
        logger.info("No host_id provided, validating by hostname: %s", hostname)
        host = db.query(Host).filter(func.lower(Host.fqdn) == hostname.lower()).first()

    if not host:
        host_name = hostname or f"host_id:{host_id}"
        logger.warning(
            "Host %s not registered - sending registration required error", host_name
        )
        _log_unregistered_host(db, hostname, host_id)
        return None, ErrorMessage(
            "host_not_registered", _("Host must register before sending inventory data")
        )

    if host.approval_status != "approved":
        logger.warning(
            "Host %s not approved (status: %s) - sending approval required error",
            host.fqdn,
            host.approval_status,
        )
        _log_unapproved_host(db, host, hostname)
        return None, ErrorMessage(
            "host_not_approved", _("Host registration pending approval")
        )

    return host, None


async def _handle_system_info_message(message, connection, db):
    """Handle system info message with error handling."""
    logger.info(
        "Calling handle_system_info - IMMEDIATE PROCESSING for connection registration"
    )
    try:
        # Process system_info immediately for connection registration
        # This is critical to ensure the connection manager is updated
        # before any outbound messages are processed
        response = await handle_system_info(db, connection, message.data)
        if response:
            await connection.send_message(response)
            logger.info(
                "handle_system_info response sent: %s",
                response.get("message_type"),
            )

            # If this was a successful registration, log the connection manager state
            if response.get("message_type") == "registration_success":
                logger.info(
                    "Agent registered successfully - connection manager now has hostnames: %s",
                    list(connection_manager.hostname_to_agent.keys()),
                )
        logger.info("handle_system_info completed successfully")
    except Exception as e:
        logger.error("Error in handle_system_info: %s", e, exc_info=True)
        raise


async def _handle_update_result_message(message, connection, db):
    """Handle update apply result message with error handling."""
    logger.info("Received update apply result from agent")
    try:
        # Handle update application results from agent directly (time-sensitive)
        await handle_update_apply_result(db, connection, message.data)
        logger.info("Update apply result processed successfully")
    except Exception as e:
        logger.error("Error processing update apply result: %s", e)
        raise


async def _process_inventory_message(message, connection, db):
    """Process inventory message after host validation."""
    # Validate host first
    host, error_msg = await _validate_and_get_host(message.data, connection, db)
    if error_msg:
        await connection.send_message(error_msg.to_dict())
        return

    hostname = host.fqdn
    logger.info("Host %s registered and approved - enqueueing message", hostname)
    logger.info(
        "DEBUG: About to enqueue with host.id=%s, host object type=%s",
        host.id,
        type(host),
    )

    # Log detailed message information
    data_keys = list(message.data.keys()) if message.data else []
    data_size = len(str(message.data)) if message.data else 0
    logger.info(
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
        logger.info(
            "SERVER_DEBUG: Hardware data - CPU: %s %s, Memory: %s MB, Storage devices: %d",
            cpu_vendor,
            cpu_model,
            memory_mb,
            storage_count,
        )
    elif message.message_type == "software_inventory_update":
        total_packages = message.data.get("total_packages", 0)
        software_packages = message.data.get("software_packages", [])
        logger.info(
            "SERVER_DEBUG: Software data - Total packages: %d, First package: %s",
            total_packages,
            software_packages[0] if software_packages else "None",
        )
    elif message.message_type == "user_access_update":
        total_users = message.data.get("total_users", 0)
        total_groups = message.data.get("total_groups", 0)
        logger.info(
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
        logger.info(
            "SERVER_DEBUG: Message enqueued successfully with queue_id=%s for host %s (message_type=%s)",
            message_id,
            hostname,
            message.message_type,
        )

        # Commit the database session to persist the enqueued message
        db.commit()
        logger.debug("Database committed for message %s", message_id)

        # Send success acknowledgment to agent
        ack_message = {
            "message_type": "ack",
            "message_id": message.data.get("message_id", "unknown"),
            "queue_id": message_id,
            "status": "queued",
        }
        await connection.send_message(ack_message)
        logger.info(
            "SERVER_DEBUG: Successfully processed and acknowledged message %s",
            message.message_type,
        )

    except Exception as e:
        logger.error("Error enqueueing message %s: %s", message.message_type, e)
        error_msg = ErrorMessage("queue_error", f"Failed to queue message: {str(e)}")
        await connection.send_message(error_msg.to_dict())


async def _handle_packages_batch_message(message, connection, db):
    """Handle packages batch messages by enqueueing them for ordered processing."""
    # Get host information for validation
    from backend.persistence.models import Host

    # Try to get host from message data first (host_id), then from connection
    host = None
    host_id = message.data.get("host_id")
    if host_id:
        host = db.query(Host).filter(Host.id == host_id).first()
        logger.info(
            "Enqueueing %s message for host_id: %s", message.message_type, host_id
        )

    if not host:
        # Fall back to hostname from connection
        hostname = getattr(connection, "hostname", "unknown")
        logger.info(
            "Enqueueing %s message for host: %s", message.message_type, hostname
        )
        host = db.query(Host).filter(Host.fqdn == hostname).first()

    if not host:
        logger.error(
            "Host not found for batch message (host_id=%s, hostname=%s)",
            host_id,
            getattr(connection, "hostname", "unknown"),
        )
        error_msg = ErrorMessage("host_not_found", "Host not found")
        await connection.send_message(error_msg.to_dict())
        return

    # Enqueue the message for processing by message processor with HIGH priority
    # to ensure batch messages are processed quickly and in order
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
        logger.info(
            "Enqueued %s from host %s (queue_id: %s)",
            message.message_type,
            host.fqdn,
            queue_message_id,
        )

        # Send acknowledgment back to agent
        ack_msg = {
            "message_type": f"{message.message_type}_queued",
            "message_id": queue_message_id,
            "status": "queued",
        }
        await connection.send_message(ack_msg)

    except Exception as e:
        logger.error("Error enqueueing %s: %s", message.message_type, e)
        error_msg = ErrorMessage(
            "queue_error", f"Failed to queue {message.message_type}: {str(e)}"
        )
        await connection.send_message(error_msg.to_dict())


class InstallationCompletionRequest(BaseModel):
    """Request from agent when installation completes."""

    request_id: str
    success: bool
    result_log: str


@router.post("/agent/installation-complete")
async def handle_installation_completion(
    request: InstallationCompletionRequest,
    agent_request: Request,
    db: Session = Depends(get_db),
):
    """
    Handle completion notification from agent using host token authentication.

    This endpoint is called by the agent when a package installation request completes.
    The agent passes back the request_id (UUID) and the result log.
    """
    try:
        # Extract host token from Authorization header
        auth_header = agent_request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=401, detail=_("Missing or invalid authorization header")
            )

        host_token = auth_header.replace("Bearer ", "")

        # Create mock message data for validation
        message_data = {
            "host_token": host_token,
            "hostname": "agent",  # This will be validated against stored hostname
        }

        # Create mock connection object for validation
        class MockConnection:
            def __init__(self):
                self.client_host = (
                    agent_request.client.host if agent_request.client else "unknown"
                )

        # Validate host authentication
        validation_result = await validate_host_authentication(
            db, MockConnection(), message_data
        )
        is_valid = validation_result[0]
        if not is_valid:
            raise HTTPException(
                status_code=403, detail=_("Invalid host authentication")
            )

        # Find the installation request
        installation_request = (
            db.query(InstallationRequest)
            .filter(InstallationRequest.id == request.request_id)
            .first()
        )

        if not installation_request:
            raise HTTPException(
                status_code=404,
                detail=_("Installation request not found: %s") % request.request_id,
            )

        # Update the request with completion data
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        installation_request.completed_at = now
        installation_request.status = "completed" if request.success else "failed"
        installation_request.result_log = request.result_log

        # Update individual package statuses
        packages = (
            db.query(InstallationPackage)
            .filter(InstallationPackage.installation_request_id == request.request_id)
            .all()
        )

        for package in packages:
            package.status = "completed" if request.success else "failed"
            package.completed_at = now

        db.commit()

        logger.info(
            "Installation completion processed for request %s: %s",
            request.request_id,
            "success" if request.success else "failed",
        )

        return {"status": "success", "message": _("Installation completion recorded")}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing installation completion: %s", e)
        raise HTTPException(status_code=500, detail=_("Internal server error")) from e
