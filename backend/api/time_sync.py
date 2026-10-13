# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Clock offsets, time-service status and offset bounds (Phase 23.3 S2/S3).

``GET /host/{id}/clock`` -- the server's own measurement of the host's clock
(median offset, round trip, sample count, method), what the host's time
service claims, and the measured-offset history.

``GET /time-sync/server`` -- the server's own clock against its reference.
Every host offset is relative to the server, so the UI shows this first.

``GET /time-sync/hosts`` -- every approved host's offset and status against
its bounds, worst first.  ``/time-sync/bounds`` -- the server-wide bounds and
the tenant / site / tag overrides (``services/clock_status.py``).  Reasons a
bound is refused travel as codes; the UI words them.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.handlers.time_status_handlers import configured_servers
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.config import config
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import clock_status, ntp_policy, server_clock
from backend.services.audit_service import ActionType, AuditService, EntityType

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(JWTBearer())])

HISTORY_DAYS = 7


class BoundsBody(BaseModel):
    warning_ms: float
    critical_ms: float


class OverrideBody(BoundsBody):
    scope_kind: str
    scope_ref: str = ""


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _require_role(current_user) -> None:
    if not current_user.has_role(SecurityRoles.MANAGE_TIME_SYNC):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required")
            % SecurityRoles.MANAGE_TIME_SYNC.value,
        )


def _measured(host) -> Optional[Dict[str, Any]]:
    if host.clock_offset_ms is None:
        return None
    return {
        "offset_ms": host.clock_offset_ms,
        "rtt_ms": host.clock_rtt_ms,
        "samples": host.clock_samples,
        "method": host.clock_method,
        "measured_at": _iso(host.clock_measured_at),
    }


def _policy_verdict(db: Session, host) -> Optional[Dict[str, Any]]:
    """The host against its fleet NTP policy, or None without the engine."""
    judged = ntp_policy.evaluate(db, [host]).get(str(host.id))
    if judged is None:
        return None
    state = db.get(models.NtpPolicyState, host.id)
    policy = judged["policy"]
    return {
        "policy": None if policy is None else ntp_policy.as_dict(policy),
        "conflict": judged["conflict"],
        "findings": judged["findings"],
        "compliant": judged["compliant"],
        "apply_status": state.status if state else None,
        "apply_error": state.last_error if state else None,
        "configured_servers": configured_servers(host),
        "enabled": host.time_service_enabled,
    }


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
    server, [(_host, bounds, status)] = await asyncio.to_thread(
        clock_status.evaluate, db, [host]
    )
    return {
        "status": status,
        "bounds": bounds,
        "ntp_policy": _policy_verdict(db, host),
        "server": server,
        "service_ok": clock_status.service_ok(host),
        "measured": _measured(host),
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


def _approved(db: Session):
    return db.query(models.Host).filter(models.Host.approval_status == "approved").all()


def _tags_by_host(db: Session, host_ids) -> Dict[str, List[Dict[str, str]]]:
    out: Dict[str, List[Dict[str, str]]] = {}
    if not host_ids:
        return out
    for host_id, tag_id, name in (
        db.query(models.HostTag.host_id, models.Tag.id, models.Tag.name)
        .join(models.Tag, models.Tag.id == models.HostTag.tag_id)
        .filter(models.HostTag.host_id.in_(host_ids))
        .order_by(models.Tag.name)
    ):
        out.setdefault(str(host_id), []).append({"id": str(tag_id), "name": name})
    return out


def _site_names(site_ids) -> Dict[str, str]:
    return clock_status.site_names(site_ids)


def _counts(rows) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for _host, _bounds, status in rows:
        counts[status] = counts.get(status, 0) + 1
    return counts


@router.get("/time-sync/hosts")
async def fleet_clocks(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    """Every approved host's clock against its bounds, worst first, with its
    site and tags so the page can filter by them."""
    hosts = _approved(db)
    server, rows = await asyncio.to_thread(clock_status.evaluate, db, hosts)
    rank = {status: i for i, status in enumerate(clock_status.STATUS_ORDER)}
    rows.sort(
        key=lambda r: (
            rank[r[2]],
            -abs(r[0].clock_offset_ms or 0.0),
            r[0].fqdn or "",
        )
    )
    tags = _tags_by_host(db, [h.id for h in hosts])
    policy = ntp_policy.evaluate(db, hosts)
    sites = _site_names({h.site_id for h in hosts if h.site_id})
    return {
        "server": server,
        "counts": _counts(rows),
        "hosts": [
            {
                "host_id": str(host.id),
                "fqdn": host.fqdn,
                "status": status,
                "bounds": bounds,
                "measured": _measured(host),
                "service_ok": clock_status.service_ok(host),
                "time_service": host.time_service,
                "time_source": host.time_source,
                "site_id": str(host.site_id) if host.site_id else None,
                "site_name": sites.get(str(host.site_id)) if host.site_id else None,
                "tags": tags.get(str(host.id), []),
                # S5b: None without the policy engine, or with no policy.
                "policy_compliant": policy.get(str(host.id), {}).get("compliant"),
                "policy_findings": [
                    f["code"] for f in policy.get(str(host.id), {}).get("findings", [])
                ],
            }
            for host, bounds, status in rows
        ],
    }


@router.get("/time-sync/summary")
async def fleet_summary(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    """Counts per status only -- what the dashboard tile polls."""
    hosts = _approved(db)
    server, rows = await asyncio.to_thread(clock_status.evaluate, db, hosts)
    return {"server": server, "total": len(rows), "counts": _counts(rows)}


@router.get("/time-sync/bounds")
async def get_bounds(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    return {
        "server": clock_status.server_bounds(),
        "overrides": clock_status.overrides(db),
        "limits": {
            "min_ms": clock_status.MIN_BOUND_MS,
            "max_ms": clock_status.MAX_BOUND_MS,
        },
        # Outside multi-tenancy the tenant level IS the server-wide one; the
        # UI offers it only when it means something.
        "multitenancy": bool((config.get_multitenancy_config() or {}).get("enabled")),
    }


def _valid_or_422(body: BoundsBody) -> None:
    reason = clock_status.valid_bounds(body.warning_ms, body.critical_ms)
    if reason:
        raise HTTPException(status_code=422, detail={"code": reason})


def _audit(db, current_user, name: str, description: str, details) -> None:
    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_name=name,
        description=description,
        user_id=current_user.id,
        username=current_user.userid,
        details=details,
    )


@router.put("/time-sync/bounds/server")
async def set_server_bounds(
    body: BoundsBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require_role(current_user)
    _valid_or_422(body)
    if not clock_status.set_server_bounds(body.warning_ms, body.critical_ms):
        raise HTTPException(status_code=503, detail={"code": "not_saved"})
    _audit(
        db,
        current_user,
        "time_sync_bounds",
        _("Clock offset bounds changed"),
        {"scope_kind": "server", **body.model_dump()},
    )
    return clock_status.server_bounds()


def _check_scope(db: Session, scope_kind: str, scope_ref: str) -> None:
    if scope_kind not in clock_status.SCOPES:
        raise HTTPException(status_code=422, detail={"code": "bad_scope"})
    if scope_kind == clock_status.SCOPE_TENANT:
        if scope_ref:
            raise HTTPException(status_code=422, detail={"code": "bad_scope"})
        return
    try:
        key = uuid.UUID(scope_ref)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "bad_scope"}) from exc
    if scope_kind == clock_status.SCOPE_TAG and db.get(models.Tag, key) is None:
        raise HTTPException(status_code=404, detail={"code": "tag_not_found"})


@router.put("/time-sync/bounds/override")
async def set_override(
    body: OverrideBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Set the bounds for the tenant, a site or a tag."""
    _require_role(current_user)
    _valid_or_422(body)
    scope_ref = body.scope_ref.strip()
    _check_scope(db, body.scope_kind, scope_ref)
    clock_status.set_override(
        db,
        body.scope_kind,
        scope_ref,
        body.warning_ms,
        body.critical_ms,
        current_user.userid,
    )
    _audit(
        db,
        current_user,
        "clock_bound",
        _("Clock offset bounds changed"),
        {**body.model_dump(), "scope_ref": scope_ref},
    )
    return {"overrides": clock_status.overrides(db)}


@router.delete("/time-sync/bounds/override")
async def clear_override(
    scope_kind: str,
    scope_ref: str = "",
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Remove an override: the scope falls back to the next level up."""
    _require_role(current_user)
    if not clock_status.clear_override(db, scope_kind, scope_ref.strip()):
        raise HTTPException(status_code=404, detail={"code": "no_override"})
    _audit(
        db,
        current_user,
        "clock_bound",
        _("Clock offset bounds removed"),
        {"scope_kind": scope_kind, "scope_ref": scope_ref.strip()},
    )
    return {"overrides": clock_status.overrides(db)}
