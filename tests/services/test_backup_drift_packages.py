# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The drift timeline (Pro+ 24.7) and package-level restore (Pro+ 24.6) in
the OSS plumbing: a diff queued after each good capture and kept per pair,
the timeline served through the engine, and a package restore that is
plan-first, in place only and confirmed.  The diff result is cut from a real
restate 2.2.0.16 run on the lab's t14 (2026-11-02)."""

import json
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api import backups as api
from backend.api import backups_drift as drift_api
from backend.persistence import models
from backend.services import backup_drift as drift
from backend.services import backup_jobs as jobs
from backend.services import backup_key_release
from backend.services import backup_package_restore as package_restore
from backend.services import backup_results as results
from backend.services import backup_views as views
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _result,
    _setup,
    sent,
)
from tests.test_backups_api import MANAGER, RESTORER

REPO = "/mnt/backups/t14-419718a7-enc"
DIFF = {
    "from": f"{REPO}::20261102T171033Z",
    "to": f"{REPO}::20261102T181741Z",
    "diff": {
        "added": 5, "deleted": 0, "modified": 22, "packages_changed": 1,
        "explained": 3, "truncated": False, "packages_truncated": False,
        "changes": [
            {"change": "M", "path": "/etc/sysmanage-proof/restore-test.conf",
             "what": "content"},
            {"change": "M", "path": "/var/log/syslog", "what": "content"},
        ],
        "packages": [{"change": "U", "manager": "apt", "name": "jq",
                      "from": "1.7", "to": "1.8", "files": 3}],
    },
}  # fmt: skip


class FakeEngine:
    """Just enough of backup_engine for the OSS side."""

    seen = None

    def drift_view(self, rows, ignore, hide_expected=True, path=None):
        FakeEngine.seen = (rows, ignore, hide_expected, path)
        return {"entries": rows, "hide_expected": hide_expected, "path": path}

    def drift_validate_patterns(self, patterns):
        if any(".." in p for p in patterns):
            raise ValueError("A pattern must not contain '..'")
        return [p.strip() for p in patterns if p.strip()]

    def package_script_summary(self, script):
        return {"lines": len(script.splitlines()), "removes_unlisted": True}


@pytest.fixture
def fake_engine():
    with patch.object(drift.module_loader, "get_module", return_value=FakeEngine()):
        yield FakeEngine()


@pytest.fixture
def no_engine():
    with patch.object(drift.module_loader, "get_module", return_value=None):
        yield


def _snapshot(session, s, name):
    session.add(models.BackupSnapshot(
        id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id, name=name,
        signed=False, seen_at=datetime(2026, 11, 2),
    ))  # fmt: skip
    session.commit()


def _able(session, s, *abilities):
    s.policy.host_abilities = json.dumps(list(abilities))
    session.commit()


def _capture(session, s, name):
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    results.record_result(session, s.host.id, _result(run, "ok", snapshot=name))
    run.snapshot = name
    return run


def _diffs_sent(sent):
    return [p for _h, _c, p in sent if p.get("action") == jobs.DIFF]


# --- the drift timeline ---------------------------------------------------


def test_a_good_capture_is_compared_with_the_snapshot_before_it(
    session, sent, fake_engine
):
    s = _setup(session)
    _able(session, s, "diff")
    _snapshot(session, s, "20261102T171033Z")
    _snapshot(session, s, "20261102T181741Z")
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    run.snapshot = "20261102T181741Z"
    drift.after_capture(session, s.policy, run)
    assert _diffs_sent(sent)[-1]["from"] == "20261102T171033Z"
    assert _diffs_sent(sent)[-1]["to"] == "20261102T181741Z"


def test_no_diff_without_the_engine_the_ability_or_a_snapshot_before(
    session, sent, no_engine
):
    s = _setup(session)
    _able(session, s, "diff")
    _snapshot(session, s, "20261102T171033Z")
    _snapshot(session, s, "20261102T181741Z")
    run = SimpleNamespace(snapshot="20261102T181741Z", host_id=s.host.id)
    drift.after_capture(session, s.policy, run)  # no engine
    with patch.object(drift.module_loader, "get_module", return_value=FakeEngine()):
        _able(session, s)  # no ability
        drift.after_capture(session, s.policy, run)
        _able(session, s, "diff")
        drift.after_capture(
            session, s.policy, SimpleNamespace(snapshot="20261102T171033Z",
                                               host_id=s.host.id)  # fmt: skip
        )  # the first snapshot has nothing before it
    assert not _diffs_sent(sent)


def test_an_encrypted_repository_releases_its_keys_for_the_diff(session, sent):
    s = _setup(session)
    s.policy.encrypt_public_key = (
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\nk\n-----END PGP PUBLIC KEY BLOCK-----\n"
    )
    s.policy.encrypt_key_ref = "secret/x"
    session.commit()
    drift.queue_diff(session, s.policy, s.host.id, "a", "b")
    assert _diffs_sent(sent)[-1]["needs_key"] is True
    assert jobs.DIFF in backup_key_release.KEYED_ACTIONS


def test_a_finished_diff_is_kept_for_its_pair(session, sent, fake_engine):
    s = _setup(session)
    run = drift.queue_diff(session, s.policy, s.host.id, None, None)
    results.record_result(session, s.host.id, _result(run, "different", **DIFF))
    row = session.query(models.BackupSnapshotDiff).one()
    assert (row.from_snapshot, row.to_snapshot) == (
        "20261102T171033Z",
        "20261102T181741Z",
    )
    assert (row.status, row.added, row.modified, row.packages_changed) == (
        "ok",
        5,
        22,
        1,
    )
    assert json.loads(row.packages)[0]["name"] == "jq"
    # The same pair again replaces the row; a failure says so.
    again = drift.queue_diff(session, s.policy, s.host.id, None, None)
    results.record_result(session, s.host.id, _result(again, "failed", **DIFF))
    assert session.query(models.BackupSnapshotDiff).one().status == "failed"


def test_a_refused_diff_never_resets_the_hosts_job_files(session, sent):
    s = _setup(session)
    run = drift.queue_diff(session, s.policy, s.host.id, None, None)
    results.record_command_result(
        session,
        {"command_id": run.command_id, "success": False,
         "result": {"reason": "not_configured", "run_id": str(run.id)}},
    )  # fmt: skip
    assert s.policy.host_acked_version == 1


@pytest.mark.asyncio
async def test_the_timeline_goes_through_the_engine(session, sent, fake_engine):
    s = _setup(session)
    _snapshot(session, s, "20261102T171033Z")
    _snapshot(session, s, "20261102T181741Z")
    _snapshot(session, s, "20261102T190000Z")
    run = drift.queue_diff(session, s.policy, s.host.id, None, None)
    results.record_result(session, s.host.id, _result(run, "different", **DIFF))
    s.policy.drift_ignore = json.dumps(["/home/*/dev"])
    session.commit()
    view = await drift_api.drift_timeline(
        str(s.host.id), True, "/etc", 30, session, RESTORER
    )
    rows, ignore, hide, path = FakeEngine.seen
    assert rows[0]["to"] == "20261102T181741Z" and ignore == ["/home/*/dev"]
    assert hide is True and path == "/etc"
    assert view["missing"] == [{"from": "20261102T181741Z", "to": "20261102T190000Z"}]


@pytest.mark.asyncio
async def test_the_timeline_needs_the_engine_and_the_restore_role(
    session, sent, no_engine
):
    s = _setup(session)
    for call, code in (
        (
            drift_api.drift_timeline(str(s.host.id), True, None, 30, session, RESTORER),
            402,
        ),
        (
            drift_api.drift_timeline(str(s.host.id), True, None, 30, session, MANAGER),
            403,
        ),
    ):
        with pytest.raises(HTTPException) as refused:
            await call
        assert refused.value.status_code == code


@pytest.mark.asyncio
async def test_compute_and_ignore(session, sent, fake_engine):
    s = _setup(session)
    with pytest.raises(HTTPException) as refused:
        await drift_api.drift_compute(str(s.host.id), None, session, MANAGER)
    assert refused.value.status_code == 409  # restate cannot diff yet
    _able(session, s, "diff")
    out = await drift_api.drift_compute(
        str(s.host.id), drift_api.ComputeBody(from_snapshot="a", to_snapshot="b"),
        session, MANAGER,
    )  # fmt: skip
    assert out["action"] == jobs.DIFF and _diffs_sent(sent)[-1]["from"] == "a"
    with pytest.raises(HTTPException) as busy:
        await drift_api.drift_compute(str(s.host.id), None, session, MANAGER)
    assert busy.value.status_code == 409
    saved = await drift_api.drift_ignore(
        str(s.host.id), drift_api.IgnoreBody(patterns=[" /srv/scratch ", ""]),
        session, MANAGER,
    )  # fmt: skip
    assert saved["ignore"] == ["/srv/scratch"]
    assert drift.ignore_patterns(s.policy) == ["/srv/scratch"]
    with pytest.raises(HTTPException) as bad:
        await drift_api.drift_ignore(
            str(s.host.id), drift_api.IgnoreBody(patterns=["/a/../b"]), session, MANAGER
        )
    assert bad.value.status_code == 422


# --- package-level restore --------------------------------------------------


def _restore_body(name, **over):
    fields = {"snapshot": name, "include": ["/etc/proof"], "packages": True,
              "acknowledge_unsigned": True}  # fmt: skip
    fields.update(over)
    return api.RestoreBody(**fields)


async def _status(call):
    try:
        await call
    except HTTPException as refused:
        return refused.status_code
    return 200


@pytest.mark.asyncio
async def test_a_package_restore_needs_the_engine_and_the_ability(
    session, sent, no_engine
):
    s = _setup(session)
    _snapshot(session, s, "20261102T181741Z")
    host = str(s.host.id)
    body = _restore_body("20261102T181741Z")
    assert await _status(api.backup_restore(host, body, session, RESTORER)) == 402
    with patch.object(package_restore.module_loader, "get_module",
                      return_value=FakeEngine()):  # fmt: skip
        assert await _status(api.backup_restore(host, body, session, RESTORER)) == 409


@pytest.mark.asyncio
async def test_a_package_restore_is_planned_then_confirmed_in_place(
    session, sent, fake_engine
):
    s = _setup(session)
    _snapshot(session, s, "20261102T181741Z")
    _able(session, s, "packages")
    host = str(s.host.id)
    plan = await api.backup_restore(
        host, _restore_body("20261102T181741Z"), session, RESTORER
    )
    assert sent[-1][2]["packages"] is True and sent[-1][2]["dry_run"] is True
    assert plan["action"] == jobs.RESTORE
    real = {"dry_run": False}
    assert (
        await _status(
            api.backup_restore(
                host, _restore_body("20261102T181741Z", **real), session, RESTORER
            )
        )
        == 422
    )
    real["in_place"] = True
    real["acknowledge_in_place"] = True
    assert (
        await _status(
            api.backup_restore(
                host, _restore_body("20261102T181741Z", **real), session, RESTORER
            )
        )
        == 409
    )
    real["acknowledge_packages"] = True
    out = await api.backup_restore(
        host, _restore_body("20261102T181741Z", **real), session, RESTORER
    )
    assert sent[-1][2]["packages"] is True and sent[-1][2]["in_place"] is True
    assert out["in_place"] is True
    audit = session.query(models.AuditLog).order_by(models.AuditLog.timestamp).all()
    assert audit[-1].description == "Backup package restore requested"


def test_the_run_view_carries_the_engines_script_summary(session, fake_engine):
    s = _setup(session)
    run = models.BackupRun(
        id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id, action=jobs.RESTORE,
        status="ok", queued_at=jobs.now(),
        result=json.dumps({"packages": {"script": "#!/bin/sh\napt-get autoremove -y\n"}}),
    )  # fmt: skip
    assert views.run_dict(run)["package_summary"] == {
        "lines": 2,
        "removes_unlisted": True,
    }
    run.result = json.dumps({"restore": {}})
    assert views.run_dict(run)["package_summary"] is None


def test_a_plain_restore_passes_the_package_checks(session, no_engine):
    s = _setup(session)
    package_restore.check(_restore_body("x", packages=False), s.policy)
    assert package_restore.audit_text(_restore_body("x", packages=False)) is None
