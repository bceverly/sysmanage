"""
Host validation utilities for SysManage server.
Contains shared validation functions to avoid circular imports.
"""

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence.models import Host


async def validate_host_id(db: Session, connection, host_id: str) -> bool:
    """
    Validate that a host_id exists in the database.
    Returns True if host exists, False if not.
    Sends error message to agent if host doesn't exist.
    """
    if not host_id:
        return True  # No host_id to validate
    host = db.query(Host).filter(Host.id == host_id).first()
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
