# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Ingest config-profile results from agents (Phase 20.1).

WHY A ROW PER RUN
-----------------
Idempotency reporting is the point of desired-state config management, and it
is a claim about HISTORY: "the last three applications of this profile changed
nothing" cannot be answered by a current-state column.  So every result lands
as its own row, including the no-ops -- those are the interesting ones.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not decide whether a host is compliant.  The agent reports what its
executor did; judging that against a desired baseline is drift analysis
(Phase 20.2) and belongs where the profiles live.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.persistence import models

logger = logging.getLogger(__name__)

# Per-task detail can be large on a long playbook.  Stored for diagnosis, not
# for querying, so it is capped rather than allowed to grow without bound --
# an unbounded Text column filled by a remote host is a disk-exhaustion path.
MAX_TASK_DETAIL_CHARS = 60000
MAX_ERROR_CHARS = 8000


def _truncate(text: Optional[str], limit: int) -> Optional[str]:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def _host_id_for(db, connection, message_data: Dict[str, Any]):
    """Resolve the reporting host, or None if it cannot be identified."""
    host_id = getattr(connection, "host_id", None)
    if host_id:
        return host_id
    hostname = getattr(connection, "hostname", None) or message_data.get("hostname")
    if not hostname:
        return None
    host = db.query(models.Host).filter(models.Host.fqdn == hostname).first()
    return host.id if host else None


async def handle_config_profile_result(db, connection, message_data: dict):
    """Record one application of a configuration profile.

    Never raises for a malformed payload: a result that cannot be stored must
    not take down the queue processor that delivered it, and losing one row is
    a better outcome than stalling every other host's messages behind it.
    """
    result = message_data.get("result") or {}
    if not isinstance(result, dict):
        logger.warning("Config profile result was not an object; ignoring")
        return {"success": False, "error": "malformed_result"}

    host_id = _host_id_for(db, connection, message_data)
    if not host_id:
        logger.warning("Config profile result from an unidentifiable host; ignoring")
        return {"success": False, "error": "unknown_host"}

    recap = result.get("recap") or {}
    tasks = result.get("tasks") or []
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    profile_id = result.get("profile_id") or message_data.get("profile_id")
    try:
        profile_uuid = uuid.UUID(str(profile_id)) if profile_id else None
    except (ValueError, AttributeError, TypeError):
        # A malformed id must not lose the whole run -- the result is still
        # worth recording, just without the association.
        logger.warning("Config profile result carried an unusable profile_id")
        profile_uuid = None

    try:
        run = models.ConfigProfileRun(
            host_id=host_id,
            command_id=message_data.get("command_id"),
            profile_id=profile_uuid,
            profile_name=result.get("profile_name") or message_data.get("profile_name"),
            executor=result.get("executor"),
            check_mode=bool(result.get("check_mode")),
            success=bool(result.get("success")),
            changed=bool(result.get("changed")),
            exit_code=result.get("exit_code"),
            tasks_ok=int(recap.get("ok") or 0),
            tasks_changed=int(recap.get("changed") or 0),
            tasks_failed=int(recap.get("failed") or 0),
            tasks_skipped=int(recap.get("skipped") or 0),
            tasks_unreachable=int(recap.get("unreachable") or 0),
            task_detail=_truncate(
                json.dumps(tasks, default=str) if tasks else None,
                MAX_TASK_DETAIL_CHARS,
            ),
            error_output=_truncate(result.get("stderr"), MAX_ERROR_CHARS),
            reason=result.get("reason"),
            started_at=None,
            completed_at=now,
            created_at=now,
        )
        db.add(run)
        db.commit()
    except Exception as exc:  # NOSONAR - see docstring: never stall the queue
        db.rollback()
        logger.exception("Failed to record config profile result: %s", exc)
        return {"success": False, "error": str(exc)}

    logger.info(
        "Config profile run recorded for host %s: success=%s changed=%s",
        host_id,
        run.success,
        run.changed,
    )
    return {
        "success": True,
        "message": "config_profile_result_recorded",
        "run_id": str(run.id),
    }
