# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
What a host's own time service claims about itself (Phase 23.3 S2).

The agent sends ``time_status_update`` whenever the claim changes: which
service runs, whether it is running and synchronized, its source and stratum,
and its own offset estimate.  This is the CLAIM; the server's independent
measurement lives in ``host.clock_*`` (``services/clock_tracking.py``).  Both
are kept so a disagreement -- a service that says "synchronized" on a clock
the server measures seconds off -- stays visible.

Every field is stored as reported, ``None`` included: "not reported" must
never be read as "in sync".
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence.models import Host

logger = logging.getLogger(__name__)

_SERVICES = {"chrony", "ntpd", "timesyncd", "openntpd", "w32time", "timed", "none"}
MAX_SERVERS = 16


def _bool(value: Any) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _float(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _text(value: Any, limit: int) -> Optional[str]:
    return value.strip()[:limit] or None if isinstance(value, str) else None


def _servers(value: Any) -> Optional[List[str]]:
    if not isinstance(value, list):
        return None
    return [
        v.strip()[:255] for v in value[:MAX_SERVERS] if isinstance(v, str) and v.strip()
    ]


def configured_servers(host) -> Optional[List[str]]:
    """The stored list, or None when the host has not reported one."""
    try:
        value = json.loads(host.time_configured_servers or "null")
    except ValueError:
        return None
    return value if isinstance(value, list) else None


def apply_claim(host, payload: Dict[str, Any]) -> None:
    """Store a time-service claim on ``host`` -- from a status update, or the
    status a clock resync reports afterwards (S5)."""
    service = payload.get("service")
    host.time_service = service if service in _SERVICES else None
    host.time_service_running = _bool(payload.get("running"))
    host.time_synchronized = _bool(payload.get("synchronized"))
    host.time_source = _text(payload.get("source"), 255)
    host.time_stratum = _int(payload.get("stratum"))
    host.time_reported_offset_ms = _float(payload.get("reported_offset_ms"))
    # S5b: how it is configured.  Older agents send none of these: kept None.
    servers = _servers(payload.get("configured_servers"))
    host.time_configured_servers = None if servers is None else json.dumps(servers)
    host.time_service_enabled = _bool(payload.get("enabled"))
    host.time_service_unit = _text(payload.get("unit"), 64)
    host.time_config_path = _text(payload.get("config_path"), 255)
    host.time_status_at = datetime.now(timezone.utc).replace(tzinfo=None)


async def handle_time_status_update(  # NOSONAR
    db: Session, connection: Any, message_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Store the host's time-service claim.  Never raises."""
    host_id = getattr(connection, "host_id", None)
    if not host_id:
        logger.warning("time_status_update with no host_id on the connection; ignored")
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "data": {},
        }
    payload = (
        message_data.get("data") if "service" not in message_data else message_data
    )
    payload = payload if isinstance(payload, dict) else {}
    host = db.query(Host).filter(Host.id == host_id).first()
    if host is None:
        logger.warning("time_status_update for unknown host %s; ignored", host_id)
        return {
            "message_type": "error",
            "error_type": "host_not_registered",
            "data": {},
        }

    apply_claim(host, payload)
    db.commit()
    if host.time_service_running is False:
        logger.warning(
            "Host %s (%s): its time service %s is not running",
            host_id,
            host.fqdn,
            host.time_service,
        )
    return {"message_type": "time_status_ack"}
