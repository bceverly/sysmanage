"""
Helper functions for virtualization handlers.

This module provides common utilities used by virtualization handlers
to reduce code duplication and improve maintainability.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

logger = logging.getLogger(__name__)


def make_error_response(
    error_type: str, message: str, data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a standardized error response."""
    return {
        "message_type": "error",
        "error_type": error_type,
        "message": message,
        "data": data or {},
    }


def get_host_id_or_error(connection: Any) -> tuple[Optional[str], Optional[Dict]]:
    """
    Extract host_id from connection or return error response.

    Returns:
        Tuple of (host_id, None) on success, or (None, error_response) on failure
    """
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        return None, make_error_response("no_host_id", _("No host_id on connection"))
    return host_id, None


def extract_result_data(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract result data from message, handling both nested and flat formats."""
    result_data = message_data.get("result", {})
    return result_data if result_data else message_data


def check_success_or_error(
    message_data: Dict[str, Any], result_data: Dict[str, Any]
) -> tuple[bool, Optional[str]]:
    """
    Check if operation succeeded, return success flag and error message.

    Returns:
        Tuple of (success, error_message)
    """
    success = message_data.get("success", result_data.get("success", False))
    if not success:
        error = message_data.get("error") or result_data.get("error", "Unknown error")
        return False, error
    return True, None


def get_host_or_error(
    db: Session, host_id: str, context: str
) -> tuple[Optional[Host], Optional[Dict]]:
    """
    Get host from database or return error response.

    Args:
        db: Database session
        host_id: Host ID to look up
        context: Context string for logging (e.g., "KVM initialize result")

    Returns:
        Tuple of (host, None) on success, or (None, error_response) on failure
    """
    host = db.query(Host).filter(Host.id == host_id).first()
    if not host:
        logger.warning("Host not found for %s: %s", context, host_id)
        return None, make_error_response("host_not_found", _("Host not found"))
    return host, None


def queue_virtualization_check(db: Session, host_id: str) -> None:
    """Queue a virtualization support check command for a host."""
    from backend.websocket.messages import create_command_message
    from backend.websocket.queue_enums import QueueDirection
    from backend.websocket.queue_operations import QueueOperations

    queue_ops = QueueOperations()
    virtualization_command = create_command_message(
        command_type="check_virtualization_support", parameters={}
    )
    queue_ops.enqueue_message(
        message_type="command",
        message_data=virtualization_command,
        direction=QueueDirection.OUTBOUND,
        host_id=str(host_id),
        db=db,
    )


def log_audit_success(
    db: Session,
    host_id: str,
    host_fqdn: str,
    description: str,
    details: Dict[str, Any],
) -> None:
    """Log a successful audit event."""
    AuditService.log(
        db=db,
        action_type=ActionType.AGENT_MESSAGE,
        entity_type=EntityType.HOST,
        entity_id=str(host_id),
        entity_name=host_fqdn,
        description=description,
        result=Result.SUCCESS,
        details=details,
    )


def make_ack_response(
    message_type: str, extra_fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a standardized acknowledgment response."""
    response = {
        "message_type": message_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra_fields:
        response.update(extra_fields)
    return response


async def handle_simple_init_result(  # NOSONAR - async handler
    db: Session,
    connection: Any,
    message_data: Dict[str, Any],
    hypervisor_name: str,
    ack_message_type: str,
    audit_description: str,
    extra_result_fields: Optional[list] = None,
    extra_ack_fields: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Generic handler for simple initialization results that queue a virtualization check.

    This handles the common pattern of:
    1. Validate host_id
    2. Check success/error
    3. Look up host
    4. Queue virtualization check
    5. Log audit event
    6. Return ack

    Args:
        db: Database session
        connection: WebSocket connection
        message_data: Message data from agent
        hypervisor_name: Name for logging (e.g., "LXD", "KVM", "bhyve")
        ack_message_type: Message type for acknowledgment response
        audit_description: Description for audit log
        extra_result_fields: Additional fields to extract from result_data
        extra_ack_fields: Additional fields to include in ack response

    Returns:
        Response dict
    """
    # Validate host_id
    host_id, error = get_host_id_or_error(connection)
    if error:
        logger.warning(
            "%s initialize result received but no host_id on connection",
            hypervisor_name,
        )
        return error

    # Extract and validate result
    result_data = extract_result_data(message_data)
    success, error_msg = check_success_or_error(message_data, result_data)

    if not success:
        logger.error(
            "%s initialization failed for host %s: %s",
            hypervisor_name,
            host_id,
            error_msg,
        )
        return make_error_response("operation_failed", error_msg or _("Unknown error"))

    # Extract extra fields from result
    extra_details = {}
    ack_extras = {}
    message = result_data.get("message", "")

    if extra_result_fields:
        for field in extra_result_fields:
            extra_details[field] = result_data.get(field)

    if extra_ack_fields:
        for field in extra_ack_fields:
            ack_extras[field] = result_data.get(field)

    logger.info(
        "%s initialization result for host %s: success=%s",
        hypervisor_name,
        host_id,
        success,
    )

    try:
        # Get host
        host, error = get_host_or_error(
            db, host_id, f"{hypervisor_name} initialize result"
        )
        if error:
            return error

        # Queue virtualization check and commit
        queue_virtualization_check(db, host_id)
        db.commit()

        # Log audit
        audit_details = {"message": message}
        audit_details.update(extra_details)
        log_audit_success(db, host_id, host.fqdn, audit_description, audit_details)

        logger.info(
            "%s initialized for host %s, queued virtualization check",
            hypervisor_name,
            host_id,
        )

        return make_ack_response(ack_message_type, ack_extras)

    except Exception as e:
        logger.error(
            "Error updating %s initialize status for host %s: %s",
            hypervisor_name,
            host_id,
            e,
            exc_info=True,
        )
        return make_error_response("operation_failed", str(e))
