# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Repair package manager on the hosts checked in the hosts grid
(2026-11-13; services/package_manager_repair.py)."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import _audit, _host_or_none, _require
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import package_manager_repair as repair
from backend.services.audit_service import EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])


class RepairBody(BaseModel):
    host_ids: List[str] = Field(min_length=1, max_length=1000)


@router.post("/hosts/repair-package-manager")
async def repair_package_managers(
    body: RepairBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Each checked host whose package manager needs a repair the agent can
    make is asked to make it; the rest come back with why not
    (``not_needed``, ``not_repairable``, ``agent_outdated``, ``no_host``)."""
    _require(current_user, SecurityRoles.APPLY_SOFTWARE_UPDATE)
    started, skipped = 0, []
    for host_id in dict.fromkeys(body.host_ids):
        host = _host_or_none(db, host_id)
        if host is None:
            skipped.append({"host_id": host_id, "fqdn": None, "reason": "no_host"})
            continue
        command_id, why = repair.start(db, host)
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
            "Package manager repair requested",
            {"command_id": command_id, "manager": host.package_manager_name,
             "reason": host.package_manager_repair_reason},  # fmt: skip
        )
    db.commit()
    return {"requested": len(body.host_ids), "started": started, "skipped": skipped}
