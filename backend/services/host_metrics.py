# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Built-in host metrics (Phase 21.5): history for numbers the agent already
reports, without anyone writing a script.

The five series are stored as SYSTEM-DEFINED custom metrics -- rows in
``custom_metric`` with a ``builtin_key``, no script and no tags -- so
everything custom metrics already has applies to them unchanged: the
retention prune (``custom_metrics_retention_days``), the samples API, the
Prometheus exporter and alerting's ``custom_metric`` condition.  Because they
have no tags, the tag-driven deploy in ``observability_engine`` never ships
them to an agent.

Resolution (decided 2026-09-28, see ROADMAP 21.5): the agent reports every
periodic run (~5 minutes); the server keeps ONE sample per series per 15
minutes.  At 259 B/row that is ~124 MB/day per 1,000 hosts.

Two gates, both deliberate:

* storing only happens while ``observability_engine`` is loaded (licensed) --
  an unlicensed install must not quietly accumulate rows nobody can view;
* a built-in an operator has DISABLED stops collecting, the same switch
  every custom metric has.
"""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from backend.licensing.module_loader import module_loader
from backend.persistence.models.custom_metric import (
    SAMPLE_STATUS_OK,
    CustomMetric,
    CustomMetricSample,
)

logger = logging.getLogger(__name__)

ENGINE = "observability_engine"

# Keep the keys in step with the agent's host_metrics_collection.py.  ``name``
# is the key itself: it is what the Prometheus ``metric`` label carries, and
# the UI shows a translated title looked up by ``builtin_key``.
BUILTINS: List[Dict[str, Any]] = [
    {"key": "host.cpu_percent", "unit": "%", "description": "CPU usage"},
    {"key": "host.memory_used_percent", "unit": "%", "description": "Memory used"},
    {"key": "host.swap_used_percent", "unit": "%", "description": "Swap used"},
    {"key": "host.load_1m", "unit": None, "description": "Load average (1 minute)"},
    {
        "key": "host.disk_used_percent_max",
        "unit": "%",
        "description": "Disk used (fullest local filesystem)",
    },
]
BUILTIN_KEYS = frozenset(b["key"] for b in BUILTINS)

STORE_INTERVAL = timedelta(minutes=15)
# The agent reports every ~5 minutes with some jitter; a sample that arrives
# a minute early must not be dropped and push the gap to 20 minutes.
_STORE_SLACK = timedelta(minutes=1)
BUILTIN_CADENCE_SECONDS = int(STORE_INTERVAL.total_seconds())
BUILTIN_INTERPRETER = "builtin"


def collecting() -> bool:
    """Whether built-in samples are stored at all on this server."""
    return module_loader.is_module_loaded(ENGINE)


def _create_builtin(db, spec) -> Optional[CustomMetric]:
    """Create one built-in row; ``None`` if its name is already taken by an
    operator's own metric (logged loudly -- we never adopt a user's script)."""
    clash = (
        db.query(CustomMetric)
        .filter(CustomMetric.name == spec["key"], CustomMetric.builtin_key.is_(None))
        .first()
    )
    if clash is not None:
        logger.warning(
            "built-in metric %s NOT created: an operator-defined custom metric "
            "(id=%s) already uses that name; rename it to collect this series",
            spec["key"],
            clash.id,
        )
        return None
    row = CustomMetric(
        name=spec["key"],
        description=spec["description"],
        script="",
        interpreter=BUILTIN_INTERPRETER,
        unit=spec["unit"],
        cadence_seconds=BUILTIN_CADENCE_SECONDS,
        enabled=True,
        builtin_key=spec["key"],
    )
    try:
        with db.begin_nested():
            db.add(row)
        return row
    except IntegrityError:
        # A concurrent message created it first: use theirs.
        return (
            db.query(CustomMetric)
            .filter(CustomMetric.builtin_key == spec["key"])
            .first()
        )


def ensure_builtin_metrics(db) -> Dict[str, CustomMetric]:
    """``{builtin_key: CustomMetric}``, creating any that are missing.

    Built-ins live in each tenant's database (custom metrics are tenant
    data), so they are created lazily the first time a host in that tenant
    reports rather than by a migration that would have to know every tenant.
    """
    existing = {
        m.builtin_key: m
        for m in db.query(CustomMetric).filter(CustomMetric.builtin_key.isnot(None))
    }
    for spec in BUILTINS:
        if spec["key"] not in existing:
            row = _create_builtin(db, spec)
            if row is not None:
                existing[spec["key"]] = row
    return existing


def _parse_time(raw: Any) -> datetime:
    if isinstance(raw, str) and raw:
        try:
            parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _last_stored(db, host_id, metric_ids) -> Dict[Any, datetime]:
    rows = (
        db.query(
            CustomMetricSample.custom_metric_id,
            func.max(CustomMetricSample.collected_at),
        )
        .filter(
            CustomMetricSample.host_id == host_id,
            CustomMetricSample.custom_metric_id.in_(metric_ids),
        )
        .group_by(CustomMetricSample.custom_metric_id)
        .all()
    )
    out = {}
    for metric_id, at in rows:
        if at is not None and at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)  # SQLite drops the zone
        out[metric_id] = at
    return out


def _numeric(value) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None  # NaN / inf are not readings


def store_host_metrics(db, host_id, payload: Dict[str, Any]) -> int:
    """Store the due samples from one ``host_metrics`` report; returns how many.

    A series is due when its last stored sample is at least 15 minutes (less
    a minute of slack) older than this report.  Unknown keys and non-numeric
    values are ignored; a disabled built-in is skipped.  The caller commits.
    """
    readings = payload.get("metrics")
    if not isinstance(readings, dict) or not readings:
        return 0
    collected_at = _parse_time(payload.get("collected_at"))
    builtins = ensure_builtin_metrics(db)
    wanted = {
        builtins[key]: _numeric(value)
        for key, value in readings.items()
        if key in builtins and builtins[key].enabled
    }
    wanted = {metric: value for metric, value in wanted.items() if value is not None}
    if not wanted:
        return 0
    last = _last_stored(db, host_id, [m.id for m in wanted])
    stored = 0
    for metric, value in wanted.items():
        previous = last.get(metric.id)
        if (
            previous is not None
            and collected_at - previous < STORE_INTERVAL - _STORE_SLACK
        ):
            continue
        db.add(
            CustomMetricSample(
                custom_metric_id=metric.id,
                host_id=host_id,
                value=value,
                status=SAMPLE_STATUS_OK,
                collected_at=collected_at,
            )
        )
        stored += 1
    return stored
