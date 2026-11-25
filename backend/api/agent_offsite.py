# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The storage host's agent asks for an off-site run's secrets (27.3).

``POST /api/agent/offsite-cloud-secret`` -- the AWS credentials and the
AES-256 key, for ONE run, once.  The agent authenticates exactly as it does
for ``/api/agent/poll`` (its connection token, and its host token in
``X-Host-Token``).  The answer comes back in the response and nowhere else --
not the message queue, not the database, not a log (``Cache-Control:
no-store``); every release is audited (``backup_offsite_secrets`` decides
whether it may happen).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.api.agent_cloud_backup import RunRequest, _audit
from backend.api.agent_poll import _authenticated_host_id, _host_session, _verify_host
from backend.persistence.db import get_db
from backend.services import backup_offsite_secrets as secrets

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


@router.post("/agent/offsite-cloud-secret")
def agent_offsite_cloud_secret(
    request: Request,
    payload: RunRequest,
    authorization: Optional[str] = Header(default=None),
    x_host_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """This host's own pending off-site run's credentials and key, once."""
    host_id = _authenticated_host_id(request, payload, authorization)
    host_db = _host_session(host_id, db)
    try:
        _verify_host(host_db, host_id, x_host_token, request)
        try:
            released = secrets.release(host_db, host_id, payload.run_id)
        except secrets.SecretRefused as refused:
            raise HTTPException(
                status_code=refused.status, detail=str(refused)
            ) from refused
        _audit(host_db, host_id, payload.run_id,
               "Off-site copy credentials and key released to the storage host")  # fmt: skip
        host_db.commit()
    finally:
        if host_db is not db:
            host_db.close()
    return JSONResponse(released, headers=_NO_STORE)
