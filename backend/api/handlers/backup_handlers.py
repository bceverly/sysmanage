# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Backup results and progress from the agent (ROADMAP Phase 24).

``backup_result`` -- restate's status word and result JSON for one run
(``services/backup_results.py`` stores it and queues the storage-side jobs
that follow a good capture); ``backup_progress`` -- the latest progress
line of a run still going.  A message naming a run that belongs to another
host is ignored and logged.
"""

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.services import backup_results

logger = logging.getLogger(__name__)


def _error() -> Dict[str, Any]:
    return {"message_type": "error", "error_type": "host_not_registered", "data": {}}


def _payload(message_data: Dict[str, Any]) -> Dict[str, Any]:
    payload = message_data if "run_id" in message_data else message_data.get("data")
    return payload if isinstance(payload, dict) else {}


async def handle_backup_result(  # NOSONAR
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Record one backup run's outcome.  Never raises."""
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning("backup_result with no host_id on the connection; ignored")
        return _error()
    try:
        run = backup_results.record_result(db, host_id, _payload(message_data))
        db.commit()
    except Exception:  # pylint: disable=broad-except
        db.rollback()
        logger.exception("backup_result from host %s could not be recorded", host_id)
        return {"message_type": "error", "error_type": "backup_result", "data": {}}
    return {"message_type": "success", "data": {"stored": run is not None}}


async def handle_backup_progress(  # NOSONAR
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Keep a running backup's latest progress.  Never raises."""
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        return _error()
    try:
        run = backup_results.record_progress(db, host_id, _payload(message_data))
        db.commit()
    except Exception:  # pylint: disable=broad-except
        db.rollback()
        logger.exception("backup_progress from host %s could not be recorded", host_id)
        return {"message_type": "error", "error_type": "backup_progress", "data": {}}
    return {"message_type": "success", "data": {"stored": run is not None}}
