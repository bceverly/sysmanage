# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Spot resynchronization of host clocks (Phase 23.3 S5).

``POST /host/{id}/clock/resync`` -- one host, now.
``POST /time-sync/resync`` -- every host in the given statuses (default:
warning and critical), released in waves.
``GET /time-sync/resyncs`` -- recent resyncs, for a host or a batch.

Every request is audited.  The first wave is released at once, so a single
host does not wait for the tick.
"""

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import clock_resync, clock_status
from backend.services.audit_service import ActionType, AuditService, EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])

DEFAULT_STATUSES = (clock_status.STATUS_WARNING, clock_status.STATUS_CRITICAL)
# Statuses a bulk resync may target: never "server_clock_off" (the SERVER is
# wrong; stepping the hosts to it would make them wrong too).
BULK_STATUSES = (
    clock_status.STATUS_WARNING,
    clock_status.STATUS_CRITICAL,
    clock_status.STATUS_OK,
    clock_status.STATUS_STALE,
)
MAX_LIST = 500


class BulkBody(BaseModel):
    statuses: List[str] = list(DEFAULT_STATUSES)
    host_ids: Optional[List[str]] = None


def _require_role(current_user) -> None:
    if not current_user.has_role(SecurityRoles.RESYNC_HOST_CLOCK):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required")
            % SecurityRoles.RESYNC_HOST_CLOCK.value,
        )


def _audit(db, current_user, name: str, description: str, details) -> None:
    AuditService.log(
        db=db,
        action_type=ActionType.EXECUTE,
        entity_type=EntityType.HOST,
        entity_name=name,
        description=description,
        user_id=current_user.id,
        username=current_user.userid,
        details=details,
    )


def _host_or_404(db: Session, host_id: str):
    try:
        key = uuid.UUID(host_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "host_not_found"}) from exc
    host = db.get(models.Host, key)
    if host is None or host.approval_status != "approved":
        raise HTTPException(status_code=404, detail={"code": "host_not_found"})
    return host


@router.post("/host/{host_id}/clock/resync")
async def resync_host(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Step one host's clock now."""
    _require_role(current_user)
    host = _host_or_404(db, host_id)
    rows, skipped = clock_resync.request(db, [host], current_user.userid)
    if skipped:
        raise HTTPException(status_code=409, detail={"code": "already_running"})
    await asyncio.to_thread(clock_resync.release, db)
    _audit(
        db,
        current_user,
        host.fqdn,
        _("Clock resync requested"),
        {"host_id": str(host.id), "offset_ms": host.clock_offset_ms},
    )
    db.refresh(rows[0])
    return clock_resync.as_dict(rows[0])


@router.post("/time-sync/resync")
async def resync_fleet(
    body: BulkBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Resync every approved host in ``statuses`` (optionally only
    ``host_ids``), in waves."""
    _require_role(current_user)
    statuses = set(body.statuses or ())
    if not statuses or not statuses <= set(BULK_STATUSES):
        raise HTTPException(status_code=422, detail={"code": "bad_statuses"})
    query = db.query(models.Host).filter(models.Host.approval_status == "approved")
    if body.host_ids is not None:
        try:
            ids = [uuid.UUID(h) for h in body.host_ids]
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail={"code": "bad_host_ids"}
            ) from exc
        query = query.filter(models.Host.id.in_(ids))
    _server, evaluated = await asyncio.to_thread(clock_status.evaluate, db, query.all())
    targets = [host for host, _b, status in evaluated if status in statuses]
    batch_id = uuid.uuid4()
    rows, skipped = clock_resync.request(
        db, targets, current_user.userid, batch_id=batch_id
    )
    await asyncio.to_thread(clock_resync.release, db)
    counts: Dict[str, int] = {}
    for row in rows:
        db.refresh(row)
        counts[row.status] = counts.get(row.status, 0) + 1
    _audit(
        db,
        current_user,
        "time_sync",
        _("Clock resync requested for the fleet"),
        {
            "batch_id": str(batch_id),
            "statuses": sorted(statuses),
            "hosts": len(rows),
            "already_running": len(skipped),
        },
    )
    return {
        "batch_id": str(batch_id),
        "requested": len(rows),
        "already_running": len(skipped),
        "counts": counts,
    }


@router.get("/time-sync/resyncs")
async def list_resyncs(
    host_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_tenant_db),
) -> Dict[str, Any]:
    """Recent resyncs, newest first, for a host or a batch."""
    query = db.query(models.ClockResync)
    try:
        if host_id:
            query = query.filter(models.ClockResync.host_id == uuid.UUID(host_id))
        if batch_id:
            query = query.filter(models.ClockResync.batch_id == uuid.UUID(batch_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "bad_id"}) from exc
    rows = (
        query.order_by(models.ClockResync.requested_at.desc())
        .limit(max(1, min(limit, MAX_LIST)))
        .all()
    )
    return {"resyncs": [clock_resync.as_dict(r) for r in rows]}
