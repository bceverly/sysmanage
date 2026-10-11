# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Machines: the hardware a host runs on (Phase 23.2 S2).

Read endpoints for a host's machine and its sibling hosts, the list of links
held for an admin's decision, and the decision itself.  The asset tag (S3)
builds on these.  Errors that the UI explains carry a ``code`` rather than
prose, so the browser renders them in the user's language.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import machine_identity
from backend.services.audit_service import ActionType, AuditService, EntityType

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(JWTBearer())])


class ResolveRequest(BaseModel):
    """``same``: the host is on that machine.  ``different``: a clone."""

    decision: str


def _machine_view(machine: Optional[models.Machine]) -> Optional[Dict[str, Any]]:
    if machine is None:
        return None
    return {
        "id": str(machine.id),
        "system_uuid": machine.system_uuid,
        "system_serial": machine.system_serial,
        "board_serial": machine.board_serial,
        "vendor": machine.vendor,
        "model": machine.model,
        "is_virtual": bool(machine.is_virtual),
        "asset_tag": machine.asset_tag,
    }


def _host_brief(host: models.Host) -> Dict[str, Any]:
    return {
        "id": str(host.id),
        "fqdn": host.fqdn,
        "platform": getattr(host, "platform", None),
        "active": bool(host.active),
    }


def _host_or_404(db: Session, host_id: str) -> models.Host:
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if host is None:
        raise HTTPException(status_code=404, detail=_("Host not found"))
    return host


def _status(host: models.Host) -> Dict[str, str]:
    try:
        return json.loads(host.hw_identity_status or "{}")
    except ValueError:
        return {}


@router.get("/host/{host_id}/machine")
async def host_machine(
    host_id: str, db: Session = Depends(get_tenant_db)
) -> Dict[str, Any]:
    """The host's reported identity, its machine and the other hosts on it."""
    host = _host_or_404(db, host_id)
    machine = db.get(models.Machine, host.machine_id) if host.machine_id else None
    siblings: List[Dict[str, Any]] = []
    if machine is not None:
        siblings = [
            _host_brief(h)
            for h in db.query(models.Host)
            .filter(models.Host.machine_id == machine.id, models.Host.id != host.id)
            .order_by(models.Host.fqdn)
            .all()
        ]
    conflict = None
    if host.machine_conflict_id:
        conflict = {
            "reason": host.machine_conflict_reason,
            "machine": _machine_view(db.get(models.Machine, host.machine_conflict_id)),
        }
    return {
        "identity": {
            "system_uuid": host.hw_system_uuid,
            "system_serial": host.hw_system_serial,
            "board_serial": host.hw_board_serial,
            "status": _status(host),
            "reported_at": (
                host.hw_identity_updated_at.isoformat()
                if host.hw_identity_updated_at
                else None
            ),
        },
        "machine": _machine_view(machine),
        "other_hosts": siblings,
        "conflict": conflict,
    }


@router.get("/machines/conflicts")
async def machine_conflicts(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    """Every host whose machine link is waiting for an admin's decision."""
    hosts = (
        db.query(models.Host)
        .filter(models.Host.machine_conflict_id.isnot(None))
        .order_by(models.Host.fqdn)
        .all()
    )
    return {
        "conflicts": [
            {
                "host": _host_brief(h),
                "reason": h.machine_conflict_reason,
                "machine": _machine_view(db.get(models.Machine, h.machine_conflict_id)),
            }
            for h in hosts
        ]
    }


@router.post("/host/{host_id}/machine/resolve")
async def resolve_machine_conflict(
    host_id: str,
    request: ResolveRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Decide a held link.  Needs the role that approves hosts; audited."""
    if not current_user.has_role(SecurityRoles.APPROVE_HOST_REGISTRATION):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required")
            % SecurityRoles.APPROVE_HOST_REGISTRATION.value,
        )
    if request.decision not in (
        machine_identity.DECISION_SAME,
        machine_identity.DECISION_DIFFERENT,
    ):
        raise HTTPException(status_code=422, detail={"code": "invalid_decision"})
    host = _host_or_404(db, host_id)
    try:
        machine = machine_identity.resolve_conflict(db, host, request.decision)
    except ValueError:
        raise HTTPException(status_code=409, detail={"code": "no_conflict"}) from None
    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.HOST,
        entity_id=str(host.id),
        entity_name=host.fqdn,
        description=_("Machine link decided for host %s") % host.fqdn,
        user_id=current_user.id,
        username=current_user.userid,
        details={"decision": request.decision, "machine_id": str(machine.id)},
        commit=False,
    )
    db.commit()
    return {"machine": _machine_view(machine)}
