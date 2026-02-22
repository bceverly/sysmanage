"""
Reboot orchestration service — state machine for safe parent host reboot.

Manages the lifecycle:
    shutting_down → rebooting → pending_restart → restarting → completed | failed
"""

import json
import logging
from datetime import datetime, timezone

from backend.i18n import _
from backend.persistence.models import HostChild, RebootOrchestration
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger("backend.services.reboot_orchestration")


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def check_shutdown_progress(db, parent_host_id):
    """
    Called after a child host is stopped. Checks if all snapshot children
    are now stopped. If so, issues the reboot command.

    Args:
        db: SQLAlchemy session
        parent_host_id: UUID of the parent host
    """
    orchestration = (
        db.query(RebootOrchestration)
        .filter(
            RebootOrchestration.parent_host_id == parent_host_id,
            RebootOrchestration.status == "shutting_down",
        )
        .first()
    )

    if not orchestration:
        return

    snapshot = json.loads(orchestration.child_hosts_snapshot)
    snapshot_names = {entry["child_name"] for entry in snapshot}

    # Check current status of all snapshot children
    still_running = (
        db.query(HostChild)
        .filter(
            HostChild.parent_host_id == parent_host_id,
            HostChild.child_name.in_(snapshot_names),
            HostChild.status == "running",
        )
        .count()
    )

    if still_running > 0:
        # Check for timeout
        elapsed = (_now() - orchestration.initiated_at).total_seconds()
        if elapsed < orchestration.shutdown_timeout_seconds:
            logger.info(
                "Orchestration %s: %d children still running, waiting (%.0fs / %ds)",
                orchestration.id,
                still_running,
                elapsed,
                orchestration.shutdown_timeout_seconds,
            )
            return

        # Timeout exceeded — proceed anyway
        logger.warning(
            "Orchestration %s: shutdown timeout exceeded, proceeding with reboot "
            "(%d children still running)",
            orchestration.id,
            still_running,
        )

    # All children stopped (or timeout) — issue reboot
    now = _now()
    orchestration.status = "rebooting"
    orchestration.shutdown_completed_at = now
    orchestration.reboot_issued_at = now

    queue_ops = QueueOperations()
    command_message = create_command_message(
        command_type="reboot_system", parameters={}
    )
    queue_ops.enqueue_message(
        message_type="command",
        message_data=command_message,
        direction=QueueDirection.OUTBOUND,
        host_id=str(parent_host_id),
        db=db,
    )

    db.commit()

    logger.info(
        "Orchestration %s: all children stopped, reboot command issued for host %s",
        orchestration.id,
        parent_host_id,
    )


def handle_agent_reconnect(db, host_id):
    """
    Called from the heartbeat handler when a host becomes active.
    If there's an active orchestration in 'rebooting' state, transitions
    to restarting children.

    Args:
        db: SQLAlchemy session
        host_id: UUID of the host that just reconnected
    """
    orchestration = (
        db.query(RebootOrchestration)
        .filter(
            RebootOrchestration.parent_host_id == host_id,
            RebootOrchestration.status == "rebooting",
        )
        .first()
    )

    if not orchestration:
        return

    now = _now()
    orchestration.agent_reconnected_at = now
    orchestration.status = "restarting"

    snapshot = json.loads(orchestration.child_hosts_snapshot)

    # Initialize restart status tracking
    restart_status = [
        {
            "id": entry["id"],
            "child_name": entry["child_name"],
            "restart_status": "pending",
            "error": None,
        }
        for entry in snapshot
    ]
    orchestration.child_hosts_restart_status = json.dumps(restart_status)

    # Enqueue start commands for each child that was running before reboot
    queue_ops = QueueOperations()
    for entry in snapshot:
        command_message = create_command_message(
            command_type="start_child_host",
            parameters={
                "child_name": entry["child_name"],
                "child_type": entry["child_type"],
            },
        )
        queue_ops.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=str(host_id),
            db=db,
        )

    db.commit()

    logger.info(
        "Orchestration %s: agent reconnected for host %s, "
        "enqueued start commands for %d children",
        orchestration.id,
        host_id,
        len(snapshot),
    )


def check_restart_progress(db, parent_host_id):
    """
    Called after a child host is started. Updates restart status and
    marks orchestration as completed when all children are restarted.

    Args:
        db: SQLAlchemy session
        parent_host_id: UUID of the parent host
    """
    orchestration = (
        db.query(RebootOrchestration)
        .filter(
            RebootOrchestration.parent_host_id == parent_host_id,
            RebootOrchestration.status == "restarting",
        )
        .first()
    )

    if not orchestration:
        return

    snapshot = json.loads(orchestration.child_hosts_snapshot)
    restart_status = json.loads(orchestration.child_hosts_restart_status or "[]")

    # Update restart status based on current child host states
    for entry in restart_status:
        child = (
            db.query(HostChild)
            .filter(
                HostChild.parent_host_id == parent_host_id,
                HostChild.child_name == entry["child_name"],
            )
            .first()
        )
        if child and child.status == "running":
            entry["restart_status"] = "running"
        elif child and child.status == "error":
            entry["restart_status"] = "failed"
            entry["error"] = child.error_message

    orchestration.child_hosts_restart_status = json.dumps(restart_status)

    # Check if all children have been restarted (or failed)
    all_done = all(
        entry["restart_status"] in ("running", "failed") for entry in restart_status
    )

    if all_done:
        failed_count = sum(
            1 for entry in restart_status if entry["restart_status"] == "failed"
        )
        orchestration.restart_completed_at = _now()

        if failed_count > 0:
            orchestration.status = "completed"
            orchestration.error_message = _(
                "%d of %d child host(s) failed to restart"
            ) % (failed_count, len(restart_status))
        else:
            orchestration.status = "completed"

        db.commit()

        logger.info(
            "Orchestration %s: completed (%d/%d restarted, %d failed)",
            orchestration.id,
            len(restart_status) - failed_count,
            len(restart_status),
            failed_count,
        )
    else:
        db.commit()

        pending_count = sum(
            1 for entry in restart_status if entry["restart_status"] == "pending"
        )
        logger.info(
            "Orchestration %s: %d children still pending restart",
            orchestration.id,
            pending_count,
        )
