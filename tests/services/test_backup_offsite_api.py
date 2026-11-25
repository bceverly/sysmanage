# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The off-site cloud copy's routes (ROADMAP 27.3).

What must hold:
  * changing needs Manage Backups, restoring Restore Files, the key export
    both; reading needs only a signed-in user;
  * Community answers 402 for setting up, never for reading or restoring;
  * the agent's secret answer is not cached and is audited.
"""

# pylint: disable=redefined-outer-name,unused-argument
import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import agent_offsite as agent_api
from backend.api import backups_offsite as api
from backend.persistence import models
from backend.security.roles import SecurityRoles
from backend.services import backup_offsite as offsite
from backend.services import backup_offsite_runs as runs
from tests.services.test_backup_offsite import (  # noqa: F401  # pylint: disable=unused-import
    SECRET,
    _copy,
    _stream,
    licensed,
    vault,
)
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _setup,
    sent,
)


def _user(*roles):
    return SimpleNamespace(id=uuid.uuid4(), userid="ops@example.com",
                           has_role=lambda r: r in roles)  # fmt: skip


MANAGER = _user(SecurityRoles.MANAGE_BACKUPS)
RESTORER = _user(SecurityRoles.RESTORE_FILES)
NOBODY = _user()


def _status(call):
    with pytest.raises(HTTPException) as caught:
        call()
    return caught.value.status_code


def test_reading_is_open_and_changing_needs_the_role(session, vault, licensed):
    s = _setup(session)
    body = api.CopyBody(target_id=str(s.target.id), bucket="acme-offsite", region="us-east-2",
                        access_key="AKIAIOSFODNN7EXAMPLE", secret_key=SECRET)  # fmt: skip
    assert _status(lambda: api.create_copy(body, session, NOBODY)) == 403
    made = api.create_copy(body, session, MANAGER)
    assert made["bucket"] == "acme-offsite" and "secret_key" not in json.dumps(made)
    listed = api.list_copies(session, NOBODY)
    assert listed["licensed"] is True and listed["copies"][0]["id"] == made["id"]
    assert listed["defaults"]["full_every_days"] == 30


def test_community_gets_402_for_setup_but_reads_and_restores(session, vault, licensed, sent,
                                                              monkeypatch):  # fmt: skip
    s = _setup(session)
    copy = _copy(session, s)
    snap = "sysmanage-offsite-20261125T020000Z"
    run = runs.queue_upload(session, copy.id, "ops")
    runs.record_result(session, str(s.nas.id), {"run_id": str(run.id), "status": "ok",
                                                "streams": [_stream(copy.id, "tank/b", snap,
                                                                    when=offsite.now())]})  # fmt: skip
    monkeypatch.setattr(offsite, "engine", lambda: None)
    assert _status(lambda: api.run_copy(str(copy.id), session, MANAGER)) == 402
    assert _status(lambda: api.rotate_key(str(copy.id), session, MANAGER)) == 402
    assert _status(lambda: api.setup_help(str(copy.id), session, MANAGER)) == 402
    assert api.list_copies(session, NOBODY)["licensed"] is False
    assert api.restore_points(str(copy.id), session, NOBODY)[0]["snapshot"] == snap
    body = api.RestoreBody(
        dataset="tank/b", snapshot=snap, target_dataset="tank/restored"
    )
    assert _status(lambda: api.restore(str(copy.id), body, session, MANAGER)) == 403
    started = api.restore(str(copy.id), body, session, RESTORER)
    assert (
        started["action"] == "restore" and started["target_dataset"] == "tank/restored"
    )


def test_the_key_export_needs_both_roles(session, vault, licensed):
    copy = _copy(session, _setup(session))
    body = api.ExportBody(recipient_key="KEY", reason="the site may flood this week")
    assert _status(lambda: api.export_keys(str(copy.id), body, session, MANAGER)) == 403
    assert (
        _status(lambda: api.export_keys(str(copy.id), body, session, RESTORER)) == 403
    )


def test_the_agents_answer_is_not_cached_and_is_audited(session, vault, licensed, sent):
    s = _setup(session)
    run = runs.queue_upload(session, _copy(session, s).id, "ops")
    session.commit()
    payload = agent_api.RunRequest(host_id=str(s.nas.id), run_id=str(run.id))
    with patch.object(agent_api, "_authenticated_host_id", return_value=str(s.nas.id)), \
            patch.object(agent_api, "_host_session", return_value=session), \
            patch.object(agent_api, "_verify_host"), \
            patch.object(agent_api, "_audit") as audit:  # fmt: skip
        answer = agent_api.agent_offsite_cloud_secret(
            None, payload, "Bearer x", "h", session
        )
    assert answer.headers["cache-control"] == "no-store"
    assert json.loads(answer.body)["secret_key"] == SECRET
    audit.assert_called_once()
    assert session.get(models.BackupOffsiteRun, run.id).secrets_released_at is not None
