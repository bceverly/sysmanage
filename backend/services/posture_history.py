# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The punch list over time: what changed, and why (ROADMAP 21.4 S6).

The punch list is recomputed every advisor tick (S3), and every state change
is a ``posture_item_event`` with its CAUSE. This module turns those events
into answers an operator can act on:

* a **regression** is an item that was satisfied and is open again BECAUSE
  THE FLEET CHANGED -- never because the wizard was re-run (that is a model
  change, reported as one);
* a **blind spot** is an item that could no longer be assessed -- worth
  seeing, never a quiet pass;
* a model diff says what changed between two threat-model versions AND what
  that change did to the punch list, as ROADMAP 21.4 asks.
"""

from typing import Any, Dict, List, Optional

from backend.persistence import models
from backend.services import posture_service as posture

KIND_REGRESSION = "regression"
KIND_RESOLVED = "resolved"
KIND_BLIND_SPOT = "blind_spot"
KIND_MEASURED = "measured_again"
KIND_ADDED = "added"
KIND_REMOVED = "removed"
KIND_ADDED_BY_MODEL = "added_by_model"
KIND_REMOVED_BY_MODEL = "removed_by_model"
KIND_MODEL_CHANGE = "changed_by_model"
KIND_WITHDRAWN = "withdrawn"
KIND_REMEDIATION = "remediation_requested"
KIND_CHANGED = "changed"


def _appearance(event) -> Optional[str]:
    """An item appearing or leaving the list, or None for a state change."""
    by_model = event.cause == posture.CAUSE_THREAT_MODEL
    if not event.from_state:
        return KIND_ADDED_BY_MODEL if by_model else KIND_ADDED
    if not event.to_state:
        if event.cause == posture.CAUSE_RULE_WITHDRAWN:
            return KIND_WITHDRAWN
        return KIND_REMOVED_BY_MODEL if by_model else KIND_REMOVED
    return None


def classify(event) -> str:
    """What one event MEANS. Order matters: a remediation request and a
    model-caused change are named before any fleet-caused transition, so a
    re-run wizard can never be reported as a regression."""
    if event.cause == "remediation_requested":
        return KIND_REMEDIATION
    appearance = _appearance(event)
    if appearance:
        return appearance
    if event.cause == posture.CAUSE_THREAT_MODEL:
        return KIND_MODEL_CHANGE
    if event.to_state == models.POSTURE_NOT_ASSESSABLE:
        return KIND_BLIND_SPOT
    if event.from_state == models.POSTURE_NOT_ASSESSABLE:
        return KIND_MEASURED
    if (event.from_state, event.to_state) == (
        models.POSTURE_SATISFIED,
        models.POSTURE_OPEN,
    ):
        return KIND_REGRESSION
    if (event.from_state, event.to_state) == (
        models.POSTURE_OPEN,
        models.POSTURE_SATISFIED,
    ):
        return KIND_RESOLVED
    return KIND_CHANGED


def _scoped_events(db):
    return db.query(models.PostureItemEvent).filter(
        models.PostureItemEvent.scope_kind == posture.SCOPE["scope_kind"],
        models.PostureItemEvent.scope_ref == posture.SCOPE["scope_ref"],
    )


def event_dict(event) -> Dict[str, Any]:
    return {
        "rule_key": event.rule_key,
        "kind": classify(event),
        "from_state": event.from_state,
        "to_state": event.to_state,
        "cause": event.cause,
        "threat_model_version": event.threat_model_version,
        "at": event.at.isoformat() if event.at else None,
    }


def history(
    db, rule_key: Optional[str] = None, limit: int = 200
) -> List[Dict[str, Any]]:
    """Newest first; one item's timeline when ``rule_key`` is given."""
    query = _scoped_events(db)
    if rule_key:
        query = query.filter(models.PostureItemEvent.rule_key == rule_key)
    rows = query.order_by(models.PostureItemEvent.at.desc()).limit(
        max(1, min(limit, 1000))
    )
    return [event_dict(e) for e in rows]


def regressed_keys(db) -> set:
    """Items whose LATEST state change was a regression: open again because
    the fleet moved, not because anyone changed the model."""
    latest: Dict[str, Any] = {}
    for event in _scoped_events(db).order_by(models.PostureItemEvent.at.asc()):
        if event.cause != "remediation_requested":
            latest[event.rule_key] = event
    return {key for key, e in latest.items() if classify(e) == KIND_REGRESSION}


def _version(db, number: int):
    return (
        db.query(models.ThreatModel)
        .filter(
            models.ThreatModel.scope_kind == posture.SCOPE["scope_kind"],
            models.ThreatModel.scope_ref == posture.SCOPE["scope_ref"],
            models.ThreatModel.model_version == number,
        )
        .first()
    )


def model_diff(
    engine, db, from_version: int, to_version: int
) -> Optional[Dict[str, Any]]:
    """What changed between two saved models, and what that did to the list:
    the events the NEWER model caused on its first evaluation. None when
    either version does not exist."""
    old, new = _version(db, from_version), _version(db, to_version)
    if old is None or new is None:
        return None
    events = (
        _scoped_events(db)
        .filter(
            models.PostureItemEvent.threat_model_version == to_version,
            models.PostureItemEvent.cause == posture.CAUSE_THREAT_MODEL,
        )
        .order_by(models.PostureItemEvent.rule_key)
    )
    return {
        "from_version": from_version,
        "to_version": to_version,
        "model": engine.diff_threat_models(
            posture.model_dict(old), posture.model_dict(new)
        ),
        "punch_list": [event_dict(e) for e in events],
    }
