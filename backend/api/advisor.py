# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The advisor's rules, recommendation feed and host view (Phase 21.2 S4).

WHY THE WHOLE ROUTER IS LICENSE-GATED
-------------------------------------
Everything here is ``advisor_engine`` (Enterprise), so the gate sits on the
router: a new endpoint added here is gated by default, which is the safe
direction to fail.

WHY THE DECISIONS LIVE IN THE ENGINE
------------------------------------
Rule validation, outcomes, scores and remediation text all come from the
licensed engine. This file owns HTTP, persistence and authorization -- the
same split as query packs, whose API this follows. (The S2 plan named an
engine-provided router via ``call_engine_router``; the query-pack shape was
chosen instead because the advisor's reads are server-side joins the engine,
which has no database, could not do.)

VALIDATION ERRORS ARE CODES
---------------------------
A rejected rule returns the engine's ``{code, field[, detail]}`` list, not
sentences: the UI (S7) owns their wording in every language, the same way
fact-coverage reasons work.

ROLES
-----
Reuses the SCRIPT roles, as query packs do: a rule is authored executable
content (a SQL query over host evidence). Reading the feed needs only an
authenticated user, like reading query-pack results.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.feature_gate import require_module_loaded
from backend.licensing.features import ModuleCode
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import advisor_catalog as catalog
from backend.services import advisor_feed as feed
from backend.services import advisor_proposals as proposals
from backend.services import advisor_tick as tick

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[
        Depends(JWTBearer()),
        Depends(require_module_loaded(ModuleCode.ADVISOR_ENGINE)),
    ]
)

_SOURCES = models.ADVISOR_RULE_SOURCES
_OUTCOMES = models.ADVISOR_OUTCOMES


class RuleRequest(BaseModel):
    """A tenant rule: the rule itself, as the engine's contract describes it."""

    rule: Dict[str, Any]
    enabled: bool = True


class RuleUpdateRequest(BaseModel):
    """Fields to change. Omitted fields are left alone."""

    rule: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


def _engine():
    # The router's dependency already guarantees the module is loaded.
    return module_loader.get_module("advisor_engine")


def _require_role(user, role) -> None:
    if not user.has_role(role):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required") % role.value,
        )


def _as_uuid(value: str, message: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=message) from exc


def _check(rule: Dict[str, Any]) -> None:
    """Refuse an invalid rule with EVERY problem, as codes."""
    errors = list(_engine().validate_rule(rule))
    if errors:
        raise HTTPException(
            status_code=400,
            detail={"message": _("The advisor rule was rejected"), "errors": errors},
        )


def _apply(row: models.AdvisorRule, rule: Dict[str, Any]) -> None:
    row.rule_key = rule["id"]
    row.contract_version = rule["contract"]
    row.rule_version = rule["version"]
    row.lens = rule["lens"]
    row.scope = rule.get("scope", "host")
    row.title = rule["title"]
    row.definition = rule


def _tenant_rule(db: Session, rule_id: str) -> models.AdvisorRule:
    row = db.get(
        models.AdvisorRule, _as_uuid(rule_id, _("Invalid advisor rule ID format"))
    )
    if row is None:
        raise HTTPException(status_code=404, detail=_("Advisor rule not found"))
    return row


def _key_taken(db: Session, key: str, except_id=None) -> bool:
    query = db.query(models.AdvisorRule).filter(models.AdvisorRule.rule_key == key)
    if except_id is not None:
        query = query.filter(models.AdvisorRule.id != except_id)
    return db.query(query.exists()).scalar()


def _refuse_duplicate() -> None:
    raise HTTPException(
        status_code=409, detail=_("An advisor rule with this ID already exists")
    )


# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------


@router.get("/advisor/rules")
async def list_rules(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    """Curated and tenant rules, each with its validation problems (codes)."""
    rules = feed.all_rules(_engine(), db).values()
    return {
        "curated": [r for r in rules if r["source"] == "shared"],
        "tenant": [r for r in rules if r["source"] == "tenant"],
    }


@router.post("/advisor/rules/validate")
async def validate_rule(request: RuleRequest) -> Dict[str, Any]:
    """Check a rule without storing it, so the editor can say why."""
    return {"errors": list(_engine().validate_rule(request.rule))}


@router.post("/advisor/rules")
async def create_rule(
    request: RuleRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require_role(current_user, SecurityRoles.ADD_SCRIPT)
    _check(request.rule)
    if _key_taken(db, request.rule["id"]):
        _refuse_duplicate()
    row = models.AdvisorRule(
        id=uuid.uuid4(), enabled=request.enabled, created_by=current_user.userid
    )
    _apply(row, request.rule)
    db.add(row)
    db.commit()
    return feed.rule_dict(
        _engine(), "tenant", row.definition, id=str(row.id), enabled=row.enabled
    )


@router.put("/advisor/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    request: RuleUpdateRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    row = _tenant_rule(db, rule_id)
    if request.rule is not None:
        _check(request.rule)
        if _key_taken(db, request.rule["id"], except_id=row.id):
            _refuse_duplicate()
        if request.rule["id"] != row.rule_key:
            # The results were computed for the old key; the tick would prune
            # them anyway, but the feed must not show them in between.
            db.query(models.AdvisorResult).filter(
                models.AdvisorResult.rule_id == row.id
            ).delete(synchronize_session=False)
        _apply(row, request.rule)
    if request.enabled is not None:
        row.enabled = request.enabled
        if not row.enabled:
            # A disabled rule is not evaluated; its old outcomes must not keep
            # standing in the feed until the next tick prunes them.
            db.query(models.AdvisorResult).filter(
                models.AdvisorResult.rule_id == row.id
            ).delete(synchronize_session=False)
    db.commit()
    return feed.rule_dict(
        _engine(), "tenant", row.definition, id=str(row.id), enabled=row.enabled
    )


@router.delete("/advisor/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, str]:
    _require_role(current_user, SecurityRoles.DELETE_SCRIPT)
    row = _tenant_rule(db, rule_id)
    db.query(models.AdvisorResult).filter(
        models.AdvisorResult.rule_id == row.id
    ).delete(synchronize_session=False)
    db.delete(row)
    db.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# feed, hosts, evaluation
# ---------------------------------------------------------------------------


@router.get("/advisor/feed")
async def get_feed(
    lens: Optional[str] = None, db: Session = Depends(get_tenant_db)
) -> Dict[str, Any]:
    """The fleet's recommendations: one entry per rule, worst first, with the
    not-assessable count beside every finding count."""
    return feed.feed(_engine(), db, lens=lens)


@router.get("/advisor/hosts/{host_id}")
async def get_host(
    host_id: str, db: Session = Depends(get_tenant_db)
) -> Dict[str, Any]:
    host = db.get(models.Host, _as_uuid(host_id, _("Invalid host ID format")))
    if host is None:
        raise HTTPException(status_code=404, detail=_("Host not found"))
    return feed.host_view(_engine(), db, host)


@router.get("/advisor/rules/{source}/{key}/hosts")
async def get_rule_hosts(
    source: str,
    key: str,
    outcome: Optional[str] = None,
    db: Session = Depends(get_tenant_db),
) -> Dict[str, Any]:
    if source not in _SOURCES or (outcome is not None and outcome not in _OUTCOMES):
        raise HTTPException(status_code=400, detail=_("Invalid advisor rule filter"))
    return feed.rule_hosts(_engine(), db, source, key, outcome=outcome)


@router.post("/advisor/evaluate")
async def evaluate_now(
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Evaluate this tenant now instead of waiting for the next tick.

    RUN_SCRIPT, not a read role: a pass may dispatch fact collections to
    hosts, which is running something on them.
    """
    _require_role(current_user, SecurityRoles.RUN_SCRIPT)
    return await run_in_threadpool(tick.evaluate_database, db, "api")


# ---------------------------------------------------------------------------
# remediation proposals (S5)
# ---------------------------------------------------------------------------


def _proposal(db: Session, proposal_id: str) -> models.AdvisorProposal:
    row = db.get(
        models.AdvisorProposal,
        _as_uuid(proposal_id, _("Invalid advisor proposal ID format")),
    )
    if row is None:
        raise HTTPException(status_code=404, detail=_("Advisor proposal not found"))
    return row


def _proposal_out(db: Session, row) -> Dict[str, Any]:
    host = db.get(models.Host, row.host_id)
    return proposals.proposal_dict(db, row, fqdn=host.fqdn if host else None)


@router.get("/advisor/proposals")
async def list_proposals(
    status: Optional[str] = None,
    host_id: Optional[str] = None,
    db: Session = Depends(get_tenant_db),
) -> Dict[str, Any]:
    """Fixes the advisor proposes, newest first. Filter by status or host."""
    query = db.query(models.AdvisorProposal)
    if status is not None:
        if status not in models.ADVISOR_PROPOSAL_STATUSES:
            raise HTTPException(
                status_code=400, detail=_("Invalid advisor proposal filter")
            )
        query = query.filter(models.AdvisorProposal.status == status)
    if host_id is not None:
        query = query.filter(
            models.AdvisorProposal.host_id
            == _as_uuid(host_id, _("Invalid host ID format"))
        )
    rows = query.order_by(models.AdvisorProposal.created_at.desc()).all()
    return {"proposals": [_proposal_out(db, row) for row in rows]}


@router.post("/advisor/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Apply a proposed fix -- through the ordinary config-profile path, so it
    waits for the host's maintenance window like any other change.

    RUN_SCRIPT, the role that already gates applying a remediation.
    """
    _require_role(current_user, SecurityRoles.RUN_SCRIPT)
    row = _proposal(db, proposal_id)
    try:
        proposals.approve(db, row, current_user.userid)
    except proposals.ProposalError as exc:
        # The decision and its failure are recorded; the operator sees why.
        db.commit()
        raise HTTPException(
            status_code=409,
            detail={
                "message": _("The advisor proposal could not be approved"),
                "reason": exc.code,
            },
        ) from exc
    db.commit()
    return _proposal_out(db, row)


@router.post("/advisor/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require_role(current_user, SecurityRoles.RUN_SCRIPT)
    row = _proposal(db, proposal_id)
    try:
        proposals.reject(row, current_user.userid)
    except proposals.ProposalError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": _("The advisor proposal could not be rejected"),
                "reason": exc.code,
            },
        ) from exc
    db.commit()
    return _proposal_out(db, row)


# ---------------------------------------------------------------------------
# curated packs (S6)
# ---------------------------------------------------------------------------


class PackChoiceRequest(BaseModel):
    """A tenant's choice. ``enabled: null`` means "follow the pack's default";
    omitted fields are left alone."""

    enabled: Optional[bool] = None
    disabled_rules: Optional[List[str]] = None


@router.get("/advisor/packs")
async def list_packs(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    """The curated catalog with this tenant's effective state, rule by rule."""
    return {"packs": catalog.list_packs(db)}


@router.put("/advisor/packs/{slug}")
async def choose_pack(
    slug: str,
    request: PackChoiceRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Turn a curated pack on or off for this tenant, or opt rules out of it.

    EDIT_SCRIPT, as editing a tenant rule: it changes what the advisor runs.
    What is switched off is cleared at once -- its outcomes and open proposals
    -- rather than left standing in the feed until the next tick.
    """
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    pack = catalog.pack_rule_keys(slug)
    if pack is None:
        raise HTTPException(status_code=404, detail=_("Advisor rule pack not found"))
    changes = request.model_dump(include=request.model_fields_set)
    unknown = sorted(set(changes.get("disabled_rules") or []) - set(pack["keys"]))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={
                "message": _("The advisor rule pack has no such rules"),
                "rules": unknown,
            },
        )
    catalog.set_choice(db, slug, changes, current_user.userid, pack)
    db.commit()
    return next(p for p in catalog.list_packs(db) if p["slug"] == slug)
