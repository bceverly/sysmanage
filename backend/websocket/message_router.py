"""
Message routing logic for SysManage.
Routes messages to appropriate handlers based on message type.
"""

from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.api.handlers import (
    handle_antivirus_status_update,
    handle_commercial_antivirus_status_update,
    handle_hardware_update,
    handle_host_certificates_update,
    handle_host_role_data_update,
    handle_os_version_update,
    handle_package_updates_update,
    handle_reboot_status_update,
    handle_script_execution_result,
    handle_software_update,
    handle_third_party_repository_update,
    handle_user_access_update,
)
from backend.api.package_handlers import (
    handle_packages_batch,
    handle_packages_batch_end,
    handle_packages_batch_start,
)
from backend.i18n import _
from backend.utils.verbosity_logger import get_logger
from backend.websocket.messages import MessageType

logger = get_logger(__name__)


async def route_inbound_message(
    message_type: str, db: Session, mock_connection: Any, message_data: Dict[str, Any]
) -> bool:
    """
    Route an inbound message to the appropriate handler.

    Args:
        message_type: The type of message to route
        db: Database session
        mock_connection: Mock connection object for handlers
        message_data: The message data to process

    Returns:
        True if message was successfully processed, False otherwise
    """
    success = False

    try:
        if message_type == MessageType.OS_VERSION_UPDATE:
            print("About to call handle_os_version_update", flush=True)
            await handle_os_version_update(db, mock_connection, message_data)
            success = True
            print("Successfully processed OS version update", flush=True)

        elif message_type == MessageType.HARDWARE_UPDATE:
            print("About to call handle_hardware_update", flush=True)
            await handle_hardware_update(db, mock_connection, message_data)
            success = True
            print("Successfully processed hardware update", flush=True)

        elif message_type == MessageType.USER_ACCESS_UPDATE:
            print("About to call handle_user_access_update", flush=True)
            await handle_user_access_update(db, mock_connection, message_data)
            success = True
            print("Successfully processed user access update", flush=True)

        elif message_type == MessageType.SOFTWARE_INVENTORY_UPDATE:
            print("About to call handle_software_update", flush=True)
            await handle_software_update(db, mock_connection, message_data)
            success = True
            print("Successfully processed software inventory update", flush=True)

        elif message_type == MessageType.PACKAGE_UPDATES_UPDATE:
            print("About to call handle_package_updates_update", flush=True)
            await handle_package_updates_update(db, mock_connection, message_data)
            success = True
            print("Successfully processed package updates", flush=True)

        elif message_type == MessageType.AVAILABLE_PACKAGES_BATCH_START:
            print("About to call handle_packages_batch_start", flush=True)
            await handle_packages_batch_start(db, mock_connection, message_data)
            success = True
            print("Successfully processed packages batch start", flush=True)

        elif message_type == MessageType.AVAILABLE_PACKAGES_BATCH:
            print("About to call handle_packages_batch", flush=True)
            await handle_packages_batch(db, mock_connection, message_data)
            success = True
            print("Successfully processed packages batch", flush=True)

        elif message_type == MessageType.AVAILABLE_PACKAGES_BATCH_END:
            print("About to call handle_packages_batch_end", flush=True)
            await handle_packages_batch_end(db, mock_connection, message_data)
            success = True
            print("Successfully processed packages batch end", flush=True)

        elif message_type == MessageType.SCRIPT_EXECUTION_RESULT:
            print("About to call handle_script_execution_result", flush=True)
            await handle_script_execution_result(db, mock_connection, message_data)
            success = True
            print("Successfully processed script execution result", flush=True)

        elif message_type == MessageType.REBOOT_STATUS_UPDATE:
            print("About to call handle_reboot_status_update", flush=True)
            await handle_reboot_status_update(db, mock_connection, message_data)
            success = True
            print("Successfully processed reboot status update", flush=True)

        elif message_type == MessageType.HOST_CERTIFICATES_UPDATE:
            print("About to call handle_host_certificates_update", flush=True)
            await handle_host_certificates_update(db, mock_connection, message_data)
            success = True
            print("Successfully processed host certificates update", flush=True)

        elif message_type == MessageType.ROLE_DATA:
            print("About to call handle_host_role_data_update", flush=True)
            await handle_host_role_data_update(db, mock_connection, message_data)
            success = True
            print("Successfully processed host role data update", flush=True)

        elif message_type == MessageType.THIRD_PARTY_REPOSITORY_UPDATE:
            print("About to call handle_third_party_repository_update", flush=True)
            await handle_third_party_repository_update(
                db, mock_connection, message_data
            )
            success = True
            print("Successfully processed third-party repository update", flush=True)

        elif message_type == MessageType.ANTIVIRUS_STATUS_UPDATE:
            print("About to call handle_antivirus_status_update", flush=True)
            await handle_antivirus_status_update(db, mock_connection, message_data)
            success = True
            print("Successfully processed antivirus status update", flush=True)

        elif message_type == MessageType.COMMERCIAL_ANTIVIRUS_STATUS_UPDATE:
            print("About to call handle_commercial_antivirus_status_update", flush=True)
            await handle_commercial_antivirus_status_update(
                db, mock_connection, message_data
            )
            success = True
            print(
                "Successfully processed commercial antivirus status update", flush=True
            )

        else:
            print(f"Unknown message type: {message_type}", flush=True)
            logger.warning(_("Unknown message type in queue: %s"), message_type)
            success = False

    except Exception as e:
        logger.error(
            _("Error routing message type %s: %s"), message_type, str(e), exc_info=True
        )
        print(f"ERROR in routing message type {message_type}: {e}", flush=True)
        success = False

    return success


def log_message_data(message_type: str, message_data: Dict[str, Any]) -> None:
    """
    Log specific data for different message types.

    Args:
        message_type: The type of message
        message_data: The message data to log
    """
    if message_type == MessageType.HARDWARE_UPDATE:
        cpu_vendor = message_data.get("cpu_vendor", "N/A")
        cpu_model = message_data.get("cpu_model", "N/A")
        memory_mb = message_data.get("memory_total_mb", "N/A")
        storage_count = len(message_data.get("storage_devices", []))
        print(
            f"Hardware data - CPU: {cpu_vendor} {cpu_model}, Memory: {memory_mb} MB, Storage: {storage_count} devices",
            flush=True,
        )
        logger.info(
            "Hardware data - CPU: %s %s, Memory: %s MB, Storage: %s devices",
            cpu_vendor,
            cpu_model,
            memory_mb,
            storage_count,
        )
    elif message_type == MessageType.SOFTWARE_INVENTORY_UPDATE:
        total_packages = message_data.get("total_packages", 0)
        software_packages = message_data.get("software_packages", [])
        print(
            f"Software data - Total packages: {total_packages}, Sample: {software_packages[0] if software_packages else 'None'}",
            flush=True,
        )
        logger.info(
            "Software data - Total packages: %s, Sample: %s",
            total_packages,
            software_packages[0] if software_packages else "None",
        )
    elif message_type == MessageType.USER_ACCESS_UPDATE:
        total_users = message_data.get("total_users", 0)
        total_groups = message_data.get("total_groups", 0)
        print(
            f"User access data - Users: {total_users}, Groups: {total_groups}",
            flush=True,
        )
        logger.info(
            "User access data - Users: %s, Groups: %s",
            total_users,
            total_groups,
        )
