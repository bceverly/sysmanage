"""
Child host control handlers.

Public handlers dispatch to the Pro+ ``child_host_handlers_engine`` when
loaded, and fall back to the OSS implementations (``_oss_*``) otherwise.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence.models import Host, HostChild
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

logger = logging.getLogger(__name__)


_ENGINE_CODE = "child_host_handlers_engine"
_ENGINE_FALLBACK_MSG = "Engine handler failed; falling back to OSS implementation: %s"


def _engine_handler(name: str):
    """Return the engine's handler with this name, or None if engine not loaded."""
    engine = module_loader.get_module(_ENGINE_CODE)
    if engine is None:
        return None
    return getattr(engine, name, None)


async def handle_child_host_start_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Dispatch to Pro+ engine when loaded; fall back to OSS implementation."""
    engine_fn = _engine_handler("handle_child_host_start_result")
    if engine_fn is not None:
        try:
            return await engine_fn(db, connection, message_data)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(_ENGINE_FALLBACK_MSG, exc)
    return await _handle_child_host_control_result(
        db, connection, message_data, "start", "running"
    )


async def handle_child_host_stop_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Dispatch to Pro+ engine when loaded; fall back to OSS implementation."""
    engine_fn = _engine_handler("handle_child_host_stop_result")
    if engine_fn is not None:
        try:
            return await engine_fn(db, connection, message_data)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(_ENGINE_FALLBACK_MSG, exc)
    return await _handle_child_host_control_result(
        db, connection, message_data, "stop", "stopped"
    )


async def handle_child_host_restart_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Dispatch to Pro+ engine when loaded; fall back to OSS implementation."""
    engine_fn = _engine_handler("handle_child_host_restart_result")
    if engine_fn is not None:
        try:
            return await engine_fn(db, connection, message_data)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(_ENGINE_FALLBACK_MSG, exc)
    return await _handle_child_host_control_result(
        db, connection, message_data, "restart", "running"
    )


async def handle_child_host_delete_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Dispatch to Pro+ engine when loaded; fall back to OSS implementation."""
    engine_fn = _engine_handler("handle_child_host_delete_result")
    if engine_fn is not None:
        try:
            return await engine_fn(db, connection, message_data)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(_ENGINE_FALLBACK_MSG, exc)
    return await _oss_handle_child_host_delete_result(db, connection, message_data)


async def _oss_handle_child_host_delete_result(  # NOSONAR
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

        return {
            "message_type": "error",
            "error_type": "operation_failed",
            "message": error or _("Unknown error"),
            "data": {},
        }

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
            return {
                "message_type": "error",
                "error_type": "host_not_found",
                "message": _("Host not found"),
                "data": {},
            }

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
            else:
                # Final fallback: try matching by child_name
                # This handles cases where hostname was NULL (e.g., bhyve VMs
                # created before metadata storage was implemented)
                # Try child_name as exact FQDN match
                matching_host = (
                    db.query(Host)
                    .filter(func.lower(Host.fqdn) == func.lower(child_name))
                    .first()
                )
                # Try child_name as prefix of Host.fqdn
                if not matching_host:
                    matching_host = (
                        db.query(Host)
                        .filter(
                            func.lower(Host.fqdn).like(func.lower(child_name + ".%"))
                        )
                        .first()
                    )
                if matching_host:
                    deleted_host_info = {
                        "id": str(matching_host.id),
                        "fqdn": matching_host.fqdn,
                    }
                    logger.info(
                        "Deleting host record matched by child_name for %s: host_id=%s, fqdn=%s",
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
        return {
            "message_type": "error",
            "error_type": "operation_failed",
            "message": str(e),
            "data": {},
        }


async def _handle_child_host_control_result(  # NOSONAR
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
        return {
            "message_type": "error",
            "error_type": "operation_failed",
            "message": error or _("Unknown error"),
            "data": {},
        }

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
            return {
                "message_type": "error",
                "error_type": "host_not_found",
                "message": _("Host not found"),
                "data": {},
            }

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

            # Check reboot orchestration progress (Pro+ safe reboot)
            try:
                from backend.licensing.module_loader import module_loader

                if module_loader.get_module("container_engine") is not None:
                    from backend.services.reboot_orchestration_service import (
                        check_restart_progress,
                        check_shutdown_progress,
                    )

                    if action == "stop":
                        check_shutdown_progress(db, host_id)
                    elif action == "start":
                        check_restart_progress(db, host_id)
            except Exception as orch_err:
                logger.warning(
                    "Error checking reboot orchestration for host %s: %s",
                    host_id,
                    orch_err,
                )

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
        return {
            "message_type": "error",
            "error_type": "operation_failed",
            "message": str(e),
            "data": {},
        }
