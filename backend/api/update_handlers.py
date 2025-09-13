"""
Update result handlers for SysManage agent communication.
Handles update application results and status tracking.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, text, update
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host, PackageUpdate

# Logger for debugging
debug_logger = logging.getLogger("debug_logger")
debug_logger.setLevel(logging.DEBUG)
try:
    import os

    os.makedirs("logs", exist_ok=True)
    file_handler = logging.FileHandler("logs/backend.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    from backend.utils.logging_formatter import UTCTimestampFormatter

    formatter = UTCTimestampFormatter("%(levelname)s: %(name)s: %(message)s")
    file_handler.setFormatter(formatter)
    debug_logger.addHandler(file_handler)
except (PermissionError, OSError) as e:
    # Fall back to console logging if file logging fails
    from backend.utils.logging_formatter import UTCTimestampFormatter

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = UTCTimestampFormatter("%(levelname)s: %(name)s: %(message)s")
    console_handler.setFormatter(formatter)
    debug_logger.addHandler(console_handler)

# Cache for storing update results
update_results_cache = {}


async def handle_update_apply_result(db: Session, connection, message_data: dict):
    """Handle update application result message from agent."""
    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        hostname = message_data.get("hostname", "unknown")
        updated_packages = message_data.get("updated_packages", [])
        failed_packages = message_data.get("failed_packages", [])
        requires_reboot = message_data.get("requires_reboot", False)

        debug_logger.info(
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
            new_version = package.get("new_version")

            if package_name and package_manager:
                # Update the package status to completed
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
                        status="completed",
                        applied_date=text("NOW()"),
                        new_version=new_version,
                    )
                )
                result = db.execute(stmt)
                debug_logger.info(
                    "Updated package %s status to completed (rows affected: %d)",
                    package_name,
                    result.rowcount,
                )

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
                        error_message=error,
                        applied_date=text("NOW()"),
                    )
                )
                result = db.execute(stmt)
                debug_logger.info(
                    "Updated package %s status to failed (rows affected: %d)",
                    package_name,
                    result.rowcount,
                )

        # Update host reboot requirement
        if requires_reboot:
            stmt = (
                update(Host)
                .where(Host.id == connection.host_id)
                .values(requires_reboot=True)
            )
            db.execute(stmt)

        db.commit()

        debug_logger.info(
            "Update results processed successfully for host %s", connection.host_id
        )

        return {
            "message_type": "success",
            "updated_count": len(updated_packages),
            "failed_count": len(failed_packages),
            "requires_reboot": requires_reboot,
        }

    except Exception as e:
        debug_logger.error("Error processing update results: %s", e)
        db.rollback()
        return {
            "message_type": "error",
            "error": _("Failed to process update results"),
        }


# Make the cache available to other modules
handle_update_apply_result.update_results_cache = update_results_cache
