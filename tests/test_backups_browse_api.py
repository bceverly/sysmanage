# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Browsing a snapshot and what changed since one (restate 2.1.0.4+): offered
only where the host's restate said it can, the right roles, the job sent to
the host, listings kept off Recent jobs and pruned after a day."""

import json
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest

from backend.api import backups as api
from backend.api import backups_browse as browse
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_results as results
from tests.services.test_backup_results import _setup
from tests.test_backups_api import MANAGER, RESTORER, _status


@pytest.fixture
def sent():
    calls = []

    def fake(_db, host_id, command_type, parameters):
        calls.append(
            (str(host_id), getattr(command_type, "value", command_type), parameters)
        )
        return str(uuid.uuid4())

    with patch.object(jobs.config_mgmt_dispatch, "queue_command", side_effect=fake):
        yield calls


def _ready(session, abilities=("list", "status")):
    s = _setup(session)
    s.policy.host_abilities = json.dumps(list(abilities))
    session.add(models.BackupSnapshot(
        id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id, name="20261023T161149Z",
        created_at=datetime(2026, 10, 23), signed=False, seen_at=datetime(2026, 10, 23),
    ))  # fmt: skip
    session.commit()
    return s


@pytest.mark.asyncio
async def test_browsing_sends_a_list_job_for_one_directory(session, sent):
    s = _ready(session)
    run = await browse.browse_snapshot(
        str(s.host.id), browse.BrowseBody(snapshot="20261023T161149Z", path="/etc"),
        session, RESTORER,
    )  # fmt: skip
    assert run["action"] == "list" and run["host_id"] == str(s.host.id)
    params = sent[-1][2]
    assert (params["action"], params["snapshot"], params["path"]) == (
        "list",
        "20261023T161149Z",
        "/etc",
    )


@pytest.mark.asyncio
async def test_browsing_needs_the_restore_role_the_ability_and_a_real_snapshot(
    session, sent
):
    s = _ready(session, abilities=("status",))
    body = browse.BrowseBody(snapshot="20261023T161149Z", path="/")
    assert (
        await _status(browse.browse_snapshot(str(s.host.id), body, session, MANAGER))
        == 403
    )
    assert (
        await _status(browse.browse_snapshot(str(s.host.id), body, session, RESTORER))
        == 409
    )
    s.policy.host_abilities = json.dumps(["list"])
    gone = browse.BrowseBody(snapshot="20991231T000000Z", path="/")
    assert (
        await _status(browse.browse_snapshot(str(s.host.id), gone, session, RESTORER))
        == 404
    )
    relative = browse.BrowseBody(snapshot="20261023T161149Z", path="etc")
    assert (
        await _status(
            browse.browse_snapshot(str(s.host.id), relative, session, RESTORER)
        )
        == 422
    )


@pytest.mark.asyncio
async def test_what_changed_defaults_to_the_newest_and_runs_once(session, sent):
    s = _ready(session)
    run = await browse.backup_changes(str(s.host.id), None, session, MANAGER)
    assert run["action"] == "status" and "snapshot" not in sent[-1][2]
    assert (
        await _status(browse.backup_changes(str(s.host.id), None, session, MANAGER))
        == 409
    )


@pytest.mark.asyncio
async def test_listings_stay_off_recent_jobs_and_go_after_a_day(session, sent):
    s = _ready(session)
    listing = jobs.queue_browse(
        session, s.policy, s.host, jobs.LIST, "20261023T161149Z", "/", "u"
    )
    changes = jobs.queue_browse(session, s.policy, s.host, jobs.STATUS, None, None, "u")
    session.commit()
    shown = await api.list_runs(limit=50, offset=0, db=session)
    actions = [r["action"] for r in shown["runs"]]
    assert "list" not in actions and "status" in actions
    listing.status, changes.status = "ok", "different"
    listing.queued_at = changes.queued_at = datetime(2026, 10, 1)
    session.commit()
    jobs.prune_run_history(session, datetime(2026, 10, 3))
    session.commit()  # as the scheduler does
    remaining = {r.action for r in session.query(models.BackupRun).all()}
    assert "list" not in remaining and "status" in remaining


def test_the_host_reports_its_abilities_on_configure(session, sent):
    s = _setup(session)
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    results.record_command_result(session, {
        "command_id": run.command_id, "success": True,
        "result": {"installed": ["capture"], "abilities": ["list", "cache", "rm -rf"]},
    })  # fmt: skip
    assert jobs.abilities(s.policy) == ["cache", "list"]


def test_an_old_agent_refusing_a_listing_does_not_reset_the_host(session, sent):
    s = _ready(session)
    run = jobs.queue_browse(
        session, s.policy, s.host, jobs.LIST, "20261023T161149Z", "/", "u"
    )
    acked = s.policy.host_acked_version
    results.record_command_result(
        session,
        {"command_id": run.command_id, "success": False, "error": "not_configured"},
    )
    assert run.status == "failed" and s.policy.host_acked_version == acked
