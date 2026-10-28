# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Yearly retention (restate 2.2.0.12, ``keep_yearly``).

The prune that honors a yearly count runs on the storage host, so a count
is accepted only once the storage host's restate has reported it can; once
set it is always sent with the prune, like the other counts."""

import json
import os
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.api import backups as api
from backend.api import backups_retention as retention
from backend.services import backup_jobs as jobs
from backend.services import backup_results as results
from backend.services import backup_views as views
from tests.services.test_backup_results import _setup
from tests.test_backup_rules_migration import _alembic
from tests.test_backups_api import MANAGER, _status

ENGINE = SimpleNamespace(
    retention_preview=lambda names, values: {"kept": [], "removed": []}
)


def _storage_reports(session, s, abilities):
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    results.record_command_result(session, {
        "command_id": run.command_id, "success": True,
        "result": {"abilities": abilities},
    })  # fmt: skip


@pytest.mark.asyncio
async def test_years_need_a_storage_host_that_can_keep_them(session):
    s = _setup(session)
    body = api.PolicyBody(keep_last=7, keep_yearly=5)
    with patch.object(retention, "_engine", return_value=ENGINE):
        assert (
            await _status(api.put_policy(str(s.host.id), body, session, MANAGER)) == 409
        )
        _storage_reports(session, s, ["keep_yearly", "something_else"])
        assert json.loads(s.policy.storage_abilities) == ["keep_yearly"]
        saved = await api.put_policy(str(s.host.id), body, session, MANAGER)
    assert saved["keep_yearly"] == 5 and saved["yearly_supported"] is True
    assert jobs.prune_keep(s.policy) == {"keep_last": 7, "keep_yearly": 5}


@pytest.mark.asyncio
async def test_a_policy_that_has_years_keeps_them_whatever_the_storage_side(session):
    """A storage host that later reports nothing (an older agent) or loses
    the ability never makes saving other settings drop the yearly count."""
    s = _setup(session)
    s.policy.keep_yearly = 3
    session.flush()
    _storage_reports(session, s, [])
    body = api.PolicyBody(keep_last=7, interval_hours=12, keep_yearly=3)
    with patch.object(retention, "_engine", return_value=None):
        saved = await api.put_policy(str(s.host.id), body, session, MANAGER)
    assert saved["keep_yearly"] == 3 and saved["yearly_supported"] is False
    assert jobs.prune_keep(s.policy)["keep_yearly"] == 3


def test_an_older_agent_reporting_nothing_leaves_what_was_known(session):
    s = _setup(session)
    _storage_reports(session, s, ["keep_yearly"])
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    results.record_command_result(
        session, {"command_id": run.command_id, "success": True, "result": {}}
    )
    assert jobs.storage_abilities(s.policy) == ["keep_yearly"]


@pytest.mark.asyncio
async def test_years_are_bounded_and_go_to_the_preview(session):
    s = _setup(session)
    _storage_reports(session, s, ["keep_yearly"])
    with patch.object(retention, "_engine", return_value=ENGINE):
        body = api.PolicyBody(keep_last=7, keep_yearly=101)
        assert (
            await _status(api.put_policy(str(s.host.id), body, session, MANAGER)) == 422
        )
    seen = {}

    def preview(names, values):
        seen.update(values)
        return {"kept": [], "removed": []}

    with patch.object(retention, "_engine",
                      return_value=SimpleNamespace(retention_preview=preview)):  # fmt: skip
        await retention.retention_preview(
            str(s.host.id), keep_last=2, keep_yearly=4, db=session
        )
    assert seen["keep_yearly"] == 4


def test_the_policy_view_says_whether_years_can_be_set(session):
    s = _setup(session)
    assert views.policy_dict(s.policy)["yearly_supported"] is False
    _storage_reports(session, s, ["keep_yearly"])
    assert views.policy_dict(s.policy)["yearly_supported"] is True


def test_q68_adds_its_columns_idempotently_and_reversibly():
    def columns(path):
        conn = sqlite3.connect(path)
        try:
            return {row[1] for row in conn.execute("PRAGMA table_info(backup_policy)")}
        finally:
            conn.close()

    wanted = {"keep_yearly", "storage_abilities"}
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], path)
        assert wanted <= columns(path)
        _alembic(["stamp", "q67backupgfs"], path)
        _alembic(["upgrade", "head"], path)
        _alembic(["downgrade", "q67backupgfs"], path)
        assert not wanted & columns(path)
        _alembic(["upgrade", "head"], path)
        assert wanted <= columns(path)
    finally:
        os.unlink(path)
