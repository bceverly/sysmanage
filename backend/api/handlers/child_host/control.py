"""
Child host control handlers.

This module handles child host control messages from agents,
including start, stop, restart, and delete operations.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host, HostChild
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

logger = logging.getLogger(__name__)


async def handle_child_host_start_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle child host start result from agent.

    Updates the host_child status to 'running' on success.

    Args:
        db: Database session
        connection: WebSocket connection object
        message_data: Message data containing start result

    Returns:
        Acknowledgment message
    """
    return await _handle_child_host_control_result(
        db, connection, message_data, "start", "running"
    )


async def handle_child_host_stop_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle child host stop result from agent.

    Updates the host_child status to 'stopped' on success.

    Args:
        db: Database session
        connection: WebSocket connection object
        message_data: Message data containing stop result

    Returns:
        Acknowledgment message
    """
    return await _handle_child_host_control_result(
        db, connection, message_data, "stop", "stopped"
    )


async def handle_child_host_restart_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle child host restart result from agent.

    Updates the host_child status to 'running' on success.

    Args:
        db: Database session
        connection: WebSocket connection object
        message_data: Message data containing restart result

    Returns:
        Acknowledgment message
    """
    return await _handle_child_host_control_result(
        db, connection, message_data, "restart", "running"
    )


async def handle_child_host_delete_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle child host delete result from agent.

    Removes the host_child record on success.

    Args:
        db: Database session
        connection: WebSocket connection object
        message_data: Message data containing delete result

    Returns:
        Acknowledgment message
    """
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning("Child host delete result received but no host_id on connection")
        return {"message_type": "error", "error": "No host_id on connection"}

    result_data = message_data.get("result", {})
    if not result_data:
        result_data = message_data

    # Check success at both message level and result level
    # command_result messages have success at top level, with result containing data
    success = message_data.get("success", result_data.get("success", False))
    child_name = result_data.get("child_name")
    child_type = result_data.get("child_type", "wsl")
    error = message_data.get("error") or result_data.get("error")

    if not success:
        # Check if this is a GUID mismatch error (stale delete prevented)
        expected_guid = result_data.get("expected_guid")
        current_guid = result_data.get("current_guid")

        if expected_guid and current_guid:
            # This is a GUID mismatch - the original instance was deleted and
            # a new one with the same name was created. The stale delete was
            # correctly prevented by the agent.
            logger.warning(
                "Stale delete prevented for host %s, child %s: "
                "expected GUID %s but found %s. Removing stale record.",
                host_id,
                child_name,
                expected_guid,
                current_guid,
            )

            # Delete the stale child host record from the database
            # since the original instance no longer exists
            if child_name:
                try:
                    child = (
                        db.query(HostChild)
                        .filter(
                            HostChild.parent_host_id == host_id,
                            HostChild.child_name == child_name,
                            HostChild.child_type == child_type,
                            HostChild.wsl_guid == expected_guid,
                        )
                        .first()
                    )
                    if child:
                        db.delete(child)
                        db.commit()
                        logger.info(
                            "Deleted stale child host record %s (GUID: %s)",
                            child_name,
                            expected_guid,
                        )
                except Exception as e:
                    logger.error("Error deleting stale child host record: %s", e)

            return {
                "message_type": "child_host_delete_stale",
                "child_name": child_name,
                "expected_guid": expected_guid,
                "current_guid": current_guid,
                "message": "Stale delete prevented - original instance no longer exists",
            }

        logger.error(
            "Child host delete failed for host %s, child %s: %s",
            host_id,
            child_name,
            error,
        )

        # Update status to error
        if child_name:
            try:
                child = (
                    db.query(HostChild)
                    .filter(
                        HostChild.parent_host_id == host_id,
                        HostChild.child_name == child_name,
                        HostChild.child_type == child_type,
                    )
                    .first()
                )
                if child:
                    child.status = "error"
                    child.error_message = error
                    child.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    db.commit()
            except Exception as e:
                logger.error("Error updating child host status: %s", e)

        return {"message_type": "error", "error": error}

    logger.info(
        "Child host deleted for host %s: name=%s, type=%s",
        host_id,
        child_name,
        child_type,
    )

    try:
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            logger.warning("Host not found for child host delete: %s", host_id)
            return {"message_type": "error", "error": "Host not found"}

        # Delete the child host record
        child = (
            db.query(HostChild)
            .filter(
                HostChild.parent_host_id == host_id,
                HostChild.child_name == child_name,
                HostChild.child_type == child_type,
            )
            .first()
        )

        if child:
            # Store child info before deleting
            child_host_id = child.child_host_id
            child_hostname = child.hostname

            # Delete the child host record first
            db.delete(child)
            db.commit()

            # Also delete any registered host record for this child
            deleted_host_info = None
            if child_host_id:
                # Delete the linked host record
                linked_host = db.query(Host).filter(Host.id == child_host_id).first()
                if linked_host:
                    deleted_host_info = {
                        "id": str(linked_host.id),
                        "fqdn": linked_host.fqdn,
                    }
                    logger.info(
                        "Deleting linked host record for child %s: host_id=%s, fqdn=%s",
                        child_name,
                        child_host_id,
                        linked_host.fqdn,
                    )
                    db.delete(linked_host)
                    db.commit()
            elif child_hostname:
                # If no linked host but we have a hostname, try to find and delete
                # a host record with matching fqdn
                # Extract short hostname (first part before any dot)
                child_short_hostname = child_hostname.split(".")[0]

                matching_host = (
                    db.query(Host)
                    .filter(func.lower(Host.fqdn) == func.lower(child_hostname))
                    .first()
                )
                # Also try prefix match (hostname without domain)
                if not matching_host:
                    matching_host = (
                        db.query(Host)
                        .filter(
                            func.lower(Host.fqdn).like(
                                func.lower(child_hostname + ".%")
                            )
                        )
                        .first()
                    )
                # Try reverse prefix match (Host.fqdn is short, child_hostname is FQDN)
                if not matching_host:
                    matching_host = (
                        db.query(Host)
                        .filter(
                            func.lower(child_hostname).like(
                                func.lower(Host.fqdn) + ".%"
                            )
                        )
                        .first()
                    )
                # Try matching just the short hostname
                if not matching_host:
                    matching_host = (
                        db.query(Host)
                        .filter(
                            func.lower(Host.fqdn) == func.lower(child_short_hostname)
                        )
                        .first()
                    )
                # Try matching short hostname as prefix of Host.fqdn
                if not matching_host:
                    matching_host = (
                        db.query(Host)
                        .filter(
                            func.lower(Host.fqdn).like(
                                func.lower(child_short_hostname + ".%")
                            )
                        )
                        .first()
                    )
                if matching_host:
                    deleted_host_info = {
                        "id": str(matching_host.id),
                        "fqdn": matching_host.fqdn,
                    }
                    logger.info(
                        "Deleting matching host record for child %s: host_id=%s, fqdn=%s",
                        child_name,
                        matching_host.id,
                        matching_host.fqdn,
                    )
                    db.delete(matching_host)
                    db.commit()

            AuditService.log(
                db=db,
                action_type=ActionType.AGENT_MESSAGE,
                entity_type=EntityType.HOST,
                entity_id=str(host_id),
                entity_name=host.fqdn,
                description=_("Child host deleted: %s") % child_name,
                result=Result.SUCCESS,
                details={
                    "child_name": child_name,
                    "child_type": child_type,
                    "child_host_id": str(child_host_id) if child_host_id else None,
                    "deleted_host": deleted_host_info,
                },
            )

        return {
            "message_type": "child_host_delete_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "child_name": child_name,
            "status": "deleted",
        }

    except Exception as e:
        db.rollback()
        logger.error(
            "Error deleting child host record for host %s: %s",
            host_id,
            e,
            exc_info=True,
        )
        return {"message_type": "error", "error": str(e)}


async def _handle_child_host_control_result(
    db: Session,
    connection: Any,
    message_data: Dict[str, Any],
    action: str,
    success_status: str,
) -> Dict[str, Any]:
    """
    Common handler for start/stop/restart result processing.

    Args:
        db: Database session
        connection: WebSocket connection object
        message_data: Message data containing result
        action: The action that was performed (start, stop, restart)
        success_status: The status to set on success (running, stopped)

    Returns:
        Acknowledgment message
    """
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning(
            "Child host %s result received but no host_id on connection", action
        )
        return {"message_type": "error", "error": "No host_id on connection"}

    result_data = message_data.get("result", {})
    if not result_data:
        result_data = message_data

    # Check success at both message level and result level
    # command_result messages have success at top level, with result containing data
    success = message_data.get("success", result_data.get("success", False))
    child_name = result_data.get("child_name")
    child_type = result_data.get("child_type", "wsl")
    new_status = result_data.get("status", success_status)
    error = message_data.get("error") or result_data.get("error")

    if not success:
        logger.error(
            "Child host %s failed for host %s, child %s: %s",
            action,
            host_id,
            child_name,
            error,
        )
        return {"message_type": "error", "error": error}

    logger.info(
        "Child host %s succeeded for host %s: name=%s, new_status=%s",
        action,
        host_id,
        child_name,
        new_status,
    )

    try:
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            logger.warning("Host not found for child host %s: %s", action, host_id)
            return {"message_type": "error", "error": "Host not found"}

        # Update the child host status
        child = (
            db.query(HostChild)
            .filter(
                HostChild.parent_host_id == host_id,
                HostChild.child_name == child_name,
                HostChild.child_type == child_type,
            )
            .first()
        )

        if child:
            child.status = new_status
            child.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            child.error_message = None  # Clear any previous error
            db.commit()

            AuditService.log(
                db=db,
                action_type=ActionType.AGENT_MESSAGE,
                entity_type=EntityType.HOST,
                entity_id=str(host_id),
                entity_name=host.fqdn,
                description=_("Child host %s: %s") % (action, child_name),
                result=Result.SUCCESS,
                details={
                    "child_name": child_name,
                    "child_type": child_type,
                    "action": action,
                    "new_status": new_status,
                },
            )

        return {
            "message_type": f"child_host_{action}_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "child_name": child_name,
            "status": new_status,
        }

    except Exception as e:
        db.rollback()
        logger.error(
            "Error updating child host %s status for host %s: %s",
            action,
            host_id,
            e,
            exc_info=True,
        )
        return {"message_type": "error", "error": str(e)}
