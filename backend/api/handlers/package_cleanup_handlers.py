# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""``package_cleanup_result``: a host's old-kernel and unneeded-package
cleanup plan or apply (ROADMAP 27.8)."""

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.services import package_cleanup

logger = logging.getLogger(__name__)


async def handle_package_cleanup_result(  # NOSONAR
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Close the cleanup run the agent names (its own host's only).  Never raises."""
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "data": {},
        }
    payload = message_data if "run_id" in message_data else message_data.get("data")
    try:
        package_cleanup.record_result(
            db, host_id, payload if isinstance(payload, dict) else {}
        )
        db.commit()
    except Exception:  # pylint: disable=broad-except
        db.rollback()
        logger.exception("package_cleanup_result from host %s not recorded", host_id)
        return {
            "message_type": "error",
            "error_type": "package_cleanup_result",
            "data": {},
        }
    return {"message_type": "success", "data": {}}
