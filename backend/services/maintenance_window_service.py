# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Maintenance-window evaluation + dispatch gating (Phase 14.2).

The heart of the feature: decide whether a change (an outbound ``command`` /
``update_request``) may reach a given host *right now*, given the operator's
maintenance and blackout windows — and compute the next window a host detail page
can surface.

Policy (deliberate, and safe-by-default):

* An **active emergency override** for the host beats everything → allowed.
* A host with **no allow-window applying to it** is unrestricted (windows are
  opt-in per host; enabling the feature must never silently freeze the fleet).
* A host **with** allow-windows may receive changes only *inside* one of them.
* A **blackout** window that currently contains "now" blocks the host even if an
  allow-window is also open (blackout wins).

Recurrence is evaluated in each window's IANA timezone via ``zoneinfo`` (stdlib) —
no cron dependency: ``once`` (absolute UTC bounds), ``daily`` and ``weekly``
(local start time + duration, weekly also gated on weekday).
"""

import logging
from datetime import datetime, time, timedelta, timezone
from typing import List, Optional

try:  # stdlib on 3.9+; the server runs 3.14
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - defensive
    ZoneInfo = None  # type: ignore[misc, assignment]

from sqlalchemy.orm import Session

from backend.persistence.models import (
    Host,
    MaintenanceOverride,
    MaintenanceWindow,
    MaintenanceWindowScope,
)
from backend.persistence.models.maintenance_windows import (
    RECURRENCE_ONCE,
    SCOPE_ALL,
    SCOPE_HOST,
    SCOPE_TAG,
    WEEKDAYS,
    WINDOW_KIND_BLACKOUT,
)

logger = logging.getLogger(__name__)

# Message types that represent an actual change action and are therefore gated.
# Control-plane pushes (config/logging updates) flow freely.
GATED_MESSAGE_TYPES = ("command", "update_request")

# How far ahead to look when computing a host's "next window open" (days).
_NEXT_LOOKAHEAD_DAYS = 8


def _tzinfo(name: Optional[str]):
    """Resolve an IANA tz name to a tzinfo, falling back to UTC (logged loudly)."""
    if not name or ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Maintenance window has an invalid timezone %r; treating as UTC", name
        )
        return timezone.utc


def _parse_hhmm(value: Optional[str]):
    """Parse ``"HH:MM"`` → ``time`` (or None on bad/empty input)."""
    if not value:
        return None
    try:
        hour_s, minute_s = value.split(":", 1)
        return time(int(hour_s), int(minute_s))
    except (ValueError, TypeError):
        return None


def _as_utc_naive(dt_aware: datetime) -> datetime:
    """Convert a tz-aware datetime to naive-UTC (the schema's storage form)."""
    return dt_aware.astimezone(timezone.utc).replace(tzinfo=None)


def _recurring_occurrence(window: MaintenanceWindow, day_date, tzinfo):
    """Return the ``(start_utc, end_utc)`` of ``window``'s occurrence *starting* on
    ``day_date`` (local), or None if it doesn't occur that day (weekly weekday
    mismatch, or malformed time/duration)."""
    start_t = _parse_hhmm(window.start_time)
    duration = window.duration_minutes
    if start_t is None or not duration or duration <= 0:
        return None
    if window.recurrence != RECURRENCE_ONCE and window.days_of_week:
        # Weekly: the occurrence's START weekday must be selected.
        allowed = {d for d in window.days_of_week.split(",") if d}
        if WEEKDAYS[day_date.weekday()] not in allowed:
            return None
    start_local = datetime.combine(day_date, start_t, tzinfo=tzinfo)
    end_local = start_local + timedelta(minutes=duration)
    return _as_utc_naive(start_local), _as_utc_naive(end_local)


def window_contains(window: MaintenanceWindow, now_utc: datetime) -> bool:
    """Is ``now_utc`` (naive UTC) inside this window's active period?"""
    if window.recurrence == RECURRENCE_ONCE:
        if not window.starts_at or not window.ends_at:
            return False
        return window.starts_at <= now_utc < window.ends_at

    tzinfo = _tzinfo(window.timezone)
    now_local = now_utc.replace(tzinfo=timezone.utc).astimezone(tzinfo)
    # Check today's and yesterday's occurrence so a window that opened before
    # local midnight and runs into the next day is still matched.
    for day_offset in (0, -1):
        occ = _recurring_occurrence(
            window, (now_local + timedelta(days=day_offset)).date(), tzinfo
        )
        if occ and occ[0] <= now_utc < occ[1]:
            return True
    return False


def _next_start(window: MaintenanceWindow, now_utc: datetime) -> Optional[datetime]:
    """The soonest UTC start of ``window`` whose end is still in the future
    (i.e. currently-open windows report their current start).  None if none
    upcoming within the lookahead."""
    if window.recurrence == RECURRENCE_ONCE:
        if window.ends_at and window.ends_at > now_utc:
            return window.starts_at
        return None

    tzinfo = _tzinfo(window.timezone)
    now_local = now_utc.replace(tzinfo=timezone.utc).astimezone(tzinfo)
    best: Optional[datetime] = None
    for day_offset in range(-1, _NEXT_LOOKAHEAD_DAYS):
        occ = _recurring_occurrence(
            window, (now_local + timedelta(days=day_offset)).date(), tzinfo
        )
        if not occ:
            continue
        start_utc, end_utc = occ
        if end_utc > now_utc and (best is None or start_utc < best):
            best = start_utc
    return best


def _scope_matches(scope: MaintenanceWindowScope, host_id, host_tag_ids: set) -> bool:
    """Does a single scope row apply to this host?"""
    if scope.scope_type == SCOPE_ALL:
        return True
    if scope.scope_type == SCOPE_HOST:
        return scope.host_id is not None and str(scope.host_id) == str(host_id)
    if scope.scope_type == SCOPE_TAG:
        return scope.tag_id is not None and str(scope.tag_id) in host_tag_ids
    return False


def _windows_for_host(db: Session, host_id, host_tag_ids: set) -> List[dict]:
    """Enabled windows applying to this host, each as ``{"window", "scopes"}``."""
    windows = (
        db.query(MaintenanceWindow).filter(MaintenanceWindow.enabled.is_(True)).all()
    )
    if not windows:
        return []
    window_ids = [w.id for w in windows]
    scopes = (
        db.query(MaintenanceWindowScope)
        .filter(MaintenanceWindowScope.window_id.in_(window_ids))
        .all()
    )
    scopes_by_window: dict = {}
    for scope in scopes:
        scopes_by_window.setdefault(str(scope.window_id), []).append(scope)

    matching = []
    for window in windows:
        wscopes = scopes_by_window.get(str(window.id), [])
        if any(_scope_matches(s, host_id, host_tag_ids) for s in wscopes):
            matching.append({"window": window, "scopes": wscopes})
    return matching


def _host_tag_ids(db: Session, host_id) -> set:
    """The set of tag-id strings carried by a host (empty on any error)."""
    host = db.query(Host).filter(Host.id == host_id).first()
    if host is None:
        return set()
    try:
        return {str(tag.id) for tag in host.tags}
    except Exception:  # pylint: disable=broad-exception-caught
        # host.tags is a dynamic relationship; be defensive so a tag-load
        # hiccup never blocks dispatch.
        return set()


def active_override(db: Session, host_id, now_utc: datetime):
    """The active (non-expired) emergency override for a host, or None."""
    return (
        db.query(MaintenanceOverride)
        .filter(
            MaintenanceOverride.host_id == host_id,
            MaintenanceOverride.expires_at > now_utc,
        )
        .order_by(MaintenanceOverride.expires_at.desc())
        .first()
    )


def is_dispatch_allowed(db: Session, host_id, now_utc: datetime) -> bool:
    """May a gated change reach ``host_id`` right now?  See module docstring for
    the policy.  Fails **open** (returns True) on any internal error — a broken
    evaluator must never freeze fleet management — and logs loudly."""
    try:
        if active_override(db, host_id, now_utc) is not None:
            return True

        host_tag_ids = _host_tag_ids(db, host_id)
        matching = _windows_for_host(db, host_id, host_tag_ids)
        if not matching:
            return True  # opt-in: no windows apply → unrestricted

        allow_windows = [
            m for m in matching if m["window"].kind != WINDOW_KIND_BLACKOUT
        ]
        blackout_windows = [
            m for m in matching if m["window"].kind == WINDOW_KIND_BLACKOUT
        ]

        # Blackout always wins.
        for m in blackout_windows:
            if window_contains(m["window"], now_utc):
                return False

        if not allow_windows:
            return True  # only blackouts apply (and none active) → unrestricted

        return any(window_contains(m["window"], now_utc) for m in allow_windows)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception(
            "Maintenance-window evaluation failed for host %s; "
            "failing OPEN (allowing dispatch) to avoid freezing the fleet",
            host_id,
        )
        return True


def _soonest_allow(
    allow: list, now_utc: datetime
) -> tuple[Optional[datetime], Optional[MaintenanceWindow]]:
    """Return (next_start, next_window) for the soonest upcoming/open allow window."""
    next_start: Optional[datetime] = None
    next_window: Optional[MaintenanceWindow] = None
    for m in allow:
        start = _next_start(m["window"], now_utc)
        if start is not None and (next_start is None or start < next_start):
            next_start = start
            next_window = m["window"]
    return next_start, next_window


def _gating_state(override, has_allow: bool, active_blackout, in_allow: bool) -> str:
    """Resolve the host's gating state from its window evaluation."""
    if override is not None:
        return "override"
    if not has_allow and active_blackout is None:
        return "unrestricted"
    if active_blackout is not None:
        return "blocked"
    if in_allow:
        return "in_window"
    return "blocked"


def next_window_for_host(db: Session, host_id, now_utc: datetime) -> dict:
    """Describe a host's current gating state + its next allow-window, for the
    HostDetail surface.  ``state`` is one of ``unrestricted`` | ``in_window`` |
    ``blocked`` | ``override``."""
    override = active_override(db, host_id, now_utc)
    host_tag_ids = _host_tag_ids(db, host_id)
    matching = _windows_for_host(db, host_id, host_tag_ids)
    allow = [m for m in matching if m["window"].kind != WINDOW_KIND_BLACKOUT]
    blackout = [m for m in matching if m["window"].kind == WINDOW_KIND_BLACKOUT]

    active_blackout = next(
        (m["window"] for m in blackout if window_contains(m["window"], now_utc)),
        None,
    )
    next_start, next_window = _soonest_allow(allow, now_utc)
    in_allow = any(window_contains(m["window"], now_utc) for m in allow)
    state = _gating_state(override, bool(allow), active_blackout, in_allow)

    # Build the next-window summary as an independent statement rather than a
    # nested conditional inside the returned literal.
    next_window_summary = None
    if next_window is not None:
        next_window_summary = {
            "id": str(next_window.id),
            "name": next_window.name,
            "starts_at": next_start.isoformat() if next_start else None,
        }

    return {
        "state": state,
        "override": override.to_dict() if override else None,
        "active_blackout": active_blackout.name if active_blackout else None,
        "next_window": next_window_summary,
    }
