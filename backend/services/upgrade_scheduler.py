"""
Upgrade-profile scheduling service (Phase 8.2).

OSS-tier scheduler:  a self-contained next-run computer for the most
common cron patterns plus a tick function the operator can invoke
manually or wire to an external trigger (systemd timer, external cron,
or a future APScheduler-backed runner).

Supported cron patterns
-----------------------

The 5-field POSIX cron syntax (minute hour dom month dow) is fully
parsed:

  - exact integers:           ``0 3 * * *``  (daily at 03:00)
  - lists:                    ``0 3,15 * * *``  (3 AM and 3 PM)
  - ranges:                   ``0 9-17 * * 1-5``  (hourly business-hour)
  - step (``*/N``):           ``*/15 * * * *``  (every 15 minutes)
  - step over range:          ``0 0-23/2 * * *``  (every 2 hours)
  - day-of-week names:        ``0 3 * * mon``

Sunday is BOTH 0 and 7 (POSIX).  Names are case-insensitive.

Why not croniter?  Adding a third-party dep for the OSS tier is a
bigger ask than this 200-line parser.  Pro+ can swap in croniter or
APScheduler under the same ``next_run_from_cron`` signature.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Set, Tuple

# Field bounds (inclusive on both sides).
_FIELD_BOUNDS = [
    (0, 59),  # minute
    (0, 23),  # hour
    (1, 31),  # day of month
    (1, 12),  # month
    (0, 6),  # day of week (0 = Sunday, 6 = Saturday)
]

_DAY_NAMES = {
    "sun": 0,
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
}
_MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


class CronParseError(ValueError):
    """Raised when a cron expression is malformed."""


def _expand_field(spec: str, bounds: Tuple[int, int], names: dict = None) -> Set[int]:
    """Expand ONE cron field (e.g., ``*/15`` or ``9-17``) into the set of
    matching integers.  Bounds are inclusive on both sides."""
    lo, hi = bounds
    spec = spec.strip().lower()
    out: Set[int] = set()

    if not spec:
        raise CronParseError("empty cron field")

    for piece in spec.split(","):
        piece = piece.strip()
        # Step component: "<range>/<step>" or "*/<step>"
        if "/" in piece:
            base, _, step_str = piece.partition("/")
            try:
                step = int(step_str)
            except ValueError as exc:
                raise CronParseError(f"invalid step value: {step_str}") from exc
            if step < 1:
                raise CronParseError(f"step must be >= 1: {piece}")
        else:
            base, step = piece, 1

        if base in ("*", ""):
            r_lo, r_hi = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            r_lo = _resolve_token(a, lo, hi, names)
            r_hi = _resolve_token(b, lo, hi, names)
            if r_lo > r_hi:
                raise CronParseError(f"reversed range: {base}")
        else:
            r_lo = r_hi = _resolve_token(base, lo, hi, names)

        for v in range(r_lo, r_hi + 1, step):
            out.add(v)

    return out


def _resolve_token(token: str, lo: int, hi: int, names: dict) -> int:
    """Resolve one cron token (integer literal or name like ``mon``)
    into an integer within [lo, hi]."""
    token = token.strip()
    if names and token in names:
        return names[token]
    try:
        v = int(token)
    except ValueError as exc:
        raise CronParseError(f"invalid token: {token}") from exc
    if v < lo or v > hi:
        # POSIX:  Sunday is BOTH 0 and 7.  Map 7 → 0.
        if lo == 0 and hi == 6 and v == 7:
            return 0
        raise CronParseError(f"value {v} out of range [{lo}, {hi}]")
    return v


def parse_cron(expr: str) -> Tuple[Set[int], Set[int], Set[int], Set[int], Set[int]]:
    """Parse a 5-field cron expression into (minutes, hours, doms, months, dows).

    Raises CronParseError on any syntactic problem."""
    fields = expr.strip().split()
    if len(fields) != 5:
        raise CronParseError(
            f"expected 5 fields (m h dom mon dow); got {len(fields)}: '{expr}'"
        )
    minutes = _expand_field(fields[0], _FIELD_BOUNDS[0])
    hours = _expand_field(fields[1], _FIELD_BOUNDS[1])
    doms = _expand_field(fields[2], _FIELD_BOUNDS[2])
    months = _expand_field(fields[3], _FIELD_BOUNDS[3], _MONTH_NAMES)
    dows = _expand_field(fields[4], _FIELD_BOUNDS[4], _DAY_NAMES)
    return minutes, hours, doms, months, dows


def next_run_from_cron(
    expr: str, anchor: datetime, *, max_iterations: int = 525600
) -> datetime:
    """Return the next datetime ≥ ``anchor`` (rounded to the next minute)
    that satisfies ``expr``.

    POSIX cron semantics:  if BOTH dom and dow are restricted (i.e., not
    ``*``), a tick fires when EITHER matches (logical OR).  If only one
    is restricted, that one alone gates.  If both are unrestricted,
    every day matches.

    ``max_iterations`` bounds the brute-force search at one year of
    minutes — pathological expressions like ``0 0 31 2 *`` (Feb 31)
    that never fire would otherwise loop forever.  Raises
    ``CronParseError`` if no match is found within the budget."""
    minutes, hours, doms, months, dows = parse_cron(expr)

    # Determine whether dom/dow are "restricted" (not the full default set).
    full_doms = set(range(1, 32))
    full_dows = set(range(0, 7))
    dom_restricted = doms != full_doms
    dow_restricted = dows != full_dows

    # Round the anchor up to the next whole minute.
    if anchor.tzinfo is None:
        cursor = anchor.replace(second=0, microsecond=0) + timedelta(minutes=1)
    else:
        cursor = anchor.astimezone(timezone.utc).replace(
            tzinfo=None, second=0, microsecond=0
        ) + timedelta(minutes=1)

    for _ in range(max_iterations):
        # Day-level filtering first (cheap fail-fast).
        if cursor.month not in months:
            # Skip to the 1st of the next valid month.
            cursor = _advance_to_next_month(cursor, months)
            continue

        # POSIX dom/dow OR-semantics when both restricted.
        py_dow = (cursor.weekday() + 1) % 7  # Python: Mon=0, Sun=6 → cron: Sun=0..Sat=6
        dom_match = cursor.day in doms
        dow_match = py_dow in dows
        day_ok = (
            (dom_match or dow_match)
            if (dom_restricted and dow_restricted)
            else (dom_match and dow_match)
        )
        if not day_ok:
            # Advance to the next midnight.
            cursor = (cursor + timedelta(days=1)).replace(hour=0, minute=0)
            continue

        # Hour and minute filtering.
        if cursor.hour not in hours:
            # Advance to the next valid hour boundary today, or wrap to tomorrow.
            next_hours = [h for h in sorted(hours) if h > cursor.hour]
            if next_hours:
                cursor = cursor.replace(hour=next_hours[0], minute=0)
            else:
                cursor = (cursor + timedelta(days=1)).replace(hour=0, minute=0)
            continue

        if cursor.minute not in minutes:
            next_minutes = [m for m in sorted(minutes) if m > cursor.minute]
            if next_minutes:
                cursor = cursor.replace(minute=next_minutes[0])
            else:
                cursor = (cursor + timedelta(hours=1)).replace(minute=0)
            continue

        # All five fields match.
        return cursor

    raise CronParseError(f"no match for cron expression '{expr}' within one year")


def _advance_to_next_month(cursor: datetime, valid_months: Set[int]) -> datetime:
    """Jump cursor to the 1st of the next month from the valid set."""
    year = cursor.year
    month = cursor.month + 1
    while True:
        if month > 12:
            month = 1
            year += 1
        if month in valid_months:
            return datetime(year, month, 1, 0, 0)
        month += 1
        # Can't go more than 12 months without finding a hit; if valid_months
        # is empty the parser would have rejected the input already.


def validate_cron(expr: str) -> None:
    """Lightweight wrapper for API-time validation:  parse the
    expression and immediately discard the result.  Raises
    CronParseError on any problem."""
    parse_cron(expr)


def selectors_for_profile(profile, db) -> List:
    """Resolve the host set this profile applies to (list of host IDs).

    If ``profile.tag_id`` is NULL, returns every approved host.  Otherwise,
    returns the hosts carrying that tag.  Returned in a deterministic
    order (by host id) so test assertions are stable."""
    from backend.persistence import models  # local import — model graph

    if profile.tag_id is None:
        rows = (
            db.query(models.Host.id)
            .filter(models.Host.approval_status == "approved")
            .order_by(models.Host.id)
            .all()
        )
        return [r[0] for r in rows]
    rows = (
        db.query(models.Host.id)
        .join(models.HostTag, models.HostTag.host_id == models.Host.id)
        .filter(
            models.HostTag.tag_id == profile.tag_id,
            models.Host.approval_status == "approved",
        )
        .order_by(models.Host.id)
        .all()
    )
    return [r[0] for r in rows]
