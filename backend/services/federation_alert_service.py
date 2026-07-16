# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Federation rollup alerting (Phase 12.1).

Enterprise-wide alerts that fire on cross-SITE conditions — distinct
from the host-scoped ``alert`` table.  Three built-in conditions are
evaluated against each enrolled site's synced state + latest rollups:

  * ``site_offline``        — the site hasn't synced within a multiple
                              of its configured ``sync_interval_seconds``
                              (it's gone dark).                 [critical]
  * ``compliance_below``    — a compliance baseline's score dropped below
                              a threshold.                       [warning]
  * ``vulnerabilities_high``— the site's critical-CVE count crossed a
                              threshold.                        [critical]

Lifecycle: an alert is OPEN (``resolved=False``) while its condition
holds and auto-resolves when the condition clears, so there's at most
ONE open alert per (site, condition) — no cooldown bookkeeping and no
duplicate spam.  Operators can additionally acknowledge an open alert.

This is pure OSS domain logic (no network, no engine dependency); the
Pro+ ``federation_controller_engine`` background task calls
:func:`evaluate_and_fire` each cycle on the coordinator, which holds the
rollup tables.  Thresholds are parameters with sensible defaults here;
operator overrides are persisted in ``federation_alert_config`` and merged
in by ``federation_alert_config_service.evaluate_with_config`` (Phase 12.1
follow-up), which the engine tick calls instead of ``evaluate_and_fire``
directly when it wants the configured values.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.persistence.models.federation import (
    FederationAlert,
    FederationComplianceRollup,
    FederationSite,
)
from backend.services import federation_rollup_service as rollup_svc

logger = logging.getLogger(__name__)

# Condition identifiers (also stored in the ``condition`` column).
COND_SITE_OFFLINE = "site_offline"
COND_COMPLIANCE_BELOW = "compliance_below"
COND_VULNERABILITIES_HIGH = "vulnerabilities_high"

# Defaults — overridable per call by the engine tick / an admin sweep.
DEFAULT_OFFLINE_MULTIPLIER = 4  # × sync_interval before "offline"
DEFAULT_MIN_OFFLINE_SECONDS = 900  # floor so fast intervals don't flap
DEFAULT_COMPLIANCE_THRESHOLD = 70.0  # score_percent below this → alert
DEFAULT_CRITICAL_CVE_THRESHOLD = 0  # critical_count strictly above → alert


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _open_alert(
    session: Session, site_id: Any, condition: str
) -> Optional[FederationAlert]:
    """The current OPEN alert for (site, condition), or None."""
    return (
        session.execute(
            select(FederationAlert)
            .where(
                FederationAlert.site_id == site_id,
                FederationAlert.condition == condition,
                FederationAlert.resolved.is_(False),
            )
            .order_by(FederationAlert.triggered_at.desc())
        )
        .scalars()
        .first()
    )


def _open_or_refresh(
    session: Session,
    site: FederationSite,
    *,
    condition: str,
    severity: str,
    title: str,
    message: str,
    details: Dict[str, Any],
) -> bool:
    """Open a new alert, or refresh the existing open one.  Returns True
    only when a NEW alert was opened (so the caller can count it)."""
    existing = _open_alert(session, site.id, condition)
    details_json = json.dumps(details, sort_keys=True)
    if existing is not None:
        existing.severity = severity
        existing.title = title
        existing.message = message
        existing.details_json = details_json
        existing.triggered_at = _utcnow_naive()
        return False
    session.add(
        FederationAlert(
            site_id=site.id,
            condition=condition,
            severity=severity,
            title=title,
            message=message,
            details_json=details_json,
            triggered_at=_utcnow_naive(),
        )
    )
    return True


def _resolve(session: Session, site_id: Any, condition: str) -> bool:
    """Resolve the open alert for (site, condition) if any.  True if one
    was resolved."""
    existing = _open_alert(session, site_id, condition)
    if existing is None:
        return False
    existing.resolved = True
    existing.resolved_at = _utcnow_naive()
    return True


# ---------------------------------------------------------------------
# Condition evaluators — each returns (triggered, title, message, details)
# ---------------------------------------------------------------------


def _eval_offline(
    site: FederationSite, *, multiplier: int, min_seconds: int
) -> Tuple[bool, str, str, Dict[str, Any]]:
    interval = site.sync_interval_seconds or 300
    threshold = max(interval * multiplier, min_seconds)
    last = site.last_sync_at
    if last is None:
        age = None
        triggered = True
    else:
        age = (_utcnow_naive() - last).total_seconds()
        triggered = age > threshold
    details = {
        "last_sync_at": last.isoformat() if last else None,
        "age_seconds": int(age) if age is not None else None,
        "threshold_seconds": threshold,
    }
    title = f"Site '{site.name}' is offline"
    message = (
        f"No sync from '{site.name}' in over {threshold} seconds"
        if last
        else f"Site '{site.name}' has never synced"
    )
    return triggered, title, message, details


def _eval_compliance(
    session: Session, site: FederationSite, *, threshold: float
) -> Tuple[bool, str, str, Dict[str, Any]]:
    # Worst baseline below the threshold wins the alert.
    baselines = (
        session.execute(
            select(FederationComplianceRollup.baseline)
            .where(FederationComplianceRollup.site_id == site.id)
            .distinct()
        )
        .scalars()
        .all()
    )
    worst: Optional[Tuple[str, float]] = None
    for baseline in baselines:
        latest = rollup_svc.get_latest_compliance_rollup(
            session, site.id, baseline=baseline
        )
        if latest is None or latest.score_percent is None:
            continue
        if latest.score_percent < threshold and (
            worst is None or latest.score_percent < worst[1]
        ):
            worst = (baseline, latest.score_percent)
    if worst is None:
        return False, "", "", {}
    details = {
        "baseline": worst[0],
        "score_percent": worst[1],
        "threshold": threshold,
    }
    title = f"Site '{site.name}' compliance below {int(threshold)}%"
    message = (
        f"Baseline '{worst[0]}' at {worst[1]:.0f}% "
        f"(threshold {int(threshold)}%) on site '{site.name}'"
    )
    return True, title, message, details


def _eval_vulnerabilities(
    session: Session, site: FederationSite, *, critical_threshold: int
) -> Tuple[bool, str, str, Dict[str, Any]]:
    latest = rollup_svc.get_latest_vulnerability_rollup(session, site.id)
    if latest is None:
        return False, "", "", {}
    triggered = latest.critical_count > critical_threshold
    if not triggered:
        return False, "", "", {}
    details = {
        "critical_count": latest.critical_count,
        "high_count": latest.high_count,
        "affected_host_count": latest.affected_host_count,
        "threshold": critical_threshold,
    }
    title = f"Site '{site.name}' has {latest.critical_count} critical CVEs"
    message = (
        f"{latest.critical_count} critical / {latest.high_count} high CVEs "
        f"across {latest.affected_host_count} hosts on site '{site.name}'"
    )
    return True, title, message, details


def evaluate_and_fire(
    session: Session,
    *,
    offline_multiplier: int = DEFAULT_OFFLINE_MULTIPLIER,
    min_offline_seconds: int = DEFAULT_MIN_OFFLINE_SECONDS,
    compliance_threshold: float = DEFAULT_COMPLIANCE_THRESHOLD,
    critical_cve_threshold: int = DEFAULT_CRITICAL_CVE_THRESHOLD,
) -> Dict[str, int]:
    """Evaluate every enrolled site against the three built-in conditions,
    opening/refreshing or resolving alerts.  Best-effort per site; one bad
    site never blocks the rest.  Returns ``{"opened", "resolved", "active"}``.
    Caller commits.
    """
    summary = {"opened": 0, "resolved": 0, "active": 0}
    sites = (
        session.execute(
            select(FederationSite).where(FederationSite.status == "enrolled")
        )
        .scalars()
        .all()
    )
    for site in sites:
        try:
            checks = [
                (
                    COND_SITE_OFFLINE,
                    "critical",
                    _eval_offline(
                        site,
                        multiplier=offline_multiplier,
                        min_seconds=min_offline_seconds,
                    ),
                ),
                (
                    COND_COMPLIANCE_BELOW,
                    "warning",
                    _eval_compliance(session, site, threshold=compliance_threshold),
                ),
                (
                    COND_VULNERABILITIES_HIGH,
                    "critical",
                    _eval_vulnerabilities(
                        session, site, critical_threshold=critical_cve_threshold
                    ),
                ),
            ]
            for condition, severity, (triggered, title, message, details) in checks:
                if triggered:
                    if _open_or_refresh(
                        session,
                        site,
                        condition=condition,
                        severity=severity,
                        title=title,
                        message=message,
                        details=details,
                    ):
                        summary["opened"] += 1
                    summary["active"] += 1
                elif _resolve(session, site.id, condition):
                    summary["resolved"] += 1
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning(
                "federation alert eval failed for site %s", site.id, exc_info=True
            )
    logger.info(
        "Federation alert sweep: opened=%s resolved=%s active=%s",
        summary["opened"],
        summary["resolved"],
        summary["active"],
    )
    return summary


# ---------------------------------------------------------------------
# Read / acknowledge (drive the UI)
# ---------------------------------------------------------------------


def list_alerts(
    session: Session,
    *,
    site_id: Optional[Any] = None,
    include_resolved: bool = False,
    limit: int = 100,
) -> List[FederationAlert]:
    """List alerts, newest first.  Open-only by default."""
    stmt = select(FederationAlert)
    if site_id is not None:
        stmt = stmt.where(FederationAlert.site_id == site_id)
    if not include_resolved:
        stmt = stmt.where(FederationAlert.resolved.is_(False))
    stmt = stmt.order_by(FederationAlert.triggered_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars().all())


def acknowledge_alert(session: Session, alert_id: Any) -> Optional[FederationAlert]:
    """Mark an alert acknowledged.  Returns the row, or None if missing."""
    alert = session.get(FederationAlert, alert_id)
    if alert is None:
        return None
    alert.acknowledged = True
    alert.acknowledged_at = _utcnow_naive()
    return alert


def prune_resolved_alerts(session: Session, *, older_than_days: int = 30) -> int:
    """Delete resolved alerts older than ``older_than_days`` (retention).
    Returns the number removed.  Cross-dialect plain ORM delete."""
    from sqlalchemy import delete  # pylint: disable=import-outside-toplevel

    cutoff = _utcnow_naive() - timedelta(days=older_than_days)
    result = session.execute(
        delete(FederationAlert).where(
            FederationAlert.resolved.is_(True),
            FederationAlert.resolved_at < cutoff,
        )
    )
    return result.rowcount or 0
