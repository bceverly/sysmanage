# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Ingest an agent's network-discovery report (Phase 21.6 S1).

Contract (from the agent, on its discovery interval):
    message_type = "network_discovery_report"
    data payload = {
        "interfaces":   [{"name", "mac", "ip", "prefix"}],
        "methods":      {"arp_listen": "ok" | "unavailable:<code>", ...},
        "window_seconds": int,
        "observations": [{"mac", "ip", "ips", "interface", "methods",
                          "count", "hostnames", "evidence"}],
    }

Routing only: ``asset_discovery_service`` stores, the licensed engine judges.
Nothing is stored unless ``asset_discovery_engine`` is loaded. Never raises.
"""

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.services import asset_discovery_service as svc
from backend.services import asset_discovery_shim as shim

logger = logging.getLogger(__name__)

ACK = {"message_type": "network_discovery_report_ack"}


async def handle_network_discovery_report(  # NOSONAR - uniform awaited handler API
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Store what one agent saw on its segments."""
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning(
            "network_discovery_report received but connection has no host_id; ignoring"
        )
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "message": "Host not registered",
            "data": {},
        }
    if not shim.engine_available():
        logger.debug(
            "network_discovery_report from host %s ignored: %s is not loaded",
            host_id,
            shim.ENGINE_CODE,
        )
        return ACK
    payload = (
        message_data.get("data") if "observations" not in message_data else message_data
    )
    try:
        summary = svc.record_report(db, host_id, payload or {})
        db.commit()
        logger.info("network_discovery_report from host %s: %s", host_id, summary)
    except Exception:  # pylint: disable=broad-except
        db.rollback()
        # A lost report is a real loss (the next one is minutes away), so it
        # is logged with its host, never swallowed quietly.
        logger.exception(
            "network_discovery_report from host %s could not be stored", host_id
        )
    return ACK
