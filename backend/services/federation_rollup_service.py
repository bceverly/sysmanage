# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Federation rollup ingestion service (Phase 12.1.D).

Coordinator-side helpers that accept upstream sync pushes from a
site server and write them into the three rollup tables plus the
host-directory tier.  The Pro+ ``federation_controller_engine``
exposes inbound REST endpoints that call these helpers; the OSS
layer owns the domain logic + validation + dedup-on-replay.

Architectural notes (see ROADMAP §12 "Data Architecture"):

  * ``federation_host_directory`` is the *hot* table — one row per
    host fleet-wide.  ``upsert_host_directory_entry`` writes it via
    an explicit "SELECT existing, then INSERT or UPDATE" path that
    works on both PostgreSQL and SQLite without dialect-specific
    INSERT-ON-CONFLICT syntax.
  * Rollup snapshot tables (``federation_host_rollup``,
    ``federation_compliance_rollup``, ``federation_vulnerability_rollup``)
    are append-only.  A retention sweeper (Phase 12.1 followup)
    prunes old rows; reads on the Sites page always pick the latest
    per (site_id [, baseline]).
  * Dedup on replay is the site's responsibility (the site sends
    each delta with a ``dedup_key`` and the coordinator stores
    monotonic ``mtime`` on the directory row); the rollup service
    just trusts incoming payloads and writes them.  If the same
    delta is replayed, the upsert is idempotent at the host-directory
    level (mtime is updated to whatever the site sent), and rollup
    snapshots just get a duplicate row with the same data — the
    "latest" query still returns one result.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from backend.persistence.models.federation import (
    FederationComplianceRollup,
    FederationHostDirectory,
    FederationHostRollup,
    FederationSite,
    FederationVulnerabilityRollup,
)
from backend.services.federation_site_service import (
    record_sync,
)

# ---------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------


class FederationRollupError(Exception):
    """Base class for rollup ingestion errors."""


class UnknownSiteError(FederationRollupError, LookupError):
    """Raised when a sync payload references a site_id that doesn't
    exist (or is in ``status='removed'``).  Distinct from
    :class:`SiteNotFoundError` only because we want to surface it
    differently in audit logs."""


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------


def _utcnow_naive() -> datetime:
    """Naive UTC timestamp — matches every other federation column."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _coerce_uuid(value: Any) -> UUID:
    """UUID coercion that accepts ``UUID`` or its string form."""
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    raise ValueError(f"Expected UUID or str, got {type(value).__name__}")


def _require_site(session: Session, site_id: Any) -> FederationSite:
    """Look up an existing (non-removed) site, raise on miss."""
    uid = _coerce_uuid(site_id)
    site = session.get(FederationSite, uid)
    if site is None:
        raise UnknownSiteError(f"No federation site with id={uid}")
    if site.status == "removed":
        raise UnknownSiteError(
            f"Federation site {uid} is removed; rollups for it are not accepted."
        )
    return site


def _json_or_none(value: Any) -> Optional[str]:
    """Serialize ``value`` to JSON; pass ``None`` through unchanged.

    Used by columns ending in ``_json`` whose callers pass native
    Python dicts / lists.  Keeps the JSON-shape contract in one
    place — every column that stores a JSON document goes through
    this helper.
    """
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


# ---------------------------------------------------------------------
# Host directory tier (upsert)
# ---------------------------------------------------------------------


# Columns the site's host-delta sync is allowed to overwrite on a
# directory row.  Anything else (``host_id``, ``site_id``, ``mtime``)
# is managed by the upsert logic itself.
_HOST_DIR_FIELDS = frozenset(
    {
        "fqdn",
        "ipv4",
        "ipv6",
        "public_ip",
        "os_family",
        "os_version",
        "platform",
        "status",
        "last_seen",
        "tags_json",
        "geo_country_code",
        "geo_subdivision_code",
        "geo_city",
        "geo_latitude",
        "geo_longitude",
    }
)


def upsert_host_directory_entry(
    session: Session,
    *,
    site_id: Any,
    host_id: Any,
    fqdn: str,
    mtime: Optional[datetime] = None,
    **fields: Any,
) -> FederationHostDirectory:
    """Insert-or-update one row in ``federation_host_directory``.

    ``site_id`` and ``host_id`` together are the natural key; on an
    INSERT we set both, on UPDATE only the per-host columns change.
    The site may move a host between status / OS versions / IPs many
    times a day; the upsert pattern keeps the row count bounded at
    1-per-host instead of growing unbounded log style.

    ``mtime`` defaults to "now" but the site can pass an explicit
    timestamp — useful when replaying buffered offline deltas so
    the coordinator's ``mtime`` reflects when the change actually
    happened at the site, not when the coordinator received it.

    Unknown kwargs raise ``ValueError`` (whitelist approach mirrors
    ``update_site``).
    """
    if not fqdn or not fqdn.strip():
        raise ValueError("fqdn is required for a host directory entry")
    unknown = set(fields) - _HOST_DIR_FIELDS
    if unknown:
        raise ValueError(f"Unknown host-directory fields: {sorted(unknown)}")
    site = _require_site(session, site_id)
    host_uid = _coerce_uuid(host_id)
    now = mtime or _utcnow_naive()

    entry = session.get(FederationHostDirectory, host_uid)
    if entry is None:
        entry = FederationHostDirectory(
            host_id=host_uid,
            site_id=site.id,
            fqdn=fqdn.strip(),
            mtime=now,
        )
        session.add(entry)
    else:
        # If the host moved between sites (rare but plausible — agent
        # re-enrolled under a different coordinator-site mapping),
        # update site_id too.  This is what makes ``host_id`` a
        # globally-unique key.
        if entry.site_id != site.id:
            entry.site_id = site.id
        entry.fqdn = fqdn.strip()
        entry.mtime = now

    for key, value in fields.items():
        setattr(entry, key, value)
    return entry


def get_host_directory_entry(
    session: Session, host_id: Any
) -> Optional[FederationHostDirectory]:
    """Look up one directory row by host_id; ``None`` on miss."""
    return session.get(FederationHostDirectory, _coerce_uuid(host_id))


def delete_host_directory_entry(session: Session, host_id: Any) -> bool:
    """Remove a directory row when the agent deactivates / is removed
    at the originating site.  Returns True if a row was deleted."""
    entry = get_host_directory_entry(session, host_id)
    if entry is None:
        return False
    session.delete(entry)
    return True


# ---------------------------------------------------------------------
# Rollup snapshots (append-only)
# ---------------------------------------------------------------------


def record_host_rollup_snapshot(
    session: Session,
    *,
    site_id: Any,
    host_count: int,
    active_count: int,
    os_breakdown: Optional[Dict[str, int]] = None,
    status_breakdown: Optional[Dict[str, int]] = None,
    snapshot_at: Optional[datetime] = None,
    update_site_host_count: bool = True,
) -> FederationHostRollup:
    """Append one ``federation_host_rollup`` row from a site's sync.

    ``host_count`` is also cached onto the parent ``FederationSite``
    row by default — the Sites page card needs it and avoiding the
    JOIN through the rollup table keeps the page fast.  Pass
    ``update_site_host_count=False`` for tests that exercise the
    rollup row independently.
    """
    if host_count < 0 or active_count < 0:
        raise ValueError("host_count and active_count must be non-negative")
    if active_count > host_count:
        raise ValueError(
            f"active_count ({active_count}) cannot exceed host_count ({host_count})"
        )
    site = _require_site(session, site_id)
    row = FederationHostRollup(
        site_id=site.id,
        snapshot_at=snapshot_at or _utcnow_naive(),
        host_count=host_count,
        active_count=active_count,
        os_breakdown_json=_json_or_none(os_breakdown),
        status_breakdown_json=_json_or_none(status_breakdown),
    )
    session.add(row)
    _prune_series(session, FederationHostRollup, site_id=site.id)
    if update_site_host_count:
        site.host_count = host_count
        # A successful rollup ingestion implies the site is talking
        # to us — refresh ``last_sync_*`` so the Sites page traffic
        # light agrees with reality.
        record_sync(session, site.id, success=True, host_count=host_count)
    return row


def record_compliance_rollup_snapshot(
    session: Session,
    *,
    site_id: Any,
    baseline: str,
    score_percent: Optional[float],
    hosts_in_scope: int,
    hosts_compliant: int,
    hosts_noncompliant: int,
    snapshot_at: Optional[datetime] = None,
) -> FederationComplianceRollup:
    """Append one compliance-snapshot row for a (site, baseline) pair."""
    if not baseline or not baseline.strip():
        raise ValueError("baseline is required (e.g. 'cis', 'stig')")
    if hosts_in_scope < 0 or hosts_compliant < 0 or hosts_noncompliant < 0:
        raise ValueError("host counts must be non-negative")
    if hosts_compliant + hosts_noncompliant > hosts_in_scope:
        raise ValueError(
            "hosts_compliant + hosts_noncompliant cannot exceed hosts_in_scope"
        )
    if score_percent is not None and not 0.0 <= score_percent <= 100.0:
        raise ValueError(f"score_percent must be in [0, 100]; got {score_percent}")
    site = _require_site(session, site_id)
    row = FederationComplianceRollup(
        site_id=site.id,
        baseline=baseline.strip(),
        snapshot_at=snapshot_at or _utcnow_naive(),
        score_percent=score_percent,
        hosts_in_scope=hosts_in_scope,
        hosts_compliant=hosts_compliant,
        hosts_noncompliant=hosts_noncompliant,
    )
    session.add(row)
    _prune_series(
        session,
        FederationComplianceRollup,
        site_id=site.id,
        baseline=baseline.strip(),
    )
    return row


def record_vulnerability_rollup_snapshot(
    session: Session,
    *,
    site_id: Any,
    critical_count: int = 0,
    high_count: int = 0,
    medium_count: int = 0,
    low_count: int = 0,
    affected_host_count: int = 0,
    top_cve_ids: Optional[List[str]] = None,
    snapshot_at: Optional[datetime] = None,
) -> FederationVulnerabilityRollup:
    """Append one CVE-exposure snapshot row for a site."""
    for label, value in (
        ("critical_count", critical_count),
        ("high_count", high_count),
        ("medium_count", medium_count),
        ("low_count", low_count),
        ("affected_host_count", affected_host_count),
    ):
        if value < 0:
            raise ValueError(f"{label} must be non-negative; got {value}")
    site = _require_site(session, site_id)
    row = FederationVulnerabilityRollup(
        site_id=site.id,
        snapshot_at=snapshot_at or _utcnow_naive(),
        critical_count=critical_count,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        affected_host_count=affected_host_count,
        top_cve_ids_json=_json_or_none(top_cve_ids),
    )
    session.add(row)
    _prune_series(session, FederationVulnerabilityRollup, site_id=site.id)
    return row


# ---------------------------------------------------------------------
# Retention sweeper (the append-only rollup tables would grow forever
# otherwise — see the module docstring's "retention sweeper" note).
# ---------------------------------------------------------------------

# How many snapshots to keep per series (per site, or per (site, baseline)
# for compliance).  Generous enough to preserve trend history; bounded so
# a long-running coordinator's rollup tables can't grow without limit.
DEFAULT_ROLLUP_RETENTION = 90


def _prune_series(
    session: Session,
    model: Any,
    *,
    site_id: Any,
    baseline: Optional[str] = None,
    keep: int = DEFAULT_ROLLUP_RETENTION,
) -> int:
    """Delete all but the newest ``keep`` snapshots for one series.

    Called opportunistically after each ingest so growth stays bounded
    without a separate background tick.  Idempotent: re-running once the
    series is already at/under ``keep`` deletes nothing.  Returns the
    number of rows pruned.  A query here autoflushes the just-added row,
    so it is counted among the kept newest.
    """
    if keep <= 0:
        return 0
    stmt = select(model.id).where(model.site_id == site_id)
    if baseline is not None:
        stmt = stmt.where(model.baseline == baseline)
    stmt = stmt.order_by(desc(model.snapshot_at), desc(model.id))
    ids = list(session.execute(stmt).scalars().all())
    stale = ids[keep:]
    if not stale:
        return 0
    session.execute(delete(model).where(model.id.in_(stale)))
    return len(stale)


def prune_rollups(
    session: Session,
    *,
    keep_per_series: int = DEFAULT_ROLLUP_RETENTION,
    older_than_days: Optional[int] = None,
) -> Dict[str, int]:
    """Explicit retention sweep across ALL sites and all three rollup
    series.  ``keep_per_series`` bounds each series by count; when
    ``older_than_days`` is also given, snapshots older than that cutoff
    are removed too (count-keep applied first so a slow-syncing site
    still retains its latest snapshot regardless of age).

    Idempotent and dialect-neutral (plain ORM ``delete``/``select``;
    no SQLite/PostgreSQL-specific SQL).  Returns per-table prune counts.
    Caller commits.
    """
    counts = {"host": 0, "compliance": 0, "vulnerability": 0}

    # Count-bounded prune, per series.  Compliance is per (site, baseline).
    for site_id in session.execute(select(FederationSite.id)).scalars().all():
        counts["host"] += _prune_series(
            session, FederationHostRollup, site_id=site_id, keep=keep_per_series
        )
        counts["vulnerability"] += _prune_series(
            session,
            FederationVulnerabilityRollup,
            site_id=site_id,
            keep=keep_per_series,
        )
        baselines = (
            session.execute(
                select(FederationComplianceRollup.baseline)
                .where(FederationComplianceRollup.site_id == site_id)
                .distinct()
            )
            .scalars()
            .all()
        )
        for baseline in baselines:
            counts["compliance"] += _prune_series(
                session,
                FederationComplianceRollup,
                site_id=site_id,
                baseline=baseline,
                keep=keep_per_series,
            )

    if older_than_days is not None and older_than_days > 0:
        cutoff = _utcnow_naive() - timedelta(days=older_than_days)
        for key, model in (
            ("host", FederationHostRollup),
            ("compliance", FederationComplianceRollup),
            ("vulnerability", FederationVulnerabilityRollup),
        ):
            result = session.execute(delete(model).where(model.snapshot_at < cutoff))
            counts[key] += result.rowcount or 0

    return counts


# ---------------------------------------------------------------------
# Latest-snapshot lookups (drive the Sites page card + dashboards)
# ---------------------------------------------------------------------


def get_latest_host_rollup(
    session: Session, site_id: Any
) -> Optional[FederationHostRollup]:
    """Return the most recent host rollup for ``site_id``, or ``None``."""
    uid = _coerce_uuid(site_id)
    return (
        session.execute(
            select(FederationHostRollup)
            .where(FederationHostRollup.site_id == uid)
            .order_by(desc(FederationHostRollup.snapshot_at))
            .limit(1)
        )
        .scalars()
        .first()
    )


def get_latest_compliance_rollup(
    session: Session, site_id: Any, *, baseline: str
) -> Optional[FederationComplianceRollup]:
    """Return the most recent compliance row for ``(site_id, baseline)``."""
    uid = _coerce_uuid(site_id)
    return (
        session.execute(
            select(FederationComplianceRollup)
            .where(
                FederationComplianceRollup.site_id == uid,
                FederationComplianceRollup.baseline == baseline,
            )
            .order_by(desc(FederationComplianceRollup.snapshot_at))
            .limit(1)
        )
        .scalars()
        .first()
    )


def get_latest_vulnerability_rollup(
    session: Session, site_id: Any
) -> Optional[FederationVulnerabilityRollup]:
    """Return the most recent vulnerability rollup row for a site."""
    uid = _coerce_uuid(site_id)
    return (
        session.execute(
            select(FederationVulnerabilityRollup)
            .where(FederationVulnerabilityRollup.site_id == uid)
            .order_by(desc(FederationVulnerabilityRollup.snapshot_at))
            .limit(1)
        )
        .scalars()
        .first()
    )


def get_dashboard_rollup(session: Session, site_id: Any) -> Tuple[
    Optional[FederationHostRollup],
    List[FederationComplianceRollup],
    Optional[FederationVulnerabilityRollup],
]:
    """One-shot read for the Sites-page card: latest host + every
    latest-per-baseline compliance + latest vulnerability rollup.

    Returns a tuple so the engine's router can pack it into one
    JSON envelope without three round-trips.  The compliance list
    is intentionally unbounded (one row per baseline) — sites
    typically evaluate against 1-3 baselines so unbounded is fine.
    """
    uid = _coerce_uuid(site_id)
    latest_host = get_latest_host_rollup(session, uid)
    # Per-baseline latest: one row per distinct baseline, picking
    # the highest ``snapshot_at`` for each.  Done as a Python-side
    # group rather than a window function so SQLite (no ROW_NUMBER
    # in older versions) keeps working.
    all_rows = (
        session.execute(
            select(FederationComplianceRollup)
            .where(FederationComplianceRollup.site_id == uid)
            .order_by(
                FederationComplianceRollup.baseline,
                desc(FederationComplianceRollup.snapshot_at),
            )
        )
        .scalars()
        .all()
    )
    latest_per_baseline: Dict[str, FederationComplianceRollup] = {}
    for row in all_rows:
        if row.baseline not in latest_per_baseline:
            latest_per_baseline[row.baseline] = row
    latest_vuln = get_latest_vulnerability_rollup(session, uid)
    return latest_host, list(latest_per_baseline.values()), latest_vuln


# Numeric per-site columns summed into the enterprise-wide totals.
_CROSS_SITE_TOTAL_KEYS = (
    "host_count",
    "active_count",
    "critical_count",
    "high_count",
    "medium_count",
    "low_count",
)


def _resolve_report_sites(
    session: Session, site_ids: Optional[List[Any]]
) -> List[FederationSite]:
    """The sites a cross-site report covers: the requested ids (existing
    only), or every enrolled site when none are given."""
    if site_ids:
        uids = [_coerce_uuid(s) for s in site_ids]
        return [
            site
            for site in (session.get(FederationSite, u) for u in uids)
            if site is not None
        ]
    return list(
        session.execute(
            select(FederationSite).where(FederationSite.status == "enrolled")
        )
        .scalars()
        .all()
    )


def _worst_compliance(compliance) -> Optional[Dict[str, Any]]:
    """The lowest-scoring baseline (ignoring null scores), or None."""
    scored = [c for c in compliance if c.score_percent is not None]
    if not scored:
        return None
    worst = min(scored, key=lambda c: c.score_percent)
    return {"baseline": worst.baseline, "score_percent": worst.score_percent}


def _cross_site_report_row(session: Session, site: FederationSite) -> Dict[str, Any]:
    """One per-site row for the federated report (latest rollups)."""
    host, compliance, vuln = get_dashboard_rollup(session, site.id)
    return {
        "site_id": str(site.id),
        "site_name": site.name,
        "host_count": host.host_count if host else site.host_count,
        "active_count": host.active_count if host else 0,
        "worst_compliance": _worst_compliance(compliance),
        "critical_count": vuln.critical_count if vuln else 0,
        "high_count": vuln.high_count if vuln else 0,
        "medium_count": vuln.medium_count if vuln else 0,
        "low_count": vuln.low_count if vuln else 0,
        "last_sync_at": site.last_sync_at,
    }


def get_cross_site_report(
    session: Session,
    site_ids: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Aggregate the latest rollups across sites for the federated Reports
    facet (Phase 12.3).

    ``site_ids`` restricts the report to those sites; ``None`` (or an empty
    list) reports on every *enrolled* site.  Returns one row per site (host
    counts, worst compliance baseline, CVE-severity counts) plus
    enterprise-wide totals so the UI can render a cross-site table without
    N round-trips.  Read-only — safe from any report context.
    """
    rows = [
        _cross_site_report_row(session, site)
        for site in _resolve_report_sites(session, site_ids)
    ]
    totals: Dict[str, int] = {"site_count": len(rows)}
    for key in _CROSS_SITE_TOTAL_KEYS:
        totals[key] = sum(row.get(key) or 0 for row in rows)
    return {"sites": rows, "totals": totals}
