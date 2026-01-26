"""
Virtualization support handlers for child hosts.

This module handles virtualization-related messages from agents,
including virtualization support checks, WSL enablement, and LXD initialization.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.api.error_constants import ERROR_UNKNOWN, ERROR_WSL_PENDING
from backend.i18n import _
from backend.persistence.models import Host

from .virtualization_helpers import (
    check_success_or_error,
    extract_result_data,
    get_host_id_or_error,
    get_host_or_error,
    handle_simple_init_result,
    log_audit_success,
    make_ack_response,
    make_error_response,
    queue_virtualization_check,
)

logger = logging.getLogger(__name__)


async def handle_virtualization_support_update(  # NOSONAR - async handler
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle virtualization support check result from agent.

    Updates the host record with supported virtualization types.
    """
    host_id, error = get_host_id_or_error(connection)
    if error:
        logger.warning(
            "Virtualization support update received but no host_id on connection"
        )
        return error

    result_data = extract_result_data(message_data)
    success, error_msg = check_success_or_error(message_data, result_data)

    if not success:
        logger.error(
            "Virtualization support check failed for host %s: %s", host_id, error_msg
        )
        return make_error_response("operation_failed", error_msg or ERROR_UNKNOWN())

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
                and host.reboot_required_reason == ERROR_WSL_PENDING()
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
                host.reboot_required_reason = ERROR_WSL_PENDING()

            db.commit()

            log_audit_success(
                db,
                host_id,
                host.fqdn,
                _("Virtualization support updated"),
                {
                    "supported_types": supported_types,
                    "reboot_required": reboot_required,
                },
            )

        return make_ack_response("virtualization_support_ack", {"status": "updated"})

    except Exception as e:
        logger.error(
            "Error updating virtualization support for host %s: %s",
            host_id,
            e,
            exc_info=True,
        )
        return make_error_response("operation_failed", str(e))


async def handle_wsl_enable_result(  # NOSONAR - async handler
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle WSL enable result from agent.

    Updates the host's reboot_required flag if WSL enablement requires a reboot.
    """
    host_id, error = get_host_id_or_error(connection)
    if error:
        logger.warning("WSL enable result received but no host_id on connection")
        return error

    result_data = extract_result_data(message_data)
    success = result_data.get("success", False)
    reboot_required = result_data.get("reboot_required", False)
    error_msg = result_data.get("error")

    if not success:
        logger.error("WSL enable failed for host %s: %s", host_id, error_msg)
        return make_error_response("operation_failed", error_msg or ERROR_UNKNOWN())

    logger.info(
        "WSL enable result for host %s: success=%s, reboot_required=%s",
        host_id,
        success,
        reboot_required,
    )

    try:
        host, error = get_host_or_error(db, host_id, "WSL enable result")
        if error:
            return error

        if reboot_required:
            # Set reboot required with specific reason
            host.reboot_required = True
            host.reboot_required_reason = ERROR_WSL_PENDING()
            db.commit()

            log_audit_success(
                db,
                host_id,
                host.fqdn,
                _("WSL enabled - reboot required"),
                {"reboot_required": True},
            )
        else:
            # WSL enabled without reboot - queue a virtualization check
            queue_virtualization_check(db, host_id)
            db.commit()

            log_audit_success(
                db,
                host_id,
                host.fqdn,
                _("WSL enabled successfully"),
                {"reboot_required": False},
            )

            logger.info(
                "WSL enabled for host %s without reboot, queued virtualization check",
                host_id,
            )

        return make_ack_response("wsl_enable_ack", {"reboot_required": reboot_required})

    except Exception as e:
        logger.error(
            "Error updating WSL enable status for host %s: %s",
            host_id,
            e,
            exc_info=True,
        )
        return make_error_response("operation_failed", str(e))


async def handle_lxd_initialize_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle LXD initialization result from agent."""
    return await handle_simple_init_result(
        db=db,
        connection=connection,
        message_data=message_data,
        hypervisor_name="LXD",
        ack_message_type="lxd_initialize_ack",
        audit_description=_("LXD initialized successfully"),
        extra_result_fields=["user_needs_relogin"],
        extra_ack_fields=["user_needs_relogin"],
    )


async def handle_vmm_initialize_result(  # NOSONAR - async handler
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle VMM/vmd initialization result from agent.

    This handler has special logic for reboot requirements.
    """
    host_id, error = get_host_id_or_error(connection)
    if error:
        logger.warning("VMM initialize result received but no host_id on connection")
        return error

    result_data = extract_result_data(message_data)
    success, error_msg = check_success_or_error(message_data, result_data)

    if not success:
        logger.error("VMM initialization failed for host %s: %s", host_id, error_msg)
        return make_error_response("operation_failed", error_msg or ERROR_UNKNOWN())

    needs_reboot = result_data.get("needs_reboot", False)
    already_enabled = result_data.get("already_enabled", False)
    message = result_data.get("message", "")

    logger.info(
        "VMM initialization result for host %s: success=%s, needs_reboot=%s, "
        "already_enabled=%s",
        host_id,
        success,
        needs_reboot,
        already_enabled,
    )

    try:
        host, error = get_host_or_error(db, host_id, "VMM initialize result")
        if error:
            return error

        if needs_reboot:
            # Set reboot required with specific reason
            host.reboot_required = True
            host.reboot_required_reason = "VMM kernel support requires reboot"
            db.commit()

            log_audit_success(
                db,
                host_id,
                host.fqdn,
                _("VMM initialization requires reboot"),
                {"needs_reboot": True},
            )
        else:
            # VMM initialized - queue a virtualization check
            queue_virtualization_check(db, host_id)
            db.commit()

            log_audit_success(
                db,
                host_id,
                host.fqdn,
                _("VMM/vmd initialized successfully"),
                {"message": message, "already_enabled": already_enabled},
            )

            logger.info(
                "VMM initialized for host %s, queued virtualization check",
                host_id,
            )

        return make_ack_response(
            "vmm_initialize_ack",
            {"needs_reboot": needs_reboot, "already_enabled": already_enabled},
        )

    except Exception as e:
        logger.error(
            "Error updating VMM initialize status for host %s: %s",
            host_id,
            e,
            exc_info=True,
        )
        return make_error_response("operation_failed", str(e))


async def handle_kvm_initialize_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle KVM/libvirt initialization result from agent."""
    return await handle_simple_init_result(
        db=db,
        connection=connection,
        message_data=message_data,
        hypervisor_name="KVM",
        ack_message_type="kvm_initialize_ack",
        audit_description=_("KVM/libvirt initialized successfully"),
        extra_result_fields=["already_installed", "needs_relogin"],
        extra_ack_fields=["needs_relogin", "already_installed"],
    )


async def handle_bhyve_initialize_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle bhyve initialization result from agent."""
    return await handle_simple_init_result(
        db=db,
        connection=connection,
        message_data=message_data,
        hypervisor_name="bhyve",
        ack_message_type="bhyve_initialize_ack",
        audit_description=_("bhyve initialized successfully"),
        extra_result_fields=[
            "already_initialized",
            "vmm_loaded",
            "loader_conf_updated",
        ],
        extra_ack_fields=["already_initialized"],
    )


async def handle_kvm_modules_enable_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle KVM modules enable result from agent."""
    return await handle_simple_init_result(
        db=db,
        connection=connection,
        message_data=message_data,
        hypervisor_name="KVM modules",
        ack_message_type="kvm_modules_enable_ack",
        audit_description=_("KVM kernel modules enabled successfully"),
        extra_result_fields=["module"],
        extra_ack_fields=["module"],
    )


async def handle_kvm_modules_disable_result(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle KVM modules disable result from agent."""
    return await handle_simple_init_result(
        db=db,
        connection=connection,
        message_data=message_data,
        hypervisor_name="KVM modules",
        ack_message_type="kvm_modules_disable_ack",
        audit_description=_("KVM kernel modules disabled successfully"),
        extra_result_fields=[],
        extra_ack_fields=[],
    )
