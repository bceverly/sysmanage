"""
Host validation utilities for SysManage server.
Contains shared validation functions to avoid circular imports.
"""

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host


async def validate_host_id(
    db: Session, connection, host_id: str, hostname: str = None
) -> bool:
    """
    Validate that a host_id exists in the database.
    Returns True if host exists, False if not.
    Sends error message to agent if host doesn't exist.

    If hostname is provided, also validate by hostname as fallback.
    """
    if not host_id:
        return True  # No host_id to validate

    # First try to find by exact host_id
    host = db.query(Host).filter(Host.id == host_id).first()

    # If not found by ID but we have hostname, try finding by hostname
    # This handles cases where agent sends incorrect host_id but correct hostname
    if not host and hostname:
        host = db.query(Host).filter(Host.fqdn == hostname).first()
        if host:
            # Found by hostname - this is valid, agent just has wrong ID
            return True

    if not host:
        # Host has been deleted - send error response
        error_message = {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": _("Host with ID %s is not registered. Please re-register.")
            % host_id,
            "data": {"host_id": host_id},
        }
        await connection.send_message(error_message)
        return False
    return True
