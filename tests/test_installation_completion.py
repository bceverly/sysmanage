# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""An agent reporting a finished package installation (POST
/agent/installation-complete) -- untested until 2026-11-18, when making the
route a plain ``def`` showed that an unknown host token answered 500, not 403."""

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api.agent import (
    InstallationCompletionRequest,
    handle_installation_completion,
)
from backend.persistence import models
from backend.utils.async_bridge import run_to_completion

TOKEN = "tok-" + "a" * 60


def _agent_request(token=TOKEN):
    return SimpleNamespace(
        headers={"Authorization": f"Bearer {token}"},
        client=SimpleNamespace(host="10.0.0.5"),
    )


def _seed(db):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    host = models.Host(id=uuid.uuid4(), fqdn="h.example.invalid", active=True,
                       approval_status="approved", host_token=TOKEN)  # fmt: skip
    db.add(host)
    db.flush()
    req = models.InstallationRequest(
        id=uuid.uuid4(), host_id=host.id, requested_by="admin@example.com",
        requested_at=now, status="in_progress", operation_type="install",
        created_at=now, updated_at=now,
    )  # fmt: skip
    db.add(req)
    db.flush()
    for name in ("nginx", "curl"):
        db.add(models.InstallationPackage(
            id=uuid.uuid4(), installation_request_id=req.id,
            package_name=name, package_manager="apt",
        ))  # fmt: skip
    db.commit()
    return req


def test_an_unknown_host_token_is_refused_403_not_500(db_session):
    body = InstallationCompletionRequest(request_id=str(uuid.uuid4()), success=True,
                                         result_log="")  # fmt: skip
    with pytest.raises(HTTPException) as refused:
        handle_installation_completion(
            body, _agent_request("tok-unknown"), db=db_session
        )
    assert refused.value.status_code == 403


def test_a_known_host_records_the_completion(db_session):
    req = _seed(db_session)
    body = InstallationCompletionRequest(request_id=str(req.id), success=False,
                                         result_log="E: broken")  # fmt: skip
    out = handle_installation_completion(body, _agent_request(), db=db_session)
    assert out["status"] == "success"
    db_session.refresh(req)
    assert (req.status, req.result_log) == ("failed", "E: broken")
    assert req.completed_at is not None
    # The packages stay listed; the outcome is recorded on the request.
    names = {p.package_name for p in db_session.query(models.InstallationPackage)
             .filter_by(installation_request_id=req.id)}  # fmt: skip
    assert names == {"nginx", "curl"}


async def _answer():
    await asyncio.sleep(0)
    return 42


def test_run_to_completion_without_a_running_loop():
    assert run_to_completion(_answer()) == 42


@pytest.mark.asyncio
async def test_run_to_completion_inside_a_running_loop():
    # asyncio.run would refuse here; the bridge uses a loop in another thread.
    assert run_to_completion(_answer()) == 42
