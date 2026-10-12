# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Clock offsets and time-service status (Phase 23.3 S2).

``GET /host/{id}/clock`` -- the server's own measurement of the host's clock
(median offset, round trip, sample count, method), what the host's time
service claims, and the measured-offset history.

``GET /time-sync/server`` -- the server's own clock against its reference.
Every host offset is relative to the server, so the UI shows this first.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.services import server_clock

router = APIRouter(dependencies=[Depends(JWTBearer())])

HISTORY_DAYS = 7


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


@router.get("/host/{host_id}/clock")
async def host_clock(
    host_id: str, db: Session = Depends(get_tenant_db)
) -> Dict[str, Any]:
    """One host's clock: measured, claimed, and its recent history."""
    try:
        key = uuid.UUID(host_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "host_not_found"}) from exc
    host = db.get(models.Host, key)
    if host is None:
        raise HTTPException(status_code=404, detail={"code": "host_not_found"})
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=HISTORY_DAYS
    )
    history = (
        db.query(models.HostClockSample)
        .filter(
            models.HostClockSample.host_id == key,
            models.HostClockSample.measured_at >= since,
        )
        .order_by(models.HostClockSample.measured_at)
        .all()
    )
    return {
        "measured": (
            None
            if host.clock_offset_ms is None
            else {
                "offset_ms": host.clock_offset_ms,
                "rtt_ms": host.clock_rtt_ms,
                "samples": host.clock_samples,
                "method": host.clock_method,
                "measured_at": _iso(host.clock_measured_at),
            }
        ),
        "time_service": (
            None
            if host.time_status_at is None
            else {
                "service": host.time_service,
                "running": host.time_service_running,
                "synchronized": host.time_synchronized,
                "source": host.time_source,
                "stratum": host.time_stratum,
                "reported_offset_ms": host.time_reported_offset_ms,
                "reported_at": _iso(host.time_status_at),
            }
        ),
        "history": [
            {
                "at": _iso(s.measured_at),
                "offset_ms": s.offset_ms,
                "rtt_ms": s.rtt_ms,
                "method": s.method,
            }
            for s in history
        ],
    }


@router.get("/time-sync/server")
async def server_clock_status() -> Dict[str, Any]:
    """The server's own clock against its configured reference."""
    # One SNTP exchange at most (cached); still off the event loop.
    return await asyncio.to_thread(server_clock.status)
