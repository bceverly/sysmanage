"""
Handler for hostname change messages from agents.
"""

from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.utils.verbosity_logger import get_logger

logger = get_logger(__name__)


async def handle_hostname_changed(
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> None:
    """
    Handle hostname changed notification from agent.

    This is called when an agent successfully changes its hostname and
    reports the new hostname back to the server.

    Args:
        db: Database session
        connection: WebSocket connection (contains host_id)
        message_data: Message data containing new_hostname and success status
    """
    try:
        host_id = getattr(connection, "host_id", None)
        if not host_id:
            logger.warning(_("Hostname changed message received without host_id"))
            return

        # Extract data from the message
        data = message_data.get("data", message_data)
        new_hostname = data.get("new_hostname")
        success = data.get("success", False)
        error_message = data.get("error")

        if not success:
            logger.warning(
                _("Hostname change failed for host %s: %s"),
                host_id,
                error_message or "Unknown error",
            )
            return

        if not new_hostname:
            logger.warning(
                _("Hostname changed message for host %s missing new_hostname"),
                host_id,
            )
            return

        # Update the host's fqdn in the database
        host = db.query(models.Host).filter(models.Host.id == host_id).first()
        if not host:
            logger.warning(_("Host %s not found for hostname update"), host_id)
            return

        old_hostname = host.fqdn
        host.fqdn = new_hostname
        db.commit()

        logger.info(
            _("Updated hostname for host %s from %s to %s"),
            host_id,
            old_hostname,
            new_hostname,
        )

    except Exception as e:
        logger.error(
            _("Error handling hostname changed message: %s"), str(e), exc_info=True
        )
        db.rollback()
