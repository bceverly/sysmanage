# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Break-glass escrow (Pro+ backup_engine, ROADMAP 24.6; 2026-11-03).

``GET /backups/escrow`` -- is every encrypted host's newest key (and the
signing key) in a break-glass export?  The last export, who made it, the key
it was sealed to, how many encrypted hosts it covers, and the remembered
escrow key.  ``applies`` is False in Community or with nothing to escrow, so
the Backups page and dashboard show nothing then.

``PUT /backups/escrow/key`` -- remember the operator's escrow PUBLIC key, so
the next export defaults to it.  Manage Backups; 402 without the engine; a
private key block is refused.  Audited.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import _audit, _require
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_escrow as escrow
from backend.services import backup_jobs as jobs
from backend.services.audit_service import EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])

MAX_KEY_BYTES = 64 * 1024


class EscrowKeyBody(BaseModel):
    public_key: str = Field(min_length=1, max_length=MAX_KEY_BYTES)


@router.get("/backups/escrow")
async def escrow_status(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    return escrow.status(db)


@router.put("/backups/escrow/key")
async def save_escrow_key(
    body: EscrowKeyBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    if escrow.backup_engine() is None:
        raise HTTPException(
            status_code=402,
            detail=_("Break-glass escrow needs the Professional+ backup engine"),
        )
    target = jobs.the_target(db)
    if target is None:
        raise HTTPException(status_code=404, detail=_("No backup target is set up yet"))
    try:
        saved = escrow.save_escrow_key(target, body.public_key, current_user.userid)
    except escrow.EscrowKeyRefused as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from refused
    _audit(
        db, current_user, EntityType.SETTING, target.id, target.name,
        "Backup break-glass escrow key saved",
        {"fingerprint": saved["fingerprint"], "uid": saved["uid"]},
    )  # fmt: skip
    db.commit()
    return saved
