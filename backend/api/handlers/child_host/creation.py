"""
Child host creation handlers.

This module handles child host creation messages from agents,
including progress updates and completion notifications.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host, HostChild
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

logger = logging.getLogger(__name__)


async def handle_child_host_creation_progress(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle child host creation progress update from agent.

    This is called during the child host creation process to provide
    real-time progress updates to the UI.

    Args:
        db: Database session
        connection: WebSocket connection object
        message_data: Message data containing progress info

    Returns:
        Acknowledgment message
    """
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning(
            "Child host creation progress received but no host_id on connection"
        )
        return {
            "message_type": "error",
            "error_type": "no_host_id",
            "message": _("No host_id on connection"),
            "data": {},
        }

    data = message_data.get("data", message_data)
    step = data.get("step", "unknown")
    message = data.get("message", "")

    logger.info(
        "Child host creation progress for host %s: step=%s, message=%s",
        host_id,
        step,
        message,
    )

    # The progress update is primarily for real-time UI updates
    # We broadcast it to connected clients via WebSocket
    # The actual state tracking is done when the creation completes

    return {
        "message_type": "child_host_creation_progress_ack",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "step": step,
    }


async def handle_child_host_created(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle child host creation result from agent.

    Updates the host_child table with the newly created child host.

    Args:
        db: Database session
        connection: WebSocket connection object
        message_data: Message data containing creation result

    Returns:
        Acknowledgment message
    """
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning(
            "Child host created message received but no host_id on connection"
        )
        return {
            "message_type": "error",
            "error_type": "no_host_id",
            "message": _("No host_id on connection"),
            "data": {},
        }

    result_data = message_data.get("result", {})
    if not result_data:
        result_data = message_data

    # Check success at both message level and result level
    # command_result messages have success at top level, with result containing data
    success = message_data.get("success", result_data.get("success", False))
    child_name = result_data.get("child_name")
    child_type = result_data.get("child_type", "wsl")
    hostname = result_data.get("hostname")
    username = result_data.get("username")
    error = message_data.get("error") or result_data.get("error")
    reboot_required = result_data.get("reboot_required", False)

    if not success:
        logger.error("Child host creation failed for host %s: %s", host_id, error)

        try:
            # Update placeholder record to error status if it exists
            existing = (
                db.query(HostChild)
                .filter(
                    HostChild.parent_host_id == host_id,
                    HostChild.child_name == child_name,
                    HostChild.child_type == child_type,
                    HostChild.status == "creating",
                )
                .first()
            )
            if existing:
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                existing.status = "error"
                existing.error_message = error
                existing.updated_at = now
                db.commit()
                logger.info(
                    "Updated placeholder child host to error status: %s", child_name
                )
        except Exception as e:
            logger.error("Error updating placeholder child host status: %s", e)

        # If reboot is required for WSL enablement, update host
        if reboot_required:
            try:
                host = db.query(Host).filter(Host.id == host_id).first()
                if host:
                    # Only set reboot_required if not already set for another reason
                    # that takes precedence
                    if not host.reboot_required or host.reboot_required_reason in [
                        None,
                        "",
                        "WSL feature enablement pending",
                    ]:
                        host.reboot_required = True
                        host.reboot_required_reason = "WSL feature enablement pending"
                        db.commit()

                        AuditService.log(
                            db=db,
                            action_type=ActionType.AGENT_MESSAGE,
                            entity_type=EntityType.HOST,
                            entity_id=str(host_id),
                            entity_name=host.fqdn,
                            description=_("WSL enablement requires reboot"),
                            result=Result.SUCCESS,
                            details={"reboot_required": True},
                        )
            except Exception as e:
                logger.error("Error updating reboot status: %s", e)

        return {
            "message_type": "child_host_creation_failed",
            "error": error,
            "reboot_required": reboot_required,
        }

    logger.info(
        "Child host created for host %s: name=%s, type=%s, hostname=%s",
        host_id,
        child_name,
        child_type,
        hostname,
    )

    try:
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            logger.warning("Host not found for child host creation: %s", host_id)
            return {
                "message_type": "error",
                "error_type": "host_not_found",
                "message": _("Host not found"),
                "data": {},
            }

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Check if child host already exists
        existing = (
            db.query(HostChild)
            .filter(
                HostChild.parent_host_id == host_id,
                HostChild.child_name == child_name,
                HostChild.child_type == child_type,
            )
            .first()
        )

        if existing:
            # Update existing record
            existing.status = "running"
            existing.hostname = hostname
            existing.default_username = username
            existing.updated_at = now
            existing.installed_at = now
            existing.error_message = None
        else:
            # Create new child host record
            child = HostChild(
                parent_host_id=host_id,
                child_name=child_name,
                child_type=child_type,
                hostname=hostname,
                default_username=username,
                status="running",
                created_at=now,
                updated_at=now,
                installed_at=now,
            )
            db.add(child)

        db.commit()

        AuditService.log(
            db=db,
            action_type=ActionType.AGENT_MESSAGE,
            entity_type=EntityType.HOST,
            entity_id=str(host_id),
            entity_name=host.fqdn,
            description=_("Child host created: %s") % child_name,
            result=Result.SUCCESS,
            details={
                "child_name": child_name,
                "child_type": child_type,
                "hostname": hostname,
            },
        )

        return {
            "message_type": "child_host_created_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "child_name": child_name,
            "status": "created",
        }

    except Exception as e:
        db.rollback()
        logger.error(
            "Error recording child host creation for host %s: %s",
            host_id,
            e,
            exc_info=True,
        )
        return {
            "message_type": "error",
            "error_type": "child_creation_failed",
            "message": _("Failed to record child host creation: %s") % str(e),
            "data": {},
        }
