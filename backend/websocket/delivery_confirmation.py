# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Delivery confirmation: an agent's message is safe only once it is stored.

Until 2026-11-06 an agent deleted each message from its own queue the moment
the WebSocket write succeeded.  When the server could not store it -- the
database restarting, upgrading, or paused for a backup -- the enqueue raised,
the agent was told only ``processing_error`` with no message id, and the
message was gone from both ends: command results, script output, backup
results.  Now:

* the agent says it can wait for confirmation (``delivery_confirmation`` in
  its ``system_info``), and the server says the same in
  ``registration_success``; neither waits for the other unless both do, so
  older agents and servers behave exactly as before;
* the server sends ``message_stored`` with the message's id only after the
  message is committed to the queue (or, for heartbeats, system_info and
  command acknowledgments, handled) -- never before;
* a message the server will never take (failed validation, claiming another
  host) is confirmed as ``rejected``, so the agent does not resend it forever;
* nothing is sent when storing failed: the agent keeps the message and sends
  it again after a timeout or a reconnect;
* a message id the host's queue already holds is not stored twice, so a
  resend whose first copy did arrive is harmless.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.persistence.models import MessageQueue
from backend.utils.verbosity_logger import sanitize_log
from backend.websocket.queue_enums import QueueDirection

logger = logging.getLogger(__name__)

SUPPORTED = 1
FLAG = "delivery_confirmation"
MESSAGE_TYPE = "message_stored"
STORED = "stored"
REJECTED = "rejected"
BUFFERED = "buffered"  # held for registration: confirmed when the resend lands


def note_system_info(connection, raw_message: dict) -> None:
    """Remember that this connection's agent waits for confirmations."""
    if raw_message.get("message_type") == "system_info" and (
        (raw_message.get("data") or {}).get(FLAG)
    ):
        connection.delivery_confirmation = True


def wanted(connection) -> bool:
    return getattr(connection, "delivery_confirmation", False) is True


async def confirm(connection, message_id: Optional[str], status: str) -> None:
    """Tell the agent ``message_id`` is stored (or will never be)."""
    if not message_id or status not in (STORED, REJECTED) or not wanted(connection):
        return
    try:
        await connection.send_message(
            {
                "message_type": MESSAGE_TYPE,
                "data": {"message_id": str(message_id), "status": status},
            }
        )
    except Exception:  # pylint: disable=broad-exception-caught
        # The agent resends after its timeout; the duplicate is not stored.
        logger.debug(
            "Could not confirm message %s", sanitize_log(message_id), exc_info=True
        )


def already_queued(db: Session, message_id: Optional[str]) -> bool:
    """The host's queue already holds this agent message (a resend)."""
    if not message_id:
        return False
    return (
        db.query(MessageQueue.id)
        .filter(
            MessageQueue.message_id == str(message_id),
            MessageQueue.direction == QueueDirection.INBOUND,
        )
        .first()
        is not None
    )
