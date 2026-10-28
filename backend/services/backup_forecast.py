# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Capacity forecasting for the backup target (ROADMAP 24.6, Pro+).

The server gathers what it already records -- bytes the last 30 days of
captures added (each snapshot's ``new_bytes``), bytes that period's prunes
freed (each pruned snapshot's ``unique_bytes`` from restate's du), and the
filesystem under the storage path -- and the Pro+ backup engine turns them
into a growth rate and the days until the target's warning and critical
marks.  None without the engine, or without enough history.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.persistence import models

logger = logging.getLogger(__name__)

PERIOD_DAYS = 30


def _engine():
    # pylint: disable=import-outside-toplevel
    from backend.licensing.module_loader import module_loader  # noqa: PLC0415

    engine = module_loader.get_module("backup_engine")
    return (
        engine if engine is not None and hasattr(engine, "capacity_forecast") else None
    )


def inputs(db: Session, target: models.BackupTarget, now: datetime) -> Dict[str, Any]:
    """``{"written", "freed", "days"}`` over the last PERIOD_DAYS (fewer when
    the target's first snapshot is newer)."""
    since = now - timedelta(days=PERIOD_DAYS)
    snapshot = models.BackupSnapshot
    policies = db.query(models.BackupPolicy.id).filter(
        models.BackupPolicy.target_id == target.id
    )
    first = (
        db.query(func.min(snapshot.created_at))
        .filter(snapshot.policy_id.in_(policies))
        .scalar()
    )
    written = (
        db.query(func.coalesce(func.sum(snapshot.new_bytes), 0))
        .filter(snapshot.policy_id.in_(policies), snapshot.created_at >= since)
        .scalar()
    )
    freed = (
        db.query(func.coalesce(func.sum(snapshot.unique_bytes), 0))
        .filter(snapshot.policy_id.in_(policies), snapshot.gone_at >= since)
        .scalar()
    )
    start = max(since, first) if first else now
    return {
        "written": int(written or 0),
        "freed": int(freed or 0),
        "days": max(0, (now - start).days),
    }


def for_target(
    db: Session,
    target: models.BackupTarget,
    health: Optional[Dict[str, Any]],
    now: datetime,
) -> Optional[Dict[str, Any]]:
    """The engine's forecast for this target, or None."""
    engine = _engine()
    space = (health or {}).get("space") or {}
    if engine is None or not space.get("total_bytes"):
        return None
    found = inputs(db, target, now)
    try:
        return engine.capacity_forecast(
            found["written"],
            found["freed"],
            found["days"],
            space.get("total_bytes"),
            space.get("available_bytes"),
            (health or {}).get("space_low_percent", 85),
            (health or {}).get("space_critical_percent", 95),
        )
    except Exception:  # pylint: disable=broad-except
        logger.warning("Backup capacity forecast failed", exc_info=True)
        return None
