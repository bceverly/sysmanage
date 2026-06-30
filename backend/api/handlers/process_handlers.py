"""
Process data handlers for SysManage agent communication (Phase 13.3).

Handles the running-process snapshot an agent reports for a host.  Each
snapshot fully replaces the prior set for that host, so ``host_process`` always
reflects the latest report rather than a time series.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.api.error_constants import error_host_not_registered
from backend.i18n import _
from backend.persistence.models import HostProcess

debug_logger = logging.getLogger("debug_logger")


def _parse_dt(value):
    """Parse an ISO8601 timestamp to a naive-UTC datetime, or None."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


async def handle_process_status_update(db: Session, connection, message_data: dict):
    """Handle a running-process snapshot from the agent."""
    from backend.utils.host_validation import validate_host_id

    agent_host_id = message_data.get("host_id")
    if agent_host_id and not await validate_host_id(db, connection, agent_host_id):
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": error_host_not_registered(),
            "data": {},
        }

    if not hasattr(connection, "host_id") or not connection.host_id:
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": error_host_not_registered(),
            "data": {},
        }

    try:
        processes = message_data.get("processes", []) or []
        collected_at = _parse_dt(message_data.get("collected_at")) or datetime.now(
            timezone.utc
        ).replace(tzinfo=None)

        debug_logger.info(
            "Processing process snapshot from %s: %d processes (truncated=%s)",
            getattr(connection, "hostname", "unknown"),
            len(processes),
            message_data.get("truncated", False),
        )

        # Replace the whole snapshot for this host.
        db.execute(delete(HostProcess).where(HostProcess.host_id == connection.host_id))

        for proc in processes:
            pid = proc.get("pid")
            if pid is None:
                continue  # a process row without a pid is unusable
            db.add(
                HostProcess(
                    host_id=connection.host_id,
                    pid=pid,
                    parent_pid=proc.get("parent_pid"),
                    process_name=(proc.get("name") or "")[:255],
                    username=(proc.get("username") or None),
                    status=(proc.get("status") or None),
                    cpu_percent=proc.get("cpu_percent"),
                    memory_percent=proc.get("memory_percent"),
                    memory_rss_bytes=proc.get("memory_rss_bytes"),
                    command_line=proc.get("command_line"),
                    started_at=_parse_dt(proc.get("started_at")),
                    collected_at=collected_at,
                )
            )

        db.commit()

        debug_logger.info(
            "Successfully stored %d processes for host %s",
            len(processes),
            getattr(connection, "hostname", "unknown"),
        )

        return {
            "message_type": "process_status_update_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "processed",
        }

    except Exception as e:
        debug_logger.exception(
            "Error processing process snapshot from %s: %s",
            getattr(connection, "hostname", "unknown"),
            e,
        )
        db.rollback()
        return {
            "message_type": "error",
            "error_type": "operation_failed",
            "message": _("Failed to process process status update: %s") % str(e),
            "data": {},
        }
