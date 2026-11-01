# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The network shares a host's backup leaves out (2026-11-01).

The host's agent leaves its network and automount points out of the backup
(another server's data) and says which at configure; the server keeps that
on the policy and the Backups page shows it.  q71backupnetmounts adds the
column."""

import json
import os
import sqlite3
import tempfile

from backend.services import backup_jobs as jobs
from backend.services import backup_results as results
from backend.services import backup_views as views
from tests.services.test_backup_results import (  # noqa: F401  pylint: disable=unused-import
    _result,
    _setup,
    sent,
)
from tests.test_backup_rules_migration import _alembic


def _host_reports(session, s, network_mounts):
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    results.record_command_result(session, {
        "command_id": run.command_id, "success": True,
        "result": {"network_mounts": network_mounts},
    })  # fmt: skip


def test_the_host_reports_what_it_left_out_and_the_view_shows_it(session):
    s = _setup(session)
    assert views.policy_dict(s.policy)["network_mounts"] is None
    _host_reports(session, s, {"excluded": ["/home/me/dev/productions", "nas:/x", 7],
                               "kept": ["/home/me/rambo"], "native": False})  # fmt: skip
    shown = views.policy_dict(s.policy)["network_mounts"]
    assert shown == {"excluded": ["/home/me/dev/productions"],
                     "kept": ["/home/me/rambo"], "native": False}  # fmt: skip


def test_an_older_agent_reporting_nothing_leaves_what_was_known(session):
    s = _setup(session)
    _host_reports(
        session, s, {"excluded": ["/data/share"], "kept": [], "native": False}
    )
    _host_reports(session, s, None)
    assert json.loads(s.policy.network_mounts)["excluded"] == ["/data/share"]


def test_a_storage_reply_never_sets_the_hosts_list(session):
    s = _setup(session)
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    results.record_command_result(session, {
        "command_id": run.command_id, "success": True,
        "result": {"network_mounts": {"excluded": ["/x"]}},
    })  # fmt: skip
    assert s.policy.network_mounts is None


def test_q71_adds_its_column_idempotently_and_reversibly():
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
        assert "network_mounts" in columns(path)
        _alembic(["stamp", "q70backupreach"], path)
        _alembic(["upgrade", "head"], path)  # already there: no error
        _alembic(["downgrade", "q70backupreach"], path)
        assert "network_mounts" not in columns(path)
        _alembic(["upgrade", "head"], path)
        assert "network_mounts" in columns(path)
    finally:
        os.unlink(path)


# restate after 2.2.0.14 skips network mounts itself (skips_network_mounts):
# its configure names nothing, and each capture says what it left out.


def _capture(session, s, **result):
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    results.record_result(session, s.host.id, _result(run, snapshot="a1", **result))


def test_a_native_capture_shows_what_restate_skipped(session, sent):
    s = _setup(session)
    _host_reports(session, s, {"excluded": [], "kept": ["/home/me/rambo"],
                               "native": True})  # fmt: skip
    _capture(session, s, skipped_network_mounts=[
        {"path": "/data/nfs", "type": "nfs4"},
        {"path": "relative", "type": "cifs"}, "junk",
        {"path": "/media/auto", "type": 7},
    ])  # fmt: skip
    shown = views.policy_dict(s.policy)["network_mounts"]
    assert shown == {
        "excluded": ["/data/nfs", "/media/auto"],
        "kept": ["/home/me/rambo"],
        "native": True,
        "skipped": [{"path": "/data/nfs", "type": "nfs4"},
                    {"path": "/media/auto", "type": ""}],
    }  # fmt: skip
    # A later configure (native: names nothing) keeps the capture's list.
    _host_reports(session, s, {"excluded": [], "kept": [], "native": True})
    shown = views.policy_dict(s.policy)["network_mounts"]
    assert shown["excluded"] == ["/data/nfs", "/media/auto"] and shown["kept"] == []
    assert shown["skipped"][0] == {"path": "/data/nfs", "type": "nfs4"}


def test_an_older_restates_capture_changes_nothing(session, sent):
    s = _setup(session)
    _host_reports(session, s, {"excluded": ["/data/share"], "kept": [],
                               "native": False})  # fmt: skip
    _capture(session, s)
    assert json.loads(s.policy.network_mounts) == {
        "excluded": ["/data/share"], "kept": [], "native": False}  # fmt: skip
    # The agent's rules file again (restate downgraded): its own list wins.
    _host_reports(session, s, {"excluded": ["/x"], "kept": [], "native": False})
    assert "skipped" not in json.loads(s.policy.network_mounts)


def test_a_failed_capture_does_not_touch_the_list(session, sent):
    s = _setup(session)
    run = jobs.queue_run(session, s.policy, s.host.id, "capture")
    results.record_result(session, s.host.id, _result(
        run, "failed", skipped_network_mounts=[{"path": "/x", "type": "nfs"}]))  # fmt: skip
    assert s.policy.network_mounts is None
