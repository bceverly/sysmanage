# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
A host's hardware health report (Phase 23.1 S2).

The agent sends ``hardware_health_update`` when a component's state changes,
else every 15 minutes: its drives, arrays, pools, sensors and memory, each
judged, with every source's status.  ``services/hardware_health.py`` stores
it and records what changed.
"""

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.persistence.models import Host
from backend.services import hardware_health

logger = logging.getLogger(__name__)


def _error() -> Dict[str, Any]:
    return {"message_type": "error", "error_type": "host_not_registered", "data": {}}


async def handle_hardware_health_update(  # NOSONAR
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Store the host's hardware health report.  Never raises."""
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning(
            "hardware_health_update with no host_id on the connection; ignored"
        )
        return _error()
    payload = (
        message_data.get("data") if "components" not in message_data else message_data
    )
    payload = payload if isinstance(payload, dict) else {}
    host = db.query(Host).filter(Host.id == host_id).first()
    if host is None:
        logger.warning("hardware_health_update for unknown host %s; ignored", host_id)
        return _error()
    events = hardware_health.apply_report(db, host, payload)
    db.commit()
    for event in events:
        log = logger.warning if event.to_state in ("failed", "gone") else logger.info
        log(
            "Host %s (%s): %s %s %s -> %s",
            host_id, host.fqdn, event.kind, event.ident,
            event.from_state or "new", event.to_state,
        )  # fmt: skip
    return {
        "message_type": "success",
        "data": {"state": host.hardware_state, "events": len(events)},
    }
