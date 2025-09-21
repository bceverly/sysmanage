"""
Package data handlers for SysManage agent communication.
Handles available packages messages from agents.
"""

import logging
from datetime import datetime, timezone
from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import (
    AvailablePackage,
    Host,
)

# Logger for debugging - use existing root logger configuration
debug_logger = logging.getLogger("debug_logger")
debug_logger.setLevel(logging.DEBUG)


async def handle_packages_update(db: Session, connection, message_data: dict):
    """Handle available packages information from agent."""
    from backend.utils.host_validation import validate_host_id

    # Check for host_id in message data (agent-provided)
    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {"message_type": "error", "error": "host_not_registered"}

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {"message_type": "error", "error": _("Host not registered")}

    try:
        # Get host information for OS details
        host = db.query(Host).filter(Host.id == connection.host_id).first()
        if not host:
            return {"message_type": "error", "error": _("Host not found")}

        # Get OS information from message or host record
        os_name = message_data.get("os_name") or host.platform or "Unknown"
        os_version = (
            message_data.get("os_version") or host.platform_release or "Unknown"
        )

        # Process available packages from different managers
        package_managers = message_data.get("package_managers", {})
        total_packages = 0

        debug_logger.info(
            "Processing available packages for host %s (%s %s): %d managers",
            connection.host_id,
            os_name,
            os_version,
            len(package_managers),
        )

        for manager_name, packages in package_managers.items():
            if not packages:
                continue

            debug_logger.info(
                "Processing %d packages from %s for host %s",
                len(packages),
                manager_name,
                connection.host_id,
            )

            # Clear existing packages for this OS/manager combination first
            db.execute(
                delete(AvailablePackage).where(
                    AvailablePackage.os_name == os_name,
                    AvailablePackage.os_version == os_version,
                    AvailablePackage.package_manager == manager_name,
                )
            )
            # Commit the deletes to fully clear the identity map
            db.commit()

            # Insert new packages
            now = datetime.now(timezone.utc)
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
                    os_name=os_name,
                    os_version=os_version,
                    package_manager=manager_name,
                    package_name=package_name,
                    package_version=package_version,
                    package_description=package_description or None,
                    last_updated=now,
                    created_at=now,
                )
                db.add(available_package)
                total_packages += 1

        # Commit the changes
        db.commit()

        debug_logger.info(
            "Successfully stored %d available packages for host %s (%s %s)",
            total_packages,
            connection.host_id,
            os_name,
            os_version,
        )

        return {
            "message_type": "acknowledgment",
            "status": "success",
            "packages_processed": total_packages,
        }

    except Exception as e:
        db.rollback()
        debug_logger.error(
            "Error processing available packages for host %s: %s",
            connection.host_id,
            e,
        )
        return {
            "message_type": "error",
            "error": _("Failed to process available packages: %s") % str(e),
        }
