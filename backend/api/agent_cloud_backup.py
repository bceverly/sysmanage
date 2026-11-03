# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The storage host's agent asks for what an iCloud job needs (24.12).

``POST /api/agent/cloud-backup-secret`` -- the Apple ID password, for ONE
run, once, at the moment icloudpd prompts for it.  ``POST
/api/agent/cloud-backup-code`` -- the two-factor code an operator typed, or
``{"code": null}`` while nobody has yet (the agent asks again).

The agent authenticates exactly as it does for ``/api/agent/poll``: its
connection token, and its host token in ``X-Host-Token``.  The answer comes
back in the response and nowhere else -- not the message queue, not the
database, not a log (``Cache-Control: no-store``).  Every password release is
audited (``cloud_backup_secrets`` decides whether it may happen).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.agent_poll import _authenticated_host_id, _host_session, _verify_host
from backend.persistence.db import get_db
from backend.services import cloud_backup_secrets as secrets
from backend.services.audit_service import ActionType, AuditService, EntityType

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


class RunRequest(BaseModel):
    host_id: str = Field(min_length=1, max_length=64)
    run_id: str = Field(min_length=1, max_length=64)


def _audit(db: Session, host_id: str, run_id: str, description: str) -> None:
    AuditService.log(
        db=db,
        user_id=None,
        username="agent",
        action_type=ActionType.UPDATE,
        entity_type=EntityType.HOST,
        entity_id=host_id,
        entity_name=None,
        description=description,
        details={"run_id": run_id},
        commit=False,
    )


@router.post("/agent/cloud-backup-secret")
async def agent_cloud_backup_secret(
    request: Request,
    payload: RunRequest,
    authorization: Optional[str] = Header(default=None),
    x_host_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """The Apple ID password for this host's own pending run, once."""
    host_id = _authenticated_host_id(request, payload, authorization)
    host_db = _host_session(host_id, db)
    try:
        _verify_host(host_db, host_id, x_host_token)
        try:
            password = secrets.release_password(host_db, host_id, payload.run_id)
        except secrets.SecretRefused as refused:
            raise HTTPException(
                status_code=refused.status, detail=str(refused)
            ) from refused
        _audit(host_db, host_id, payload.run_id,
               "iCloud password released to the storage host")  # fmt: skip
        host_db.commit()
    finally:
        if host_db is not db:
            host_db.close()
    return JSONResponse({"password": password}, headers=_NO_STORE)


@router.post("/agent/cloud-backup-code")
async def agent_cloud_backup_code(
    request: Request,
    payload: RunRequest,
    authorization: Optional[str] = Header(default=None),
    x_host_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """The operator's two-factor code for this host's waiting sign-in."""
    host_id = _authenticated_host_id(request, payload, authorization)
    host_db = _host_session(host_id, db)
    try:
        _verify_host(host_db, host_id, x_host_token)
        try:
            code = secrets.release_code(host_db, host_id, payload.run_id)
        except secrets.SecretRefused as refused:
            host_db.commit()  # keep "waiting since" for the next ask
            raise HTTPException(
                status_code=refused.status, detail=str(refused)
            ) from refused
        if code is not None:
            _audit(host_db, host_id, payload.run_id,
                   "iCloud two-factor code released to the storage host")  # fmt: skip
        host_db.commit()
    finally:
        if host_db is not db:
            host_db.close()
    return JSONResponse({"code": code}, headers=_NO_STORE)
