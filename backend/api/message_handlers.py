"""
Message handlers for SysManage agent WebSocket communication.
Handles various message types received from agents.

This module is the main entry point that re-exports handlers from sub-modules:
- Core handlers (authentication, system_info, heartbeat) from message_handlers_core
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host, SoftwareInstallationLog
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

# Re-export core handlers for backwards compatibility
from backend.api.message_handlers_core import (
    validate_host_authentication,
    handle_system_info,
    handle_heartbeat,
)

# Use standard logger that respects /etc/sysmanage.yaml configuration
logger = logging.getLogger(__name__)

# Export all handlers for use by message router
__all__ = [
    "validate_host_authentication",
    "handle_system_info",
    "handle_heartbeat",
    "handle_command_result",
    "handle_config_acknowledgment",
    "handle_diagnostic_result",
    "handle_command_acknowledgment",
    "handle_installation_status",
]


async def handle_command_result(connection, message_data: dict):  # NOSONAR
    """Handle command execution result from agent."""
    logger.info(
        "Command result from %s: %s",
        getattr(connection, "hostname", "unknown"),
        {
            k: (
                v
                if k
                not in ["packages", "package_managers", "child_hosts", "capabilities"]
                else f"<{len(v) if isinstance(v, list) else 'dict'} items>"
            )
            for k, v in message_data.items()
        },
    )

    # Check if this is a script execution result
    if "execution_id" in message_data:
        logger.info("Detected script execution result, routing to script handler")
        # Import here to avoid circular imports
        from backend.api.handlers import handle_script_execution_result
        from backend.persistence.db import get_db

        # Get database session and route to script handler
        db_session = next(get_db())
        try:
            return await handle_script_execution_result(
                db_session, connection, message_data
            )
        finally:
            db_session.close()

    # Check if this is a virtualization support result
    result_data = message_data.get("result", {})
    if result_data is None:
        result_data = {}

    if "supported_types" in result_data or "capabilities" in result_data:
        logger.info("Detected virtualization support result, routing to handler")
        from backend.api.handlers import handle_virtualization_support_update
        from backend.persistence.db import get_db

        db_session = next(get_db())
        try:
            return await handle_virtualization_support_update(
                db_session, connection, message_data
            )
        finally:
            db_session.close()

    # Check if this is a child hosts list result
    if "child_hosts" in result_data:
        logger.info("Detected child hosts list result, routing to handler")
        from backend.api.handlers import handle_child_hosts_list_update
        from backend.persistence.db import get_db

        db_session = next(get_db())
        try:
            return await handle_child_hosts_list_update(
                db_session, connection, message_data
            )
        finally:
            db_session.close()

    # Check if this is a child host control result (start/stop/restart/delete)
    # This must be checked BEFORE the creation result check since control results
    # also have child_name and child_type in them
    command_type = message_data.get("command_type") or message_data.get("data", {}).get(
        "command_type"
    )
    if command_type in [
        "start_child_host",
        "stop_child_host",
        "restart_child_host",
        "delete_child_host",
    ]:
        logger.info(
            "Detected child host control result (%s), routing to handler", command_type
        )
        from backend.api.handlers.child_host_handlers import (
            handle_child_host_start_result,
            handle_child_host_stop_result,
            handle_child_host_restart_result,
            handle_child_host_delete_result,
        )
        from backend.persistence.db import get_db

        handler_map = {
            "start_child_host": handle_child_host_start_result,
            "stop_child_host": handle_child_host_stop_result,
            "restart_child_host": handle_child_host_restart_result,
            "delete_child_host": handle_child_host_delete_result,
        }

        db_session = next(get_db())
        try:
            return await handler_map[command_type](db_session, connection, message_data)
        finally:
            db_session.close()

    # Check if this is a child host creation result
    # This must be checked AFTER control commands since they also have child_name/child_type
    if "child_name" in result_data and result_data.get("child_type"):
        # Only route to creation handler if it's not a control command result
        # Control commands are already handled above
        if command_type not in [
            "start_child_host",
            "stop_child_host",
            "restart_child_host",
            "delete_child_host",
        ]:
            logger.info("Detected child host creation result, routing to handler")
            from backend.api.handlers import handle_child_host_created
            from backend.persistence.db import get_db

            db_session = next(get_db())
            try:
                return await handle_child_host_created(
                    db_session, connection, message_data
                )
            finally:
                db_session.close()

    # Check if this is a WSL enable result
    if "reboot_required" in result_data and result_data.get("success") is not None:
        # Check if this looks like a WSL enable result (not a generic reboot status)
        if command_type == "enable_wsl":
            logger.info("Detected WSL enable result, routing to handler")
            from backend.api.handlers import handle_wsl_enable_result
            from backend.persistence.db import get_db

            db_session = next(get_db())
            try:
                return await handle_wsl_enable_result(
                    db_session, connection, message_data
                )
            finally:
                db_session.close()

    # Check if this is a LXD initialize result
    if command_type == "initialize_lxd":
        logger.info("Detected LXD initialize result, routing to handler")
        from backend.api.handlers import handle_lxd_initialize_result
        from backend.persistence.db import get_db

        db_session = next(get_db())
        try:
            return await handle_lxd_initialize_result(
                db_session, connection, message_data
            )
        finally:
            db_session.close()

    # Check if this is a VMM initialize result
    if command_type == "initialize_vmm":
        logger.info("Detected VMM initialize result, routing to handler")
        from backend.api.handlers import handle_vmm_initialize_result
        from backend.persistence.db import get_db

        db_session = next(get_db())
        try:
            return await handle_vmm_initialize_result(
                db_session, connection, message_data
            )
        finally:
            db_session.close()

    # Check if this is a KVM initialize result
    if command_type == "initialize_kvm":
        logger.info("Detected KVM initialize result, routing to handler")
        from backend.api.handlers import handle_kvm_initialize_result
        from backend.persistence.db import get_db

        db_session = next(get_db())
        try:
            return await handle_kvm_initialize_result(
                db_session, connection, message_data
            )
        finally:
            db_session.close()

    logger.info("PACKAGE_DEBUG: message_data keys: %s", list(message_data.keys()))
    logger.info(
        "PACKAGE_DEBUG: result_data type: %s, keys: %s",
        type(result_data),
        list(result_data.keys()) if isinstance(result_data, dict) else "N/A",
    )
    if (
        "packages" in message_data
        or "package_managers" in message_data
        or "packages" in result_data
        or "package_managers" in result_data
    ):
        logger.info("Detected package collection result, routing to package handler")
        # Import here to avoid circular imports
        from backend.api.handlers import handle_package_collection
        from backend.persistence.db import get_db

        # For new message format, merge result data into message_data for backwards compatibility
        if result_data and (
            "packages" in result_data or "package_managers" in result_data
        ):
            combined_data = {**message_data, **result_data}
        else:
            combined_data = message_data

        # Get database session and route to package handler
        db_session = next(get_db())
        try:
            return handle_package_collection(db_session, connection, combined_data)
        finally:
            db_session.close()

    # Regular command result - just acknowledge
    return {
        "message_type": "command_result_ack",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def handle_config_acknowledgment(connection, message_data: dict):  # NOSONAR
    """Handle configuration acknowledgment from agent."""
    logger.info(
        "Configuration acknowledged by %s: %s",
        getattr(connection, "hostname", "unknown"),
        message_data.get("status", "unknown"),
    )

    return {
        "message_type": "config_ack_received",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def handle_diagnostic_result(db: Session, connection, message_data: dict):
    """Handle diagnostic collection result from agent."""
    from backend.api.diagnostics import process_diagnostic_result

    logger.info(
        "Diagnostic collection result from %s: %s",
        getattr(connection, "hostname", "unknown"),
        {
            k: v for k, v in message_data.items() if k != "data"
        },  # Log metadata without full data
    )

    try:
        # Process the diagnostic result
        await process_diagnostic_result(message_data)

        # Update host diagnostics request status to completed if we have a host_id
        if hasattr(connection, "host_id") and connection.host_id:
            stmt = (
                update(Host)
                .where(Host.id == connection.host_id)
                .values(diagnostics_request_status="completed")
            )
            db.execute(stmt)
            db.commit()

        return {
            "message_type": "diagnostic_result_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
        }
    except Exception as e:
        logger.error(
            "Error processing diagnostic result from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )

        # Mark diagnostics request as failed if we have a host_id
        if hasattr(connection, "host_id") and connection.host_id:
            try:
                stmt = (
                    update(Host)
                    .where(Host.id == connection.host_id)
                    .values(diagnostics_request_status="failed")
                )
                db.execute(stmt)
                db.commit()
            except Exception as db_error:
                logger.error(
                    "Failed to update diagnostics request status to failed: %s",
                    db_error,
                )

        return {
            "message_type": "error",
            "error_type": "operation_failed",
            "message": _("Failed to process diagnostic result: %s") % str(e),
            "data": {},
        }


async def handle_command_acknowledgment(  # NOSONAR
    db: Session, connection, message_data: dict
):
    """
    Handle command acknowledgment from agent.

    When the agent receives a command, it sends an acknowledgment back to confirm receipt.
    This allows us to mark the message as completed and avoid retrying it.

    Args:
        db: Database session
        connection: The WebSocket connection
        message_data: The acknowledgment message data containing 'message_id'

    Returns:
        Acknowledgment response dict
    """
    from backend.websocket.queue_manager import server_queue_manager

    message_id = message_data.get("message_id")
    hostname = getattr(connection, "hostname", "unknown")

    if not message_id:
        logger.warning("Command acknowledgment from %s missing message_id", hostname)
        return {
            "message_type": "error",
            "error_type": "missing_message_id",
            "message": _("Missing message_id in command acknowledgment"),
            "data": {},
        }

    # Look up the original message to get command details for logging
    from backend.persistence.models import MessageQueue

    original_msg = db.query(MessageQueue).filter_by(message_id=message_id).first()

    if original_msg:
        try:
            import json

            msg_data = (
                json.loads(original_msg.message_data)
                if isinstance(original_msg.message_data, str)
                else original_msg.message_data
            )
            command_type = msg_data.get("data", {}).get("command_type", "unknown")
            if command_type == "create_child_host":
                distribution = (
                    msg_data.get("data", {})
                    .get("parameters", {})
                    .get("distribution", "unknown")
                )
                logger.info(
                    "ACK RECEIVED for create_child_host: message_id=%s, distribution=%s, from=%s, current_status=%s",
                    message_id,
                    distribution,
                    hostname,
                    original_msg.status,
                )
            else:
                logger.info(
                    "ACK RECEIVED: message_id=%s, command_type=%s, from=%s, current_status=%s",
                    message_id,
                    command_type,
                    hostname,
                    original_msg.status,
                )
        except Exception as e:
            logger.info(
                "ACK RECEIVED: message_id=%s, from=%s (could not parse details: %s)",
                message_id,
                hostname,
                str(e),
            )
    else:
        logger.warning(
            "ACK RECEIVED for UNKNOWN message: message_id=%s, from=%s",
            message_id,
            hostname,
        )

    # Mark the message as acknowledged (completed)
    success = server_queue_manager.mark_acknowledged(message_id, db=db)

    if success:
        logger.info(
            "ACK PROCESSED: message %s marked as completed from %s",
            message_id,
            hostname,
        )
    else:
        logger.warning(
            "ACK FAILED: Could not mark message %s as acknowledged from %s - may not exist or wrong status",
            message_id,
            hostname,
        )

    return {
        "message_type": "command_acknowledgment_received",
        "message_id": message_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def handle_installation_status(  # NOSONAR
    db: Session, connection, message_data: dict
):
    """Handle package installation status update from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": _("Host not registered"),
            "data": {},
        }

    installation_id = message_data.get("installation_id")
    status = message_data.get("status")
    package_name = message_data.get("package_name")
    error_message = message_data.get("error_message")
    installed_version = message_data.get("installed_version")
    installation_log = message_data.get("installation_log")

    logger.info(
        "Package installation status from %s: %s - %s (%s)",
        getattr(connection, "hostname", "unknown"),
        package_name,
        status,
        installation_id,
    )

    if not installation_id:
        logger.error("Package installation status missing installation_id")
        return {
            "message_type": "error",
            "error_type": "missing_installation_id",
            "message": _("Missing installation_id in package installation status"),
            "data": {},
        }

    try:
        # Find the installation log entry
        installation_log_entry = (
            db.query(SoftwareInstallationLog)
            .filter(SoftwareInstallationLog.installation_id == installation_id)
            .first()
        )

        if not installation_log_entry:
            logger.warning(
                "Installation log entry not found for installation_id: %s",
                installation_id,
            )
            return {
                "message_type": "error",
                "error_type": "installation_not_found",
                "message": _("Installation log entry not found for ID: %s")
                % installation_id,
                "data": {},
            }

        # Update the installation log with the new status
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        installation_log_entry.status = status
        installation_log_entry.updated_at = now

        if status == "installing":
            installation_log_entry.started_at = now
        elif status in ["completed", "failed"]:
            installation_log_entry.completed_at = now
            installation_log_entry.success = status == "completed"

            if error_message:
                installation_log_entry.error_message = error_message
            if installed_version:
                installation_log_entry.installed_version = installed_version
            if installation_log:
                installation_log_entry.installation_log = installation_log

        # Commit the changes
        db.commit()

        logger.info(
            "Updated package installation status: %s -> %s (ID: %s)",
            package_name,
            status,
            installation_id,
        )

        # Log significant package installation status changes (not "installing" state)
        if status in ["completed", "failed"]:
            hostname = getattr(connection, "hostname", "unknown")
            host_id_value = getattr(connection, "host_id", None)

            AuditService.log(
                db=db,
                action_type=ActionType.AGENT_MESSAGE,
                entity_type=EntityType.PACKAGE,
                entity_id=str(installation_id),
                entity_name=package_name or "unknown",
                description=_(
                    "Package installation {status} on agent {hostname}"
                ).format(status=status, hostname=hostname),
                result=Result.SUCCESS if status == "completed" else Result.FAILURE,
                details={
                    "installation_id": str(installation_id),
                    "package_name": package_name,
                    "status": status,
                    "installed_version": installed_version,
                    "host_id": str(host_id_value) if host_id_value else None,
                    "hostname": hostname,
                },
                error_message=error_message if status == "failed" else None,
            )

        return {
            "message_type": "package_installation_status_ack",
            "timestamp": now.isoformat(),
            "installation_id": installation_id,
            "status": "updated",
        }

    except Exception as e:
        db.rollback()
        logger.error(
            "Error updating package installation status for %s: %s", installation_id, e
        )
        return {
            "message_type": "error",
            "error_type": "operation_failed",
            "message": _("Failed to update package installation status: %s") % str(e),
            "data": {},
        }
