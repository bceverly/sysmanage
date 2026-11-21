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

2026-11-21 (production): it never fired.  A reconnecting agent's SYSTEM_INFO
stores its version first, so by the first heartbeat the stored version
already matched and hosts on 3.15.0.3 still listed the update to it.  The
SYSTEM_INFO handler now asks here before it writes the version.

The SysManage server's own host is asked too, once per server process, the
first time it connects: an upgrade of the ``sysmanage`` package restarts the
server, not that host's agent, so nothing else would refresh the host's list
(it went on listing the server upgrade just installed).
"""

import logging

from backend.utils.verbosity_logger import sanitize_log
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)
queue_ops = QueueOperations()
# The server's own host has been asked for its updates since this process
# started (per tenant: the same host id cannot repeat across tenants).
_SERVER_HOST_ASKED: set = set()
# Which host is this server, worked out once per tenant per process: every
# SYSTEM_INFO asks, and finding it reads every approved host.
_SERVER_HOST_ID: dict = {}


def _tenant_key():
    # pylint: disable=import-outside-toplevel
    from backend.persistence.tenant_context import get_active_tenant  # noqa: PLC0415

    return get_active_tenant() or ""


def _server_host_id(db):
    key = _tenant_key()
    if key not in _SERVER_HOST_ID:
        # pylint: disable=import-outside-toplevel
        from backend.services import backup_server  # noqa: PLC0415

        try:
            _SERVER_HOST_ID[key] = backup_server.server_host_id(db)
        except Exception as error:  # pylint: disable=broad-exception-caught
            # A failure here must never stop an agent registering.
            logger.warning("Could not tell which host is this server: %s", error)
            return None
    return _SERVER_HOST_ID[key]


def _queue_check(db, host) -> None:
    queue_ops.enqueue_message(
        message_type="command",
        message_data=create_command_message(
            command_type="check_updates", parameters={}
        ),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )


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
    _queue_check(db, host)
    logger.info(
        "Host %s: agent %s -> %s; update check queued",
        host.id,
        sanitize_log(previous),
        sanitize_log(reported),
    )
    return True


def note_server_host_connected(db, host) -> bool:
    """The first time this server process sees its own host connect, ask
    that host for its updates (the server itself may have just been
    upgraded).  True when one was queued."""
    if host.approval_status != "approved" or str(host.id) in _SERVER_HOST_ASKED:
        return False
    if _server_host_id(db) != str(host.id):
        return False
    _SERVER_HOST_ASKED.add(str(host.id))
    _queue_check(db, host)
    logger.info("Host %s is this server: update check queued after start", host.id)
    return True
