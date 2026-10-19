# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Hardware health (Phase 23.1 S2): store an agent's report, remember what
changed, and say how each host stands.

A report is the whole current picture (the agent sends it when a component's
state changes, else every 15 minutes).  Storing it:

* each component's row is created or updated; a STATE CHANGE -- or a new
  component that is not ok -- adds a ``hardware_event``, so an unchanged
  report adds nothing and the history is a list of things that happened;
* a component that is no longer reported is removed with a ``gone`` event
  when it was a drive, array or pool (a failed drive often just drops off
  the bus) or was not ok -- unless the source that reported it FAILED this
  time, in which case it is kept: a broken ``smartctl`` is not a drive
  pulled out;
* the host keeps the worst state, when, and each source's status;
* a report the operating system TRIGGERED (S3: the kernel log, devd or the
  Windows System log announced a hardware problem) carries the evidence
  lines: each category in it (storage, thermal, memory, power) becomes one
  ``system`` event, its distinct lines as reasons -- whether or not any
  component's state changed, because an I/O error is news on its own.

How a host stands (``host_status``): its worst component state -- or
``unmeasured`` (never reported: an agent too old, or not connected) or
``stale`` (no report for an hour; reports come every 15 minutes) -- never
``ok`` without a recent report saying so.

Everything from the agent is validated and capped: kinds and states from a
fixed set, strings and lists bounded, metrics scalar.  Reasons stay codes
with parameters; the UI words them.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import hardware_temperature_limit as temperature_limit

logger = logging.getLogger(__name__)

KINDS = ("drive", "array", "pool", "sensor", "memory")
STATES = ("ok", "unknown", "warning", "failed")
_RANK = {state: i for i, state in enumerate(STATES)}
GONE = "gone"
# Kinds whose disappearance is itself news (a failed drive leaves the bus).
_GONE_MATTERS = ("drive", "array", "pool")
# Host statuses beyond a component state, worst first in the fleet view.
STATUS_ORDER = ("failed", "warning", "stale", "unknown", "unmeasured", "ok")
STALE_AFTER = timedelta(hours=1)

EVIDENCE_CATEGORIES = ("storage", "thermal", "memory", "power")
SYSTEM = "system"  # the kind of an event the operating system announced
MAX_EVIDENCE = 20

MAX_COMPONENTS = 1000
MAX_SOURCES = 64
MAX_REASONS = 20
MAX_METRICS = 64
_SCALARS = (str, int, float, bool)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _text(value: Any, limit: int) -> Optional[str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    return value.strip()[:limit] or None if isinstance(value, str) else None


def _param(value: Any) -> Any:
    if isinstance(value, str):
        return value[:255]
    if isinstance(value, _SCALARS) or value is None:
        return value
    if isinstance(value, list):
        return [_param(v) for v in value[:16] if isinstance(v, _SCALARS)]
    return None


def clean_reasons(value: Any) -> List[Dict[str, Any]]:
    """``[{"code": ..., params}]``, codes bounded; anything else dropped."""
    out = []
    for item in value[:MAX_REASONS] if isinstance(value, list) else []:
        code = _text(item.get("code"), 64) if isinstance(item, dict) else None
        if code:
            params = {str(k)[:32]: _param(v) for k, v in item.items() if k != "code"}
            out.append({"code": code, **params})
    return out


def _metrics(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    items = list(value.items())[:MAX_METRICS]
    return {
        str(k)[:64]: (v[:255] if isinstance(v, str) else v)
        for k, v in items
        if isinstance(v, _SCALARS)
    }


def clean_component(value: Any) -> Optional[Dict[str, Any]]:
    """One reported component, validated -- or None to drop it."""
    if not isinstance(value, dict):
        return None
    kind, state = value.get("kind"), value.get("state")
    ident = _text(value.get("id"), 255)
    if kind not in KINDS or state not in STATES or not ident:
        return None
    return {
        "kind": kind,
        "ident": ident,
        "name": _text(value.get("name"), 255) or ident,
        "state": state,
        "reasons": clean_reasons(value.get("reasons")),
        "metrics": _metrics(value.get("metrics")),
        "source": _text(value.get("source"), 64),
    }


def clean_sources(value: Any) -> List[Dict[str, Any]]:
    out = []
    for item in value[:MAX_SOURCES] if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        name, status = _text(item.get("name"), 64), item.get("status")
        if name and status in ("ran", "absent", "failed"):
            entry = {"name": name, "status": status}
            detail = _text(item.get("detail"), 300)
            if detail:
                entry["detail"] = detail
            out.append(entry)
    return out


def clean_evidence(value: Any) -> Dict[str, List[Dict[str, Any]]]:
    """``{category: [reason]}`` from a triggered report's evidence lines."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for item in value[:MAX_EVIDENCE] if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        category, text = item.get("category"), _text(item.get("text"), 500)
        if category not in EVIDENCE_CATEGORIES or not text:
            continue
        out.setdefault(category, []).append(
            {
                "code": f"os_{category}_event",
                "source": _text(item.get("source"), 32),
                "text": text,
            }
        )
    return out


def _evidence_events(host, evidence, now) -> List[models.HardwareEvent]:
    return [
        _event(
            host.id,
            {"kind": SYSTEM, "ident": category, "name": category},
            None,
            "warning",
            reasons,
            now,
        )
        for category, reasons in evidence.items()
    ]


def worst(states) -> str:
    return max(states, key=lambda s: _RANK.get(s, 0), default="unknown")


def _event(host_id, comp, from_state, to_state, reasons, now) -> models.HardwareEvent:
    return models.HardwareEvent(
        id=uuid.uuid4(),
        host_id=host_id,
        kind=comp["kind"],
        ident=comp["ident"],
        name=comp["name"],
        from_state=from_state,
        to_state=to_state,
        reasons=json.dumps(reasons),
        occurred_at=now,
    )


# A temperature that crossed its limit stays a warning until it falls this far
# below it.  Without the band a laptop idling at its "high" mark flipped
# Warning <-> Healthy on every report -- dozens of events a night, each a
# one-degree wobble (2026-10-19).
SENSOR_HYSTERESIS_C = 5.0


def _with_hysteresis(comp, row) -> Dict[str, Any]:
    """``comp``, held at warning if it is a sensor still inside the band."""
    if row is None or row.state != "warning" or comp["state"] != "ok":
        return comp
    temp, high = comp["metrics"].get("temperature_c"), comp["metrics"].get("high_c")
    if comp["kind"] != "sensor" or not all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in (temp, high)
    ):
        return comp
    if temp <= high - SENSOR_HYSTERESIS_C:
        return comp
    held = dict(comp, state="warning")
    held["reasons"] = _loads(row.reasons, []) or comp["reasons"]
    return held


def _upsert(db, host, comp, row, now) -> Optional[models.HardwareEvent]:
    """Store one component; the event its change makes, if any."""
    reasons = json.dumps(comp["reasons"])
    if row is None:
        db.add(
            models.HardwareComponent(
                id=uuid.uuid4(), host_id=host.id, kind=comp["kind"],
                ident=comp["ident"], name=comp["name"], state=comp["state"],
                reasons=reasons, metrics=json.dumps(comp["metrics"]),
                source=comp["source"], first_seen_at=now, last_seen_at=now,
                state_since=now,
            )
        )  # fmt: skip
        if comp["state"] == "ok":
            return None  # healthy on arrival is not news
        return _event(host.id, comp, None, comp["state"], comp["reasons"], now)
    changed = row.state != comp["state"]
    previous = row.state
    row.name, row.reasons, row.source = comp["name"], reasons, comp["source"]
    row.metrics, row.last_seen_at = json.dumps(comp["metrics"]), now
    if not changed:
        return None
    row.state, row.state_since = comp["state"], now
    return _event(host.id, comp, previous, comp["state"], comp["reasons"], now)


def _gone(db, host, rows, reported, failed_sources, now) -> List[models.HardwareEvent]:
    """Rows no longer reported: removed, with an event when that matters --
    kept when the source that reported them failed this time."""
    events = []
    for key, row in rows.items():
        if key in reported or row.source in failed_sources:
            continue
        if row.kind in _GONE_MATTERS or row.state != "ok":
            comp = {"kind": row.kind, "ident": row.ident, "name": row.name}
            events.append(_event(host.id, comp, row.state, GONE, [], now))
        db.delete(row)
    return events


def _components(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The report's valid components, first of each (kind, id) only."""
    raw = payload.get("components")
    seen, out = set(), []
    for value in raw[:MAX_COMPONENTS] if isinstance(raw, list) else []:
        comp = clean_component(value)
        if comp is None or (comp["kind"], comp["ident"]) in seen:
            continue  # invalid, or a duplicate in one report: the first wins
        seen.add((comp["kind"], comp["ident"]))
        out.append(comp)
    return out


def apply_report(
    db: Session,
    host: models.Host,
    payload: Dict[str, Any],
    now: Optional[datetime] = None,
) -> List[models.HardwareEvent]:
    """Store a hardware health report for ``host``; the events it made.
    The caller commits."""
    now = now or _now()
    sources = clean_sources(payload.get("sources"))
    failed = {s["name"] for s in sources if s["status"] == "failed"}
    rows = {
        (r.kind, r.ident): r
        for r in db.query(models.HardwareComponent).filter(
            models.HardwareComponent.host_id == host.id
        )
    }
    limit = host.hardware_temp_warning_c
    components = [
        _with_hysteresis(
            temperature_limit.apply_limit(c, limit), rows.get((c["kind"], c["ident"]))
        )
        for c in _components(payload)
    ]
    events = [
        event
        for event in (
            _upsert(db, host, c, rows.get((c["kind"], c["ident"])), now)
            for c in components
        )
        if event is not None
    ]
    reported = {(c["kind"], c["ident"]) for c in components}
    events += _gone(db, host, rows, reported, failed, now)
    events += _evidence_events(host, clean_evidence(payload.get("evidence")), now)
    for event in events:
        db.add(event)
    host.hardware_state = (
        worst(c["state"] for c in components) if components else "unknown"
    )
    host.hardware_reported_at = now
    host.hardware_sources = json.dumps(sources)
    return events


def host_status(host: models.Host, now: Optional[datetime] = None) -> str:
    """failed / warning / unknown / ok -- or unmeasured / stale."""
    if host.hardware_reported_at is None:
        return "unmeasured"
    if (now or _now()) - host.hardware_reported_at > STALE_AFTER:
        return "stale"
    return host.hardware_state or "unknown"


def _loads(text: Optional[str], default):
    try:
        value = json.loads(text) if text else default
    except ValueError:
        return default
    return value if isinstance(value, type(default)) else default


def component_view(row: models.HardwareComponent) -> Dict[str, Any]:
    return {
        "kind": row.kind,
        "id": row.ident,
        "name": row.name,
        "state": row.state,
        "reasons": _loads(row.reasons, []),
        "metrics": _loads(row.metrics, {}),
        "source": row.source,
        "state_since": row.state_since.isoformat() if row.state_since else None,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
    }


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def event_view(row: models.HardwareEvent) -> Dict[str, Any]:
    iso = _iso
    return {
        "id": str(row.id),
        "host_id": str(row.host_id),
        "kind": row.kind,
        "component_id": row.ident,
        "name": row.name,
        "from_state": row.from_state,
        "to_state": row.to_state,
        "reasons": _loads(row.reasons, []),
        "occurred_at": iso(row.occurred_at),
        "acknowledged_at": iso(row.acknowledged_at),
        "acknowledged_by": row.acknowledged_by,
        "resolved_at": iso(row.resolved_at),
        "resolved_by": row.resolved_by,
        "note": row.note,
    }


def _component_order(row: models.HardwareComponent) -> Tuple[int, str, str]:
    return (-_RANK.get(row.state, 0), row.kind, row.ident)


def host_view(db: Session, host: models.Host, event_limit: int = 50) -> Dict[str, Any]:
    rows = (
        db.query(models.HardwareComponent)
        .filter(models.HardwareComponent.host_id == host.id)
        .all()
    )
    events = (
        db.query(models.HardwareEvent)
        .filter(models.HardwareEvent.host_id == host.id)
        .order_by(models.HardwareEvent.occurred_at.desc())
        .limit(event_limit)
        .all()
    )
    return {
        "status": host_status(host),
        "reported_at": (
            host.hardware_reported_at.isoformat() if host.hardware_reported_at else None
        ),
        "sources": _loads(host.hardware_sources, []),
        "temperature_limit_c": host.hardware_temp_warning_c,
        "components": [component_view(r) for r in sorted(rows, key=_component_order)],
        "events": [event_view(e) for e in events],
    }


def counts_by_host(db: Session, host_ids) -> Dict[str, Dict[str, int]]:
    """{host_id: {state: n}} over the hosts' components."""
    out: Dict[str, Dict[str, int]] = {}
    if not host_ids:
        return out
    for host_id, state in db.query(
        models.HardwareComponent.host_id, models.HardwareComponent.state
    ).filter(models.HardwareComponent.host_id.in_(host_ids)):
        bucket = out.setdefault(str(host_id), {})
        bucket[state] = bucket.get(state, 0) + 1
    return out


def problems_by_host(db: Session, host_ids, per_host: int = 3) -> Dict[str, List]:
    """The worst few components of each host that are not ok."""
    out: Dict[str, List] = {}
    if not host_ids:
        return out
    rows = (
        db.query(models.HardwareComponent)
        .filter(
            models.HardwareComponent.host_id.in_(host_ids),
            models.HardwareComponent.state.in_(("failed", "warning")),
        )
        .all()
    )
    for row in sorted(rows, key=_component_order):
        bucket = out.setdefault(str(row.host_id), [])
        if len(bucket) < per_host:
            bucket.append(component_view(row))
    return out


def _open_event(db: Session, event_id: str) -> Optional[models.HardwareEvent]:
    try:
        key = uuid.UUID(str(event_id))
    except ValueError:
        return None
    return db.query(models.HardwareEvent).filter(models.HardwareEvent.id == key).first()


def acknowledge(db: Session, event_id: str, user: str, note: Optional[str] = None):
    event = _open_event(db, event_id)
    if event is None or event.acknowledged_at is not None:
        return event
    event.acknowledged_at, event.acknowledged_by = _now(), user
    if note:
        event.note = note[:500]
    return event


def resolve(db: Session, event_id: str, user: str, note: Optional[str] = None):
    event = _open_event(db, event_id)
    if event is None or event.resolved_at is not None:
        return event
    event.resolved_at, event.resolved_by = _now(), user
    if event.acknowledged_at is None:
        event.acknowledged_at, event.acknowledged_by = event.resolved_at, user
    if note:
        event.note = note[:500]
    return event
