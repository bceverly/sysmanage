# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Back up this SysManage server (ROADMAP 25.9, Community).

``GET /backups/server`` -- which host is this server (the marked policy's,
or the hosts named as this machine is), whether it has a good backup, and the
preset a new server policy starts from, with the paths that are never backed
up (escrowed instead).

``PUT /backups/server-policy`` -- give the chosen host the server's policy:
an ordinary host policy (the same checks, the same reach refusal) marked as
the server's, which always pauses the databases and always leaves OpenBAO's
init material and token out.  Marking another host moves the mark (the
server moved to another machine).  Manage Backups; audited.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.backups import (
    PolicyBody,
    _audit,
    _host_or_404,
    _require,
    save_policy,
)
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_escrow
from backend.services import backup_jobs as jobs
from backend.services import backup_server
from backend.services import backup_views as views
from backend.services.audit_service import EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])


class ServerPolicyBody(PolicyBody):
    host_id: str


@router.get("/backups/server")
async def server_backup(
    host_id: Optional[str] = None, db: Session = Depends(get_tenant_db)
) -> Dict[str, Any]:
    """``host_id``: the preset for a host the operator picked instead."""
    rows = views.overview(db)["hosts"]
    found = backup_server.status(db, rows)
    found["candidates"] = [
        {"host_id": str(h.id), "fqdn": h.fqdn} for h in backup_server.candidates(db)
    ]
    chosen = _host_or_404(db, host_id).id if host_id else found["host_id"]
    found["preset"] = backup_server.preset(db, chosen) if chosen else None
    found["encryption"] = backup_server.encryption(db)
    return found


@router.put("/backups/server-policy")
async def put_server_policy(
    body: ServerPolicyBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    host = _host_or_404(db, body.host_id)
    body.quiesce = True  # the databases are always paused (and enforced)
    engine = backup_escrow.backup_engine()
    target = jobs.the_target(db)
    if engine is not None and target is not None and not target.escrow_fingerprint:
        # Pro+: never an unencrypted server backup, and never one keyed from
        # the OpenBAO it holds a copy of.
        raise HTTPException(status_code=409, detail=backup_server.NO_ESCROW_KEY)
    moved = []

    def mark(policy) -> None:
        previous = backup_server.mark(db, policy)
        if previous is not None:
            moved.append(str(previous.host_id))
        if engine is not None:
            backup_server.encrypt_to_escrow(db, engine, policy, host, target)

    try:
        saved = save_policy(
            db,
            current_user,
            host,
            PolicyBody(**body.model_dump(exclude={"host_id"})),
            mark,
        )
    except Exception as refused:  # pylint: disable=broad-exception-caught
        raise backup_server.refusal(refused) from refused
    if moved:
        _audit(
            db,
            current_user,
            EntityType.HOST,
            host.id,
            host.fqdn,
            "SysManage server backup moved to this host",
            {"previous_host_id": moved[0]},
        )
        db.commit()
    return saved
