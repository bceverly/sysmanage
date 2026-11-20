# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Four-eyes restore approval (ROADMAP 27.2, Enterprise ``backup_ops_engine``).

``GET/PUT /backups/four-eyes`` -- the tenant's setting (off by default) and
the restore requests; ``POST /backups/restore-requests/{id}/approve``,
``.../reject`` and ``.../withdraw``.  All answer 402 without the engine.
Approving sends exactly the restore that was asked for, through the same
path as an unheld restore, after checking the host can still take it.
"""

import json
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.backups import (
    RestoreBody,
    _audit,
    _host_or_404,
    _ready_policy,
    _require,
    _uuid_or_404,
)
from backend.api import backups_restore_flow as restore_flow
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.migration_compat import missing_engine_detail
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_four_eyes as four_eyes
from backend.services import backup_jobs as jobs
from backend.services import backup_reach as reach
from backend.services.audit_service import EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])


def _engine_or_402():
    eng = four_eyes.engine()
    if eng is None:
        raise HTTPException(
            status_code=402,
            detail=missing_engine_detail(
                four_eyes.ENGINE,
                _("Four-eyes approval needs the Enterprise backup operations engine"),
            ),
        )
    return eng


_REFUSALS = {
    "expired": (
        409,
        lambda: _("This restore request has expired; ask for the restore again"),
    ),
    "not_pending": (409, lambda: _("This restore request has already been decided")),
    "no_role": (403, lambda: _("Permission denied: Restore Files role required")),
    "own_request": (
        403,
        lambda: _("A restore you asked for must be approved by someone else"),
    ),
    "not_requester": (
        403,
        lambda: _("Only the person who asked for this restore can withdraw it"),
    ),
}


def _refuse(code: Optional[str]) -> None:
    if code:
        status, text = _REFUSALS[code]
        raise HTTPException(status_code=status, detail=text())


def _request_or_404(db: Session, request_id: str) -> models.BackupRestoreRequest:
    key = _uuid_or_404(request_id, _("Restore request not found"))
    request = db.get(models.BackupRestoreRequest, key)
    if request is None:
        raise HTTPException(status_code=404, detail=_("Restore request not found"))
    return request


class FourEyesBody(BaseModel):
    enabled: bool


class RejectBody(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


@router.get("/backups/four-eyes")
def get_four_eyes(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    eng = _engine_or_402()
    return {
        "enabled": four_eyes.enabled(),
        "ttl_hours": eng.REQUEST_TTL_HOURS,
        "requests": four_eyes.recent(db, eng, jobs.now()),
    }


@router.put("/backups/four-eyes")
def put_four_eyes(
    body: FourEyesBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    _engine_or_402()
    four_eyes.set_enabled(body.enabled)
    _audit(
        db,
        current_user,
        EntityType.SETTING,
        None,
        "backups",
        "Four-eyes restore approval turned on" if body.enabled
        else "Four-eyes restore approval turned off",
        {"enabled": body.enabled},
    )  # fmt: skip
    db.commit()
    return {"enabled": four_eyes.enabled()}


@router.post("/backups/restore-requests/{request_id}/approve")
def approve_restore(
    request_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    eng = _engine_or_402()
    request = _request_or_404(db, request_id)
    now = jobs.now()
    _refuse(four_eyes.approval_refusal(eng, request, current_user, now))
    host = _host_or_404(db, str(request.host_id))
    body = RestoreBody(**json.loads(request.body))
    # The host may have changed since it was asked for: check it again.
    policy = _ready_policy(db, host)
    reach.refuse_if_blocked(db, host)
    request.status, request.decided_by, request.decided_at = (
        "approved",
        current_user.userid,
        now,
    )
    out = restore_flow.perform(
        db, current_user, host, policy, body, approved_by=current_user.userid
    )
    request.run_id = uuid.UUID(out["id"])
    db.commit()
    return out


@router.post("/backups/restore-requests/{request_id}/reject")
def reject_restore(
    request_id: str,
    body: RejectBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    eng = _engine_or_402()
    request = _request_or_404(db, request_id)
    now = jobs.now()
    code = four_eyes.approval_refusal(eng, request, current_user, now)
    # The requester withdraws instead; anyone else with the role may reject.
    _refuse(code)
    request.status, request.decided_by, request.decided_at = (
        "rejected",
        current_user.userid,
        now,
    )
    request.reason = body.reason
    host = db.get(models.Host, request.host_id)
    _audit(
        db,
        current_user,
        EntityType.HOST,
        request.host_id,
        host.fqdn if host else None,
        "Restore request rejected",
        {"request_id": str(request.id), "reason": body.reason},
    )
    db.commit()
    return {"status": "rejected"}


@router.post("/backups/restore-requests/{request_id}/withdraw")
def withdraw_restore(
    request_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    eng = _engine_or_402()
    request = _request_or_404(db, request_id)
    now = jobs.now()
    _refuse(four_eyes.withdraw_refusal(eng, request, current_user, now))
    request.status, request.decided_by, request.decided_at = (
        "withdrawn",
        current_user.userid,
        now,
    )
    host = db.get(models.Host, request.host_id)
    _audit(
        db,
        current_user,
        EntityType.HOST,
        request.host_id,
        host.fqdn if host else None,
        "Restore request withdrawn",
        {"request_id": str(request.id)},
    )
    db.commit()
    return {"status": "withdrawn"}
