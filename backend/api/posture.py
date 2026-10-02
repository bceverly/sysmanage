# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The threat model, the posture punch list and its waivers (Phase 21.4 S3/S4).

Part of ``advisor_engine`` (Enterprise), so the whole router is license-gated,
like the advisor's. Derivation and evaluation are the engine's; this file owns
HTTP, persistence and authorization.

WHO MAY CHANGE IT
-----------------
Saving a threat model is a POLICY statement ("we hold health data, vendors
have access") that decides which obligations the installation is judged
against, and a waiver (S4) is an acceptance of risk: both need an
ADMINISTRATOR. Reading needs only an authenticated user, like the feed.

NO MODEL, NO LIST
-----------------
Until a threat model is saved the punch list is ABSENT (``threat_model:
null``, ``items: []``) and the UI sends the operator to the wizard -- never an
empty list that reads as "nothing to do".
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.feature_gate import require_module_loaded
from backend.licensing.features import ModuleCode
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.services import posture_history as history
from backend.services import posture_remedies as remedies
from backend.services import posture_service as posture
from backend.services import posture_waivers as waivers
from backend.services import threat_model_catalog

logger = logging.getLogger(__name__)

_REMEDY_CONFLICT_CODES = {
    code: code
    for code in (
        remedies.UNAVAILABLE_UNKNOWN,
        remedies.UNAVAILABLE_NOT_AUTOMATED,
        remedies.UNAVAILABLE_NOT_OPEN,
        remedies.UNAVAILABLE_SERVER_MANAGED,
        remedies.UNAVAILABLE_NOTHING_TO_DO,
    )
}

router = APIRouter(
    dependencies=[
        Depends(JWTBearer()),
        Depends(require_module_loaded(ModuleCode.ADVISOR_ENGINE)),
    ]
)


class WaiverRequest(BaseModel):
    """Why the risk is accepted -- required, and kept with the waiver."""

    reason: str


class ReaffirmRequest(BaseModel):
    """Optionally a new reason when re-affirming a stale waiver."""

    reason: str = ""


class ThreatModelRequest(BaseModel):
    """The wizard's answers: ``{question_id: option | [options]}``."""

    answers: Dict[str, Any]


def _engine():
    return module_loader.get_module("advisor_engine")


def _require_admin(user) -> None:
    if not getattr(user, "is_admin", False):
        raise HTTPException(
            status_code=403,
            detail=_("Only an administrator can change the threat model"),
        )


def _require_admin_for_waivers(user) -> None:
    if not getattr(user, "is_admin", False):
        raise HTTPException(
            status_code=403,
            detail=_("Only an administrator can waive or re-affirm a posture item"),
        )


def _model_out(row) -> Dict[str, Any]:
    out = posture.model_dict(row)
    out.update(
        id=str(row.id),
        model_version=row.model_version,
        created_by=row.created_by,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )
    return out


@router.get("/advisor/threat-model/questionnaire")
async def get_questionnaire() -> Dict[str, Any]:
    """The newest curated questionnaire (prose is looked up by key in the UI)."""
    questionnaire = threat_model_catalog.load_questionnaire(posture.QUESTIONNAIRE_SLUG)
    if questionnaire is None:
        raise HTTPException(
            status_code=503,
            detail=_("The threat-model questionnaire has not been loaded yet"),
        )
    return questionnaire


@router.get("/advisor/threat-model")
async def get_threat_model(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    """The current model and the list of every saved version."""
    current = posture.current_threat_model(db)
    versions = (
        db.query(models.ThreatModel)
        .filter(
            models.ThreatModel.scope_kind == posture.SCOPE["scope_kind"],
            models.ThreatModel.scope_ref == posture.SCOPE["scope_ref"],
        )
        .order_by(models.ThreatModel.model_version.desc())
        .all()
    )
    return {
        "current": _model_out(current) if current is not None else None,
        "versions": [
            {
                "model_version": v.model_version,
                "created_by": v.created_by,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "complete": bool(v.complete),
            }
            for v in versions
        ],
    }


@router.post("/advisor/threat-model")
async def save_threat_model(
    request: ThreatModelRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Save the wizard's answers as a NEW version; returns it and what changed."""
    _require_admin(current_user)
    try:
        row, diff = posture.save_threat_model(
            _engine(), db, request.answers, current_user.userid
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=503,
            detail=_("The threat-model questionnaire has not been loaded yet"),
        ) from exc
    db.commit()
    return {"threat_model": _model_out(row), "changes": diff}


@router.get("/advisor/posture")
async def get_posture(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    """The punch list under the current threat model."""
    current = posture.current_threat_model(db)
    if current is None:
        return {"threat_model": None, "items": [], "totals": {}}
    items = (
        db.query(models.PostureItem)
        .filter(
            models.PostureItem.scope_kind == posture.SCOPE["scope_kind"],
            models.PostureItem.scope_ref == posture.SCOPE["scope_ref"],
        )
        .all()
    )
    rules = posture.rules_by_key(db)
    regressed = history.regressed_keys(db)
    totals: Dict[str, int] = {}
    shown = []
    for item in sorted(items, key=lambda i: i.rule_key):
        waiver = waivers.active_waiver(db, posture.SCOPE, item.rule_key)
        state = waivers.display_state(item, waiver)
        totals[state] = totals.get(state, 0) + 1
        shown.append((item, waiver, state))
    return {
        "threat_model": _model_out(current),
        "totals": totals,
        "items": [
            {
                "rule_key": i.rule_key,
                "rule_source": i.rule_source,
                "rule_version": i.rule_version,
                # ``state`` is what the list shows (waived is an overlay);
                # ``evaluated_state`` is what the evaluation says underneath.
                "state": state,
                "evaluated_state": i.state,
                "waiver": _waiver_out(waiver),
                # What fixes it (S5): the kind decides the UI control -- a
                # button (setting/fleet), a link (guided) or a plain "no
                # automated path" (none).
                "remedy": (rules.get(i.rule_key) or {}).get("remedy"),
                "remedy_kind": remedies.kind_of(
                    (rules.get(i.rule_key) or {}).get("remedy")
                ),
                "remedy_target": remedies.GUIDED.get(
                    (rules.get(i.rule_key) or {}).get("remedy")
                ),
                "outcome": i.outcome,
                "managed_by": i.managed_by,
                "impact": i.impact,
                "likelihood": i.likelihood,
                "risk": i.risk,
                "gaps": i.gaps or [],
                "coverage": i.coverage,
                "evaluated_at": i.evaluated_at.isoformat() if i.evaluated_at else None,
                "state_changed_at": (
                    i.state_changed_at.isoformat() if i.state_changed_at else None
                ),
                "evaluated_under_current_model": i.threat_model_id == current.id,
                # S6: open again because the FLEET moved (never a wizard re-run).
                "regressed": i.rule_key in regressed and i.state == "open",
            }
            for i, waiver, state in shown
        ],
    }


def _waiver_out(waiver):
    if waiver is None:
        return None
    return {
        "id": str(waiver.id),
        "reason": waiver.reason,
        "granted_by": waiver.granted_by,
        "granted_at": waiver.granted_at.isoformat() if waiver.granted_at else None,
        "reaffirmed_by": waiver.reaffirmed_by,
        "reaffirmed_at": (
            waiver.reaffirmed_at.isoformat() if waiver.reaffirmed_at else None
        ),
        "stale_reason": waiver.stale_reason,
        "stale_since": waiver.stale_since.isoformat() if waiver.stale_since else None,
        "risk": waiver.risk,
        "rule_version": waiver.rule_version,
        "basis_attributes": waiver.basis_attributes or {},
    }


def _item_and_rule(db, rule_key: str):
    item = (
        db.query(models.PostureItem)
        .filter(
            models.PostureItem.scope_kind == posture.SCOPE["scope_kind"],
            models.PostureItem.scope_ref == posture.SCOPE["scope_ref"],
            models.PostureItem.rule_key == rule_key,
        )
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail=_("Posture item not found"))
    rule = posture.rule_definition(db, item.rule_source, rule_key) or {}
    return item, rule


def _waiver_call(action):
    try:
        return action()
    except waivers.WaiverError as exc:
        # A code, like every other refusal the UI words itself.
        raise HTTPException(status_code=409, detail={"code": exc.code}) from exc


@router.post("/advisor/posture/{rule_key}/waiver")
async def waive_item(
    rule_key: str,
    request: WaiverRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Accept an OPEN item's risk. Audited; administrators only."""
    _require_admin_for_waivers(current_user)
    item, rule = _item_and_rule(db, rule_key)
    model = posture.current_threat_model(db)
    waiver = _waiver_call(
        lambda: waivers.grant(
            db, posture.SCOPE, item, rule, model, current_user, request.reason
        )
    )
    db.commit()
    return {"waiver": _waiver_out(waiver)}


@router.delete("/advisor/posture/{rule_key}/waiver")
async def revoke_waiver(
    rule_key: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Withdraw the waiver: the item counts as open again. Audited."""
    _require_admin_for_waivers(current_user)
    item, _rule = _item_and_rule(db, rule_key)
    waiver = _waiver_call(lambda: waivers.revoke(db, posture.SCOPE, item, current_user))
    db.commit()
    return {"waiver": _waiver_out(waiver)}


@router.post("/advisor/posture/{rule_key}/waiver/reaffirm")
async def reaffirm_waiver(
    rule_key: str,
    # Optional BODY, not just an optional field: re-affirming with no new
    # reason is the common case, and FastAPI requires a body for a model.
    request: Optional[ReaffirmRequest] = None,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Accept a STALE waiver again on the current basis. Audited."""
    _require_admin_for_waivers(current_user)
    item, rule = _item_and_rule(db, rule_key)
    model = posture.current_threat_model(db)
    waiver = _waiver_call(
        lambda: waivers.reaffirm(
            db,
            posture.SCOPE,
            item,
            rule,
            model,
            current_user,
            request.reason if request else None,
        )
    )
    db.commit()
    return {"waiver": _waiver_out(waiver)}


@router.get("/advisor/posture/{rule_key}/remedy")
async def preview_remedy(
    rule_key: str, db: Session = Depends(get_tenant_db)
) -> Dict[str, Any]:
    """Exactly what applying the remedy would change, and whether it can."""
    item, rule = _item_and_rule(db, rule_key)
    return remedies.preview(db, item, rule)


@router.post("/advisor/posture/{rule_key}/remedy")
async def apply_remedy(
    rule_key: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Apply the remedy. Administrators only -- AND the role the per-host
    action needs, so this page never widens anyone's permissions. Audited."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=403,
            detail=_("Only an administrator can apply a posture remedy"),
        )
    item, rule = _item_and_rule(db, rule_key)
    role = remedies.required_role(rule)
    if role is not None and not current_user.has_role(role):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required") % role.value,
        )
    model = posture.current_threat_model(db)
    try:
        result = remedies.apply(
            db,
            posture.SCOPE,
            item,
            rule,
            current_user,
            model.model_version if model else None,
        )
    except ValueError as exc:
        # The reason comes from the remedy's own plan, never from the
        # exception (CodeQL py/stack-trace-exposure): apply() refuses exactly
        # when preview() says the remedy is unavailable.
        logger.debug("Remedy refused for %s: %s", rule_key, exc)
        reason = remedies.preview(db, item, rule).get("unavailable_reason")
        code = reason if reason in _REMEDY_CONFLICT_CODES else "remedy_unavailable"
        raise HTTPException(status_code=409, detail={"code": code}) from None
    db.commit()
    return result


@router.get("/advisor/posture/history")
async def posture_history(
    limit: int = 200, db: Session = Depends(get_tenant_db)
) -> Dict[str, Any]:
    """Every punch-list change, newest first, each classified."""
    return {"events": history.history(db, limit=limit)}


@router.get("/advisor/posture/{rule_key}/history")
async def item_history(
    rule_key: str, limit: int = 200, db: Session = Depends(get_tenant_db)
) -> Dict[str, Any]:
    """One item's timeline."""
    return {"events": history.history(db, rule_key=rule_key, limit=limit)}


@router.get("/advisor/threat-model/diff")
async def threat_model_diff(
    from_version: int, to_version: int, db: Session = Depends(get_tenant_db)
) -> Dict[str, Any]:
    """What changed between two model versions, and what it did to the list."""
    diff = history.model_diff(_engine(), db, from_version, to_version)
    if diff is None:
        raise HTTPException(status_code=404, detail=_("Threat model version not found"))
    return diff
