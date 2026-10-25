# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""``POST /api/agent/backup-key`` -- a host fetches its run's decryption
keys (Pro+ backup_engine, 24.6 S4).

The agent authenticates exactly as it does for ``/api/agent/poll``: its
connection token, and its host token in ``X-Host-Token``.  The keys come back
in the response and nowhere else -- not the message queue, not the database,
not a log (``Cache-Control: no-store``).  ``backup_key_release`` decides
whether this run may have them, and does so once.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.agent_poll import _authenticated_host_id, _host_session, _verify_host
from backend.persistence.db import get_db
from backend.services import backup_key_release as key_release
from backend.services.audit_service import ActionType, AuditService, EntityType

router = APIRouter()


class KeyRequest(BaseModel):
    host_id: str = Field(min_length=1, max_length=64)
    run_id: str = Field(min_length=1, max_length=64)


def _audit(db: Session, host_id: str, run_id: str) -> None:
    AuditService.log(
        db=db,
        user_id=None,
        username="agent",
        action_type=ActionType.UPDATE,
        entity_type=EntityType.HOST,
        entity_id=host_id,
        entity_name=None,
        description="Backup decryption key released to the host",
        details={"run_id": run_id},
        commit=False,
    )


@router.post("/agent/backup-key")
async def agent_backup_key(
    request: Request,
    payload: KeyRequest,
    authorization: Optional[str] = Header(default=None),
    x_host_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """The decryption keys for this host's own pending run, once."""
    host_id = _authenticated_host_id(request, payload, authorization)
    host_db = _host_session(host_id, db)
    try:
        _verify_host(host_db, host_id, x_host_token)
        try:
            keys = key_release.release(host_db, host_id, payload.run_id)
        except key_release.KeyRefused as refused:
            raise HTTPException(
                status_code=refused.status, detail=str(refused)
            ) from refused
        _audit(host_db, host_id, payload.run_id)
        host_db.commit()
    finally:
        if host_db is not db:
            host_db.close()
    return JSONResponse({"keys": keys}, headers={"Cache-Control": "no-store"})
