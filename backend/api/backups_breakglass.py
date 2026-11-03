# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Break-glass key export in every edition (ROADMAP 24.6; 2026-11-03).

A lapsed license never locks anyone out of their own backups ("please don't
hold someone's safety hostage", Bryan, 2026-11-03).  So exporting the keys of
the encrypted backups that already exist works without the Pro+ engine:

``GET /backups/break-glass`` -- is there anything to export (encrypted hosts),
and the remembered escrow key, if any.

``POST /backups/break-glass`` -- the sealed export, the same file the Pro+
panel makes (backup_breakglass is the one implementation).  Needs Manage
Backups AND Restore Files; audited per host, exactly as the engine's route
audits, so the escrow status counts it.  Making, rotating and turning on
encryption stay Pro+.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import _audit, _require
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_breakglass as breakglass
from backend.services import backup_jobs as jobs
from backend.services.audit_service import EntityType
from backend.services.backup_escrow import BREAK_GLASS_AUDIT

router = APIRouter(dependencies=[Depends(JWTBearer())])

MAX_HOSTS = 5000


class BreakGlassBody(BaseModel):
    # Omitted: the remembered escrow key (Pro+ saved it; it stays usable).
    recipient_key: Optional[str] = Field(
        default=None, max_length=breakglass.MAX_RECIPIENT_BYTES
    )
    reason: str = Field(min_length=1, max_length=breakglass.MAX_REASON_CHARS * 2)
    host_ids: Optional[List[str]] = Field(default=None, max_length=MAX_HOSTS)


@router.get("/backups/break-glass")
async def break_glass_info(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    target = jobs.the_target(db)
    pairs = breakglass.encrypted_pairs(db)
    return {
        "available": bool(pairs),
        "encrypted_hosts": len(pairs),
        "escrow_key_fingerprint": getattr(target, "escrow_fingerprint", None),
    }


@router.post("/backups/break-glass")
async def break_glass_export(
    body: BreakGlassBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Response:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    _require(current_user, SecurityRoles.RESTORE_FILES)
    target = jobs.the_target(db)
    recipient = body.recipient_key or getattr(target, "escrow_public_key", None)
    if not recipient:
        raise HTTPException(
            status_code=422,
            detail=_("Paste the OpenPGP public key to seal the export to"),
        )
    who = getattr(current_user, "userid", None) or "unknown"
    pairs = breakglass.encrypted_pairs(db, body.host_ids)
    try:
        name, sealed, summary = breakglass.break_glass_export(
            db, pairs, target, recipient, body.reason, who
        )
    except breakglass.BreakGlassRefused as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from refused
    except breakglass.BreakGlassError as failed:
        raise HTTPException(status_code=503, detail=str(failed)) from failed
    for host, _policy in pairs:
        _audit(
            db, current_user, EntityType.HOST, host.id, host.fqdn, BREAK_GLASS_AUDIT,
            {"recipient": summary["recipient"], "reason": summary["reason"],
             "hosts_in_export": len(summary["hosts"])},
        )  # fmt: skip
    db.commit()
    return Response(
        content=sealed,
        media_type="application/pgp-encrypted",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )
