"""
Maintenance-windows API (Phase 14.2).

Admin CRUD for operator-defined change windows (allow + blackout), a time-boxed
emergency override (audited), and a per-host status endpoint the HostDetail page
uses to surface the next window.  Windows are per-tenant operational data, so the
session is routed to the active tenant's database (server scope = main engine).
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import db as db_module
from backend.persistence.models import (
    MaintenanceOverride,
    MaintenanceWindow,
    MaintenanceWindowScope,
)
from backend.persistence.models.maintenance_windows import (
    RECURRENCE_ONCE,
    RECURRENCES,
    SCOPE_HOST,
    SCOPE_TAG,
    SCOPE_TYPES,
    WEEKDAYS,
    WINDOW_KINDS,
)
from backend.services import maintenance_window_service as mw
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

router = APIRouter()


def _sessionmaker():
    """A sessionmaker bound to the active tenant's engine (main engine at server
    scope) — maintenance windows are tenant-partition data."""
    from backend.persistence.partitions import get_request_engine  # noqa: PLC0415
    from backend.persistence.tenant_context import get_active_tenant  # noqa: PLC0415

    tenant_id = get_active_tenant()
    bind = (
        db_module.get_engine() if tenant_id is None else get_request_engine(tenant_id)
    )
    return sessionmaker(autocommit=False, autoflush=False, bind=bind)


def _require_admin(current_user) -> None:
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: administrator required"),
        )


class ScopeIn(BaseModel):
    """One scope target for a window."""

    scope_type: str  # all | host | tag
    host_id: Optional[str] = None
    tag_id: Optional[str] = None


class MaintenanceWindowIn(BaseModel):
    """Create/update payload for a maintenance window."""

    name: str
    description: Optional[str] = None
    enabled: bool = True
    kind: str = "allow"  # allow | blackout
    recurrence: str = "daily"  # once | daily | weekly
    timezone: str = "UTC"
    start_time: Optional[str] = None  # "HH:MM" (daily/weekly)
    duration_minutes: Optional[int] = None  # (daily/weekly)
    days_of_week: Optional[List[str]] = None  # (weekly)
    starts_at: Optional[datetime] = None  # (once)
    ends_at: Optional[datetime] = None  # (once)
    scopes: List[ScopeIn] = []


class OverrideIn(BaseModel):
    """Emergency-override payload."""

    host_id: str
    reason: str
    duration_minutes: int = 120


def _to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Normalize an (optionally tz-aware) datetime to naive UTC for storage."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _validate_meta(payload: MaintenanceWindowIn) -> None:
    """Validate the always-present fields (name, kind, recurrence, timezone)."""
    if not (payload.name or "").strip():
        raise HTTPException(status_code=400, detail=_("A window name is required."))
    if payload.kind not in WINDOW_KINDS:
        raise HTTPException(
            status_code=400, detail=_("kind must be 'allow' or 'blackout'.")
        )
    if payload.recurrence not in RECURRENCES:
        raise HTTPException(
            status_code=400,
            detail=_("recurrence must be 'once', 'daily', or 'weekly'."),
        )
    # Timezone must be resolvable (defence for the recurrence evaluator).
    if mw.ZoneInfo is not None:
        try:
            mw.ZoneInfo(payload.timezone)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            raise HTTPException(
                status_code=400,
                detail=_("Unknown timezone: %s") % payload.timezone,
            ) from exc


def _validate_schedule(payload: MaintenanceWindowIn) -> None:
    """Validate the schedule fields for the payload's recurrence mode."""
    if payload.recurrence == RECURRENCE_ONCE:
        start = _to_naive_utc(payload.starts_at)
        end = _to_naive_utc(payload.ends_at)
        if start is None or end is None or end <= start:
            raise HTTPException(
                status_code=400,
                detail=_("A one-time window needs starts_at before ends_at."),
            )
        return

    if mw._parse_hhmm(payload.start_time) is None:  # pylint: disable=protected-access
        raise HTTPException(
            status_code=400,
            detail=_("A recurring window needs a start_time as 'HH:MM'."),
        )
    if not payload.duration_minutes or payload.duration_minutes <= 0:
        raise HTTPException(
            status_code=400,
            detail=_("A recurring window needs a positive duration_minutes."),
        )
    if payload.recurrence == "weekly":
        days = payload.days_of_week or []
        if not days or any(d not in WEEKDAYS for d in days):
            raise HTTPException(
                status_code=400,
                detail=_("A weekly window needs valid days_of_week."),
            )


def _validate_scope(scope) -> None:
    """Validate a single scope entry."""
    if scope.scope_type not in SCOPE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=_("scope_type must be 'all', 'host', or 'tag'."),
        )
    if scope.scope_type == SCOPE_HOST and not scope.host_id:
        raise HTTPException(status_code=400, detail=_("A host scope needs a host_id."))
    if scope.scope_type == SCOPE_TAG and not scope.tag_id:
        raise HTTPException(status_code=400, detail=_("A tag scope needs a tag_id."))


def _validate_window(payload: MaintenanceWindowIn) -> None:
    """Reject a malformed window before it touches the DB (HTTP 400)."""
    _validate_meta(payload)
    _validate_schedule(payload)
    if not payload.scopes:
        raise HTTPException(
            status_code=400,
            detail=_("A window needs at least one scope (all, host, or tag)."),
        )
    for scope in payload.scopes:
        _validate_scope(scope)


def _apply_payload(window: MaintenanceWindow, payload: MaintenanceWindowIn) -> None:
    """Copy validated payload fields onto a window row (scopes handled separately)."""
    window.name = payload.name.strip()
    window.description = payload.description or None
    window.enabled = bool(payload.enabled)
    window.kind = payload.kind
    window.recurrence = payload.recurrence
    window.timezone = payload.timezone or "UTC"
    if payload.recurrence == RECURRENCE_ONCE:
        window.start_time = None
        window.duration_minutes = None
        window.days_of_week = None
        window.starts_at = _to_naive_utc(payload.starts_at)
        window.ends_at = _to_naive_utc(payload.ends_at)
    else:
        window.start_time = payload.start_time
        window.duration_minutes = payload.duration_minutes
        window.days_of_week = (
            ",".join(payload.days_of_week)
            if payload.recurrence == "weekly" and payload.days_of_week
            else None
        )
        window.starts_at = None
        window.ends_at = None


def _write_scopes(session: Session, window_id, payload: MaintenanceWindowIn) -> None:
    """Replace a window's scope rows with the payload's set (caller commits)."""
    session.query(MaintenanceWindowScope).filter(
        MaintenanceWindowScope.window_id == window_id
    ).delete()
    for scope in payload.scopes:
        session.add(
            MaintenanceWindowScope(
                window_id=window_id,
                scope_type=scope.scope_type,
                host_id=(
                    uuid.UUID(scope.host_id)
                    if scope.scope_type == SCOPE_HOST and scope.host_id
                    else None
                ),
                tag_id=(
                    uuid.UUID(scope.tag_id)
                    if scope.scope_type == SCOPE_TAG and scope.tag_id
                    else None
                ),
            )
        )


def _serialize(session: Session, windows: List[MaintenanceWindow]) -> List[dict]:
    """Serialize windows with their scopes in one scope query."""
    if not windows:
        return []
    scopes = (
        session.query(MaintenanceWindowScope)
        .filter(MaintenanceWindowScope.window_id.in_([w.id for w in windows]))
        .all()
    )
    by_window: dict = {}
    for scope in scopes:
        by_window.setdefault(str(scope.window_id), []).append(scope)
    return [w.to_dict(scopes=by_window.get(str(w.id), [])) for w in windows]


@router.get("/maintenance-windows", dependencies=[Depends(JWTBearer())])
async def list_maintenance_windows(
    current_user=Depends(require_authenticated_user),
):
    """List all maintenance windows (with their scopes)."""
    _require_admin(current_user)
    with _sessionmaker()() as session:
        windows = (
            session.query(MaintenanceWindow)
            .order_by(MaintenanceWindow.name.asc())
            .all()
        )
        return {"windows": _serialize(session, windows)}


@router.post("/maintenance-windows", dependencies=[Depends(JWTBearer())])
async def create_maintenance_window(
    payload: MaintenanceWindowIn,
    current_user=Depends(require_authenticated_user),
):
    """Create a maintenance window."""
    _require_admin(current_user)
    _validate_window(payload)
    with _sessionmaker()() as session:
        window = MaintenanceWindow(created_by=getattr(current_user, "id", None))
        _apply_payload(window, payload)
        session.add(window)
        session.flush()  # assign window.id
        _write_scopes(session, window.id, payload)
        session.commit()
        return _serialize(session, [window])[0]


@router.put("/maintenance-windows/{window_id}", dependencies=[Depends(JWTBearer())])
async def update_maintenance_window(
    window_id: str,
    payload: MaintenanceWindowIn,
    current_user=Depends(require_authenticated_user),
):
    """Update a maintenance window (replaces its scope set)."""
    _require_admin(current_user)
    _validate_window(payload)
    with _sessionmaker()() as session:
        window = (
            session.query(MaintenanceWindow)
            .filter(MaintenanceWindow.id == window_id)
            .first()
        )
        if window is None:
            raise HTTPException(
                status_code=404, detail=_("Maintenance window not found.")
            )
        _apply_payload(window, payload)
        _write_scopes(session, window.id, payload)
        session.commit()
        return _serialize(session, [window])[0]


@router.delete("/maintenance-windows/{window_id}", dependencies=[Depends(JWTBearer())])
async def delete_maintenance_window(
    window_id: str,
    current_user=Depends(require_authenticated_user),
):
    """Delete a maintenance window and its scopes."""
    _require_admin(current_user)
    with _sessionmaker()() as session:
        window = (
            session.query(MaintenanceWindow)
            .filter(MaintenanceWindow.id == window_id)
            .first()
        )
        if window is None:
            raise HTTPException(
                status_code=404, detail=_("Maintenance window not found.")
            )
        session.query(MaintenanceWindowScope).filter(
            MaintenanceWindowScope.window_id == window.id
        ).delete()
        session.delete(window)
        session.commit()
        return {"status": "deleted", "id": window_id}


@router.post("/maintenance-windows/overrides", dependencies=[Depends(JWTBearer())])
async def create_override(
    payload: OverrideIn,
    current_user=Depends(require_authenticated_user),
):
    """Create a time-boxed emergency override for a host (audited)."""
    _require_admin(current_user)
    if not (payload.reason or "").strip():
        raise HTTPException(
            status_code=400, detail=_("An override reason is required.")
        )
    if payload.duration_minutes <= 0:
        raise HTTPException(
            status_code=400, detail=_("Override duration must be positive.")
        )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now + timedelta(minutes=payload.duration_minutes)
    with _sessionmaker()() as session:
        override = MaintenanceOverride(
            host_id=uuid.UUID(payload.host_id),
            reason=payload.reason.strip(),
            created_by=getattr(current_user, "id", None),
            username=getattr(current_user, "userid", None),
            created_at=now,
            expires_at=expires_at,
        )
        session.add(override)
        # Audit the override: it deliberately bypasses change control.
        AuditService.log(
            db=session,
            action_type=ActionType.EXECUTE,
            entity_type=EntityType.MAINTENANCE_WINDOW,
            description=(
                f"Emergency maintenance override for host {payload.host_id} "
                f"({payload.duration_minutes} min)"
            ),
            result=Result.SUCCESS,
            user_id=getattr(current_user, "id", None),
            username=getattr(current_user, "userid", None),
            entity_id=payload.host_id,
            details={
                "reason": payload.reason.strip(),
                "expires_at": expires_at.isoformat(),
                "duration_minutes": payload.duration_minutes,
            },
        )
        session.commit()
        return override.to_dict()


@router.get(
    "/maintenance-windows/host/{host_id}/status",
    dependencies=[Depends(JWTBearer())],
)
async def host_window_status(
    host_id: str,
    current_user=Depends(require_authenticated_user),
):
    """Current gating state + next window for a host (HostDetail surface)."""
    _require_admin(current_user)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with _sessionmaker()() as session:
        return mw.next_window_for_host(session, uuid.UUID(host_id), now)
