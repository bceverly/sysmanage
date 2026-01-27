"""
Update result handlers for SysManage agent communication.
Handles update application results and status tracking.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, text, update
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host, PackageUpdate, UpdateExecutionLog

# Use standard logger that respects /etc/sysmanage.yaml configuration
logger = logging.getLogger(__name__)

# Cache for storing update results
update_results_cache = {}


async def handle_update_apply_result(  # NOSONAR
    db: Session, connection, message_data: dict
):
    """Handle update application result message from agent."""
    # Import validation helper
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
        hostname = message_data.get("hostname", "unknown")
        updated_packages = message_data.get("updated_packages", [])
        failed_packages = message_data.get("failed_packages", [])
        requires_reboot = message_data.get("requires_reboot", False)

        logger.info(
            "Update application result from %s: %d succeeded, %d failed",
            hostname,
            len(updated_packages),
            len(failed_packages),
        )

        # Cache the results for the frontend to access
        update_results_cache[str(connection.host_id)] = {
            "updated_packages": updated_packages,
            "failed_packages": failed_packages,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Update package statuses in database
        for package in updated_packages:
            package_name = package.get("package_name")
            package_manager = package.get("package_manager")

            if package_name and package_manager:
                # Delete the package_update entry since it was successfully applied
                result = (
                    db.query(PackageUpdate)
                    .filter(
                        and_(
                            PackageUpdate.host_id == connection.host_id,
                            PackageUpdate.package_name == package_name,
                            PackageUpdate.package_manager == package_manager,
                        )
                    )
                    .delete()
                )

                logger.info(
                    "Removed successfully updated package %s from pending updates (rows affected: %d)",
                    package_name,
                    result,
                )

                # Update execution log to success
                exec_result = (
                    db.query(UpdateExecutionLog)
                    .filter(
                        and_(
                            UpdateExecutionLog.host_id == connection.host_id,
                            UpdateExecutionLog.package_name == package_name,
                            UpdateExecutionLog.package_manager == package_manager,
                            UpdateExecutionLog.execution_status == "pending",
                        )
                    )
                    .order_by(UpdateExecutionLog.created_at.desc())
                    .first()
                )

                if exec_result:
                    exec_result.execution_status = "success"
                    exec_result.completed_at = datetime.now(timezone.utc)
                    exec_result.updated_at = datetime.now(timezone.utc)
                    logger.info("Updated execution log for %s to success", package_name)

        for package in failed_packages:
            package_name = package.get("package_name")
            package_manager = package.get("package_manager")
            error = package.get("error", "Unknown error")

            if package_name and package_manager:
                # Update the package status to failed
                stmt = (
                    update(PackageUpdate)
                    .where(
                        and_(
                            PackageUpdate.host_id == connection.host_id,
                            PackageUpdate.package_name == package_name,
                            PackageUpdate.package_manager == package_manager,
                        )
                    )
                    .values(
                        status="failed",
                        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    )
                )
                result = db.execute(stmt)
                logger.info(
                    "Updated package %s status to failed (rows affected: %d)",
                    package_name,
                    result.rowcount,
                )

                # Update execution log to failed
                exec_result = (
                    db.query(UpdateExecutionLog)
                    .filter(
                        and_(
                            UpdateExecutionLog.host_id == connection.host_id,
                            UpdateExecutionLog.package_name == package_name,
                            UpdateExecutionLog.package_manager == package_manager,
                            UpdateExecutionLog.execution_status == "pending",
                        )
                    )
                    .order_by(UpdateExecutionLog.created_at.desc())
                    .first()
                )

                if exec_result:
                    exec_result.execution_status = "failed"
                    exec_result.completed_at = datetime.now(timezone.utc)
                    exec_result.updated_at = datetime.now(timezone.utc)
                    exec_result.error_log = error
                    logger.info("Updated execution log for %s to failed", package_name)

        # Update host reboot requirement
        if requires_reboot:
            stmt = (
                update(Host)
                .where(Host.id == connection.host_id)
                .values(requires_reboot=True)
            )
            db.execute(stmt)

        db.commit()

        logger.info(
            "Update results processed successfully for host %s", connection.host_id
        )

        return {
            "message_type": "success",
            "updated_count": len(updated_packages),
            "failed_count": len(failed_packages),
            "requires_reboot": requires_reboot,
        }

    except Exception as e:
        logger.error("Error processing update results: %s", e)
        db.rollback()
        return {
            "message_type": "error",
            "error_type": "update_result_failed",
            "message": _("Failed to process update results"),
            "data": {},
        }


# Make the cache available to other modules
handle_update_apply_result.update_results_cache = update_results_cache
