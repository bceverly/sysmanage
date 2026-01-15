"""
Package data handlers for SysManage agent communication.
Handles available packages messages from agents.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import AvailablePackage, Host

# Logger for debugging - use existing root logger configuration
debug_logger = logging.getLogger("debug_logger")


# OLD NON-PAGINATED HANDLER REMOVED - USE PAGINATED HANDLERS ONLY


# Global storage for batched package data (in-memory for now)
_batch_sessions = {}


async def handle_packages_batch_start(db: Session, connection, message_data: dict):
    """Handle the start of a paginated available packages batch."""
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

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": _("Host not registered"),
            "data": {},
        }

    try:
        # Get host information for OS details
        host = db.query(Host).filter(Host.id == connection.host_id).first()
        if not host:
            return {
                "message_type": "error",
                "error_type": "host_not_found",
                "message": _("Host not found"),
                "data": {},
            }

        # Get batch information
        batch_id = message_data.get("batch_id")
        if not batch_id:
            return {
                "message_type": "error",
                "error_type": "missing_batch_id",
                "message": _("Missing batch_id"),
                "data": {},
            }

        os_name = message_data.get("os_name") or host.platform or "Unknown"
        os_version = (
            message_data.get("os_version") or host.platform_release or "Unknown"
        )
        package_managers = message_data.get("package_managers", [])

        # Validate that the host is reporting packages for its own OS
        if host.platform and host.platform_release:
            if os_name != host.platform or os_version != host.platform_release:
                error_msg = _(
                    "Host %s (%s %s) attempted to report packages for %s %s"
                ) % (
                    host.fqdn,
                    host.platform,
                    host.platform_release,
                    os_name,
                    os_version,
                )
                debug_logger.error(error_msg)
                return {
                    "message_type": "error",
                    "error_type": "os_mismatch",
                    "message": error_msg,
                    "data": {},
                }

        debug_logger.info(
            "Starting available packages batch %s for host %s (%s %s) with managers: %s",
            batch_id,
            connection.host_id,
            os_name,
            os_version,
            package_managers,
        )

        # Clear existing packages for this OS/manager combination
        for manager_name in package_managers:
            db.execute(
                delete(AvailablePackage).where(
                    AvailablePackage.os_name == os_name,
                    AvailablePackage.os_version == os_version,
                    AvailablePackage.package_manager == manager_name,
                )
            )
        db.commit()

        # Initialize batch session
        _batch_sessions[batch_id] = {
            "host_id": connection.host_id,
            "os_name": os_name,
            "os_version": os_version,
            "package_managers": package_managers,
            "total_packages": 0,
            "started_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }

        return {
            "message_type": "acknowledgment",
            "status": "batch_started",
            "batch_id": batch_id,
        }

    except Exception as e:
        db.rollback()
        debug_logger.error(
            "Error starting available packages batch for host %s: %s",
            connection.host_id,
            e,
        )
        return {
            "message_type": "error",
            "error_type": "batch_start_failed",
            "message": _("Failed to start packages batch: %s") % str(e),
            "data": {},
        }


async def handle_packages_batch(db: Session, connection, message_data: dict):
    """Handle a batch of available packages data."""
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

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": _("Host not registered"),
            "data": {},
        }

    try:
        batch_id = message_data.get("batch_id")
        if not batch_id or batch_id not in _batch_sessions:
            return {
                "message_type": "error",
                "error_type": "invalid_batch_id",
                "message": _("Invalid or expired batch_id"),
                "data": {},
            }

        batch_session = _batch_sessions[batch_id]

        # Verify this is the same host
        if batch_session["host_id"] != connection.host_id:
            return {
                "message_type": "error",
                "error_type": "batch_host_mismatch",
                "message": _("Batch belongs to different host"),
                "data": {},
            }

        # Process packages from this batch
        package_managers = message_data.get("package_managers", {})
        batch_packages = 0

        for manager_name, packages in package_managers.items():
            if not packages:
                continue

            debug_logger.info(
                "Processing batch with %d packages from %s for host %s (batch %s)",
                len(packages),
                manager_name,
                connection.host_id,
                batch_id,
            )

            # Insert packages from this batch
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for package in packages:
                package_name = package.get("name", "").strip()
                package_version = package.get("version", "").strip()
                package_description = package.get("description", "").strip()

                if not package_name or not package_version:
                    debug_logger.warning(
                        "Skipping invalid package: name='%s', version='%s'",
                        package_name,
                        package_version,
                    )
                    continue

                # Truncate description if too long for database
                if len(package_description) > 1000:
                    package_description = package_description[:997] + "..."

                available_package = AvailablePackage(
                    package_name=package_name,
                    package_version=package_version,
                    package_description=package_description,
                    package_manager=manager_name,
                    os_name=batch_session["os_name"],
                    os_version=batch_session["os_version"],
                    created_at=now,
                    last_updated=now,
                )
                db.add(available_package)
                batch_packages += 1

        # Commit this batch
        db.commit()
        batch_session["total_packages"] += batch_packages

        debug_logger.info(
            "Processed batch %s: %d packages (total so far: %d)",
            batch_id,
            batch_packages,
            batch_session["total_packages"],
        )

        return {
            "message_type": "acknowledgment",
            "status": "batch_processed",
            "batch_id": batch_id,
            "packages_in_batch": batch_packages,
        }

    except Exception as e:
        db.rollback()
        debug_logger.error(
            "Error processing available packages batch for host %s: %s",
            connection.host_id,
            e,
        )
        return {
            "message_type": "error",
            "error_type": "batch_process_failed",
            "message": _("Failed to process packages batch: %s") % str(e),
            "data": {},
        }


async def handle_packages_batch_end(db: Session, connection, message_data: dict):
    """Handle the end of a paginated available packages batch."""
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

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": _("Host not registered"),
            "data": {},
        }

    try:
        batch_id = message_data.get("batch_id")
        if not batch_id or batch_id not in _batch_sessions:
            return {
                "message_type": "error",
                "error_type": "invalid_batch_id",
                "message": _("Invalid or expired batch_id"),
                "data": {},
            }

        batch_session = _batch_sessions[batch_id]

        # Verify this is the same host
        if batch_session["host_id"] != connection.host_id:
            return {
                "message_type": "error",
                "error_type": "batch_host_mismatch",
                "message": _("Batch belongs to different host"),
                "data": {},
            }

        total_packages = batch_session["total_packages"]

        debug_logger.info(
            "Completed available packages batch %s for host %s (%s %s): %d total packages",
            batch_id,
            connection.host_id,
            batch_session["os_name"],
            batch_session["os_version"],
            total_packages,
        )

        # Clean up batch session
        del _batch_sessions[batch_id]

        return {
            "message_type": "acknowledgment",
            "status": "batch_completed",
            "batch_id": batch_id,
            "total_packages_processed": total_packages,
        }

    except Exception as e:
        debug_logger.error(
            "Error ending available packages batch for host %s: %s",
            connection.host_id,
            e,
        )
        return {
            "message_type": "error",
            "error_type": "batch_end_failed",
            "message": _("Failed to end packages batch: %s") % str(e),
            "data": {},
        }
