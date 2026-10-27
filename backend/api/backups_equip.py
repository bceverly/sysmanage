# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Equipping a host for backups (ROADMAP Phase 24).

A host can back up -- or hold others' backups -- once its agent can run
restate.  The agent says so in its capability report, which it sent only when
it registered: restate installed afterwards left the host reading "not
equipped" until its agent restarted (production, 2026-10-25).  ``Check
again`` asks the agent for a fresh report now.

``Equip for backup`` has the agent install restate where it is packaged for a
host it backs up (backend/services/backup_equip.py); the agent decides how.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import _audit, _host_or_404, _require
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import agent_capability_service as capabilities
from backend.services import backup_equip as equip
from backend.services.audit_service import EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])


@router.post("/host/{host_id}/backup-recheck")
async def backup_recheck(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Ask the host's agent whether it can run restate now; the host's backup
    status follows within seconds of its answer."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    host = _host_or_404(db, host_id)
    command_id = capabilities.request_refresh(db, host.id)
    _audit(
        db,
        current_user,
        EntityType.HOST,
        host.id,
        host.fqdn,
        "Backup readiness re-check requested",
        {"command_id": command_id},
    )
    db.commit()
    return {"command_id": command_id}


def _refusal(code: str) -> HTTPException:
    """409 with what the operator can do about it."""
    text = {
        equip.NOT_NEEDED: _("This host can already run backups"),
        equip.AGENT_OUTDATED: _(
            "This host's agent cannot install restate yet; upgrade the agent first"
        ),
        equip.NOT_APPLICABLE: _(
            "restate has no package the agent can install on this operating "
            "system; build and install it by hand (see restate's README)"
        ),
        equip.IN_PROGRESS: _("Equipping this host is already in progress"),
    }.get(code, _("This host cannot run backups: %s") % code)
    return HTTPException(status_code=409, detail=text)


@router.post("/host/{host_id}/backup-equip")
async def backup_equip(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Have the host's agent install restate; the Backups page shows it as
    equipping until the agent answers."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    host = _host_or_404(db, host_id)
    command_id, why = equip.start(db, host, current_user.userid)
    if why:
        raise _refusal(why)
    _audit(
        db,
        current_user,
        EntityType.HOST,
        host.id,
        host.fqdn,
        "Equip for backup requested (install restate)",
        {"command_id": command_id},
    )
    db.commit()
    return {"command_id": command_id, "equip": equip.state(db, host.id)}


class BulkEquipBody(BaseModel):
    host_ids: List[str] = Field(min_length=1, max_length=500)


@router.post("/backups/equip")
async def bulk_backup_equip(
    body: BulkEquipBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Equip for backup on many hosts: each one that can is started; the rest
    come back with why (the same codes as one host's refusal)."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    started, skipped = 0, []
    for host_id in dict.fromkeys(body.host_ids):
        try:
            host = _host_or_404(db, host_id)
        except HTTPException:
            skipped.append({"host_id": host_id, "fqdn": None, "reason": "no_host"})
            continue
        command_id, why = equip.start(db, host, current_user.userid)
        if why:
            skipped.append({"host_id": host_id, "fqdn": host.fqdn, "reason": why})
            continue
        started += 1
        _audit(
            db,
            current_user,
            EntityType.HOST,
            host.id,
            host.fqdn,
            "Equip for backup requested (install restate)",
            {"command_id": command_id},
        )
    db.commit()
    return {"requested": len(body.host_ids), "started": started, "skipped": skipped}
