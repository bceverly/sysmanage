"""Federation site-side compliance + vulnerability rollup producers (Phase 12).

Aggregates THIS site's local CVE findings and compliance-scan results into the
rollup shapes the coordinator ingests at ``/sites/{id}/rollups/vulnerabilities``
and ``/sites/{id}/rollups/compliance``, then enqueues them for the outbound
sync tick — the same pattern as the metadata + host-directory producers.

These read the Pro+ data tables (``host_vulnerability_finding`` /
``host_compliance_scan``); on a site that hasn't run a vuln/compliance scan yet
they simply find nothing and enqueue nothing (the coordinator's panel stays
empty rather than showing a misleading "0 findings").
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.services import (
    federation_coordinator_service as coord_svc,
    federation_sync_queue_service as sync_svc,
)

VULN_ROLLUP_PAYLOAD_TYPE = "vulnerability_rollup"
VULN_ROLLUP_DEDUP_KEY = "vulnerability_rollup:self"
COMPLIANCE_ROLLUP_PAYLOAD_TYPE = "compliance_rollup"
COMPLIANCE_ROLLUP_DEDUP_PREFIX = "compliance_rollup:"

_SEVERITIES = ("critical", "high", "medium", "low")


def collect_vulnerability_rollup(session: Session) -> Optional[Dict[str, Any]]:
    """CVE-exposure snapshot for this site, or ``None`` if nothing's been found.

    Counts findings by severity and the number of distinct affected hosts.
    """
    from backend.persistence.models.proplus import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
        HostVulnerabilityFinding,
        HostVulnerabilityScan,
    )

    counts = dict.fromkeys(_SEVERITIES, 0)
    total = 0
    severity_count = func.count()  # pylint: disable=not-callable
    for severity, num in session.execute(
        select(HostVulnerabilityFinding.severity, severity_count).group_by(
            HostVulnerabilityFinding.severity
        )
    ).all():
        total += int(num or 0)
        key = (severity or "").strip().lower()
        if key in counts:
            counts[key] += int(num or 0)

    if total == 0:
        return None

    distinct_hosts = func.count(  # pylint: disable=not-callable
        func.distinct(HostVulnerabilityScan.host_id)
    )
    affected = (
        session.execute(
            select(distinct_hosts)
            .select_from(HostVulnerabilityFinding)
            .join(
                HostVulnerabilityScan,
                HostVulnerabilityFinding.scan_id == HostVulnerabilityScan.id,
            )
        ).scalar()
        or 0
    )
    return {
        "critical_count": counts["critical"],
        "high_count": counts["high"],
        "medium_count": counts["medium"],
        "low_count": counts["low"],
        "affected_host_count": int(affected),
        "top_cve_ids": None,
    }


def collect_compliance_rollups(session: Session) -> List[Dict[str, Any]]:
    """One compliance rollup per profile (baseline), over the latest scan per
    host.  Empty list when no compliance scans exist on this site."""
    from backend.persistence.models.proplus import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
        ComplianceProfile,
        HostComplianceScan,
    )

    # Latest scan per (host, profile): newest-first, keep first seen.
    latest: Dict[Any, tuple] = {}
    for host_id, profile_id, score, failed, _scanned in session.execute(
        select(
            HostComplianceScan.host_id,
            HostComplianceScan.profile_id,
            HostComplianceScan.compliance_score,
            HostComplianceScan.failed_rules,
            HostComplianceScan.scanned_at,
        ).order_by(HostComplianceScan.scanned_at.desc())
    ).all():
        latest.setdefault((host_id, profile_id), (score, failed))

    if not latest:
        return []

    names = dict(
        session.execute(select(ComplianceProfile.id, ComplianceProfile.name)).all()
    )

    agg: Dict[Any, Dict[str, Any]] = {}
    for (_host_id, profile_id), (score, failed) in latest.items():
        bucket = agg.setdefault(
            profile_id, {"scores": [], "compliant": 0, "noncompliant": 0}
        )
        bucket["scores"].append(int(score or 0))
        if (failed or 0) == 0:
            bucket["compliant"] += 1
        else:
            bucket["noncompliant"] += 1

    rollups: List[Dict[str, Any]] = []
    for profile_id, bucket in agg.items():
        scores = bucket["scores"]
        in_scope = bucket["compliant"] + bucket["noncompliant"]
        rollups.append(
            {
                "baseline": names.get(profile_id) or str(profile_id) or "default",
                "score_percent": (
                    round(sum(scores) / len(scores), 1) if scores else None
                ),
                "hosts_in_scope": in_scope,
                "hosts_compliant": bucket["compliant"],
                "hosts_noncompliant": bucket["noncompliant"],
            }
        )
    return rollups


def enqueue_vulnerability_rollup(session: Session) -> Optional[Any]:
    """Enqueue the vulnerability rollup if there are findings + we're enrolled."""
    if not coord_svc.is_enrolled(session):
        return None
    payload = collect_vulnerability_rollup(session)
    if payload is None:
        return None
    return sync_svc.enqueue(
        session,
        payload_type=VULN_ROLLUP_PAYLOAD_TYPE,
        payload=payload,
        dedup_key=VULN_ROLLUP_DEDUP_KEY,
    )


def enqueue_compliance_rollups(session: Session) -> int:
    """Enqueue one compliance rollup per baseline.  Returns the number queued."""
    if not coord_svc.is_enrolled(session):
        return 0
    queued = 0
    for rollup in collect_compliance_rollups(session):
        sync_svc.enqueue(
            session,
            payload_type=COMPLIANCE_ROLLUP_PAYLOAD_TYPE,
            payload=rollup,
            dedup_key=COMPLIANCE_ROLLUP_DEDUP_PREFIX + str(rollup["baseline"]),
        )
        queued += 1
    return queued


HOST_ROLLUP_PAYLOAD_TYPE = "host_rollup"
HOST_ROLLUP_DEDUP_KEY = "host_rollup:self"


def collect_host_rollup(session: Session) -> Dict[str, Any]:
    """Aggregate host-count snapshot for this site (total/active + breakdowns).

    Feeds the coordinator's host-count *trend* charts (the per-tick current
    count already rides on site_metadata; this is the time-series).
    """
    from backend.persistence.models.core import (
        Host,
    )  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    count_star = func.count()  # pylint: disable=not-callable
    total = session.execute(select(count_star).select_from(Host)).scalar() or 0
    active = (
        session.execute(
            select(count_star).select_from(Host).where(Host.active.is_(True))
        ).scalar()
        or 0
    )
    os_rows = session.execute(
        select(Host.platform, count_star).select_from(Host).group_by(Host.platform)
    ).all()
    status_rows = session.execute(
        select(Host.status, count_star).select_from(Host).group_by(Host.status)
    ).all()
    return {
        "host_count": int(total),
        "active_count": int(active),
        "os_breakdown": {(p or "unknown"): int(c) for p, c in os_rows},
        "status_breakdown": {(s or "unknown"): int(c) for s, c in status_rows},
    }


def enqueue_host_rollup(session: Session) -> Optional[Any]:
    """Enqueue the host-count rollup snapshot if enrolled."""
    if not coord_svc.is_enrolled(session):
        return None
    return sync_svc.enqueue(
        session,
        payload_type=HOST_ROLLUP_PAYLOAD_TYPE,
        payload=collect_host_rollup(session),
        dedup_key=HOST_ROLLUP_DEDUP_KEY,
    )
