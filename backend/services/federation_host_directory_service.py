# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Cross-site federation host-directory search (Phase 12.1.E).

Read-side queries against ``federation_host_directory`` — the
coordinator's host-directory tier, populated by 12.1.D's rollup
ingestion.  The Pro+ engine wraps these as ``/api/v1/federation/hosts``
endpoints; the OSS layer owns the actual SQLAlchemy logic so the
query semantics are testable without standing up the engine.

Architectural constraint (see ROADMAP §12 "Data Architecture"):

  * Host-directory queries MUST be answerable from the coordinator's
    own database — no fan-out to per-site servers.  The directory
    tier exists so an operator can ask "all hosts with condition X
    across the entire fleet" without depending on every site being
    online.
  * Filters are limited to columns physically stored on the
    directory tier.  Anything deeper (e.g. "hosts running a specific
    package version") requires a drill-down to the originating
    site — that's the detail-tier proxy path 12.1's router will
    expose separately.
"""

# ``sqlalchemy.func`` is a dynamic-attribute proxy — pylint can't
# resolve ``func.count`` statically and emits ``not-callable`` for
# every COUNT(*) clause below.  Disable at the file level because
# every COUNT here is the same false positive.
# pylint: disable=not-callable

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from backend.persistence.models.federation import FederationHostDirectory

# Maximum number of hosts a single search call can return.  At 1M-
# host fleet scale, an unbounded LIMIT is a foot-gun — pagination is
# how the frontend handles big result sets, not "give me everything
# and I'll filter client-side".
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 1000


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _build_filter_clauses(
    *,
    site_ids: Optional[List[Any]] = None,
    fqdn_contains: Optional[str] = None,
    ipv4_contains: Optional[str] = None,
    os_family: Optional[str] = None,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    geo_country_code: Optional[str] = None,
    geo_subdivision_code: Optional[str] = None,
    last_seen_after: Optional[datetime] = None,
    last_seen_before: Optional[datetime] = None,
) -> list:
    """Translate the kwargs surface into a list of SQLAlchemy clauses.

    Extracted so :func:`search_hosts` and :func:`count_hosts` apply
    the same filter logic — keeps the contract uniform.
    """
    clauses = []
    if site_ids:
        # Multi-select facet.  Each entry coerced from str/UUID; an
        # empty list earlier in the chain means "any site".
        uids = [_coerce_uuid(s) for s in site_ids]
        clauses.append(FederationHostDirectory.site_id.in_(uids))
    if fqdn_contains:
        clauses.append(FederationHostDirectory.fqdn.ilike(f"%{fqdn_contains}%"))
    if ipv4_contains:
        # Substring on ipv4 is the existing Hosts-page UX (operator
        # types "10.0.0." to find the /24).  ``ilike`` is overkill on
        # an IPv4 string but stays portable across PG / SQLite.
        clauses.append(FederationHostDirectory.ipv4.ilike(f"%{ipv4_contains}%"))
    if os_family:
        clauses.append(FederationHostDirectory.os_family == os_family)
    if platform:
        clauses.append(FederationHostDirectory.platform == platform)
    if status:
        clauses.append(FederationHostDirectory.status == status)
    if geo_country_code:
        clauses.append(FederationHostDirectory.geo_country_code == geo_country_code)
    if geo_subdivision_code:
        clauses.append(
            FederationHostDirectory.geo_subdivision_code == geo_subdivision_code
        )
    if last_seen_after is not None:
        clauses.append(FederationHostDirectory.last_seen >= last_seen_after)
    if last_seen_before is not None:
        clauses.append(FederationHostDirectory.last_seen < last_seen_before)
    return clauses


# Filter kwargs ``search_hosts`` forwards verbatim to
# :func:`_build_filter_clauses`.  Kept as a module constant so the
# ``**filters`` passthrough can reject typos with the same error a
# real keyword parameter would have raised.
_FILTER_FIELDS = frozenset(
    {
        "site_ids",
        "fqdn_contains",
        "ipv4_contains",
        "os_family",
        "platform",
        "status",
        "geo_country_code",
        "geo_subdivision_code",
        "last_seen_after",
        "last_seen_before",
    }
)


def _validate_pagination(limit: int, offset: int) -> None:
    """Raise ``ValueError`` for out-of-range pagination knobs."""
    if limit <= 0:
        raise ValueError("limit must be > 0")
    if limit > MAX_PAGE_LIMIT:
        raise ValueError(f"limit cannot exceed {MAX_PAGE_LIMIT}")
    if offset < 0:
        raise ValueError("offset must be >= 0")


def _resolve_order_column(order_by: str):
    """Map an ``order_by`` token to its column, validating the whitelist.

    Open columns to "any column" would let a caller surface internal
    columns the engine's audit policy might want to suppress.
    """
    order_columns = {
        "fqdn": FederationHostDirectory.fqdn,
        "last_seen": FederationHostDirectory.last_seen,
        "status": FederationHostDirectory.status,
        "os_family": FederationHostDirectory.os_family,
        "platform": FederationHostDirectory.platform,
        "site_id": FederationHostDirectory.site_id,
        "geo_country_code": FederationHostDirectory.geo_country_code,
    }
    if order_by not in order_columns:
        raise ValueError(
            f"order_by must be one of {sorted(order_columns)}; got {order_by!r}"
        )
    return order_columns[order_by]


def _append_free_text_clause(clauses: list, free_text: Optional[str]) -> None:
    """Append the free-text OR clause across the identifier columns.

    Free-text OR clause: typed-in box in the Hosts page hits all the
    "identifier" columns at once.  Done as a single ``or_`` rather than
    UNION so paging/count still works.
    """
    if free_text:
        pat = f"%{free_text}%"
        clauses.append(
            or_(
                FederationHostDirectory.fqdn.ilike(pat),
                FederationHostDirectory.ipv4.ilike(pat),
                FederationHostDirectory.public_ip.ilike(pat),
            )
        )


def search_hosts(
    session: Session,
    *,
    free_text: Optional[str] = None,
    order_by: str = "fqdn",
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
    **filters: Any,
) -> Tuple[List[FederationHostDirectory], int]:
    """Paginated cross-site host search.

    Returns ``(rows, total_match_count)`` so the frontend can render
    "Page 3 of 27" without a second round-trip.  All filters compose
    with AND; the special ``free_text`` parameter ORs across fqdn /
    ipv4 / public_ip for the Hosts-page search box.

    Column filters (``site_ids``, ``fqdn_contains``, ``ipv4_contains``,
    ``os_family``, ``platform``, ``status``, ``geo_country_code``,
    ``geo_subdivision_code``, ``last_seen_after``, ``last_seen_before``)
    are accepted as keyword arguments and forwarded verbatim to
    :func:`_build_filter_clauses`; an unknown filter name raises
    ``TypeError`` just as a stray keyword parameter would have.

    ``order_by`` accepts ``fqdn``, ``last_seen``, ``status``,
    ``os_family``, or any column name on ``FederationHostDirectory``
    that's safe to order by (validated against a whitelist below).
    """
    unknown = set(filters) - _FILTER_FIELDS
    if unknown:
        raise TypeError(
            f"search_hosts() got unexpected keyword argument(s): {sorted(unknown)}"
        )

    _validate_pagination(limit, offset)
    order_col = _resolve_order_column(order_by)

    clauses = _build_filter_clauses(**filters)
    _append_free_text_clause(clauses, free_text)

    base = select(FederationHostDirectory)
    if clauses:
        base = base.where(and_(*clauses))

    # Total count is computed BEFORE limit/offset so the frontend can
    # render "x of N".  Wrapping the filter in a subquery keeps it
    # consistent with paginated results (same WHERE).
    total = session.scalar(
        select(func.count()).select_from(FederationHostDirectory).where(and_(*clauses))
        if clauses
        else select(func.count()).select_from(FederationHostDirectory)
    )

    rows = (
        session.execute(
            base.order_by(order_col, FederationHostDirectory.host_id)
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(rows), int(total or 0)


def count_hosts(
    session: Session,
    *,
    site_ids: Optional[List[Any]] = None,
    fqdn_contains: Optional[str] = None,
    ipv4_contains: Optional[str] = None,
    os_family: Optional[str] = None,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    geo_country_code: Optional[str] = None,
    geo_subdivision_code: Optional[str] = None,
    last_seen_after: Optional[datetime] = None,
    last_seen_before: Optional[datetime] = None,
) -> int:
    """Count matching hosts without fetching rows.

    Used by per-site card widgets and dashboard tiles that just need
    a number.  Same filter surface as :func:`search_hosts` minus the
    pagination / order / free-text knobs.
    """
    clauses = _build_filter_clauses(
        site_ids=site_ids,
        fqdn_contains=fqdn_contains,
        ipv4_contains=ipv4_contains,
        os_family=os_family,
        platform=platform,
        status=status,
        geo_country_code=geo_country_code,
        geo_subdivision_code=geo_subdivision_code,
        last_seen_after=last_seen_after,
        last_seen_before=last_seen_before,
    )
    stmt = select(func.count()).select_from(FederationHostDirectory)
    if clauses:
        stmt = stmt.where(and_(*clauses))
    return int(session.scalar(stmt) or 0)


def status_breakdown(session: Session, *, site_ids: Optional[List[Any]] = None) -> dict:
    """Return ``{status: count}`` across the directory tier.

    Powers the "8 up / 2 down / 1 unknown" tally on the Sites page.
    NULL status (host registered but never reported a heartbeat) is
    bucketed under the ``"unknown"`` key.
    """
    clauses = []
    if site_ids:
        uids = [_coerce_uuid(s) for s in site_ids]
        clauses.append(FederationHostDirectory.site_id.in_(uids))

    stmt = select(FederationHostDirectory.status, func.count()).group_by(
        FederationHostDirectory.status
    )
    if clauses:
        stmt = stmt.where(and_(*clauses))

    # NULL status and a literal ``"unknown"`` string both bucket under
    # the ``"unknown"`` key.  Accumulate (don't overwrite) because the
    # GROUP BY returns them as separate rows.
    breakdown: dict = {}
    for status, count in session.execute(stmt).all():
        key = status or "unknown"
        breakdown[key] = breakdown.get(key, 0) + int(count)
    return breakdown


def country_breakdown(
    session: Session, *, site_ids: Optional[List[Any]] = None
) -> dict:
    """Return ``{country_code: count}``, NULL bucketed under ``""``.

    Powers the federation map's per-country density coloring.
    """
    clauses = []
    if site_ids:
        uids = [_coerce_uuid(s) for s in site_ids]
        clauses.append(FederationHostDirectory.site_id.in_(uids))

    stmt = select(FederationHostDirectory.geo_country_code, func.count()).group_by(
        FederationHostDirectory.geo_country_code
    )
    if clauses:
        stmt = stmt.where(and_(*clauses))

    # Same NULL-or-empty-string accumulation as status_breakdown.
    breakdown: dict = {}
    for cc, count in session.execute(stmt).all():
        key = cc or ""
        breakdown[key] = breakdown.get(key, 0) + int(count)
    return breakdown


# ---------------------------------------------------------------------------
# Write side — re-exported from ``federation_rollup_service``, which owns the
# canonical host-directory upsert/get (with fqdn + site validation).  The
# Pro+ controller engine imports THIS module as ``host_dir_svc`` and calls
# ``upsert_host_directory_entry`` / ``get_host_directory_entry`` on it during
# ``ingest_host_directory``; surface them here so that resolves without a
# second implementation that could drift.
# ---------------------------------------------------------------------------

from backend.services.federation_rollup_service import (  # noqa: E402  # pylint: disable=wrong-import-position
    get_host_directory_entry,
    upsert_host_directory_entry,
)

__all__ = [  # noqa: F822  (names defined above + re-exported here)
    "search_hosts",
    "count_hosts",
    "status_breakdown",
    "country_breakdown",
    "upsert_host_directory_entry",
    "get_host_directory_entry",
]
