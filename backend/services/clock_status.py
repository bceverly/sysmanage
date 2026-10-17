# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Clock offset bounds and each host's clock status (Phase 23.3 S3).

BOUNDS
------
A warning and a critical offset, in ms of absolute offset.  Resolved per host,
most specific first:

    tag  >  site  >  tenant  >  server-wide  >  built-in (1 s / 5 s)

The server-wide pair is a server setting (``time_sync_bounds``, DB Settings);
the tenant, site and tag overrides are ``clock_bound`` rows in the tenant's
database.  A host carrying several tags with bounds gets the TIGHTEST of them:
a domain controller that is also tagged "lab" is still a domain controller.

STATUS
------
``ok`` / ``warning`` / ``critical`` from the measured offset against the
host's bounds, and four that never pass for "in sync":

* ``unmeasured`` -- no measurement yet (an older agent, or never connected);
* ``stale`` -- the last measurement is older than ``STALE_AFTER`` (the host is
  not connected, so its clock is no longer being watched);
* ``uncertain`` -- the last measurement's uncertainty (half the exchange's
  round trip) reaches the warning bound, so it cannot say whether the clock
  is in bounds.  2026-10-17: a busy agent answered late, the round trip was
  8.06 s and the "offset" +4.03 s -- exactly half -- while the host's own time
  service was synchronized to the millisecond.  Such a figure is not judged:
  no warning, no alert, no resync.  ``evaluate`` falls back to the newest
  CERTAIN history sample still inside ``STALE_AFTER`` when there is one;
* ``server_clock_off`` -- the SERVER's own clock is measured off its reference
  by more than ``server_clock.TRUST_MS``.  Every host offset is relative to
  the server, so judging hosts against a clock known to be wrong would report
  the server's error as theirs: the status is withheld instead.

A server whose reference is unreachable, or that has none configured, still
judges -- relative to itself, which is what Kerberos and token expiry compare
against -- and says so (``server.verified`` is false beside every status).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.config import settings_service
from backend.persistence import models
from backend.services import server_clock

logger = logging.getLogger(__name__)

SETTING_KEY = "time_sync_bounds"
DEFAULT_WARNING_MS = 1000.0
DEFAULT_CRITICAL_MS = 5000.0
# Bounds an operator may set: 1 ms (finer than any measurement here is
# meaningless) to a day (beyond it the message timestamp check refuses first).
MIN_BOUND_MS = 1.0
MAX_BOUND_MS = 86_400_000.0
STALE_AFTER = timedelta(minutes=30)

SCOPE_TENANT = "tenant"
SCOPE_SITE = "site"
SCOPE_TAG = "tag"
SCOPES = (SCOPE_TENANT, SCOPE_SITE, SCOPE_TAG)

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_CRITICAL = "critical"
STATUS_UNMEASURED = "unmeasured"
STATUS_STALE = "stale"
STATUS_SERVER_OFF = "server_clock_off"
STATUS_UNCERTAIN = "uncertain"
# Worst first: the order the fleet view sorts by.
STATUS_ORDER = (
    STATUS_CRITICAL,
    STATUS_WARNING,
    STATUS_SERVER_OFF,
    STATUS_STALE,
    STATUS_UNCERTAIN,
    STATUS_UNMEASURED,
    STATUS_OK,
)
# The exchange method's error bound is half its round trip; the coarse
# timestamp method has none (it exists for clocks minutes to hours off).
METHOD_EXCHANGE = "exchange"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def valid_bounds(warning_ms: Any, critical_ms: Any) -> Optional[str]:
    """None when the pair is usable, else a reason code."""
    for value in (warning_ms, critical_ms):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "not_a_number"
        if not MIN_BOUND_MS <= value <= MAX_BOUND_MS:
            return "out_of_range"
    if warning_ms >= critical_ms:
        return "warning_not_below_critical"
    return None


def _pair(warning_ms, critical_ms, source: str, ref: str = "") -> Dict[str, Any]:
    return {
        "warning_ms": float(warning_ms),
        "critical_ms": float(critical_ms),
        "source": source,
        "ref": ref,
    }


def server_bounds() -> Dict[str, Any]:
    """The server-wide pair, or the built-in one when none (or a bad one) is
    stored.  A bad stored pair is logged, never used."""
    stored = settings_service.get_setting(SETTING_KEY, default=None)
    if isinstance(stored, dict):
        warning, critical = stored.get("warning_ms"), stored.get("critical_ms")
        if valid_bounds(warning, critical) is None:
            return _pair(warning, critical, "server")
        logger.warning(
            "Ignoring the stored server clock bounds %r: %s",
            stored,
            valid_bounds(warning, critical),
        )
    return _pair(DEFAULT_WARNING_MS, DEFAULT_CRITICAL_MS, "default")


def set_server_bounds(warning_ms: float, critical_ms: float) -> bool:
    return settings_service.set_setting(
        SETTING_KEY, {"warning_ms": warning_ms, "critical_ms": critical_ms}
    )


class Resolver:
    """Bounds for many hosts from ONE read of the overrides."""

    def __init__(self, db):
        self.base = server_bounds()
        self.tenant: Optional[Dict[str, Any]] = None
        self.sites: Dict[str, Dict[str, Any]] = {}
        self.tags: Dict[str, Dict[str, Any]] = {}
        for row in db.query(models.ClockBound).all():
            pair = _pair(row.warning_ms, row.critical_ms, row.scope_kind, row.scope_ref)
            if row.scope_kind == SCOPE_TENANT:
                self.tenant = pair
            elif row.scope_kind == SCOPE_SITE:
                self.sites[row.scope_ref] = pair
            elif row.scope_kind == SCOPE_TAG:
                self.tags[row.scope_ref] = pair
        self.host_tags: Dict[str, List[str]] = {}
        if self.tags:
            for host_id, tag_id in db.query(
                models.HostTag.host_id, models.HostTag.tag_id
            ).filter(models.HostTag.tag_id.in_(list(self.tags))):
                self.host_tags.setdefault(str(host_id), []).append(str(tag_id))

    def bounds_for(self, host) -> Dict[str, Any]:
        tagged = [self.tags[t] for t in self.host_tags.get(str(host.id), ())]
        if tagged:
            # The tightest: a host is held to its strictest role.
            return min(tagged, key=lambda p: (p["critical_ms"], p["warning_ms"]))
        site = self.sites.get(str(host.site_id)) if host.site_id else None
        return site or self.tenant or self.base


def uncertainty_ms(method: Optional[str], rtt_ms: Optional[float]) -> Optional[float]:
    """How far the true offset may be from a measured one: half the round
    trip for an exchange (the delay may have been all on one leg), None when
    the method gives no bound."""
    if method == METHOD_EXCHANGE and isinstance(rtt_ms, (int, float)):
        return max(0.0, float(rtt_ms)) / 2
    return None


def too_uncertain(method, rtt_ms, bounds: Dict[str, Any]) -> bool:
    """True when the measurement cannot tell in-bounds from out of bounds."""
    error = uncertainty_ms(method, rtt_ms)
    return error is not None and error >= bounds["warning_ms"]


def _judge(offset_ms: float, bounds: Dict[str, Any]) -> str:
    offset = abs(offset_ms)
    if offset >= bounds["critical_ms"]:
        return STATUS_CRITICAL
    if offset >= bounds["warning_ms"]:
        return STATUS_WARNING
    return STATUS_OK


def host_status(
    host, bounds: Dict[str, Any], server: Dict[str, Any], now: datetime
) -> str:
    if server.get("reason") == "server_off":
        return STATUS_SERVER_OFF
    if host.clock_offset_ms is None or host.clock_measured_at is None:
        return STATUS_UNMEASURED
    if now - host.clock_measured_at > STALE_AFTER:
        return STATUS_STALE
    if too_uncertain(
        getattr(host, "clock_method", None), getattr(host, "clock_rtt_ms", None), bounds
    ):
        return STATUS_UNCERTAIN
    return _judge(host.clock_offset_ms, bounds)


def last_certain_sample(db, host, bounds: Dict[str, Any], now: datetime):
    """The newest history sample for ``host`` that is both inside
    ``STALE_AFTER`` and certain enough to judge, or None."""
    rows = (
        db.query(models.HostClockSample)
        .filter(
            models.HostClockSample.host_id == host.id,
            models.HostClockSample.measured_at >= now - STALE_AFTER,
        )
        .order_by(models.HostClockSample.measured_at.desc())
        .limit(20)
        .all()
    )
    for row in rows:
        if row.offset_ms is not None and not too_uncertain(
            row.method, row.rtt_ms, bounds
        ):
            return row
    return None


def measurement_note(db, host, bounds: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """What the card says about the latest measurement's quality."""
    method = getattr(host, "clock_method", None)
    rtt_ms = getattr(host, "clock_rtt_ms", None)
    error = uncertainty_ms(method, rtt_ms)
    uncertain = too_uncertain(method, rtt_ms, bounds)
    fallback = last_certain_sample(db, host, bounds, now) if uncertain else None
    reported = getattr(host, "time_reported_offset_ms", None)
    vouches = bool(
        service_ok(host)
        and isinstance(reported, (int, float))
        and abs(reported) < bounds["warning_ms"]
    )
    return {
        "uncertain": uncertain,
        "uncertainty_ms": error,
        "judged_from": (
            None
            if fallback is None
            else {
                "at": fallback.measured_at.isoformat(),
                "offset_ms": fallback.offset_ms,
                "rtt_ms": fallback.rtt_ms,
            }
        ),
        # The host's own time service says it is synchronized and close:
        # trusted over an exchange too slow to measure anything.
        "time_service_vouches": vouches,
    }


def service_ok(host) -> Optional[bool]:
    """Whether the host's own time service is running and synchronized:
    None when it has not said (never read as yes)."""
    if host.time_status_at is None:
        return None
    if host.time_service_running is False or host.time_synchronized is False:
        return False
    if host.time_service_running and host.time_synchronized:
        return True
    return None


def evaluate(
    db, hosts: Iterable, now: Optional[datetime] = None
) -> Tuple[Dict[str, Any], List[Tuple[Any, Dict[str, Any], str]]]:
    """``(server status, [(host, bounds, status), ...])`` for ``hosts``."""
    now = now or _now()
    server = server_clock.status()
    resolver = Resolver(db)
    rows = []
    for host in hosts:
        bounds = resolver.bounds_for(host)
        status = host_status(host, bounds, server, now)
        if status == STATUS_UNCERTAIN:
            fallback = last_certain_sample(db, host, bounds, now)
            if fallback is not None:
                status = _judge(fallback.offset_ms, bounds)
        rows.append((host, bounds, status))
    return server, rows


def coverage_state(status: str) -> str:
    """The posture coverage state (21.4) for a clock status."""
    if status == STATUS_OK:
        return "ok"
    if status in (STATUS_WARNING, STATUS_CRITICAL):
        return "failing"
    return "unknown"


def overrides(db) -> List[Dict[str, Any]]:
    return [
        {
            "scope_kind": row.scope_kind,
            "scope_ref": row.scope_ref,
            "warning_ms": row.warning_ms,
            "critical_ms": row.critical_ms,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": row.updated_by,
        }
        for row in db.query(models.ClockBound).order_by(
            models.ClockBound.scope_kind, models.ClockBound.scope_ref
        )
    ]


def set_override(db, scope_kind, scope_ref, warning_ms, critical_ms, user) -> None:
    row = (
        db.query(models.ClockBound)
        .filter(
            models.ClockBound.scope_kind == scope_kind,
            models.ClockBound.scope_ref == scope_ref,
        )
        .first()
    )
    if row is None:
        row = models.ClockBound(scope_kind=scope_kind, scope_ref=scope_ref)
        db.add(row)
    row.warning_ms, row.critical_ms = float(warning_ms), float(critical_ms)
    row.updated_at, row.updated_by = _now(), user
    db.commit()


def clear_override(db, scope_kind, scope_ref) -> bool:
    deleted = (
        db.query(models.ClockBound)
        .filter(
            models.ClockBound.scope_kind == scope_kind,
            models.ClockBound.scope_ref == scope_ref,
        )
        .delete()
    )
    db.commit()
    return bool(deleted)


def clock_verdict(host, bounds: Dict[str, Any], server: Dict[str, Any], now: datetime):
    """``"ok"`` / ``"warning"`` / ``"critical"``, or None when the clock
    cannot be judged (unmeasured, stale, or the server's own clock is off).
    For alerting (S6): nothing is raised -- or cleared -- on a measurement
    that was withheld."""
    status = host_status(host, bounds, server, now)
    return status if status in (STATUS_OK, STATUS_WARNING, STATUS_CRITICAL) else None


def site_names(site_ids) -> Dict[str, str]:
    """Site names live with the coordinator (bootstrap database); best
    effort -- an unnamed site is still grouped by its id."""
    if not site_ids:
        return {}
    # pylint: disable=import-outside-toplevel
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from backend.persistence import db as dbm  # noqa: PLC0415

    try:
        with sessionmaker(bind=dbm.get_engine())() as main:
            return {
                str(site_id): name
                for site_id, name in main.query(
                    models.FederationSite.id, models.FederationSite.name
                ).filter(models.FederationSite.id.in_(list(site_ids)))
            }
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Clock status: could not read site names")
        return {}
