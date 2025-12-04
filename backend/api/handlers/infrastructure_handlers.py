"""
Infrastructure data handlers for SysManage agent communication.
Handles script execution results, reboot status, certificates, and host role data.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host, HostCertificate, HostRole
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

# Logger for debugging - use existing root logger configuration
debug_logger = logging.getLogger("debug_logger")


async def handle_script_execution_result(db: Session, connection, message_data: dict):
    """Handle script execution result from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    debug_logger.info(
        "Processing script execution result from %s", message_data.get("hostname")
    )

    try:
        execution_id = message_data.get("execution_id")
        execution_uuid = message_data.get("execution_uuid")

        if not execution_id:
            debug_logger.error("No execution_id provided in script execution result")
            return {"message_type": "error", "error": _("Execution ID is required")}

        # Check for duplicate execution UUID to prevent duplicate processing
        if execution_uuid:
            from backend.persistence.models import ScriptExecutionLog

            # Check if we've already processed this execution UUID
            existing_execution = (
                db.query(ScriptExecutionLog)
                .filter(ScriptExecutionLog.execution_uuid == execution_uuid)
                .filter(ScriptExecutionLog.status.in_(["completed", "failed"]))
                .first()
            )

            if existing_execution:
                debug_logger.error(
                    "Duplicate script execution result received for UUID %s, ignoring",
                    execution_uuid,
                )
                return {
                    "message_type": "error",
                    "error": _("Script execution result with UUID %s already processed")
                    % execution_uuid,
                }

        # Use connection object's host_id if available (from message processor)
        # Otherwise fall back to hostname lookup for direct WebSocket calls
        host = None
        if hasattr(connection, "host_id") and connection.host_id:
            host = db.query(Host).filter(Host.id == connection.host_id).first()

        # Fallback to hostname lookup if no host_id or host not found
        if not host:
            hostname = message_data.get("hostname")
            if not hostname:
                debug_logger.error("No hostname provided and no host_id in connection")
                return {"message_type": "error", "error": _("Hostname is required")}

            # Find the host (case-insensitive)
            host = db.query(Host).filter(Host.fqdn.ilike(hostname)).first()
            if not host:
                debug_logger.error("Host not found: %s", hostname)
                return {
                    "message_type": "error",
                    "error": _("Host not found: %s") % hostname,
                }

        # Find existing script execution log entry by execution_id
        from backend.persistence.models import ScriptExecutionLog

        execution_log = (
            db.query(ScriptExecutionLog)
            .filter(ScriptExecutionLog.execution_id == execution_id)
            .first()
        )

        if execution_log:
            # Update existing entry
            debug_logger.info(
                "Updating existing script execution log for execution_id: %s",
                execution_id,
            )
            execution_log.status = (
                "completed" if message_data.get("success", False) else "failed"
            )
            execution_log.exit_code = message_data.get("exit_code")
            execution_log.stdout_output = message_data.get("stdout", "")
            execution_log.stderr_output = message_data.get("stderr", "")
            execution_log.execution_time = message_data.get("execution_time")
            execution_log.shell_used = message_data.get("shell_used")
            execution_log.error_message = message_data.get("error")
            execution_log.timed_out = message_data.get("timeout", False)
            execution_log.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            execution_log.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

            # Set started_at if not already set
            if not execution_log.started_at:
                execution_log.started_at = execution_log.completed_at

        else:
            # Create new entry (fallback for cases where execution wasn't properly logged)
            debug_logger.warning(
                "No existing execution log found for execution_id: %s, creating new entry",
                execution_id,
            )
            execution_log = ScriptExecutionLog(
                host_id=host.id,
                saved_script_id=message_data.get(
                    "script_id"
                ),  # May be None for ad-hoc scripts
                script_name=message_data.get("script_name", "Unknown"),
                script_content="",  # Not available in result message
                shell_type=message_data.get("shell_used", "bash"),
                run_as_user=None,  # Not available in result message
                requested_by="system",  # Fallback value
                execution_id=execution_id,
                status="completed" if message_data.get("success", False) else "failed",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                exit_code=message_data.get("exit_code"),
                stdout_output=message_data.get("stdout", ""),
                stderr_output=message_data.get("stderr", ""),
                error_message=message_data.get("error"),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(execution_log)

        db.commit()

        debug_logger.info(
            "Successfully stored script execution result for host %s (execution_id: %s)",
            host.fqdn,
            execution_id,
        )

        # Log script execution result
        script_status = "completed" if message_data.get("success", False) else "failed"
        AuditService.log(
            db=db,
            action_type=ActionType.AGENT_MESSAGE,
            entity_type=EntityType.SCRIPT,
            entity_id=str(execution_log.id),
            entity_name=message_data.get("script_name", "Unknown"),
            description=_("Script execution {status} on agent {hostname}").format(
                status=script_status, hostname=host.fqdn
            ),
            result=(
                Result.SUCCESS if message_data.get("success", False) else Result.FAILURE
            ),
            details={
                "execution_id": execution_id,
                "script_name": message_data.get("script_name"),
                "exit_code": message_data.get("exit_code"),
                "execution_time": message_data.get("execution_time"),
                "shell_used": message_data.get("shell_used"),
                "host_id": str(host.id),
                "hostname": host.fqdn,
                "timed_out": message_data.get("timeout", False),
            },
            error_message=message_data.get("error"),
        )

        return {
            "message_type": "script_execution_result_stored",
            "execution_log_id": execution_log.id,
            "host_id": host.id,
        }

    except Exception as e:
        debug_logger.error("Error storing script execution result: %s", e)
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to store script execution result: %s") % str(e),
        }


async def handle_reboot_status_update(db: Session, connection, message_data: dict):
    """Handle reboot status update from an agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    try:
        hostname = message_data.get("hostname")
        reboot_required = message_data.get("reboot_required", False)
        reboot_reason = message_data.get("reboot_required_reason")

        # Try to find the host by hostname or by host_id from connection info
        host = None
        if hostname:
            host = db.query(Host).filter(Host.fqdn == hostname).first()

        # If no hostname provided or host not found, try connection info
        if not host:
            conn_info = message_data.get("_connection_info", {})
            conn_hostname = conn_info.get("hostname")
            if conn_hostname:
                host = db.query(Host).filter(Host.fqdn == conn_hostname).first()
                if host:
                    hostname = conn_hostname

        if not host:
            debug_logger.error(
                "Host not found for reboot status update: hostname=%s", hostname
            )
            return {
                "message_type": "error",
                "error": _("Host not found for reboot status update"),
            }

        debug_logger.info("Processing reboot status update from %s", hostname)

        # Protect WSL enablement pending reboot flag from being overwritten
        # If the host has reboot_required=True with reason "WSL feature enablement pending",
        # don't allow the agent to clear it until the reboot actually happens
        # (which will be detected by the agent after reboot)
        protected_reasons = ["WSL feature enablement pending"]
        current_reason = host.reboot_required_reason or ""

        if (
            host.reboot_required
            and current_reason in protected_reasons
            and not reboot_required
        ):
            debug_logger.info(
                "Preserving protected reboot_required flag for host %s (reason: %s)",
                hostname,
                current_reason,
            )
            # Don't update - preserve the protected state
            return {
                "message_type": "reboot_status_preserved",
                "host_id": host.id,
                "reboot_required": host.reboot_required,
                "reason": current_reason,
            }

        # Update the reboot status
        host.reboot_required = reboot_required
        host.reboot_required_updated_at = datetime.now(timezone.utc).replace(
            tzinfo=None
        )

        # Set or clear the reason based on reboot_required status
        if reboot_required and reboot_reason:
            host.reboot_required_reason = reboot_reason
        elif not reboot_required:
            host.reboot_required_reason = None

        db.commit()

        debug_logger.info(
            "Successfully updated reboot status for host %s: "
            "reboot_required=%s, reason=%s",
            hostname,
            reboot_required,
            reboot_reason,
        )

        return {
            "message_type": "reboot_status_updated",
            "host_id": host.id,
            "reboot_required": reboot_required,
            "reason": reboot_reason,
        }

    except Exception as e:
        debug_logger.error("Error updating reboot status: %s", e)
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to update reboot status: %s") % str(e),
        }


async def handle_host_certificates_update(db: Session, connection, message_data: dict):
    """Handle host certificates update message from agent."""
    from backend.utils.host_validation import validate_host_id

    try:
        # Check for host_id in message data (agent-provided)
        agent_host_id = message_data.get("host_id")
        if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
            return {"message_type": "error", "error": "host_not_registered"}

        # Find the host by hostname or other connection attributes
        host = None
        if hasattr(connection, "hostname") and connection.hostname:
            host = db.query(Host).filter(Host.fqdn == connection.hostname).first()

        if not host and agent_host_id:
            host = db.query(Host).filter(Host.id == agent_host_id).first()

        if not host:
            debug_logger.warning(
                "Could not identify host for certificates update from connection %s",
                getattr(connection, "hostname", "unknown"),
            )
            return {"message_type": "error", "error": "host_identification_failed"}

        # Get certificates data from message
        certificates_data = message_data.get("certificates", [])
        collected_at = message_data.get("collected_at")

        debug_logger.info(
            "Processing %d certificates for host %s (%s)",
            len(certificates_data),
            host.fqdn,
            host.id,
        )

        # Clear existing certificates for this host
        db.query(HostCertificate).filter(HostCertificate.host_id == host.id).delete()

        # Process and store new certificates
        certificates_processed = 0
        for cert_data in certificates_data:
            try:
                # Parse dates
                not_before = None
                not_after = None

                if cert_data.get("not_before"):
                    not_before = datetime.fromisoformat(
                        cert_data["not_before"].replace("Z", "+00:00")
                    )
                if cert_data.get("not_after"):
                    not_after = datetime.fromisoformat(
                        cert_data["not_after"].replace("Z", "+00:00")
                    )

                collected_at_dt = None
                if collected_at:
                    collected_at_dt = datetime.fromisoformat(
                        collected_at.replace("Z", "+00:00")
                    )

                # Create certificate record
                certificate = HostCertificate(
                    host_id=host.id,
                    file_path=cert_data.get("file_path", ""),
                    certificate_name=cert_data.get("certificate_name"),
                    subject=cert_data.get("subject"),
                    issuer=cert_data.get("issuer"),
                    not_before=not_before,
                    not_after=not_after,
                    serial_number=cert_data.get("serial_number"),
                    fingerprint_sha256=cert_data.get("fingerprint_sha256"),
                    is_ca=cert_data.get("is_ca", False),
                    key_usage=cert_data.get("key_usage"),
                    collected_at=collected_at_dt or datetime.now(timezone.utc),
                )

                db.add(certificate)
                certificates_processed += 1

            except Exception as e:
                debug_logger.warning(
                    "Failed to process certificate %s for host %s: %s",
                    cert_data.get("file_path", "unknown"),
                    host.fqdn,
                    e,
                )
                continue

        # Commit all changes
        db.commit()

        debug_logger.info(
            "Successfully stored %d certificates for host %s",
            certificates_processed,
            host.fqdn,
        )

        return {
            "message_type": "certificates_update_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
            "certificates_stored": certificates_processed,
        }

    except Exception as e:
        debug_logger.error(
            "Error processing certificates update from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()

        return {
            "message_type": "error",
            "error": f"Failed to process certificates update: {str(e)}",
        }


async def handle_host_role_data_update(db: Session, connection, message_data: dict):
    """Handle host role data update message from agent."""
    from backend.utils.host_validation import validate_host_id

    try:
        # Check for host_id in message data (agent-provided)
        agent_host_id = message_data.get("host_id")
        if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
            return {"message_type": "error", "error": "host_not_registered"}

        # Find the host by hostname or other connection attributes
        host = None
        if hasattr(connection, "hostname") and connection.hostname:
            host = db.query(Host).filter(Host.fqdn == connection.hostname).first()
        if not host and agent_host_id:
            host = db.query(Host).filter(Host.id == agent_host_id).first()

        if not host:
            debug_logger.warning(
                "Could not identify host for role data update from connection %s",
                getattr(connection, "hostname", "unknown"),
            )
            return {"message_type": "error", "error": "host_identification_failed"}

        # Get role data from message
        roles_data = message_data.get("roles", [])
        collection_timestamp = message_data.get("collection_timestamp")

        debug_logger.info(
            "Processing %d server roles for host %s (%s)",
            len(roles_data),
            host.fqdn,
            host.id,
        )

        # Clear existing roles for this host
        db.query(HostRole).filter(HostRole.host_id == host.id).delete()

        # Process and store new roles
        roles_processed = 0
        for role_data in roles_data:
            try:
                # Parse collection timestamp
                detected_at = None
                if collection_timestamp:
                    detected_at = datetime.fromisoformat(
                        collection_timestamp.replace("Z", "+00:00")
                    )

                # Create role record
                role = HostRole(
                    host_id=host.id,
                    role=role_data.get("role", ""),
                    package_name=role_data.get("package_name", ""),
                    package_version=role_data.get("package_version"),
                    service_name=role_data.get("service_name"),
                    service_status=role_data.get("service_status"),
                    is_active=role_data.get("is_active", False),
                    detected_at=detected_at or datetime.now(timezone.utc),
                )

                db.add(role)
                roles_processed += 1

            except Exception as e:
                debug_logger.warning(
                    "Failed to process role %s for host %s: %s",
                    role_data.get("role", "unknown"),
                    host.fqdn,
                    e,
                )
                continue

        # Commit all changes
        db.commit()

        debug_logger.info(
            "Successfully stored %d server roles for host %s",
            roles_processed,
            host.fqdn,
        )

        return {
            "message_type": "role_data_update_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
            "roles_stored": roles_processed,
        }

    except Exception as e:
        debug_logger.error(
            "Error processing role data update from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()
        return {
            "message_type": "error",
            "error": f"Failed to process role data update: {str(e)}",
        }
