# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
The fleet NTP policy (Phase 23.3 S5b; gated on ``config_management_engine``).

``GET /time-sync/ntp-policies`` -- the fleet, site and tag policies.
``PUT /time-sync/ntp-policies`` -- set one (Manage Time Sync role).
``DELETE /time-sync/ntp-policies`` -- remove one; the scope falls back.
``GET /time-sync/ntp-compliance`` -- every host against its policy.

Reasons a policy is refused travel as codes; the UI words them.  Changes are
audited.
"""

import uuid
from typing import Any, Dict, List

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
from backend.services import ntp_policy
from backend.services.audit_service import ActionType, AuditService, EntityType

router = APIRouter(
    dependencies=[
        Depends(JWTBearer()),
        Depends(require_module_loaded(ModuleCode.CONFIG_MANAGEMENT_ENGINE)),
    ]
)


class PolicyBody(BaseModel):
    scope_kind: str
    scope_ref: str = ""
    servers: List[str]
    enforce: bool = False
    auto_resync: bool = False


def _require_role(current_user) -> None:
    if not current_user.has_role(SecurityRoles.MANAGE_TIME_SYNC):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required")
            % SecurityRoles.MANAGE_TIME_SYNC.value,
        )


def _engine():
    module = ntp_policy.engine()
    if module is None:
        raise HTTPException(status_code=503, detail={"code": "no_policy_engine"})
    return module


def _check_scope(db: Session, scope_kind: str, scope_ref: str) -> None:
    if scope_kind not in ntp_policy.SCOPES:
        raise HTTPException(status_code=422, detail={"code": "bad_scope"})
    if scope_kind == ntp_policy.SCOPE_FLEET:
        if scope_ref:
            raise HTTPException(status_code=422, detail={"code": "bad_scope"})
        return
    try:
        key = uuid.UUID(scope_ref)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "bad_scope"}) from exc
    if scope_kind == ntp_policy.SCOPE_TAG and db.get(models.Tag, key) is None:
        raise HTTPException(status_code=404, detail={"code": "tag_not_found"})


def _audit(db, current_user, description: str, details) -> None:
    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_name="ntp_policy",
        description=description,
        user_id=current_user.id,
        username=current_user.userid,
        details=details,
    )


@router.get("/time-sync/ntp-policies")
async def list_policies(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    rows = db.query(models.NtpPolicy).order_by(
        models.NtpPolicy.scope_kind, models.NtpPolicy.scope_ref
    )
    return {
        "policies": [ntp_policy.as_dict(r) for r in rows],
        "max_servers": 8,
    }


@router.put("/time-sync/ntp-policies")
async def set_policy(
    body: PolicyBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require_role(current_user)
    module = _engine()
    servers = [s.strip() for s in body.servers]
    errors = module.ntp_validate_servers(servers)
    if errors:
        raise HTTPException(status_code=422, detail={"code": errors[0]})
    scope_ref = body.scope_ref.strip()
    _check_scope(db, body.scope_kind, scope_ref)
    row = ntp_policy.set_policy(
        db,
        body.scope_kind,
        scope_ref,
        servers,
        body.enforce,
        body.auto_resync,
        current_user.userid,
    )
    _audit(db, current_user, _("NTP policy changed"), ntp_policy.as_dict(row))
    return ntp_policy.as_dict(row)


@router.delete("/time-sync/ntp-policies")
async def clear_policy(
    scope_kind: str,
    scope_ref: str = "",
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require_role(current_user)
    if not ntp_policy.clear_policy(db, scope_kind, scope_ref.strip()):
        raise HTTPException(status_code=404, detail={"code": "no_policy"})
    _audit(
        db,
        current_user,
        _("NTP policy removed"),
        {"scope_kind": scope_kind, "scope_ref": scope_ref.strip()},
    )
    return {"removed": True}


@router.get("/time-sync/ntp-compliance")
async def compliance(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    """Every approved host against its policy, with where applying stands."""
    _engine()
    hosts = (
        db.query(models.Host).filter(models.Host.approval_status == "approved").all()
    )
    judged = ntp_policy.evaluate(db, hosts)
    states = {str(s.host_id): s for s in db.query(models.NtpPolicyState)}
    out = []
    for host in hosts:
        verdict = judged.get(str(host.id), {})
        policy = verdict.get("policy")
        state = states.get(str(host.id))
        out.append(
            {
                "host_id": str(host.id),
                "fqdn": host.fqdn,
                "policy": None if policy is None else ntp_policy.as_dict(policy),
                "conflict": verdict.get("conflict", False),
                "findings": verdict.get("findings", []),
                "compliant": verdict.get("compliant"),
                "apply_status": state.status if state else None,
                "apply_error": state.last_error if state else None,
            }
        )
    return {"hosts": out}
