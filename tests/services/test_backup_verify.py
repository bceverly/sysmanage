# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Scheduled verification (Pro+ 24.6): restate ``check --read-all`` on the
backed-up host every ``verify_interval_days`` -- queued only with the engine,
never beside a capture, a day after a failure, and with the keys released to
the host for that run when the repository is encrypted."""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from backend.api import backups as api
from backend.api import backups_retention as retention
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_key_release as release
from backend.services import backup_results as results
from backend.services import backup_verify as verify
from backend.services import backup_views as views
from tests.services.test_backup_encryption import _encrypt
from tests.services.test_backup_key_release import SECRET, _Engine
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _setup,
    sent,
)
from tests.test_backup_rules_migration import _alembic
from tests.test_backups_api import MANAGER, _status

NOW = datetime(2026, 11, 1, 3, 0)


@pytest.fixture
def loaded_engine(monkeypatch):
    loaded = _Engine()
    monkeypatch.setattr(verify, "_engine", lambda: loaded)
    return loaded


def _run(session, s, action, status, ended, host=None):
    run = models.BackupRun(
        policy_id=s.policy.id, host_id=(host or s.host).id, action=action,
        status=status, queued_at=ended, finished_at=None if status in jobs.PENDING
        else ended, requested_by=jobs.SYSTEM_ACTOR,
    )  # fmt: skip
    session.add(run)
    session.flush()
    return run


def _ready(session, s, days=30, abilities=("verify",)):
    s.policy.verify_interval_days = days
    s.policy.host_abilities = json.dumps(list(abilities))
    _run(session, s, "capture", "ok", NOW - timedelta(days=1))


def _verifies(session, s):
    return [r for r in session.query(models.BackupRun).all() if r.action == "verify"]


def test_nothing_is_queued_without_a_cadence_or_the_engine(session, sent, monkeypatch):
    s = _setup(session)
    _ready(session, s, days=0)
    monkeypatch.setattr(verify, "_engine", _Engine)
    assert not verify.maybe_verify(session, s.policy, s.host, NOW)
    s.policy.verify_interval_days = 30
    monkeypatch.setattr(verify, "_engine", lambda: None)
    assert not verify.maybe_verify(session, s.policy, s.host, NOW)


def test_a_due_pass_is_queued_on_the_host(session, sent, loaded_engine):
    s = _setup(session)
    _ready(session, s)
    assert verify.maybe_verify(session, s.policy, s.host, NOW)
    (run,) = _verifies(session, s)
    assert str(run.host_id) == str(s.host.id)
    assert sent[-1][2] == {"policy_id": str(s.policy.id), "action": "verify",
                           "run_id": str(run.id)}  # fmt: skip
    # pending: not again
    assert not verify.maybe_verify(session, s.policy, s.host, NOW)


def test_never_beside_a_capture_and_never_before_one(session, sent, loaded_engine):
    s = _setup(session)
    s.policy.verify_interval_days = 30
    s.policy.host_abilities = json.dumps(["verify"])
    assert not verify.maybe_verify(session, s.policy, s.host, NOW)  # no capture yet
    _run(session, s, "capture", "ok", NOW - timedelta(days=1))
    _run(session, s, "capture", "queued", NOW)
    assert not verify.maybe_verify(session, s.policy, s.host, NOW)


def test_cadence_and_retry_after_a_failure(session, sent, loaded_engine):
    s = _setup(session)
    _ready(session, s, days=30)
    _run(session, s, "verify", "ok", NOW - timedelta(days=10))
    assert not verify.maybe_verify(session, s.policy, s.host, NOW)
    assert verify.maybe_verify(session, s.policy, s.host, NOW + timedelta(days=21))
    s2 = _setup(session)
    _ready(session, s2)
    _run(session, s2, "verify", "failed", NOW - timedelta(hours=2))
    assert not verify.maybe_verify(session, s2.policy, s2.host, NOW)
    assert verify.maybe_verify(session, s2.policy, s2.host, NOW + timedelta(hours=23))


def test_a_busy_verify_is_retried_soon(session, sent, loaded_engine):
    """Refused while the storage host pruned: nothing failed (mail.archive,
    2026-10-29), so not the day-long wait of a failure."""
    s = _setup(session)
    _ready(session, s)
    _run(session, s, "verify", "busy", NOW)
    assert not verify.maybe_verify(
        session, s.policy, s.host, NOW + timedelta(minutes=10)
    )
    assert verify.maybe_verify(session, s.policy, s.host, NOW + verify.BUSY_RETRY)


def test_a_host_whose_restate_cannot_check_or_decrypt_is_skipped(
    session, sent, loaded_engine
):
    s = _setup(session)
    _ready(session, s, abilities=())
    assert not verify.maybe_verify(session, s.policy, s.host, NOW)
    _encrypt(session, s)
    s.policy.host_abilities = json.dumps(["verify"])  # no "decrypt"
    assert not verify.maybe_verify(session, s.policy, s.host, NOW)
    s.policy.host_abilities = json.dumps(["verify", "decrypt"])
    assert verify.maybe_verify(session, s.policy, s.host, NOW)
    assert sent[-1][2]["needs_key"] is True


def test_the_state_the_ui_and_alerts_read(session, sent, loaded_engine):
    s = _setup(session)
    assert verify.state(session, s.policy, NOW)["state"] == verify.OFF
    s.policy.verify_interval_days = 30
    assert verify.state(session, s.policy, NOW)["state"] == verify.UNVERIFIED
    _run(session, s, "verify", "ok", NOW - timedelta(days=5))
    got = verify.state(session, s.policy, NOW)
    assert got["state"] == verify.VERIFIED and got["last_good_at"]
    assert verify.state(session, s.policy, NOW + timedelta(days=26))["state"] == (
        verify.UNVERIFIED
    )
    _run(session, s, "verify", "failed", NOW - timedelta(days=1))
    assert verify.state(session, s.policy, NOW)["state"] == verify.FAILED
    _run(session, s, "verify", "running", NOW)
    assert verify.state(session, s.policy, NOW)["state"] == verify.RUNNING
    row = views.host_status(session, s.host, NOW)
    assert row["verification"]["state"] == verify.RUNNING
    assert row["policy"]["verify_interval_days"] == 30


def test_an_encrypted_verification_gets_its_keys_once(session, sent, monkeypatch):
    s = _setup(session)
    _encrypt(session, s)
    run = jobs.queue_verify(session, s.policy, s.host.id, needs_key=True)
    monkeypatch.setattr(release.module_loader, "get_module",
                        {"backup_engine": _Engine()}.get)  # fmt: skip
    assert release.release(session, str(s.host.id), str(run.id)) == [SECRET]


def test_the_decrypt_and_verify_abilities_survive_a_configure_reply(session, sent):
    """Production bug found 2026-10-28: the server's ability allow-list
    dropped "decrypt", so every encrypted restore, browse and what-changed
    was refused 409 -- tests had set the stored abilities directly."""
    s = _setup(session)
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    results.record_command_result(session, {
        "command_id": run.command_id, "success": True,
        "result": {"abilities": ["list", "status", "cache", "decrypt", "verify", "x"]},
    })  # fmt: skip
    assert jobs.abilities(s.policy) == ["cache", "decrypt", "list", "status", "verify"]


@pytest.mark.asyncio
async def test_setting_the_cadence_needs_the_engine(session):
    s = _setup(session)
    body = api.PolicyBody(keep_last=7, verify_interval_days=30)
    with patch.object(retention, "_engine", return_value=None):
        assert (
            await _status(api.put_policy(str(s.host.id), body, session, MANAGER)) == 402
        )
    with patch.object(retention, "_engine", return_value=object()):
        saved = await api.put_policy(str(s.host.id), body, session, MANAGER)
        assert saved["verify_interval_days"] == 30
        bad = api.PolicyBody(keep_last=7, verify_interval_days=366)
        assert (
            await _status(api.put_policy(str(s.host.id), bad, session, MANAGER)) == 422
        )
    # a lapsed licence keeps the cadence and can still save other settings
    with patch.object(retention, "_engine", return_value=None):
        same = api.PolicyBody(keep_last=7, interval_hours=12, verify_interval_days=30)
        saved = await api.put_policy(str(s.host.id), same, session, MANAGER)
        assert saved["interval_hours"] == 12 and saved["verify_interval_days"] == 30


def test_q69_adds_its_column_idempotently_and_reversibly():
    def columns(path):
        conn = sqlite3.connect(path)
        try:
            return {row[1] for row in conn.execute("PRAGMA table_info(backup_policy)")}
        finally:
            conn.close()

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], path)
        assert "verify_interval_days" in columns(path)
        _alembic(["stamp", "q68backupyearly"], path)
        _alembic(["upgrade", "head"], path)
        _alembic(["downgrade", "q68backupyearly"], path)
        assert "verify_interval_days" not in columns(path)
        _alembic(["upgrade", "head"], path)
    finally:
        os.unlink(path)
