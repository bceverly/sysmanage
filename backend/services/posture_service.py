# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The threat model and the posture punch list, per tenant (ROADMAP 21.4 S3).

* ``save_threat_model`` -- answers -> a NEW threat model version (never an
  overwrite: re-running the wizard must be able to say what changed).
  Derivation is the licensed engine's; this module stores it.
* ``evaluate`` -- the tenant's installation checks x its current threat model
  x the installation evidence -> ``posture_item`` rows, with an event for
  every state change so "what changed, and why" stays answerable (S6).

No current threat model means NO punch list, not an empty one: an empty list
reads as "nothing to do", and a tenant that has not answered the wizard has
told us nothing to judge against. Waivers are S4 (an overlay on open items).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.persistence import models
from backend.services import posture_evidence, posture_waivers, threat_model_catalog

logger = logging.getLogger(__name__)

QUESTIONNAIRE_SLUG = "sysmanage-threat-model"
SCOPE = {"scope_kind": models.SCOPE_TENANT, "scope_ref": ""}

CAUSE_EVALUATION = "evaluation"
CAUSE_THREAT_MODEL = "threat_model"
CAUSE_RULE_WITHDRAWN = "rule_withdrawn"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _scoped(query, model):
    return query.filter(
        model.scope_kind == SCOPE["scope_kind"], model.scope_ref == SCOPE["scope_ref"]
    )


def current_threat_model(db) -> Optional[models.ThreatModel]:
    return (
        _scoped(db.query(models.ThreatModel), models.ThreatModel)
        .filter(models.ThreatModel.is_current.is_(True))
        .first()
    )


def model_dict(row: Optional[models.ThreatModel]) -> Optional[Dict[str, Any]]:
    """A stored threat model in the shape the engine derived it."""
    if row is None:
        return None
    return {
        "questionnaire": row.questionnaire_slug,
        "questionnaire_version": row.questionnaire_version,
        "attributes": dict(row.attributes or {}),
        "answers": dict(row.answers or {}),
        "digest": row.digest,
        "complete": bool(row.complete),
        "missing": list(row.missing or []),
        "ignored": list(row.ignored or []),
    }


def save_threat_model(engine, db, answers: Dict[str, Any], user: str):
    """Derive and store a new version. Returns ``(row, diff)``; raises
    LookupError when the questionnaire catalog has no questionnaire yet."""
    questionnaire = threat_model_catalog.load_questionnaire(QUESTIONNAIRE_SLUG)
    if questionnaire is None:
        raise LookupError(QUESTIONNAIRE_SLUG)
    derived = engine.derive_threat_model(questionnaire, answers or {})
    previous = current_threat_model(db)
    last = (
        _scoped(db.query(models.ThreatModel), models.ThreatModel)
        .order_by(models.ThreatModel.model_version.desc())
        .first()
    )
    if previous is not None:
        previous.is_current = False
    row = models.ThreatModel(
        **SCOPE,
        model_version=(last.model_version + 1) if last else 1,
        is_current=True,
        questionnaire_slug=derived["questionnaire"],
        questionnaire_version=derived["questionnaire_version"],
        answers=derived["answers"],
        attributes=derived["attributes"],
        digest=derived["digest"],
        complete=derived["complete"],
        missing=derived["missing"],
        ignored=derived["ignored"],
        created_by=user,
        created_at=_now(),
    )
    db.add(row)
    db.flush()
    diff = engine.diff_threat_models(model_dict(previous), derived)
    return row, diff


def rule_definition(db, source: str, key: str) -> Optional[Dict[str, Any]]:
    """The installation rule behind an item, from wherever it lives."""
    if source == models.ADVISOR_RULE_SOURCE_TENANT:
        row = db.query(models.AdvisorRule).filter_by(rule_key=key).first()
        return dict(row.definition or {}, id=key) if row is not None else None
    from backend.services import advisor_tick  # noqa: PLC0415 - avoids an import cycle

    for entry in advisor_tick.load_shared_rules() or ():
        if entry["key"] == key:
            return entry["rule"]
    return None


def rules_by_key(db) -> Dict[str, Dict[str, Any]]:
    """Every installation rule this tenant could have an item for, by key --
    loaded ONCE (the punch list must not query the catalog per item)."""
    from backend.services import advisor_tick  # noqa: PLC0415 - avoids an import cycle

    out = {
        e["key"]: e["rule"]
        for e in advisor_tick.load_shared_rules() or ()
        if (e.get("rule") or {}).get("scope") == "installation"
    }
    for row in db.query(models.AdvisorRule).all():
        rule = dict(row.definition or {}, id=row.rule_key)
        if rule.get("scope") == "installation":
            out[row.rule_key] = rule
    return out


def installation_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        e for e in entries or () if (e.get("rule") or {}).get("scope") == "installation"
    ]


def _event(db, rule_key, before, after, cause, model_version, now) -> None:
    db.add(
        models.PostureItemEvent(
            **SCOPE,
            rule_key=rule_key,
            from_state=before,
            to_state=after,
            cause=cause,
            threat_model_version=model_version,
            at=now,
        )
    )


def _upsert(db, item, entry, result, state, model, now):
    """Write one item; returns ``(item, previous)`` -- the previous state when
    it CHANGED, else None (the empty string for a new item)."""
    previous = None
    if item is None:
        item = models.PostureItem(
            **SCOPE, rule_key=entry["key"], first_seen_at=now, state_changed_at=now
        )
        db.add(item)
        previous = ""
    elif item.state != state:
        previous = item.state
        item.state_changed_at = now
    item.rule_source = entry["source"]
    item.rule_version = result.get("rule_version")
    item.threat_model_id = model.id
    item.state = state
    item.outcome = result["outcome"]
    item.managed_by = result.get("managed_by") or "tenant"
    item.impact = result.get("impact")
    item.likelihood = result.get("likelihood")
    item.risk = result.get("risk")
    item.gaps = result.get("gaps") or []
    item.coverage = result.get("coverage")
    item.matches = result.get("matches") or []
    item.evaluated_at = now
    return item, previous


def _apply_result(engine, db, result, entry, item, run, out) -> bool:
    """Fold one engine verdict into the punch list; True when the rule still
    applies (so its item is kept)."""
    model, cause, now = run
    key = result.get("rule_id")
    state = engine.posture_state(result)
    if state is None:  # the threat model no longer applies this check
        if item is not None:
            _event(db, key, item.state, None, cause, model.model_version, now)
            db.delete(item)
            out["posture_changes"] += 1
        return False
    item, previous = _upsert(db, item, entry, result, state, model, now)
    # S4: a waiver granted on another basis stops covering the item.
    if posture_waivers.refresh_staleness(
        db, SCOPE, item, entry["rule"], model.attributes, now
    ):
        out["posture_stale_waivers"] = out.get("posture_stale_waivers", 0) + 1
    out["posture_items"] += 1
    if previous is not None:
        _event(db, key, previous or None, state, cause, model.model_version, now)
        out["posture_changes"] += 1
    return True


def evaluate(engine, db, tenant_id, entries, now=None, summary=None) -> Dict[str, Any]:
    """Recompute this tenant's punch list. The caller commits."""
    now = now or _now()
    out = summary if summary is not None else {}
    out.setdefault("posture_items", 0)
    out.setdefault("posture_changes", 0)
    model = current_threat_model(db)
    if model is None or not hasattr(engine, "evaluate_installation"):
        return out
    rules = installation_entries(entries)
    by_key = {e["key"]: e for e in rules}
    evidence = posture_evidence.gather(db, tenant_id, now)
    results = engine.evaluate_installation(
        [e["rule"] for e in rules], model_dict(model), evidence
    )
    items = {
        i.rule_key: i for i in _scoped(db.query(models.PostureItem), models.PostureItem)
    }
    # The first pass under a (re-)derived model: every change in it is the
    # model's doing, not the fleet's -- S6 must not report it as a regression.
    cause = (
        CAUSE_EVALUATION
        if any(i.threat_model_id == model.id for i in items.values())
        else CAUSE_THREAT_MODEL
    )
    seen = set()
    run = (model, cause, now)
    for result in results:
        key = result.get("rule_id")
        entry = by_key.get(key)
        if entry is None:
            continue
        if _apply_result(engine, db, result, entry, items.get(key), run, out):
            seen.add(key)
    evaluated = {r.get("rule_id") for r in results}
    for key, item in items.items():
        if key not in seen and key not in evaluated:
            # The check itself is gone (pack switched off, rule withdrawn).
            _event(
                db,
                key,
                item.state,
                None,
                CAUSE_RULE_WITHDRAWN,
                model.model_version,
                now,
            )
            db.delete(item)
            out["posture_changes"] += 1
    return out
