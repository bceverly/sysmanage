# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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

from backend.api.handlers import handle_os_version_update  # re-export for tests
from backend.api.message_handlers import (
    handle_command_acknowledgment,
    handle_heartbeat,
    handle_system_info,
    validate_host_authentication,
)
from backend.config.config_push import config_push_manager
from backend.i18n import _
from backend.persistence.db import get_db
from backend.persistence.models import InstallationPackage, InstallationRequest
from backend.security.communication_security import websocket_security
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.utils.verbosity_logger import get_logger
from backend.websocket.connection_manager import connection_manager
from backend.websocket.messages import ErrorMessage, MessageType, create_message

# Set up logger with verbosity support
logger = get_logger("websocket.agent")
logger.info("Agent WebSocket module initialized")

# Ensure config_push_manager is available for tests
__all__ = ["config_push_manager", "handle_os_version_update"]


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
            logger.exception(
                "WEBSOCKET_UNKNOWN_ERROR: Unexpected RuntimeError in WebSocket handler: %s",
                e,
                exc_info=True,
            )
            raise
    except Exception as e:
        logger.exception(
            "WEBSOCKET_UNKNOWN_ERROR: Unexpected exception in WebSocket handler: %s",
            e,
            exc_info=True,
        )
        raise
    finally:
        # Clean up
        connection_manager.disconnect(connection.agent_id)
        db.close()


async def _handle_time_sensitive_message(message, connection, db):
    """Route a time-sensitive message (heartbeat / command-ack) to the host's
    TENANT database when the host is bound, else the bootstrap ``db``.  These
    touch host-scoped data (host status, the host's queue), so a bound host's
    must hit its tenant DB.  SYSTEM_INFO self-routes from its own host_id and the
    id isn't known on the first connection, so it stays on ``db`` here.  Inert
    when MT is off / host unbound.  Commits the fresh tenant session — command-ack
    doesn't self-commit (heartbeat does, so the extra commit no-ops)."""
    from backend.persistence.partitions import tenant_engine_for_host  # noqa: PLC0415

    host_id = getattr(connection, "host_id", None)
    tenant_engine = (
        None
        if message.message_type == MessageType.SYSTEM_INFO or not host_id
        else tenant_engine_for_host(host_id)
    )
    if tenant_engine is None:
        await _handle_message_by_type(message, connection, db)
        return

    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    tenant_db = sessionmaker(bind=tenant_engine)()
    try:
        await _handle_message_by_type(message, connection, tenant_db)
        tenant_db.commit()
    except Exception:
        tenant_db.rollback()
        raise
    finally:
        tenant_db.close()


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

        # Handle time-sensitive messages immediately (heartbeats, system_info,
        # command_acknowledgment). These should not be queued as they need
        # immediate processing. Command acks are especially time-sensitive
        # because the server has a 60-second ack timeout window.
        if message.message_type in [
            MessageType.HEARTBEAT,
            MessageType.SYSTEM_INFO,
            MessageType.COMMAND_ACKNOWLEDGMENT,
        ]:
            await _handle_time_sensitive_message(message, connection, db)
        else:
            # Queue all other messages for background processing
            _enqueue_inbound_message(message, connection, db)

    except json.JSONDecodeError:
        # Invalid JSON - send error
        error_msg = ErrorMessage("invalid_json", _("Message must be valid JSON"))
        await connection.send_message(error_msg.to_dict())

    except Exception as exc:
        # Error processing message from agent
        logger.exception("Error processing message: %s", exc, exc_info=True)
        error_msg = ErrorMessage("processing_error", str(exc))
        try:
            await connection.send_message(error_msg.to_dict())
        except Exception as send_exc:
            logger.exception("Failed to send error message: %s", send_exc)


def _enqueue_inbound_message(message, connection, db):
    """
    Enqueue an inbound message for background processing.
    WebSocket thread should ONLY queue messages, not process them.

    If the WebSocket connection has not yet completed SYSTEM_INFO
    registration (``connection.hostname`` still ``None``), non-handshake
    messages are buffered on the connection instead of enqueued.
    Without this, messages that race ahead of registration end up
    persisted with ``_connection_info.hostname=null`` and the inbound
    processor's NULL-host_id path discards them as "Missing hostname
    and host_id" — losing data entirely (the OS section of theol9
    surfaced this: every ``os_version_update`` was dropped because the
    agent fired it ~340 ms before the SYSTEM_INFO handler set
    ``connection.hostname``).  Buffered messages are flushed by
    ``flush_pending_inbound_messages`` once registration completes.

    SYSTEM_INFO messages are exempt from buffering — they ARE the
    registration handshake, and buffering them would deadlock the
    connection.  In production they take a separate immediate-handler
    path (``_handle_message_by_type``) and never arrive here, but this
    function is also exercised directly by unit tests, so the guard
    keeps the behaviour correct in both call paths.
    """
    if not connection.hostname and message.message_type != MessageType.SYSTEM_INFO:
        existing = getattr(connection, "_pending_inbound_messages", None)
        if not isinstance(existing, list):
            existing = []
            connection._pending_inbound_messages = (  # pylint: disable=protected-access
                existing
            )
        existing.append(message)
        logger.info(
            "Buffered %s message from connection %s — registration not "
            "yet complete (connection.hostname is None)",
            message.message_type,
            connection.agent_id,
        )
        return

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
    # Commit the enqueue NOW.  ``enqueue_message`` only FLUSHES when handed a
    # session — the commit is the caller's job.  We must not rely on a later
    # handler committing this same ``db``: for a tenant-bound host the
    # time-sensitive handlers (heartbeat/ack) route to and commit the host's
    # TENANT session instead (see ``_handle_time_sensitive_message``), so this
    # bootstrap session would otherwise never be committed and the queued
    # message would be silently rolled back — losing the agent's inventory/OS
    # updates entirely.
    db.commit()

    logger.info(
        "Enqueued %s message from connection %s for background processing",
        message.message_type,
        connection.agent_id,
    )


def flush_pending_inbound_messages(connection, db):
    """Drain any pre-registration buffered messages on the connection.

    Called from the SYSTEM_INFO handler once ``connection.hostname`` and
    ``connection.host_id`` have been populated, so the messages can be
    re-enqueued with a complete ``_connection_info`` snapshot.

    Type-check the buffer with ``isinstance(..., list)`` instead of
    relying on ``getattr(..., None)`` — Mock-based connection fixtures
    in the unit tests auto-create attributes on access and would return
    a Mock instead of None, which then fails ``len()``.
    """
    pending = getattr(connection, "_pending_inbound_messages", None)
    if not isinstance(pending, list) or not pending:
        return
    connection._pending_inbound_messages = []  # pylint: disable=protected-access
    logger.info(
        "Flushing %d buffered inbound messages for connection %s (host=%s)",
        len(pending),
        connection.agent_id,
        connection.hostname,
    )
    for buffered in pending:
        _enqueue_inbound_message(buffered, connection, db)


async def _handle_message_by_type(message, connection, db):
    """
    Handle time-sensitive messages that need immediate processing.

    Called for HEARTBEAT, SYSTEM_INFO, and COMMAND_ACKNOWLEDGMENT messages.
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

    elif message.message_type == MessageType.COMMAND_ACKNOWLEDGMENT:
        # Process acks immediately - they are time-sensitive (60-second window)
        # and the message_id (which references the outbound message to acknowledge)
        # is at the top level, not inside message.data, so it would be lost
        # if enqueued through the normal background processing pipeline.
        ack_data = {"message_id": message.message_id}
        await handle_command_acknowledgment(db, connection, ack_data)
        # Commit the ack status change - mark_acknowledged() skips commit when
        # a session is provided, and the WebSocket handler uses a long-lived
        # session, so we must commit explicitly (same pattern as handle_heartbeat).
        db.commit()

    else:
        # This should never happen - log a warning
        logger.warning(
            "Unexpected message type in _handle_message_by_type: %s. "
            "This function should only be called for HEARTBEAT and SYSTEM_INFO messages.",
            message.message_type,
        )


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
        logger.exception("Error in handle_system_info: %s", e, exc_info=True)
        raise


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
        logger.exception("Error processing installation completion: %s", e)
        raise HTTPException(status_code=500, detail=_("Internal server error")) from e
