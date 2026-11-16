# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A host's agent came back on a different version: ask it for its updates.

"Update agent on selected" only queues ``update_agent``; nothing refreshed
the host's pending updates afterwards.  The upgraded agent skips its startup
update check when one ran recently (Phase 22.1), so the update it had just
installed stayed listed on the Updates page until its next scheduled check
(production, 2026-11-16: hosts on .21 still listed an update to .21).  The
first heartbeat that reports a new version now queues ``check_updates``,
the same command as "Check for updates" on the host.
"""

import logging

from backend.utils.verbosity_logger import sanitize_log
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)
queue_ops = QueueOperations()


def note_agent_version(db, host, reported) -> bool:
    """Store the version the agent reported.  When it differs from the one
    stored -- not the first report, which the agent's own startup check
    covers -- and the host is approved, queue an update check.  True when
    one was queued."""
    if not reported:
        return False
    previous = host.agent_version
    host.agent_version = reported
    if not previous or previous == reported or host.approval_status != "approved":
        return False
    queue_ops.enqueue_message(
        message_type="command",
        message_data=create_command_message(
            command_type="check_updates", parameters={}
        ),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )
    logger.info(
        "Host %s: agent %s -> %s; update check queued",
        host.id,
        sanitize_log(previous),
        sanitize_log(reported),
    )
    return True
