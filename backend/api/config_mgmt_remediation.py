# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Remediation playbooks: rules and targeted repairs (Phase 20.1).

20.2 shipped remediate-to-baseline, which re-applies the whole profile a host
drifted from. This is the narrow alternative: a rule binds a drift finding to
the profile that repairs just that divergence, so fixing one file mode does not
mean re-converging four hundred tasks inside a maintenance window budgeted for
one change.

A remediation playbook IS a ``ConfigProfile``. Only the BINDING is new, which
is why there is no second authoring surface here -- versioning, validation, the
licensed spec builders and run history are all the profile machinery, reused.

LICENCE-GATED AT THE ROUTER, as every config-management router is.

ROLES: authoring a rule is EDIT_SCRIPT-class. FIRING one runs a profile on a
host, so it is RUN_SCRIPT -- identical blast radius to an ad-hoc apply, and a
softer permission for the same capability would be an escalation path dressed
up as a feature.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.feature_gate import require_module_loaded
from backend.licensing.features import ModuleCode
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import config_mgmt_dispatch as dispatch
from backend.services import config_mgmt_fleet as fleet
from backend.services import config_mgmt_remediation as remediation

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[
        Depends(JWTBearer()),
        Depends(require_module_loaded(ModuleCode.CONFIG_MANAGEMENT_ENGINE)),
    ]
)


class RuleRequest(BaseModel):
    """A new remediation rule."""

    name: str
    task_pattern: str
    remediation_profile_id: str
    description: Optional[str] = None
    # NULL scopes the rule to every profile, which is what makes a rule
    # library worth having across profiles.
    profile_id: Optional[str] = None
    enabled: bool = True
    priority: int = 100
    auto_apply: bool = False


class RuleUpdateRequest(BaseModel):
    """Fields to change. Omitted fields are left alone."""

    name: Optional[str] = None
    description: Optional[str] = None
    profile_id: Optional[str] = None
    task_pattern: Optional[str] = None
    remediation_profile_id: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    auto_apply: Optional[bool] = None


class RuleResponse(BaseModel):
    """A stored remediation rule."""

    id: str
    name: str
    description: Optional[str] = None
    profile_id: Optional[str] = None
    profile_name: Optional[str] = None
    task_pattern: str
    remediation_profile_id: str
    remediation_profile_name: Optional[str] = None
    enabled: bool
    priority: int
    auto_apply: bool
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RemediationMatchResponse(BaseModel):
    """What would repair one finding, if anything.

    Three distinguishable answers, because they send an operator to three
    different places: nothing matched (write a rule), a rule matched but its
    profile is retired (turn it back on), or here is what will run.
    """

    finding_id: str
    matched: bool
    # Set when a rule matched but its remediation profile is gone or inactive.
    unavailable: bool = False
    rule_id: Optional[str] = None
    rule_name: Optional[str] = None
    remediation_profile_id: Optional[str] = None
    remediation_profile_name: Optional[str] = None
    preview: Optional[Dict[str, Any]] = None


class RepairResponse(BaseModel):
    """Result of queuing a targeted repair."""

    finding_id: str
    host_id: str
    profile_id: str
    profile_name: Optional[str] = None
    queued: bool
    message: str


def _require_role(user, role) -> None:
    if not user.has_role(role):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required") % role.value,
        )


def _as_uuid(value: str, message: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=message) from exc


def _load_rule(db_session: Session, rule_id: str):
    row = (
        db_session.query(models.ConfigRemediationRule)
        .filter(
            models.ConfigRemediationRule.id
            == _as_uuid(rule_id, _("Invalid rule ID format"))
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_("Remediation rule not found"))
    return row


def _load_finding(db_session: Session, finding_id: str):
    row = (
        db_session.query(models.ConfigDriftFinding)
        .filter(
            models.ConfigDriftFinding.id
            == _as_uuid(finding_id, _("Invalid finding ID format"))
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_("Drift finding not found"))
    return row


def _require_profile(db_session: Session, profile_id: str):
    row = (
        db_session.query(models.ConfigProfile)
        .filter(
            models.ConfigProfile.id
            == _as_uuid(profile_id, _("Invalid profile ID format"))
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_("Profile not found"))
    return row


def _name_taken(db_session: Session, name: str, exclude_id=None) -> bool:
    query = db_session.query(models.ConfigRemediationRule).filter(
        models.ConfigRemediationRule.name == (name or "").strip()
    )
    if exclude_id is not None:
        query = query.filter(models.ConfigRemediationRule.id != exclude_id)
    return query.first() is not None


def _serialise(db_session: Session, rows) -> List[RuleResponse]:
    names = remediation.profile_names_for(db_session, rows)
    return [RuleResponse(**remediation.rule_to_dict(row, names)) for row in rows]


# --- rules -------------------------------------------------------------------


@router.get("/config-management/remediation-rules", response_model=List[RuleResponse])
async def list_rules(db_session: Session = Depends(get_tenant_db)):
    """Every rule, in the order the engine would consider them.

    Ordered by precedence rather than by name so the list reads as what it is:
    the sequence a finding is tested against. A name-ordered list of
    overlapping rules tells an operator nothing about which one will fire.
    """
    rows = (
        db_session.query(models.ConfigRemediationRule)
        .order_by(
            models.ConfigRemediationRule.priority.asc(),
            models.ConfigRemediationRule.name.asc(),
        )
        .all()
    )
    return _serialise(db_session, rows)


@router.post("/config-management/remediation-rules", response_model=RuleResponse)
async def create_rule(
    request: RuleRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Store a remediation rule."""
    _require_role(current_user, SecurityRoles.ADD_SCRIPT)

    problem = remediation.validate_rule(
        request.name, request.task_pattern, request.priority
    )
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    if _name_taken(db_session, request.name):
        raise HTTPException(
            status_code=409,
            detail=_("A remediation rule named '%s' already exists") % request.name,
        )

    repair = _require_profile(db_session, request.remediation_profile_id)
    scope = (
        _require_profile(db_session, request.profile_id).id
        if request.profile_id
        else None
    )

    now = fleet.now_naive()
    row = models.ConfigRemediationRule(
        name=request.name.strip(),
        description=request.description,
        profile_id=scope,
        task_pattern=request.task_pattern.strip(),
        remediation_profile_id=repair.id,
        enabled=bool(request.enabled),
        priority=int(request.priority),
        auto_apply=bool(request.auto_apply),
        created_by=current_user.userid,
        updated_by=current_user.userid,
        created_at=now,
        updated_at=now,
    )
    db_session.add(row)
    db_session.commit()
    logger.info(
        "Remediation rule created: %s (pattern=%r, auto_apply=%s)",
        row.name,
        row.task_pattern,
        row.auto_apply,
    )
    return _serialise(db_session, [row])[0]


@router.put(
    "/config-management/remediation-rules/{rule_id}", response_model=RuleResponse
)
async def update_rule(
    rule_id: str,
    request: RuleUpdateRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Change a remediation rule."""
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    row = _load_rule(db_session, rule_id)
    changes = request.model_dump(exclude_unset=True)

    # Validated against the rule the change WOULD produce, not the delta.
    problem = remediation.validate_rule(
        changes.get("name", row.name),
        changes.get("task_pattern", row.task_pattern),
        changes.get("priority", row.priority),
    )
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    if "name" in changes and _name_taken(
        db_session, changes["name"], exclude_id=row.id
    ):
        raise HTTPException(
            status_code=409,
            detail=_("A remediation rule named '%s' already exists") % changes["name"],
        )

    if "remediation_profile_id" in changes:
        row.remediation_profile_id = _require_profile(
            db_session, changes["remediation_profile_id"]
        ).id
    if "profile_id" in changes:
        row.profile_id = (
            _require_profile(db_session, changes["profile_id"]).id
            if changes["profile_id"]
            else None
        )
    if "name" in changes:
        row.name = str(changes["name"]).strip()
    if "description" in changes:
        row.description = changes["description"]
    if "task_pattern" in changes:
        row.task_pattern = str(changes["task_pattern"]).strip()
    if "enabled" in changes:
        row.enabled = bool(changes["enabled"])
    if "priority" in changes:
        row.priority = int(changes["priority"])
    if "auto_apply" in changes:
        row.auto_apply = bool(changes["auto_apply"])

    row.updated_by = current_user.userid
    row.updated_at = fleet.now_naive()
    db_session.commit()
    return _serialise(db_session, [row])[0]


@router.delete("/config-management/remediation-rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Delete a remediation rule. The profiles it named are untouched."""
    _require_role(current_user, SecurityRoles.DELETE_SCRIPT)
    row = _load_rule(db_session, rule_id)
    name = row.name
    db_session.delete(row)
    db_session.commit()
    logger.info("Remediation rule deleted: %s", name)
    return {"success": True, "message": _("Remediation rule deleted")}


# --- per-finding repair ------------------------------------------------------


@router.get(
    "/config-management/drift/findings/{finding_id}/remediation",
    response_model=RemediationMatchResponse,
)
async def match_finding(finding_id: str, db_session: Session = Depends(get_tenant_db)):
    """What would repair this finding, without doing it.

    The preview comes from the ENGINE rather than being assembled here, so the
    sentence an operator confirms is produced by the same code that made the
    decision -- not a frontend reconstruction of it that can drift.
    """
    finding = _load_finding(db_session, finding_id)
    rule, profile = remediation.match_for_finding(db_session, finding)

    if rule is None:
        return RemediationMatchResponse(finding_id=str(finding.id), matched=False)
    if profile is None:
        return RemediationMatchResponse(
            finding_id=str(finding.id),
            matched=True,
            unavailable=True,
            rule_id=str(rule.id),
            rule_name=rule.name,
        )
    return RemediationMatchResponse(
        finding_id=str(finding.id),
        matched=True,
        rule_id=str(rule.id),
        rule_name=rule.name,
        remediation_profile_id=str(profile.id),
        remediation_profile_name=profile.name,
        preview=remediation.preview(rule, finding.task_name),
    )


@router.post(
    "/config-management/drift/findings/{finding_id}/remediate",
    response_model=RepairResponse,
)
async def repair_finding(
    finding_id: str,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Apply the matched playbook to the host this finding is on.

    Distinct from ``/config-management/drift/remediate``, which re-applies the
    whole profile: this runs only the playbook a rule named for this
    divergence.

    Inherits both existing guards and re-implements neither:
    ``enqueue_message`` refuses a host that has not advertised support
    (Phase 19), and ``outbound_processor`` holds delivery outside a
    maintenance window (Phase 14.2).
    """
    _require_role(current_user, SecurityRoles.RUN_SCRIPT)
    finding = _load_finding(db_session, finding_id)

    rule, profile = remediation.match_for_finding(db_session, finding)
    if rule is None:
        raise HTTPException(
            status_code=404,
            detail=_("No remediation rule matches this finding"),
        )
    if profile is None:
        raise HTTPException(
            status_code=400,
            detail=_("The profile this rule repairs with is missing or not active"),
        )

    host = (
        db_session.query(models.Host).filter(models.Host.id == finding.host_id).first()
    )
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))
    if not host.active:
        raise HTTPException(status_code=400, detail=_("Host is not active"))

    try:
        remediation.apply_remediation(db_session, host, profile)
    except dispatch.DispatchError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc
    db_session.commit()

    logger.info(
        "Targeted remediation queued: rule '%s' applies profile '%s' to host %s "
        "for drift on task %r",
        rule.name,
        profile.name,
        host.fqdn,
        finding.task_name,
    )
    return RepairResponse(
        finding_id=str(finding.id),
        host_id=str(host.id),
        profile_id=str(profile.id),
        profile_name=profile.name,
        queued=True,
        # The finding is NOT resolved here. It clears when the next check-mode
        # run observes the host is back in line -- claiming success before the
        # agent has reported would be a dashboard that lies.
        message=_("The repair was queued for this host"),
    )
