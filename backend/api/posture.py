# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The threat model and the posture punch list (Phase 21.4 S3).

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
from typing import Any, Dict

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
from backend.services import posture_service as posture
from backend.services import threat_model_catalog

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[
        Depends(JWTBearer()),
        Depends(require_module_loaded(ModuleCode.ADVISOR_ENGINE)),
    ]
)


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
    totals: Dict[str, int] = {}
    for item in items:
        totals[item.state] = totals.get(item.state, 0) + 1
    return {
        "threat_model": _model_out(current),
        "totals": totals,
        "items": [
            {
                "rule_key": i.rule_key,
                "rule_source": i.rule_source,
                "rule_version": i.rule_version,
                "state": i.state,
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
            }
            for i in sorted(items, key=lambda i: i.rule_key)
        ],
    }
