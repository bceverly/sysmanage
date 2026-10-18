# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The scheduled compliance scan (ROADMAP 24.4).

Scans used to run only when someone opened a host's Compliance tab or clicked
Run scan, so a host nobody opened showed "Not scanned" (milsurpmonitor,
2026-10-18) and a fixed setting stayed failed until someone looked.  Every
``TICK_INTERVAL_SECONDS``, in EVERY host database (scans and evidence live in
each tenant's own database), this scans each approved, active host that:

* has never been scanned,
* reported compliance evidence newer than its latest scan (the agent sends
  it when what the checks read changes -- so a fix shows within one tick), or
* was last scanned more than ``RESCAN_AFTER`` ago (packages and users change
  without new evidence).

At most ``MAX_SCANS_PER_PASS`` per database per pass, never-scanned first,
then the stalest.  Scan history older than ``SCAN_RETENTION_DAYS`` is pruned,
keeping each host's latest.  Started from ``background_ticks`` only when the
``compliance_engine`` is loaded (licensed); a pass is a no-op without it.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import iter_host_databases
from backend.startup.leadership import singleton_task
from backend.startup.tick_runner import run_periodic

logger = logging.getLogger(__name__)

ENGINE_CODE = "compliance_engine"
TICK_INTERVAL_SECONDS = 300
ERROR_BACKOFF_SECONDS = 60
RESCAN_AFTER = timedelta(hours=24)
MAX_SCANS_PER_PASS = 200
SCAN_RETENTION_DAYS = 180

_TASK: Optional[asyncio.Task] = None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def engine():
    """The loaded compliance engine, or None (unlicensed or not loaded)."""
    return module_loader.get_module(ENGINE_CODE)


def _scanner(loaded):
    """The engine's scan entry point: ``scan_host_compliance`` (24.4), else
    the service an older engine exposes; None when neither exists."""
    scan = getattr(loaded, "scan_host_compliance", None)
    if callable(scan):
        return scan
    service = getattr(loaded, "_compliance_service", None)
    return getattr(service, "scan_host", None)


def due_hosts(db: Session, now: datetime, limit: int = MAX_SCANS_PER_PASS) -> List[Any]:
    """Approved, active hosts due a scan: never scanned first, then the
    stalest (oldest scan, or evidence newer than the scan)."""
    latest = (
        db.query(
            models.HostComplianceScan.host_id.label("host_id"),
            func.max(models.HostComplianceScan.scanned_at).label("scanned_at"),
        )
        .group_by(models.HostComplianceScan.host_id)
        .subquery()
    )
    rows = (
        db.query(
            models.Host.id,
            latest.c.scanned_at,
            models.HostComplianceEvidence.received_at,
        )
        .outerjoin(latest, latest.c.host_id == models.Host.id)
        .outerjoin(
            models.HostComplianceEvidence,
            models.HostComplianceEvidence.host_id == models.Host.id,
        )
        .filter(models.Host.active.is_(True))
        .filter(models.Host.approval_status == "approved")
        .all()
    )
    cutoff = now - RESCAN_AFTER
    due = [
        (scanned_at or datetime.min, host_id)
        for host_id, scanned_at, received_at in rows
        if scanned_at is None
        or scanned_at < cutoff
        or (received_at is not None and received_at > scanned_at)
    ]
    due.sort(key=lambda item: item[0])
    return [host_id for _when, host_id in due[:limit]]


def prune_history(db: Session, now: datetime) -> int:
    """Delete scans older than the retention window, never a host's latest."""
    cutoff = now - timedelta(days=SCAN_RETENTION_DAYS)
    scans = models.HostComplianceScan
    newest = dict(
        db.query(scans.host_id, func.max(scans.scanned_at))
        .group_by(scans.host_id)
        .all()
    )
    stale = [
        scan_id
        for scan_id, host_id, scanned_at in db.query(
            scans.id, scans.host_id, scans.scanned_at
        ).filter(scans.scanned_at < cutoff)
        if scanned_at != newest.get(host_id)
    ]
    for start in range(0, len(stale), 500):
        db.query(scans).filter(scans.id.in_(stale[start : start + 500])).delete(
            synchronize_session=False
        )
    return len(stale)


def scan_database(db: Session, label: str, scan, now: datetime) -> Dict[str, int]:
    """Scan this database's due hosts; counts.  One host's failure is
    logged and skipped, never the rest."""
    scanned = failed = 0
    for host_id in due_hosts(db, now):
        try:
            scan(str(host_id), db, models)
            scanned += 1
        except Exception:  # pylint: disable=broad-except
            failed += 1
            db.rollback()
            logger.exception(
                "scheduled compliance scan failed for host %s in %s", host_id, label
            )
    return {"scanned": scanned, "failed": failed}


def run_one_tick(now: Optional[datetime] = None) -> Dict[str, Any]:
    """One pass over every host database.  Never raises."""
    scan = _scanner(engine())
    if scan is None:
        return {"scanned": 0, "failed": 0, "engine": False}
    now = now or _now()
    totals = {"scanned": 0, "failed": 0, "pruned": 0, "engine": True}
    for label, _tenant, db in iter_host_databases():
        try:
            counts = scan_database(db, label, scan, now)
            totals["scanned"] += counts["scanned"]
            totals["failed"] += counts["failed"]
            totals["pruned"] += prune_history(db, now)
            db.commit()
        except Exception:  # pylint: disable=broad-except
            logger.exception("scheduled compliance scan pass failed for %s", label)
            db.rollback()
        finally:
            db.close()
    if totals["scanned"] or totals["failed"]:
        logger.info(
            "Scheduled compliance scans: %d scanned, %d failed",
            totals["scanned"], totals["failed"],
        )  # fmt: skip
    return totals


async def compliance_scan_tick_service() -> None:
    """Background service: one pass every ``TICK_INTERVAL_SECONDS``."""
    await run_periodic(
        "Compliance scan tick",
        run_one_tick,
        TICK_INTERVAL_SECONDS,
        ERROR_BACKOFF_SECONDS,
        logger=logger,
    )


def start_if_licensed():
    """Start the tick when the engine is loaded; the task or None. Never fatal."""
    global _TASK  # pylint: disable=global-statement
    if engine() is None:
        return None
    if _TASK is not None and not _TASK.done():
        return _TASK
    try:
        _TASK = singleton_task(compliance_scan_tick_service())
        logger.info("Scheduled compliance scan tick started")
        return _TASK
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Compliance scan tick did not start: %s", exc)
        return None
