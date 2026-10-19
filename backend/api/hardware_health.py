# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Hardware health (Phase 23.1 S2).

``GET /host/{id}/hardware-health`` -- the host's components (worst first),
each source's status and the recent events.

``GET /hardware-health/hosts`` -- every approved host's status, counts per
state and its worst components, with site and tags so the page can filter.
``GET /hardware-health/summary`` -- counts per status, for the dashboard
tile.  ``GET /hardware-health/events`` -- the fleet's state changes, newest
first (``?open=true``: not yet resolved).

``POST /hardware-health/events/{id}/acknowledge`` and ``.../resolve`` --
with an optional note; the Manage Hardware Health role.  Reasons travel as
codes with parameters; the UI words them.

``GET /hardware-health/smartmontools`` -- the hosts whose drives cannot be
read without smartmontools (S6), each one's last install, and whether the
automatic install is licensed (Enterprise) and consented to.
``POST /hardware-health/smartmontools/install`` -- install it on the given
hosts (Manage Hardware Health + Add Package).  ``PUT
/hardware-health/smartmontools`` -- an administrator's consent to the
automatic install.

``PUT /host/{id}/hardware-health/temperature-limit`` -- the host's own
temperature warning limit, replacing each sensor's device "high" limit
(``{"limit_c": null}`` clears it); the Manage Hardware Health role.
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.persistence.tenant_context import get_active_tenant
from backend.security.roles import SecurityRoles
from backend.services import clock_status, hardware_health, smartmontools_install
from backend.services import hardware_temperature_limit as temperature_limit
from backend.services.audit_service import ActionType, AuditService, EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])


class EventNote(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class BulkEvents(BaseModel):
    # Either the events picked on screen, or every event the action would
    # still change ("Select all N matching"), optionally on one host.
    event_ids: Optional[List[str]] = Field(
        default=None, max_length=hardware_health.MAX_BULK_EVENTS
    )
    all_open: bool = False
    host_id: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=500)


class InstallRequest(BaseModel):
    host_ids: List[str] = Field(min_length=1, max_length=5000)


class AutoInstall(BaseModel):
    auto: bool


class TemperatureLimit(BaseModel):
    # None clears the host's limit; the range is checked in the endpoint so
    # the error is worded for people, not as a schema failure.
    limit_c: Optional[float] = None


def _host_or_404(db: Session, host_id: str) -> models.Host:
    try:
        key = uuid.UUID(host_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=_("Host not found")) from exc
    host = db.query(models.Host).filter(models.Host.id == key).first()
    if host is None:
        raise HTTPException(status_code=404, detail=_("Host not found"))
    return host


@router.get("/host/{host_id}/hardware-health")
async def host_hardware_health(
    host_id: str, db: Session = Depends(get_tenant_db)
) -> Dict[str, Any]:
    host = _host_or_404(db, host_id)
    view = hardware_health.host_view(db, host)
    view["smartmontools"] = {
        "recommended": any(
            r.get("code") == smartmontools_install.REASON
            for c in view["components"]
            if c["kind"] == "drive"
            for r in c["reasons"]
        ),
        "install": smartmontools_install.installs_by_host(db, [host.id]).get(
            str(host.id)
        ),
    }
    return view


def _approved(db: Session) -> List[models.Host]:
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


def _counts(statuses) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    return counts


@router.get("/hardware-health/hosts")
async def fleet_hardware_health(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    """Every approved host, worst first."""
    hosts = _approved(db)
    ids = [h.id for h in hosts]
    rank = {s: i for i, s in enumerate(hardware_health.STATUS_ORDER)}
    counts = hardware_health.counts_by_host(db, ids)
    rows = sorted(
        (
            (
                h,
                hardware_health.host_status(
                    h, has_components=bool(counts.get(str(h.id)))
                ),
            )
            for h in hosts
        ),
        key=lambda r: (rank.get(r[1], len(rank)), r[0].fqdn or ""),
    )
    problems = hardware_health.problems_by_host(db, ids)
    tags = _tags_by_host(db, ids)
    sites = clock_status.site_names({h.site_id for h in hosts if h.site_id})
    return {
        "counts": _counts(status for _h, status in rows),
        "hosts": [
            {
                "host_id": str(host.id),
                "fqdn": host.fqdn,
                "platform": host.platform,
                "status": status,
                "reported_at": (
                    host.hardware_reported_at.isoformat()
                    if host.hardware_reported_at
                    else None
                ),
                "component_counts": counts.get(str(host.id), {}),
                "problems": problems.get(str(host.id), []),
                "site_id": str(host.site_id) if host.site_id else None,
                "site_name": sites.get(str(host.site_id)) if host.site_id else None,
                "tags": tags.get(str(host.id), []),
            }
            for host, status in rows
        ],
    }


@router.get("/hardware-health/summary")
async def fleet_summary(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    hosts = _approved(db)
    with_parts = hardware_health.hosts_with_components(db, [h.id for h in hosts])
    statuses = [
        hardware_health.host_status(h, has_components=str(h.id) in with_parts)
        for h in hosts
    ]
    return {"total": len(statuses), "counts": _counts(statuses)}


@router.get("/hardware-health/events")
async def fleet_events(
    db: Session = Depends(get_tenant_db),
    open_only: bool = Query(False, alias="open"),
    host_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
) -> Dict[str, Any]:
    query = db.query(models.HardwareEvent)
    if open_only:
        query = query.filter(models.HardwareEvent.resolved_at.is_(None))
    if host_id:
        query = query.filter(
            models.HardwareEvent.host_id == _host_or_404(db, host_id).id
        )
    total = query.count()  # "Select all N matching" needs N beyond the page
    events = query.order_by(models.HardwareEvent.occurred_at.desc()).limit(limit).all()
    fqdns = {
        str(h.id): h.fqdn
        for h in db.query(models.Host.id, models.Host.fqdn).filter(
            models.Host.id.in_({e.host_id for e in events})
        )
    } if events else {}  # fmt: skip
    return {
        "events": [
            {**hardware_health.event_view(e), "fqdn": fqdns.get(str(e.host_id))}
            for e in events
        ],
        "total": total,
    }


def _require_role(current_user) -> None:
    if not current_user.has_role(SecurityRoles.MANAGE_HARDWARE_HEALTH):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required")
            % SecurityRoles.MANAGE_HARDWARE_HEALTH.value,
        )


def _change(db, event_id, body, current_user, action):
    _require_role(current_user)
    change = (
        hardware_health.acknowledge
        if action == "acknowledge"
        else hardware_health.resolve
    )
    event = change(db, event_id, current_user.userid, body.note)
    if event is None:
        raise HTTPException(status_code=404, detail=_("Hardware event not found"))
    AuditService.log(
        db=db,
        user_id=current_user.id,
        username=current_user.userid,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.HOST,
        entity_id=str(event.host_id),
        entity_name=event.name,
        description=f"Hardware event {action}d: {event.kind} {event.ident}",
        details={"event_id": str(event.id), "note": body.note},
    )
    db.commit()
    return hardware_health.event_view(event)


@router.post("/hardware-health/events/{event_id}/acknowledge")
async def acknowledge_event(
    event_id: str,
    body: EventNote,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    return _change(db, event_id, body, current_user, "acknowledge")


@router.post("/hardware-health/events/{event_id}/resolve")
async def resolve_event(
    event_id: str,
    body: EventNote,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    return _change(db, event_id, body, current_user, "resolve")


def _bulk_audit(db, current_user, action: str, changed, note) -> None:
    """One entry per host touched, not one per event: a bulk resolve of a
    flapping sensor's 200 events is one decision, and the host's own audit
    trail still shows it."""
    by_host: Dict[str, List[models.HardwareEvent]] = {}
    for event in changed:
        by_host.setdefault(str(event.host_id), []).append(event)
    for host_id, events in by_host.items():
        AuditService.log(
            db=db,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.HOST,
            entity_id=host_id,
            description=f"Hardware events {action}d in bulk: {len(events)}",
            details={"event_ids": [str(e.id) for e in events], "note": note},
            commit=False,
        )


def _bulk(db, body: BulkEvents, current_user, action: str) -> Dict[str, Any]:
    _require_role(current_user)
    if (body.event_ids is None) == (not body.all_open):
        raise HTTPException(
            status_code=422,
            detail=_(
                "Choose either specific events or all unresolved events, not both."
            ),
        )
    host = _host_or_404(db, body.host_id).id if body.host_id else None
    result = hardware_health.bulk_change(
        db, action, current_user.userid,
        event_ids=body.event_ids, host_id=host, note=body.note,
    )  # fmt: skip
    _bulk_audit(db, current_user, action, result["changed"], body.note)
    db.flush()
    # "all open" changes at most MAX_BULK_EVENTS per call; say what is left
    remaining = hardware_health.count_open(db, action, host) if body.all_open else 0
    db.commit()
    return {
        f"{action}d": len(result["changed"]),
        "skipped": result["skipped"],
        "remaining": remaining,
    }


@router.post("/hardware-health/events/acknowledge")
async def acknowledge_events(
    body: BulkEvents,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    return _bulk(db, body, current_user, "acknowledge")


@router.post("/hardware-health/events/resolve")
async def resolve_events(
    body: BulkEvents,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    return _bulk(db, body, current_user, "resolve")


@router.put("/host/{host_id}/hardware-health/temperature-limit")
async def set_temperature_limit(
    host_id: str,
    body: TemperatureLimit,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """The host's own temperature warning limit (C), or None for the
    hardware's own.  Applies from the host's next report."""
    _require_role(current_user)
    host = _host_or_404(db, host_id)
    if not temperature_limit.valid_limit(body.limit_c):
        # The range is written out, not interpolated: the translator has
        # mangled named placeholders before.  Keep it equal to LIMIT_RANGE_C.
        raise HTTPException(
            status_code=422,
            detail=_("The temperature limit must be between 30 and 125 C"),
        )
    previous = host.hardware_temp_warning_c
    host.hardware_temp_warning_c = body.limit_c
    AuditService.log(
        db=db,
        user_id=current_user.id,
        username=current_user.userid,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.HOST,
        entity_id=str(host.id),
        entity_name=host.fqdn,
        description=(
            f"Temperature warning limit set to {body.limit_c} C"
            if body.limit_c is not None
            else "Temperature warning limit cleared (device limits apply)"
        ),
        details={"previous_c": previous, "limit_c": body.limit_c},
    )
    db.commit()
    return {"temperature_limit_c": host.hardware_temp_warning_c}


@router.get("/hardware-health/smartmontools")
async def smartmontools_status(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    hosts = smartmontools_install.recommended_hosts(db)
    installs = smartmontools_install.installs_by_host(db, [h.id for h in hosts])
    return {
        "licensed": smartmontools_install.licensed(),
        "auto": smartmontools_install.auto_enabled(get_active_tenant()),
        "hosts": [
            {
                "host_id": str(h.id),
                "fqdn": h.fqdn,
                "platform": h.platform,
                "install": installs.get(str(h.id)),
            }
            for h in hosts
        ],
    }


def _require_install_roles(current_user) -> None:
    _require_role(current_user)
    if not current_user.has_role(SecurityRoles.ADD_PACKAGE):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required")
            % SecurityRoles.ADD_PACKAGE.value,
        )


@router.post("/hardware-health/smartmontools/install")
async def install_smartmontools(
    body: InstallRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Only hosts it is recommended for: the rest are skipped, not errors."""
    _require_install_roles(current_user)
    wanted = set(body.host_ids)
    hosts = [
        h for h in smartmontools_install.recommended_hosts(db) if str(h.id) in wanted
    ]
    for host in hosts:
        smartmontools_install.queue_install(db, host, current_user.userid)
        AuditService.log(
            db=db,
            user_id=current_user.id,
            username=current_user.userid,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.HOST,
            entity_id=str(host.id),
            entity_name=host.fqdn,
            description=f"{smartmontools_install.PACKAGE} install queued",
            details={"package": smartmontools_install.PACKAGE},
        )
    db.commit()
    return {"queued": len(hosts), "skipped": len(wanted) - len(hosts)}


@router.put("/hardware-health/smartmontools")
async def set_smartmontools_auto(
    body: AutoInstall,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """An administrator's consent; Enterprise."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=403, detail=_("Permission denied: administrator required")
        )
    _require_install_roles(current_user)
    if body.auto and not smartmontools_install.licensed():
        raise HTTPException(
            status_code=402,
            detail=_("Automatic installation requires a SysManage Enterprise license."),
        )
    tenant_id = get_active_tenant()
    if not smartmontools_install.set_auto(tenant_id, body.auto):
        raise HTTPException(status_code=500, detail=_("The setting could not be saved"))
    AuditService.log(
        db=db,
        user_id=current_user.id,
        username=current_user.userid,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_id=smartmontools_install.SETTING_AUTO,
        entity_name=smartmontools_install.SETTING_AUTO,
        description=(
            f"Automatic {smartmontools_install.PACKAGE} install "
            + ("enabled" if body.auto else "disabled")
        ),
        details={"auto": body.auto, "tenant_id": tenant_id},
    )
    db.commit()
    return {"auto": body.auto}
