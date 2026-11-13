# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Automatic Ubuntu Pro attach (2026-11-13).

The Ubuntu Pro settings page has always stored "auto-attach" beside the
master key, but nothing acted on it.  Now: when an approved host reports
Ubuntu Pro as not attached, and its tenant has auto-attach on with a
master key, the server queues one ``ubuntu_pro_attach`` with that key.

Each host is handled once, recorded in ``host.ubuntu_pro_auto_attach_at``:
the attach is never retried in a loop, and a host that has been seen
attached is marked too, so detaching it on purpose later is respected.
A failed attempt can be repeated by hand from the host's Ubuntu Pro tab.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)

queue_ops = QueueOperations()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def consider(db: Session, host, attached: bool) -> bool:
    """Queue the one automatic attach for ``host`` if it is due.

    Called with each Ubuntu Pro report; returns True when an attach was
    queued.  Never raises into the report's handling."""
    if host.ubuntu_pro_auto_attach_at is not None:
        return False
    if attached:
        host.ubuntu_pro_auto_attach_at = _now()
        return False
    if host.approval_status != "approved" or not host.active:
        return False
    settings = db.query(models.UbuntuProSettings).first()
    if not settings or not settings.auto_attach_enabled or not settings.master_key:
        return False
    queue_ops.enqueue_message(
        message_type="command",
        message_data=create_command_message(
            "ubuntu_pro_attach",
            {
                "token": settings.master_key,
                "organization": settings.organization_name,
            },
        ),
        direction=QueueDirection.OUTBOUND,
        host_id=host.id,
        db=db,
    )
    host.ubuntu_pro_auto_attach_at = _now()
    logger.info("Ubuntu Pro auto-attach queued for host %s", host.id)
    return True
