"""
Virtualization support handlers for child hosts.

This module handles virtualization-related messages from agents,
including virtualization support checks, WSL enablement, and LXD initialization.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

logger = logging.getLogger(__name__)


async def handle_virtualization_support_update(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle virtualization support check result from agent.

    Updates the host record with supported virtualization types.

    Args:
        db: Database session
        connection: WebSocket connection object
        message_data: Message data containing virtualization support info

    Returns:
        Acknowledgment message
    """
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning(
            "Virtualization support update received but no host_id on connection"
        )
        return {"message_type": "error", "error": "No host_id on connection"}

    result_data = message_data.get("result", {})
    if not result_data:
        result_data = message_data

    # Check success at both levels - command_result has success at top level,
    # but result_data may also have it for direct updates
    success = message_data.get("success", result_data.get("success", False))
    if not success:
        error = message_data.get("error") or result_data.get("error", "Unknown error")
        logger.error(
            "Virtualization support check failed for host %s: %s", host_id, error
        )
        return {"message_type": "error", "error": error}

    supported_types = result_data.get("supported_types", [])
    capabilities = result_data.get("capabilities", {})
    reboot_required = result_data.get("reboot_required", False)

    logger.info(
        "Virtualization support for host %s: types=%s, reboot_required=%s",
        host_id,
        supported_types,
        reboot_required,
    )

    try:
        host = db.query(Host).filter(Host.id == host_id).first()
        if host:
            import json

            # Store virtualization info in host record
            host.virtualization_types = json.dumps(supported_types)
            host.virtualization_capabilities = json.dumps(capabilities)
            host.virtualization_updated_at = datetime.now(timezone.utc).replace(
                tzinfo=None
            )

            # Check WSL status from capabilities
            wsl_caps = capabilities.get("wsl", {})
            wsl_enabled = wsl_caps.get("enabled", False)
            wsl_needs_enable = wsl_caps.get("needs_enable", False)

            # If WSL is now enabled and we had a pending "WSL feature enablement" reboot,
            # clear the reboot flag - the reboot completed successfully
            if (
                wsl_enabled
                and host.reboot_required
                and host.reboot_required_reason == "WSL feature enablement pending"
            ):
                host.reboot_required = False
                host.reboot_required_reason = None
                logger.info(
                    "Clearing WSL reboot flag for host %s - WSL is now enabled",
                    host_id,
                )

            # If WSL needs enablement and reboot is required, set reboot flag
            elif reboot_required and "wsl" in supported_types and wsl_needs_enable:
                host.reboot_required = True
                host.reboot_required_reason = "WSL feature enablement pending"

            db.commit()

            AuditService.log(
                db=db,
                action_type=ActionType.AGENT_MESSAGE,
                entity_type=EntityType.HOST,
                entity_id=str(host_id),
                entity_name=host.fqdn,
                description=_("Virtualization support updated"),
                result=Result.SUCCESS,
                details={
                    "supported_types": supported_types,
                    "reboot_required": reboot_required,
                },
            )

        return {
            "message_type": "virtualization_support_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "updated",
        }

    except Exception as e:
        logger.error(
            "Error updating virtualization support for host %s: %s",
            host_id,
            e,
            exc_info=True,
        )
        return {"message_type": "error", "error": str(e)}


async def handle_wsl_enable_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle WSL enable result from agent.

    Updates the host's reboot_required flag if WSL enablement requires a reboot.

    Args:
        db: Database session
        connection: WebSocket connection object
        message_data: Message data containing WSL enable result

    Returns:
        Acknowledgment message
    """
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning("WSL enable result received but no host_id on connection")
        return {"message_type": "error", "error": "No host_id on connection"}

    result_data = message_data.get("result", {})
    if not result_data:
        result_data = message_data

    success = result_data.get("success", False)
    reboot_required = result_data.get("reboot_required", False)
    error = result_data.get("error")

    if not success:
        logger.error("WSL enable failed for host %s: %s", host_id, error)
        return {"message_type": "error", "error": error}

    logger.info(
        "WSL enable result for host %s: success=%s, reboot_required=%s",
        host_id,
        success,
        reboot_required,
    )

    try:
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            logger.warning("Host not found for WSL enable result: %s", host_id)
            return {"message_type": "error", "error": "Host not found"}

        if reboot_required:
            # Set reboot required with specific reason
            # This reason is protected from being overwritten by other updates
            host.reboot_required = True
            host.reboot_required_reason = "WSL feature enablement pending"
            db.commit()

            AuditService.log(
                db=db,
                action_type=ActionType.AGENT_MESSAGE,
                entity_type=EntityType.HOST,
                entity_id=str(host_id),
                entity_name=host.fqdn,
                description=_("WSL enabled - reboot required"),
                result=Result.SUCCESS,
                details={"reboot_required": True},
            )
        else:
            # WSL enabled without reboot - queue a virtualization check
            # to refresh the host's virtualization state in the UI
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
            db.commit()

            AuditService.log(
                db=db,
                action_type=ActionType.AGENT_MESSAGE,
                entity_type=EntityType.HOST,
                entity_id=str(host_id),
                entity_name=host.fqdn,
                description=_("WSL enabled successfully"),
                result=Result.SUCCESS,
                details={"reboot_required": False},
            )

            logger.info(
                "WSL enabled for host %s without reboot, queued virtualization check",
                host_id,
            )

        return {
            "message_type": "wsl_enable_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reboot_required": reboot_required,
        }

    except Exception as e:
        logger.error(
            "Error updating WSL enable status for host %s: %s",
            host_id,
            e,
            exc_info=True,
        )
        return {"message_type": "error", "error": str(e)}


async def handle_lxd_initialize_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle LXD initialization result from agent.

    After LXD is initialized, queues a virtualization check to refresh
    the host's virtualization capabilities.

    Args:
        db: Database session
        connection: WebSocket connection object
        message_data: Message data containing LXD init result

    Returns:
        Acknowledgment message
    """
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning("LXD initialize result received but no host_id on connection")
        return {"message_type": "error", "error": "No host_id on connection"}

    result_data = message_data.get("result", {})
    if not result_data:
        result_data = message_data

    success = result_data.get("success", False)
    user_needs_relogin = result_data.get("user_needs_relogin", False)
    error = result_data.get("error")
    message = result_data.get("message", "")

    if not success:
        logger.error("LXD initialization failed for host %s: %s", host_id, error)
        return {"message_type": "error", "error": error}

    logger.info(
        "LXD initialization result for host %s: success=%s, user_needs_relogin=%s",
        host_id,
        success,
        user_needs_relogin,
    )

    try:
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            logger.warning("Host not found for LXD initialize result: %s", host_id)
            return {"message_type": "error", "error": "Host not found"}

        # LXD initialized - queue a virtualization check to refresh
        # the host's virtualization state in the UI
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
        db.commit()

        AuditService.log(
            db=db,
            action_type=ActionType.AGENT_MESSAGE,
            entity_type=EntityType.HOST,
            entity_id=str(host_id),
            entity_name=host.fqdn,
            description=_("LXD initialized successfully"),
            result=Result.SUCCESS,
            details={
                "message": message,
                "user_needs_relogin": user_needs_relogin,
            },
        )

        logger.info(
            "LXD initialized for host %s, queued virtualization check",
            host_id,
        )

        return {
            "message_type": "lxd_initialize_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_needs_relogin": user_needs_relogin,
        }

    except Exception as e:
        logger.error(
            "Error updating LXD initialize status for host %s: %s",
            host_id,
            e,
            exc_info=True,
        )
        return {"message_type": "error", "error": str(e)}


async def handle_vmm_initialize_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle VMM/vmd initialization result from agent.

    After vmd is started, queues a virtualization check to refresh
    the host's virtualization capabilities.

    Args:
        db: Database session
        connection: WebSocket connection object
        message_data: Message data containing VMM init result

    Returns:
        Acknowledgment message
    """
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning("VMM initialize result received but no host_id on connection")
        return {"message_type": "error", "error": "No host_id on connection"}

    result_data = message_data.get("result", {})
    if not result_data:
        result_data = message_data

    success = result_data.get("success", False)
    needs_reboot = result_data.get("needs_reboot", False)
    already_enabled = result_data.get("already_enabled", False)
    error = result_data.get("error")
    message = result_data.get("message", "")

    if not success:
        logger.error("VMM initialization failed for host %s: %s", host_id, error)
        return {"message_type": "error", "error": error}

    logger.info(
        "VMM initialization result for host %s: success=%s, needs_reboot=%s, "
        "already_enabled=%s",
        host_id,
        success,
        needs_reboot,
        already_enabled,
    )

    try:
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            logger.warning("Host not found for VMM initialize result: %s", host_id)
            return {"message_type": "error", "error": "Host not found"}

        if needs_reboot:
            # Set reboot required with specific reason
            host.reboot_required = True
            host.reboot_required_reason = "VMM kernel support requires reboot"
            db.commit()

            AuditService.log(
                db=db,
                action_type=ActionType.AGENT_MESSAGE,
                entity_type=EntityType.HOST,
                entity_id=str(host_id),
                entity_name=host.fqdn,
                description=_("VMM initialization requires reboot"),
                result=Result.SUCCESS,
                details={"needs_reboot": True},
            )
        else:
            # VMM initialized - queue a virtualization check to refresh
            # the host's virtualization state in the UI
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
            db.commit()

            AuditService.log(
                db=db,
                action_type=ActionType.AGENT_MESSAGE,
                entity_type=EntityType.HOST,
                entity_id=str(host_id),
                entity_name=host.fqdn,
                description=_("VMM/vmd initialized successfully"),
                result=Result.SUCCESS,
                details={
                    "message": message,
                    "already_enabled": already_enabled,
                },
            )

            logger.info(
                "VMM initialized for host %s, queued virtualization check",
                host_id,
            )

        return {
            "message_type": "vmm_initialize_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "needs_reboot": needs_reboot,
            "already_enabled": already_enabled,
        }

    except Exception as e:
        logger.error(
            "Error updating VMM initialize status for host %s: %s",
            host_id,
            e,
            exc_info=True,
        )
        return {"message_type": "error", "error": str(e)}
